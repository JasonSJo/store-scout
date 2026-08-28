#!/usr/bin/env python3
"""
심의표 — M1~M5 를 돌려 후보지별 3단 판정(통과/보류/부결)을 낸다.

    python3 review_sites.py
    python3 review_sites.py --sites 내후보지.csv --stores 기존점.csv

출력
    output/심의표.md      사람이 읽는 심의 자료 (사내 한정)
    output/심의결과.json   다른 도구(콘솔·리포트)가 먹는 원본
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pipeline
from collect_transactions import lawd, summarize
from m5_verdict import PY_PER_M2 as M5PY
from common import nf, read_csv, write_json, write_text
from config import FATAL_FLAGS, MODE_B_WEIGHTS, c, overridden, unvalidated

ROOT = Path(__file__).resolve().parent
MARK = {"통과": "○", "보류": "△", "부결": "✕"}


def header(settings: dict) -> list[str]:
    g = settings.get("거버넌스", {}) or {}
    return [
        f"# 점포개발 심의표 — {settings.get('브랜드', '')}", "",
        f"**{g.get('문서등급', '사내 한정 · 대외 배포 금지')}**", "",
        f"> {(g.get('고지') or '').strip()}", "",
    ]


def market(sites: list[dict], path: Path) -> list[str]:
    """지역 실거래가 요약. collect_transactions.py 가 만든 표가 있을 때만 싣는다.

    **판정에도 매출 추정에도 들어가지 않는다 — 참고 자료다.** 매매가는 임대 조건이
    아니고, 상업용은 층·용도·전면에 따라 편차가 크며, 매매가를 임대료로 바꾸는 데
    쓰는 연임대수익률이 미검증 계수다. 검증되지 않은 환산으로 보류를 만들면 실거래
    데이터가 있는 지역의 후보지만 근거 없이 불리해진다.

    그래서 숫자는 싣되 판단은 사람이 한다. 제시 임대료가 지역 수준을 크게 벗어나면
    실사에서 확인할 일이지, 알고리즘이 자동으로 깎을 일이 아니다.
    """
    if not path.exists():
        return []
    rows = [r for r in read_csv(path) if (r.get("지역코드") or "").strip()]
    if not rows:
        return []

    regions = {}
    for r in sites:
        code = lawd(r["후보지"].get("법정동코드"))
        if code:
            regions.setdefault(code, []).append(r["이름"])
    if not regions:
        return []

    def f(v):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0

    L = ["---", "", "## 지역 실거래가 (참고 — 판정 미반영)", "",
         "국토교통부 상업업무용 부동산 매매 신고 자료. **판정에도 매출 추정에도 "
         "들어가지 않습니다.** 매매가는 임대 조건이 아니고, 상업용은 층·용도·전면에 "
         "따라 편차가 크며, 매매가를 임대료로 바꾸는 연임대수익률이 미검증 계수입니다. "
         "검증되지 않은 환산으로 보류를 만들면 실거래 데이터가 있는 지역의 후보지만 "
         "근거 없이 불리해집니다.", "",
         "참고 삼아 환산해 보려면 아래 중앙 단가를 "
         f"`건물가치 = 중앙 만원/㎡ × 전용면적 × {M5PY:.6g}` · "
         f"`기대 월임대료 = 건물가치 × {c('상업용_연임대수익률'):.3f} ÷ 12` 로 쓰면 됩니다"
         f"(거래 {int(c('시세대조_최소건수'))}건 미만인 지역은 대조하지 않습니다). "
         "제시 임대료가 지역 수준을 크게 벗어나면 **실사에서 확인할 일**이지 "
         "알고리즘이 자동으로 깎을 일이 아닙니다.", "",
         "| 지역코드 | 후보지 | 건수 | 중앙 만원/㎡ | 중앙 거래금액(만원) | 최근 거래 |",
         "|---|---|---:|---:|---:|---|"]
    for code, names in regions.items():
        hit = [{"만원_per_m2": f(r.get("만원_per_m2")),
                "거래금액_만원": f(r.get("거래금액_만원")),
                "거래일": r.get("거래일", "")}
               for r in rows if (r.get("지역코드") or "").strip() == code]
        hit = [h for h in hit if h["거래금액_만원"]]
        if not hit:
            L.append(f"| {code} | {'·'.join(names)} | 0 | — | — | — |")
            continue
        s2 = summarize(hit)
        u = f"{s2['만원_per_m2_중앙']:,.1f}" if s2["만원_per_m2_중앙"] else "—"
        a = f"{s2['거래금액_만원_중앙']:,.0f}" if s2["거래금액_만원_중앙"] else "—"
        L.append(f"| {code} | {'·'.join(names)} | {s2['건수']} | {u} | {a} | "
                 f"{s2['최근_거래일'] or '—'} |")
    return L + [""]


def render(res: dict, market_csv: Path = None) -> str:
    settings = res["설정"]
    cands = sorted(res["후보지"], key=lambda r: (
        {"통과": 0, "보류": 1, "부결": 2}[r["판정"]["판정"]], -(r["판정"]["margin"] or -9)))
    L = header(settings)

    간편 = [r["이름"] for r in res["후보지"]
          if "간편 입력" in str(r["후보지"].get("비고", ""))]
    if 간편:
        L += ["> ⚠ **가정값이 섞인 입력입니다.** 다음 후보지는 간편 입력(주소 + 마진율)으로 "
              f"만들어졌습니다 — {', '.join(간편)}. 전용면적·좌석수·층·코너·전면폭·주차·정차·"
              "방향적합·계약조건점수는 실사 결과가 아니라 자리표시자이고, 임대료는 지역 "
              "실거래가에서 역산한 값일 수 있습니다. 아래 판정은 **후보지를 추리는 용도**이며 "
              "출점 결정의 근거가 되지 않습니다. 칸별 출처는 `output/quick/출처표.md` 에 "
              "있습니다.", ""]

    m = res["모델"]
    if res["모드"] == "A" and m and "beta" in m:
        L += [f"매출 추정: **Mode A(회귀)** · 유효표본 {m['표본수']} · "
              f"R² {m['R2']:.3f} · {m['CV']['방식']} MAPE "
              f"{('%.1f%%' % (m['CV']['MAPE'] * 100)) if m['CV']['MAPE'] else '—'}", ""]
    else:
        L += ["매출 추정: **Mode B(앵커링)** — 유효표본이 15개 미만입니다. "
              "임의 배점으로 실매출을 비례 조정한 값이므로 심의 참고자료로만 쓰십시오.", ""]

    L += ["| 판정 | 후보지 | S | 월매출(중앙) | 예측구간 | BEP | margin | margin_low | 중첩 | 사유 |",
          "|:--:|---|---:|---:|---|---:|---:|---:|---:|---|"]
    for r in cands:
        j, p = r["판정"], r["매출"]
        L.append(
            f"| {MARK[j['판정']]} {j['판정']} | {r['이름']} | {nf(r.get('S', 0), 1)} | "
            f"{nf(p.get('월매출_중앙', 0))} | "
            f"{nf(p.get('월매출_하한', 0))}~{nf(p.get('월매출_상한', 0))} | "
            f"{nf(j['BEP_만원'] or 0)} | "
            f"{nf((j['margin'] or 0) * 100, 1)}% | {nf((j['margin_low'] or 0) * 100, 1)}% | "
            f"{nf(j['카니발']['최대_overlap'] * 100)}% | {'; '.join(j['사유']) or '—'} |")
    L += ["", f"> 금액 단위 만원. 판정 기준 — 부결: 치명플래그 ≥1 또는 "
              f"margin < {nf(c('부결_마진') * 100)}% · "
              f"보류: margin < {nf(c('보류_마진') * 100)}% 또는 S < {nf(c('보류_점수'))} 또는 "
              f"중첩 > {nf(c('보류_중첩') * 100)}% 또는 margin_low < 0", ""]

    for r in cands:
        j, p, a, d, s = r["판정"], r["매출"], r["상권"], r["수요"], r["경쟁"]
        L += ["---", "", f"## {MARK[j['판정']]} {r['이름']} — {j['판정']}", ""]
        if j["사유"]:
            L += ["**사유**"] + [f"- {x}" for x in j["사유"]] + [""]
        L += [
            "| 구분 | 값 |", "|---|---|",
            f"| 위치 | {r['후보지'].get('주소', '')}"
            + (f" · 우편번호 {r['후보지']['우편번호']}" if r['후보지'].get('우편번호') else "")
            + (f" · 법정동 {r['후보지']['법정동코드']}" if r['후보지'].get('법정동코드') else "")
            + " |",
            f"| M1 상권 | P10 {nf(a['P10_면적_m2'] / 10000, 1)}ha · 잔존율 R={nf(a['R'], 2)} · 출처 {a['출처']} |",
            f"| M2 수요 | H {nf(d['H'])}세대 · W {nf(d['W'])}명 · "
            f"D_am {nf(d['D_am'])} → 보정 {nf(d['D_am_adj'])} · D_all {nf(d['D_all'])} |",
            f"| M3 경쟁 | Huff S={nf(s['S'] * 100, 2)}% · 반경 내 {s['반경내_경쟁']}곳 "
            f"(동일가격대 {s['동일가격대_수']} · 저가형 {s['저가형_수']}) · λ={s['λ']} |",
            f"| M4 매출 | {p.get('모드', '—')} · 중앙 {nf(p.get('월매출_중앙', 0))}만원 "
            f"(하한 {nf(p.get('월매출_하한', 0))} · 상한 {nf(p.get('월매출_상한', 0))}) |",
            f"| M5 손익 | F {nf(j['고정비']['F'])}만원 · v {nf(j['변동비율'] * 100, 1)}% · "
            f"BEP {nf(j['BEP_만원'] or 0)}만원 |",
            f"| M5 카니발 | 최대 중첩 {nf(j['카니발']['최대_overlap'] * 100)}% · "
            f"잠식 {nf(j['카니발']['잠식액_합_만원'])}만원/월 (κ={j['카니발']['κ']}) |",
            f"| S 배점 | " + " · ".join(
                f"{ax} {nf(v, 1)}/{sum(MODE_B_WEIGHTS[ax].values())}"
                for ax, v in (r.get("S_축") or {}).items()) + " |",
            "",
        ]
        if j["치명_미확인"]:
            L += ["**치명 항목 미확인**"] + [f"- {x}" for x in j["치명_미확인"]] + [""]
        if j["비고"]:
            L += [f"- {x}" for x in j["비고"]] + [""]
        if r["경고"]:
            L += ["**데이터 경고**"] + [f"- {x}" for x in r["경고"]] + [""]

    if market_csv:
        L += market(cands, market_csv)

    ovr = overridden()
    if ovr:
        L += ["---", "", "## 콘솔에서 입력한 계수", "",
              "아래 값은 명세 기본값이 아니라 심의 콘솔에서 사람이 직접 넣은 값입니다. "
              "이 산출물의 숫자는 전부 이 입력값 위에서 계산되었습니다.", "",
              "| 계수 | 명세값 | 입력값 |", "|---|---:|---:|"]
        L += [f"| {k} | {old_v} | **{new_v}** |" for k, old_v, new_v in sorted(ovr)]
        L += [""]

    L += ["---", "", "## 미검증 계수", "",
          "아래 값은 실증 근거가 아닌 실무 판단 초기값입니다. M6 사후 보정 루프로 "
          "순차 교정해야 하며, 교정 전 산출물은 그만큼의 불확실성을 안고 있습니다.", "",
          "| 계수 | 값 | 설명 |", "|---|---:|---|"]
    L += [f"| {k} | {v} | {why} |" for k, v, why in unvalidated()]
    L += ["", "| 항목 | 상태 |", "|---|---|",
          "| M4 Mode B 배점 | 실증 회귀 아님 — 후보지 간 상대 비교용 |",
          "| M3 브랜드 티어 가중 | 실무 판단값 |", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="점포개발 심의표 생성 (M1~M5)")
    pipeline.add_common_args(ap, ROOT)
    ap.add_argument("--out", default=str(ROOT / "output" / "심의표.md"))
    ap.add_argument("--json", default=str(ROOT / "output" / "심의결과.json"))
    args = ap.parse_args()

    data = pipeline.load_all(ROOT, args)
    if not data["sites"]:
        print(f"후보지 CSV 를 찾을 수 없습니다: {args.sites}", file=sys.stderr)
        return 1
    res = pipeline.analyze_all(data["sites"], data["stores"], data["isos"], data["cells"],
                               data["points"], data["competitors"], data["settings"],
                               market=data["market"])
    write_text(Path(args.out), render(res, Path(args.실거래)))
    write_json(Path(args.json), export(res))

    print(f"후보지 {len(res['후보지'])}곳 심의 → {args.out}   (모드 {res['모드']})")
    for r in sorted(res["후보지"], key=lambda x: {"통과": 0, "보류": 1, "부결": 2}[x["판정"]["판정"]]):
        j = r["판정"]
        print(f"  {MARK[j['판정']]} {j['판정']:<3} {r['이름']:<16} "
              f"S {nf(r.get('S', 0), 1):>5}  월 {nf(r['매출'].get('월매출_중앙', 0)):>6}만  "
              f"margin {nf((j['margin'] or 0) * 100, 1):>6}%  {'; '.join(j['사유'])}")
    return 0


def export(res: dict) -> dict:
    """콘솔·리포트가 먹는 직렬화. 폴리곤 원본은 무거워서 요약만 싣는다."""
    def one(r):
        return {
            "이름": r["이름"], "S": r.get("S"), "S_축": r.get("S_축"),
            "S_풀최대": r.get("S_풀최대"), "S_게이트_축퇴": r.get("S_게이트_축퇴"),
            "상권": {k: v for k, v in r["상권"].items() if k not in ("P5", "P10")},
            "수요": r["수요"], "경쟁": {k: v for k, v in r["경쟁"].items()},
            "매출": r["매출"], "판정": r["판정"], "시세": r.get("시세"),
            "경고": r["경고"],
            "입력": r["후보지"],
        }
    m = res["모델"]
    return {
        "생성": "review_sites.py", "모드": res["모드"], "설정": res["설정"],
        "입력계수": {k: {"명세값": o, "입력값": n} for k, o, n in overridden()},
        "모델": ({"표본수": m["표본수"], "R2": m["R2"], "특징": m["특징"],
                 "beta": m["beta"], "CV": {k: v for k, v in m["CV"].items() if k != "잔차"},
                 "잔차": m["잔차"]} if m and "beta" in m else m),
        "후보지": [one(r) for r in res["후보지"]],
        "기존점": [{"이름": e["이름"], "S": e.get("S"),
                  "월매출_만원": e["후보지"].get("월매출_만원"),
                  "기준점포": e["후보지"].get("기준점포")} for e in res["기존점"]],
    }


if __name__ == "__main__":
    raise SystemExit(main())
