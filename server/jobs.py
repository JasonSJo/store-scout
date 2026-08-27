#!/usr/bin/env python3
"""
파이프라인 실행

조직이 올린 후보지 CSV 를 **격리된 임시 디렉터리**에서 돌린다. 조직끼리 산출물이
섞이지 않게, 그리고 실행이 끝나면 디스크에 원본이 남지 않게 하기 위해서다.
결과는 DB 에 저장하고 임시 디렉터리는 지운다.

파이프라인 자체(M1~M6)는 이 저장소에 없다. STORE_SCOUT_PIPELINE 이 가리키는
analysis 디렉터리를 서브프로세스로 부른다 — 알고리즘의 원본을 한 곳에 두기 위해서다.
import 로 끌어 쓰면 파이프라인의 전역 계수 레지스트리(config.COEFFICIENTS)가
요청 사이에 공유되어, 한 조직이 넣은 계수가 다른 조직의 판정에 새어 든다.
서브프로세스는 그 사고를 구조적으로 막는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

def _find_pipeline() -> Path:
    """analysis 디렉터리를 찾는다.

    이 저장소는 알고리즘을 담지 않는다 — 원본은 jasons-company 한 곳에 둔다.
    그래서 경로를 밖에서 받아야 하고, 흔한 배치 몇 가지는 알아서 찾아 준다.
    못 찾으면 조용히 넘어가지 않고 available() 이 이유를 말한다.
    """
    env = os.environ.get("STORE_SCOUT_PIPELINE", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    후보 = [
        here.parents[2] / "jasons-company" / "cafe-trade-area" / "analysis",  # 나란히 클론
        here.parents[3] / "jasons-company" / "cafe-trade-area" / "analysis",
        here.parents[2] / "cafe-trade-area" / "analysis",   # 이관 전 한 저장소 안
    ]
    for c in 후보:
        if (c / "review_sites.py").exists():
            return c
    return 후보[0]


PIPELINE = _find_pipeline()

TIMEOUT = int(os.environ.get("STORE_SCOUT_TIMEOUT", "600"))


def available() -> tuple[bool, str]:
    안내 = ("상권분석 저장소를 나란히 클론하거나 STORE_SCOUT_PIPELINE 로 경로를 "
          "지정하십시오:\n"
          "  git clone https://github.com/JasonSJo/jasons-company\n"
          "  export STORE_SCOUT_PIPELINE=$PWD/jasons-company/cafe-trade-area/analysis")
    if not PIPELINE.exists():
        return False, f"파이프라인 디렉터리가 없습니다: {PIPELINE}\n{안내}"
    if not (PIPELINE / "review_sites.py").exists():
        return False, f"review_sites.py 를 찾지 못했습니다: {PIPELINE}\n{안내}"
    return True, ""


def count_sites(csv_text: str) -> int:
    """청구 단위 = 이름이 있는 후보지 수. 빈 줄과 머리글은 세지 않는다."""
    import csv as _csv
    import io
    rows = list(_csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))))
    return sum(1 for r in rows if (r.get("후보지명") or "").strip())


def run(sites_csv: str, settings_yaml: str = "", coefficients_json: str = "") -> dict:
    """후보지 CSV 한 벌을 심의한다. 성공/실패 모두 dict 로 돌려준다."""
    ok, why = available()
    if not ok:
        return {"ok": False, "error": why}

    work = Path(tempfile.mkdtemp(prefix="scout-"))
    try:
        (work / "sites.csv").write_text(sites_csv, encoding="utf-8-sig")
        cmd = [sys.executable, str(PIPELINE / "review_sites.py"),
               "--sites", str(work / "sites.csv"),
               "--out", str(work / "심의표.md"),
               "--json", str(work / "심의결과.json")]
        if settings_yaml:
            (work / "설정.yaml").write_text(settings_yaml, encoding="utf-8")
            cmd += ["--settings", str(work / "설정.yaml")]
        if coefficients_json:
            (work / "계수.json").write_text(coefficients_json, encoding="utf-8")
            cmd += ["--계수", str(work / "계수.json")]

        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=str(PIPELINE))
        if p.returncode != 0:
            return {"ok": False, "error": (p.stderr or p.stdout or "").strip()[-2000:]}

        result_path, report_path = work / "심의결과.json", work / "심의표.md"
        if not result_path.exists():
            return {"ok": False, "error": "심의결과.json 이 생성되지 않았습니다.\n"
                                          + (p.stdout or "")[-1000:]}
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        return {
            "ok": True,
            "result": result,
            "report": report_path.read_text(encoding="utf-8") if report_path.exists() else "",
            "mode": result.get("모드", ""),
            "stdout": (p.stdout or "").strip()[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"제한 시간 {TIMEOUT}초를 넘겨 중단했습니다."}
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        # 조직 데이터를 디스크에 남기지 않는다
        shutil.rmtree(work, ignore_errors=True)


def summarize(result: dict) -> dict:
    """대시보드에 쓸 요약. 매출은 **구간으로만** 싣는다 —
    단일 숫자를 보여 주면 그 숫자가 상담 자리에서 그대로 인용된다."""
    out = {"통과": 0, "보류": 0, "부결": 0, "후보지": []}
    sites = result.get("후보지") if isinstance(result, dict) else None
    for r in (sites if isinstance(sites, list) else []):
        if not isinstance(r, dict):
            continue
        j = r.get("판정") if isinstance(r.get("판정"), dict) else {}
        v = j.get("판정", "")
        if v in out:
            out[v] += 1
        m = r.get("매출") if isinstance(r.get("매출"), dict) else {}
        out["후보지"].append({
            "이름": r.get("이름", ""), "판정": v, "S": r.get("S"),
            "월매출_하한": m.get("월매출_하한"), "월매출_상한": m.get("월매출_상한"),
            "margin": j.get("margin"), "BEP_만원": j.get("BEP_만원"),
            "사유": j.get("사유", []), "경고수": len(r.get("경고", [])),
        })
    return out
