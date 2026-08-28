#!/usr/bin/env python3
"""
상담 조건 → 심의 입력

상담 페이지(consult/)가 내보낸 `상담조건.json` 을 읽어 두 가지를 만든다.

    1. 설정 override — 운영 형태와 투자금 형태가 **고정비 F 를 바꾼다**.
       F 가 바뀌면 BEP 가 바뀌고 margin 이 바뀌고 판정이 바뀐다.
       상담에서 받은 값 중 알고리즘에 실제로 닿는 것은 이 둘뿐이다.

    2. 후보지 필터 — 희망 평수·투자금·지역·상권 유형으로 후보지를 거른다.
       이것은 알고리즘이 아니라 **필터**다. 걸러진 물건은 심의에 올라오지 않는다.
       점수를 깎는 게 아니라 목록에서 빼는 것이므로, 무엇이 왜 빠졌는지 남긴다.

  python3 consult.py --상담 상담조건.json --sites 후보지.csv

⚠ **개인정보는 읽지 않는다.** 상담조건.json 의 고객명·전화번호는 이 도구가 손대지
   않고 산출물에도 싣지 않는다. 심의표는 사내 회람 문서라 고객 연락처가 들어갈 자리가
   아니다 — 상담 기록과 심의 자료는 분리해서 보관해야 한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

from common import read_csv, to_f, write_json, write_text

ROOT = Path(__file__).resolve().parent

# 상담조건.json 에서 이 도구가 읽는 키. 개인정보 키는 의도적으로 빠져 있다.
읽는키 = ("희망평수", "희망상권", "희망지역", "보증금_만원", "권리금_만원",
        "투자금형태", "운영형태")
개인정보키 = ("고객명", "고객전화번호", "거주지", "근무지")

상권유형 = ("오피스", "주거", "학교", "병원", "메인", "복합")


def load_consult(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8-sig"))
    return doc.get("조건", doc)


def 금융비용(cond: dict, settings: dict) -> dict:
    """투자금 형태 → 월 금융비용.

        월이자 = (보증금 + 권리금) × 대출비율 × 연금리 ÷ 12
        월비용 = 월이자 + 리스료

    대출 원금을 (보증금+권리금)으로 잡는 것은 **과소 추정**이다 — 인테리어·집기 같은
    시설자금과 운전자금이 빠져 있다. 상담 단계에서 아는 것이 그것뿐이라 그렇게 둔다.
    """
    표 = (settings.get("투자금형태") or {})
    형태 = str(cond.get("투자금형태", "")).strip()
    사양 = 표.get(형태)
    if not 사양:
        return {"형태": 형태, "월_금융비용_만원": 0.0, "적용": False,
                "사유": f"설정.yaml 의 투자금형태에 '{형태}' 가 없습니다" if 형태
                      else "투자금 형태가 비어 있습니다"}
    원금 = to_f(cond.get("보증금_만원")) + to_f(cond.get("권리금_만원"))
    이자 = 원금 * to_f(사양.get("대출비율")) * to_f(사양.get("연금리")) / 12.0
    리스 = to_f(사양.get("리스_월_만원"))
    return {"형태": 형태, "차입_추정_만원": 원금 * to_f(사양.get("대출비율")),
            "월이자_만원": 이자, "리스_월_만원": 리스,
            "월_금융비용_만원": 이자 + 리스, "적용": True,
            "설명": 사양.get("설명", "")}


def 인건비(cond: dict, settings: dict) -> dict:
    표 = (settings.get("운영형태") or {})
    형태 = str(cond.get("운영형태", "")).strip()
    사양 = 표.get(형태)
    if not 사양:
        return {"형태": 형태, "적용": False,
                "사유": f"설정.yaml 의 운영형태에 '{형태}' 가 없습니다" if 형태
                      else "운영 형태가 비어 있습니다"}
    return {"형태": 형태, "고정인건비_월_만원": to_f(사양.get("고정인건비_월_만원")),
            "적용": True, "설명": 사양.get("설명", "")}


def apply_settings(cond: dict, settings: dict) -> tuple[dict, list[str]]:
    """상담 조건을 설정에 얹는다. 설정 파일 자체는 건드리지 않는다."""
    out = dict(settings)
    운영 = dict(out.get("운영", {}) or {})
    고정 = dict(운영.get("고정비", {}) or {})
    바뀐 = []

    노무 = 인건비(cond, settings)
    if 노무["적용"]:
        before = to_f(고정.get("고정인건비_월_만원"))
        고정["고정인건비_월_만원"] = 노무["고정인건비_월_만원"]
        if before != 노무["고정인건비_월_만원"]:
            바뀐.append(f"고정인건비 {before:,.0f} → {노무['고정인건비_월_만원']:,.0f}만원 "
                      f"(운영 형태: {노무['형태']})")

    금융 = 금융비용(cond, settings)
    if 금융["적용"] and 금융["월_금융비용_만원"] > 0:
        before = to_f(고정.get("기타_월_만원"))
        고정["기타_월_만원"] = before + 금융["월_금융비용_만원"]
        바뀐.append(f"기타 고정비 {before:,.0f} → {고정['기타_월_만원']:,.0f}만원 "
                  f"(금융비용 {금융['월_금융비용_만원']:,.0f} 가산 · {금융['형태']})")

    운영["고정비"] = 고정
    out["운영"] = 운영
    return out, 바뀐


def 필터(cond: dict, sites: list[dict], settings: dict) -> tuple[list[dict], list[dict]]:
    """희망 조건으로 후보지를 거른다. 뺀 이유를 행마다 남긴다."""
    f = settings.get("상담필터") or {}
    평수오차 = to_f(f.get("평수_허용오차"), 0.3)
    초과허용 = to_f(f.get("투자금_초과허용"), 0.1)

    희망평 = to_f(cond.get("희망평수"))
    한도 = (to_f(cond.get("보증금_만원")) + to_f(cond.get("권리금_만원"))) * (1 + 초과허용)
    지역 = [x.strip() for x in (cond.get("희망지역") or []) if str(x).strip()]
    상권 = [x.strip() for x in (cond.get("희망상권") or []) if str(x).strip()]

    통과, 제외 = [], []
    for s in sites:
        이유 = []
        평 = to_f(s.get("전용면적_평"))
        if 희망평 > 0 and 평 > 0:
            lo, hi = 희망평 * (1 - 평수오차), 희망평 * (1 + 평수오차)
            if not (lo <= 평 <= hi):
                이유.append(f"평수 {평:g}평이 희망 {희망평:g}평 ±{평수오차:.0%} 밖")
        투자 = to_f(s.get("보증금_만원")) + to_f(s.get("권리금_만원"))
        if 한도 > 0 and 투자 > 한도:
            이유.append(f"보증금+권리금 {투자:,.0f}만원이 한도 {한도:,.0f}만원 초과")
        if 지역:
            주소 = str(s.get("주소") or "") + " " + str(s.get("후보지명") or "")
            if not any(g in 주소 for g in 지역):
                이유.append(f"희망 지역({'·'.join(지역)})에 해당하지 않음")
        if 상권:
            유형 = str(s.get("상권유형") or "").strip()
            if 유형 and 유형 not in 상권:
                이유.append(f"상권 유형 {유형} 이 희망({'·'.join(상권)})과 불일치")
        (제외 if 이유 else 통과).append({**s, "_제외사유": "; ".join(이유)} if 이유 else s)
    return 통과, 제외


def render(cond: dict, settings: dict, 바뀐: list[str],
           통과: list[dict], 제외: list[dict]) -> str:
    노무, 금융 = 인건비(cond, settings), 금융비용(cond, settings)
    L = ["# 상담 조건 반영 결과", "",
         "> 고객 개인정보(성명·연락처·거주지·근무지)는 이 문서에 싣지 않습니다. "
         "심의 자료는 사내 회람 문서라 고객 연락처가 들어갈 자리가 아닙니다.", "",
         "## 알고리즘에 들어간 것", "",
         "상담에서 받은 값 중 판정에 실제로 닿는 것은 **운영 형태와 투자금 형태** 둘뿐입니다. "
         "둘 다 고정비 F 를 바꾸고, F 가 바뀌면 BEP → margin → 판정이 바뀝니다.", "",
         "| 항목 | 값 | 반영 |", "|---|---|---|"]
    L.append(f"| 운영 형태 | {노무['형태'] or '—'} | "
             + (f"고정인건비 {노무['고정인건비_월_만원']:,.0f}만원 — {노무['설명']}"
                if 노무["적용"] else f"⚠ 반영 안 됨: {노무.get('사유', '')}") + " |")
    L.append(f"| 투자금 형태 | {금융['형태'] or '—'} | "
             + (f"월 금융비용 {금융['월_금융비용_만원']:,.0f}만원 "
                f"(이자 {금융['월이자_만원']:,.0f} + 리스 {금융['리스_월_만원']:,.0f})"
                if 금융["적용"] else f"⚠ 반영 안 됨: {금융.get('사유', '')}") + " |")
    if 바뀐:
        L += ["", "### 설정이 이렇게 바뀌었습니다", ""] + [f"- {x}" for x in 바뀐]
    if 금융.get("적용") and 금융.get("차입_추정_만원", 0) > 0:
        L += ["", f"> ⚠ 차입 원금을 (보증금+권리금) × 대출비율 = "
                  f"{금융['차입_추정_만원']:,.0f}만원 으로 잡았습니다. 인테리어·집기 같은 "
                  "시설자금과 운전자금이 빠진 **과소 추정**입니다 — 실제 월 상환액이 "
                  "나오면 설정.yaml 을 고치십시오."]

    L += ["", "## 알고리즘에 들어가지 않는 것", "",
          "| 항목 | 값 | 쓰이는 곳 |", "|---|---|---|",
          f"| 희망 평수 | {cond.get('희망평수', '—')}평 | 후보지 필터 · 후보지의 전용면적으로 옮기면 M5 시세 대조 |",
          f"| 보증금 | {to_f(cond.get('보증금_만원')):,.0f}만원 | 투자 한도 필터 (알고리즘 미사용) |",
          f"| 권리금 | {to_f(cond.get('권리금_만원')):,.0f}만원 | 투자 한도 필터 (알고리즘 미사용) |",
          f"| 희망 지역 | {'·'.join(cond.get('희망지역') or []) or '—'} | 후보지 필터 |",
          f"| 희망 상권 | {'·'.join(cond.get('희망상권') or []) or '—'} | 후보지 필터 |", ""]

    L += ["## 후보지 선별", "",
          f"통과 {len(통과)}곳 · 제외 {len(제외)}곳", ""]
    if 제외:
        L += ["필터는 점수를 깎는 게 아니라 목록에서 빼는 것이라, 무엇이 왜 빠졌는지 "
              "남깁니다. 조건이 지나치게 좁으면 여기서 알아채야 합니다.", "",
              "| 후보지 | 제외 사유 |", "|---|---|"]
        for s in 제외:
            L.append(f"| {s.get('후보지명', '')} | {s['_제외사유']} |")
    if not 통과:
        L += ["", "> ⛔ **남은 후보지가 없습니다.** 희망 조건이 시장에 없는 조건이거나 "
                  "후보지 풀이 부족합니다. 조건을 넓히거나 후보지를 더 모아야 합니다 — "
                  "조건에 맞춘다고 판정 기준을 낮추면 안 됩니다."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="상담 조건을 심의 입력으로 옮긴다")
    ap.add_argument("--상담", dest="상담", required=True, help="상담 페이지가 내보낸 JSON")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--settings", default=str(ROOT / "설정.example.yaml"))
    ap.add_argument("--outdir", default=str(ROOT / "output" / "consult"))
    args = ap.parse_args()

    cond = load_consult(args.상담)
    if not cond:
        print(f"상담 조건을 읽지 못했습니다: {args.상담}", file=sys.stderr)
        return 1
    남은 = [k for k in 개인정보키 if k in cond]
    settings = yaml.safe_load(Path(args.settings).read_text(encoding="utf-8")) or {}
    sites = read_csv(Path(args.sites)) if Path(args.sites).exists() else []

    merged, 바뀐 = apply_settings(cond, settings)
    통과, 제외 = 필터(cond, sites, settings)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "설정.yaml").write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if sites:
        cols = list(sites[0].keys())
        with (out / "sites.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows([{k: s.get(k, "") for k in cols} for s in 통과])
    write_text(out / "상담반영.md", render(cond, settings, 바뀐, 통과, 제외))
    # 개인정보는 산출물에 싣지 않는다 — 읽는 키만 골라 다시 쓴다
    write_json(out / "조건.json", {k: cond.get(k) for k in 읽는키 if k in cond})

    print(f"상담 조건 반영 — 후보지 통과 {len(통과)} · 제외 {len(제외)}")
    for x in 바뀐:
        print(f"  · {x}")
    if 남은:
        print(f"  🙋 상담 JSON 에 개인정보 {len(남은)}건({', '.join(남은)})이 있습니다 — "
              f"산출물에는 싣지 않았습니다.")
    print(f"  → {out}/sites.csv · 설정.yaml · 상담반영.md")
    print(f"  다음: python3 review_sites.py --sites {out}/sites.csv "
          f"--settings {out}/설정.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
