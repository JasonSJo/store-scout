#!/usr/bin/env python3
"""
후보지별 심의 리포트 — **사내 한정**

    python3 build_report.py --site "판교"

⚠ 이 리포트는 내부 의사결정 자료다. 가맹희망자에게 제공하는 예상매출액 산정서와
수치를 혼용해서는 안 되며, 제공치가 내부 **중앙값** 추정치를 초과하지 않도록
별도 통제해야 한다. 문서 머리말에 이 통제 문구가 항상 인쇄된다.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pipeline
from common import nf, write_text
from config import MODE_B_WEIGHTS, unvalidated

ROOT = Path(__file__).resolve().parent


def render(r: dict, res: dict, today: str = "") -> str:
    settings = res["설정"]
    g = settings.get("거버넌스", {}) or {}
    j, p, a, d, s = r["판정"], r["매출"], r["상권"], r["수요"], r["경쟁"]
    L = [
        f"# 점포개발 심의 리포트 — {r['이름']}", "",
        f"**{g.get('문서등급', '사내 한정 · 대외 배포 금지')}**", "",
        f"> {(g.get('고지') or '').strip()}", "",
        "| | |", "|---|---|",
        f"| 브랜드 | {settings.get('브랜드', '—')} |",
        f"| 주소 | {r['후보지'].get('주소') or '—'} |",
        f"| 심의일 | {today or date.today().isoformat()} |",
        f"| 추정 모드 | {p.get('모드', '—')} |",
        f"| **판정** | **{j['판정']}** |", "",
    ]
    if j["사유"]:
        L += ["**사유**"] + [f"- {x}" for x in j["사유"]] + [""]

    L += ["## M1 · 상권 획정", "",
          f"- P10 면적 {nf(a['P10_면적_m2'] / 10000, 1)}ha · P5 {nf(a['P5_면적_m2'] / 10000, 1)}ha",
          f"- 잔존율 **R = {nf(a['R'], 2)}** (이상 원형 π×667m² 대비)",
          f"- 등시선 출처: {a['출처']}", ""]
    if a["경고"]:
        L += [f"- {x}" for x in a["경고"]] + [""]

    L += ["## M2 · 수요 변수", "",
          "| 변수 | 값 | 정의 |", "|---|---:|---|",
          f"| H | {nf(d['H'])}세대 | 격자세대수 × P10 면적비 |",
          f"| W | {nf(d['W'])}명 | 격자직장인구 × P10 면적비 |",
          f"| D_am | {nf(d['D_am'])}명 | 07~10시 유동 (P5) |",
          f"| D_am_adj | **{nf(d['D_am_adj'])}명** | 같은편 {nf(d['D_am_같은편'])} + "
          f"반대편 {nf(d['D_am_반대편'])} × {d['횡단저항']} |",
          f"| D_all | {nf(d['D_all'])}명 | 전시간대 유동 (P5) |", ""]
    if d.get("경고"):
        L += [f"- {x}" for x in d["경고"]] + [""]

    L += ["## M3 · 경쟁 배분 (Huff)", "",
          f"- 흡인력 A = 좌석수^0.5 × 브랜드가중 = {nf(s['A_후보'], 2)}",
          f"- 거리 마찰계수 λ = {s['λ']} **[미검증]**",
          f"- 수요가중 점유율 **S = {nf(s['S'] * 100, 2)}%** "
          f"(수요원점 {s['수요원점']}칸 기준)",
          f"- 참고: 수요중심 한 점 기준 {nf(s['S_점'] * 100, 2)}% — 원점이 후보지와 "
          f"거의 겹쳐 발산하므로 판정에 쓰지 않습니다",
          f"- 반경 내 경쟁 {s['반경내_경쟁']}곳 · 동일가격대 {s['동일가격대_수']} · "
          f"저가형 {s['저가형_수']} · 티어 {s['티어분포']}", ""]
    if s["경고"]:
        L += [f"- {x}" for x in s["경고"]] + [""]

    L += ["## M4 · 매출 추정", ""]
    if p.get("모드") == "A":
        L += [f"Mode A(회귀) · 유효표본 {p.get('표본수')} · R² {nf(p.get('R2', 0), 3)} · "
              f"{p.get('검증')} MAPE {nf((p.get('MAPE') or 0) * 100, 1)}%", ""]
    else:
        L += ["Mode B(앵커링) — 기준점포 실매출을 배점 S 로 비례 조정한 값입니다.", ""]
        for x in p.get("기준점포", []):
            L.append(f"- 기준점포 {x['기준점포']}: S {nf(x['S'], 1)} · "
                     f"월매출 {nf(x['월매출_만원'])}만원")
        L.append("")
    # 구간의 의미가 모드마다 다르다 — Mode A 는 잔차 분위수, Mode B 는 가정한 폭이다
    if p.get("모드") == "A":
        lo_lb, hi_lb = "하한 (잔차 25분위)", "상한 (잔차 75분위)"
    else:
        w = p.get("구간폭", 0)
        lo_lb, hi_lb = f"하한 (중앙 −{nf(w * 100)}%)", f"상한 (중앙 +{nf(w * 100)}%)"
    L += ["| 구간 | 월매출(만원) | 일매출(만원) |", "|---|---:|---:|",
          f"| {lo_lb} | {nf(p.get('월매출_하한', 0))} | {nf(p.get('일매출_하한', 0), 1)} |",
          f"| **중앙 (심의 기준값)** | **{nf(p.get('월매출_중앙', 0))}** | {nf(p.get('일매출_중앙', 0), 1)} |",
          f"| {hi_lb} | {nf(p.get('월매출_상한', 0))} | {nf(p.get('일매출_상한', 0), 1)} |", ""]
    if p.get("경고"):
        L += [f"- {x}" for x in p["경고"]] + [""]

    fc = j["고정비"]
    L += ["## M5 · 판정", "",
          "| 항목 | 값 |", "|---|---:|",
          f"| 고정비 F | {nf(fc['F'])}만원 (임대 {nf(fc['임대료'])} + 관리 {nf(fc['관리비'])} "
          f"+ 고정인건비 {nf(fc['고정인건비'])} + 기타 {nf(fc['기타'])}) |",
          f"| 변동비율 v | {nf(j['변동비율'] * 100, 1)}% |",
          f"| BEP | {nf(j['BEP_만원'] or 0)}만원 |",
          f"| margin | {nf((j['margin'] or 0) * 100, 1)}% |",
          f"| margin_low | {nf((j['margin_low'] or 0) * 100, 1)}% |",
          f"| S | {nf(j['S'], 1)} / 100 |",
          f"| 최대 상권 중첩 | {nf(j['카니발']['최대_overlap'] * 100)}% |",
          f"| 잠식 추정 | {nf(j['카니발']['잠식액_합_만원'])}만원/월 (κ={j['카니발']['κ']} 미검증) |",
          f"| 순증 월매출 | {nf(j['순증_월매출_만원'] or 0)}만원 |", ""]
    if j["카니발"]["상세"]:
        L += ["| 인접 자사점 | 중첩 | 잠식(만원/월) |", "|---|---:|---:|"]
        L += [f"| {x['점포명']} | {nf(x['overlap'] * 100)}% | {nf(x['잠식액_만원'])} |"
              for x in j["카니발"]["상세"]]
        L.append("")

    L += ["### 치명 플래그", ""]
    if j["치명플래그"]:
        L += [f"- ⛔ {x}" for x in j["치명플래그"]]
    else:
        L.append("- 해당 없음")
    if j["치명_미확인"]:
        L += ["", "**미확인(실사 필요)**"] + [f"- {x}" for x in j["치명_미확인"]]
    L.append("")
    if j["비고"]:
        L += [f"- {x}" for x in j["비고"]] + [""]

    L += ["### S 배점 (Mode B 기준)", "",
          "| 축 | 배점 | 획득 |", "|---|---:|---:|"]
    for ax, got in (r.get("S_축") or {}).items():
        L.append(f"| {ax} | {sum(MODE_B_WEIGHTS[ax].values())} | {nf(got, 1)} |")
    L += [f"| **합계** | **100** | **{nf(r.get('S', 0), 1)}** |", "",
          "> 이 배점은 실증 회귀가 아닌 임의 설정값이며 후보지 간 상대 비교용으로만 "
          "유효합니다. 절대 점수로 해석하지 마십시오.", ""]

    L += ["## 미검증 계수", "", "| 계수 | 값 | 설명 |", "|---|---:|---|"]
    L += [f"| {k} | {v} | {why} |" for k, v, why in unvalidated()]

    L += ["", "---", "",
          "※ 본 리포트의 매출·손익은 규칙 기반 모델에 의한 **추정치**이며 실제 매출을 "
          "보장하지 않습니다. 정량 점수는 보조 자료이고 실질 방어선은 부결 트리거"
          "(치명 플래그·안전마진)입니다. **사후 보정 루프(M6) 없이는 운영하지 마십시오.**"]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="후보지별 심의 리포트(사내 한정)")
    pipeline.add_common_args(ap, ROOT)
    ap.add_argument("--site", default="", help="후보지명 부분일치. 생략 시 전체")
    ap.add_argument("--outdir", default=str(ROOT / "output" / "reports"))
    args = ap.parse_args()

    data = pipeline.load_all(ROOT, args)
    res = pipeline.analyze_all(data["sites"], data["stores"], data["isos"], data["cells"],
                               data["points"], data["competitors"], data["settings"],
                               market=data["market"])
    targets = [r for r in res["후보지"] if not args.site or args.site in r["이름"]]
    if not targets:
        print(f"'{args.site}' 와 일치하는 후보지가 없습니다.")
        return 1
    outdir = Path(args.outdir)
    for r in targets:
        safe = r["이름"].replace("/", "-").replace(" ", "_")
        path = write_text(outdir / f"심의리포트_{safe}.md", render(r, res))
        print(f"  {r['판정']['판정']:<3} {r['이름']:<16} → {path.name}")
    print(f"리포트 {len(targets)}건 → {outdir}  (사내 한정 · 대외 배포 금지)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
