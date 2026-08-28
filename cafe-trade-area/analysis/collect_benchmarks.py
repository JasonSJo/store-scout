#!/usr/bin/env python3
"""
M4 보조 · 브랜드 매출 벤치마크 수집 (공정거래위원회 가맹사업 정보공개서)

가맹본부는 정보공개서에 **가맹점 평균매출액**을 시도별로 공시해야 한다. 공정위가
이것을 API 로 개방한다. 자사·경쟁 브랜드의 매출 수준을 **연 1회** 갱신할 수 있는
유일한 공식 출처다(정보공개서 등록 주기가 연 단위라 갱신도 연 단위다).

  python3 collect_benchmarks.py                          # dry-run (호출 없음)
  DATA_GO_KR_KEY=... python3 collect_benchmarks.py --live --연도 2025

⚠ **이것은 기존점 실매출의 대체가 아니다.**

  M4 Mode A(회귀)는 점포별 좌석수·층·전면폭·상권 지표가 있어야 설명변수가 만들어진다.
  Mode B(앵커링)는 기준점포의 **좌표**가 있어야 S 를 같은 척도에 놓을 수 있다.
  공시 데이터에는 둘 다 없다 — 브랜드×시도 단위의 평균 한 숫자뿐이다.
  따라서 회귀 표본으로도, 앵커로도 **직접 쓸 수 없다.**

  쓸 수 있는 자리는 하나다: **대조선**. 면적당 평균매출 × 후보지 전용면적으로 만든
  업계 수준과 M4 추정치를 나란히 놓아, 추정이 업계에서 얼마나 떨어져 있는지 본다.
  실적 데이터가 쌓이기 전까지 추정치를 검증할 유일한 외부 기준이다.

⚠ **엔드포인트와 응답 필드명이 실제 호출로 검증되지 않았다.** 서비스키가 없어 한 번도
   호출해 보지 못했다. 파서는 여러 표기를 함께 받고, 하나도 못 읽으면 응답 앞부분을
   그대로 출력한다 — 그 출력을 보고 ENDPOINT / FIELDS 를 고치면 된다.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import read_csv, to_f, write_text

ROOT = Path(__file__).resolve().parent

# 공정거래위원회_가맹정보_브랜드별 가맹점 현황 제공 서비스
ENDPOINT = "https://apis.data.go.kr/1130000/FftcBrandFrcsstatsService/getBrandFrcsstats"

FIELDS = {
    "연도": ["yr", "가맹사업기준년도", "baseYr", "stdrYear"],
    "브랜드": ["brandNm", "브랜드명", "brand"],
    "상호": ["corpNm", "상호", "hdqrtrsNm"],
    "업종": ["indutyMlsfcNm", "업종", "indutyNm"],
    "시도": ["areaNm", "시도", "ctprvnNm", "sidoNm"],
    "가맹점수": ["frcsCnt", "가맹점수", "frcsNo"],
    "평균매출": ["avrgSlsAmt", "평균매출금액", "arUnitAvrgSlsAmt2"],
    "면적당평균매출": ["arUnitAvrgSlsAmt", "면적당평균매출금액", "unitAreaAvrgSlsAmt"],
}
HEADER = ["연도", "브랜드", "상호", "업종", "시도", "가맹점수",
          "연평균매출_만원", "월평균매출_만원", "면적당_연매출_만원_per_m2"]


def pick(item: dict, names: list[str]) -> str:
    for n in names:
        if n in item and str(item[n]).strip() not in ("", "None"):
            return str(item[n]).strip()
    return ""


def fetch(key: str, brand: str, year: str, endpoint: str, rows: int = 100):
    q = urllib.parse.urlencode({
        "serviceKey": key, "pageNo": 1, "numOfRows": rows,
        "resultType": "json", "yr": year, "brandNm": brand,
    }, safe="%")
    try:
        with urllib.request.urlopen(f"{endpoint}?{q}", timeout=20,
                                    context=ssl.create_default_context()) as r:
            return r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except OSError as e:
        return "", f"네트워크 오류: {e}"


def parse(body: str) -> tuple[list[dict], str]:
    """포털은 오류도 200 으로 담아 보낸다. XML 로 돌아오는 경우도 있어 함께 본다."""
    body = body.strip()
    if body.startswith("<"):
        return [], f"XML 로 응답했습니다(resultType 미지원?): {body[:120]}"
    try:
        doc = json.loads(body)
    except ValueError as e:
        return [], f"JSON 파싱 실패: {e}"

    def dig(o):
        if isinstance(o, list):
            return o
        if isinstance(o, dict):
            for k in ("items", "item", "row", "data", "body", "response", "result"):
                if k in o:
                    got = dig(o[k])
                    if got:
                        return got
        return []

    head = (doc.get("response") or {}).get("header") or {}
    code = str(head.get("resultCode", "")).strip()
    if code and code not in ("00", "0", "000"):
        return [], f"API 오류 {code}: {head.get('resultMsg', '')}"
    rows = dig(doc)
    return rows, "" if rows else "항목을 하나도 읽지 못했습니다"


def normalize(rows: list[dict]) -> list[dict]:
    """공시 금액 단위는 **천원**이다. 이 저장소는 전부 만원으로 다루므로 맞춘다.

    단위를 틀리면 벤치마크가 10배로 어긋나 대조가 통째로 무의미해진다.
    """
    out = []
    for r in rows:
        연매출_천원 = to_f(pick(r, FIELDS["평균매출"]))
        면적당_천원 = to_f(pick(r, FIELDS["면적당평균매출"]))
        연매출 = 연매출_천원 / 10.0            # 천원 → 만원
        out.append({
            "연도": pick(r, FIELDS["연도"]),
            "브랜드": pick(r, FIELDS["브랜드"]),
            "상호": pick(r, FIELDS["상호"]),
            "업종": pick(r, FIELDS["업종"]),
            "시도": pick(r, FIELDS["시도"]),
            "가맹점수": pick(r, FIELDS["가맹점수"]),
            "연평균매출_만원": round(연매출, 1) if 연매출 else "",
            "월평균매출_만원": round(연매출 / 12.0, 1) if 연매출 else "",
            "면적당_연매출_만원_per_m2": round(면적당_천원 / 10.0, 3) if 면적당_천원 else "",
        })
    return out


def expected_monthly(area_py: float, rows: list[dict]) -> dict | None:
    """면적당 공시 매출 × 후보지 전용면적 → 업계 수준 월매출.

    평균이 아니라 중앙값을 쓴다 — 브랜드 몇 개가 표본을 통째로 끌어올린다.
    """
    from m5_verdict import PY_PER_M2
    vals = sorted(to_f(r["면적당_연매출_만원_per_m2"]) for r in rows
                  if to_f(r["면적당_연매출_만원_per_m2"]) > 0)
    if not vals or area_py <= 0:
        return None
    mid = (vals[len(vals) // 2] if len(vals) % 2
           else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2)
    return {"표본": len(vals), "면적당_중앙_만원_per_m2": mid,
            "기대_월매출_만원": mid * area_py * PY_PER_M2 / 12.0}


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in HEADER} for r in rows])


def load(path) -> list[dict]:
    return read_csv(Path(path)) if path and Path(path).exists() else []


def main() -> int:
    ap = argparse.ArgumentParser(description="브랜드 매출 벤치마크 수집 (공정위 정보공개서)")
    ap.add_argument("--브랜드", dest="브랜드", nargs="*", default=[],
                    help="조회할 브랜드명. 비우면 설정.yaml 의 자사 브랜드 + 경쟁점 CSV 의 브랜드")
    ap.add_argument("--연도", dest="연도", default="",
                    help="가맹사업 기준연도. 비우면 작년 (공시는 전년도 실적이 최신이다)")
    ap.add_argument("--competitors", default=str(ROOT / "경쟁점.example.csv"))
    ap.add_argument("--settings", default=str(ROOT / "설정.example.yaml"))
    ap.add_argument("--out", default=str(ROOT / "output" / "브랜드벤치마크.csv"))
    ap.add_argument("--summary", default=str(ROOT / "output" / "브랜드벤치마크.md"))
    ap.add_argument("--endpoint", default=ENDPOINT, help="포털이 주소를 바꾸면 여기서 교체")
    ap.add_argument("--live", action="store_true", help="실제 호출 (DATA_GO_KR_KEY 필요)")
    args = ap.parse_args()

    brands = list(args.브랜드)
    if not brands:
        import yaml
        st = Path(args.settings)
        cfg = (yaml.safe_load(st.read_text(encoding="utf-8")) or {}) if st.exists() else {}
        own = str(cfg.get("브랜드", "")).strip()
        rivals = {(r.get("브랜드") or "").strip()
                  for r in load(args.competitors)}
        # 자사 브랜드는 경쟁점 CSV 에도 자사 표시로 들어 있어 그대로 두면 두 번 조회된다
        seen, brands = set(), []
        for b in ([own] if own else []) + sorted(x for x in rivals if x):
            if b and b not in seen:
                seen.add(b)
                brands.append(b)

    year = args.연도.strip()
    if not year:
        import datetime as dt
        # 공시는 전년도 실적이 최신이다 — 올해를 물으면 빈 결과가 온다
        year = str(dt.date.today().year - 1)

    out = Path(args.out)
    if not args.live:
        # 매출액을 지어내지 않는다 — 벤치마크가 실측으로 오인되면 추정치 검증이 무의미해진다
        write_rows(out, [])
        print(f"[dry-run] API 를 호출하지 않았습니다 — 빈 표만 만들었습니다: {out}")
        print(f"  기준연도 {year} · 조회 대상 브랜드 {len(brands)}개: "
              + (", ".join(brands) or "없음"))
        print("  실제 수집: DATA_GO_KR_KEY=... python3 collect_benchmarks.py --live")
        print("  🙋 갱신은 연 1회면 충분합니다 — 정보공개서 등록 주기가 연 단위입니다.")
        return 0

    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY 환경변수가 없습니다.\n"
              "  공공데이터포털에서 '공정거래위원회_가맹정보' 활용신청 후 발급받으십시오.\n"
              "  (실거래가와 같은 키를 씁니다.)", file=sys.stderr)
        return 1
    if not brands:
        print("조회할 브랜드가 없습니다 — --브랜드 로 지정하거나 경쟁점 CSV 를 넣으십시오.",
              file=sys.stderr)
        return 1

    all_rows, problems = [], []
    for b in brands:
        body, err = fetch(key, b, year, args.endpoint)
        if err:
            problems.append(f"{b}: {err}")
            continue
        rows, perr = parse(body)
        if perr and not rows:
            problems.append(f"{b}: {perr}")
            if len(problems) == 1:
                print("    ↓ 응답 앞부분 (형식이 다르면 이걸 보고 FIELDS 를 고치십시오)",
                      file=sys.stderr)
                print("    " + body[:400].replace("\n", "\n    "), file=sys.stderr)
            continue
        got = normalize(rows)
        all_rows += got
        print(f"  · {b} … {len(got)}건")

    write_rows(out, all_rows)

    L = [f"# 브랜드 매출 벤치마크 — {year}년 기준", "",
         "공정거래위원회 가맹사업 정보공개서 공시 자료. **연 1회 갱신**하면 충분합니다 "
         "(정보공개서 등록 주기가 연 단위입니다).", "",
         "> ⚠ **기존점 실매출의 대체가 아닙니다.** 브랜드×시도 단위 평균 한 숫자뿐이라 "
         "M4 회귀의 설명변수도, Mode B 앵커의 좌표도 만들 수 없습니다. "
         "추정치를 업계 수준과 나란히 놓는 **대조선**으로만 쓰십시오.", "",
         "| 브랜드 | 시도 | 가맹점수 | 월평균매출(만원) | 면적당 연매출(만원/㎡) |",
         "|---|---|---:|---:|---:|"]
    for r in sorted(all_rows, key=lambda x: (x["브랜드"], x["시도"])):
        L.append(f"| {r['브랜드']} | {r['시도']} | {r['가맹점수']} | "
                 f"{r['월평균매출_만원']} | {r['면적당_연매출_만원_per_m2']} |")
    if problems:
        L += ["", "## 수집 실패", ""] + [f"- {x}" for x in problems]
    write_text(Path(args.summary), "\n".join(L) + "\n")

    print(f"  → {out} ({len(all_rows)}행) · {args.summary}")
    for x in problems:
        print(f"  ⚠ {x}", file=sys.stderr)
    print("  🙋 공시 금액 단위는 천원입니다 — 만원으로 환산해 저장했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
