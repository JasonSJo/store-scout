#!/usr/bin/env python3
"""
M6 사후 보정 루프 — 실적으로 계수를 교정한다.

    python3 calibrate.py --actuals 실적.csv

**계수를 자동으로 바꾸지 않는다.** 제안서를 내고 사람이 config.py 에 반영한다.
심의 기준이 아무도 모르게 바뀌는 쪽이 더 위험하다.

출력
    output/보정_제안.md    사람이 읽는 제안서
    output/보정_제안.yaml  config.py 에 반영할 값
"""
from __future__ import annotations

import argparse
from pathlib import Path

import config
import m4_revenue as M4
import m6_calibrate as M6
import pipeline
from common import nf, read_csv, write_text

ROOT = Path(__file__).resolve().parent


def lambda_search(data: dict):
    """λ 를 바꿔 가며 기존점 회귀의 CV MAPE 를 잰다. 계수는 탐색 후 반드시 되돌린다."""
    original = config.COEFFICIENTS["거리마찰_람다"]

    def mape_of(lam: float):
        config.COEFFICIENTS["거리마찰_람다"] = (lam, original[1], original[2])
        try:
            res = pipeline.analyze_all(
                [], data["stores"], data["isos"], data["cells"], data["points"],
                data["competitors"], data["settings"])
            m = res["모델"]
            return m["CV"]["MAPE"] if (m and "beta" in m and m["CV"]["MAPE"]) else None
        finally:
            config.COEFFICIENTS["거리마찰_람다"] = original

    return M6.recalibrate_lambda(mape_of)


def render(err, lam, kap, sw, cross, prop, settings) -> str:
    g = settings.get("거버넌스", {}) or {}
    L = [f"# M6 사후 보정 제안 — {settings.get('브랜드', '')}", "",
         f"**{g.get('문서등급', '사내 한정 · 대외 배포 금지')}**", "",
         "> 이 문서는 제안입니다. 아래 값을 `config.py` 에 반영할지는 사람이 결정합니다.", "",
         "## 1. 예측 오차", ""]
    if err["기록"]:
        L += [f"- 표본 {len(err['기록'])}건 · MAPE **{nf(err['MAPE'] * 100, 1)}%** · "
              f"편향 {nf(err['편향'] * 100, 1)}% (양수면 과대추정)",
              f"- {nf(err['임계'] * 100)}% 초과 연속 최대 {err['연속초과_최대']}건 "
              f"(기준 {err['연속기준']}건) → **재적합 {'필요' if err['재적합_필요'] else '불필요'}**", "",
              "| 개점일 | 점포 | 예측 | 실적 | 오차율 |", "|---|---|---:|---:|---:|"]
        L += [f"| {x['개점일']} | {x['점포명']} | {nf(x['예측'])} | {nf(x['실적'])} | "
              f"{nf(x['오차율'] * 100, 1)}% |" for x in err["기록"]]
    else:
        L.append("- 유효한 실적 기록이 없습니다.")
    L.append("")

    L += ["## 2. λ (거리 마찰계수)", ""]
    if "실패" in lam:
        L.append(f"- {lam['실패']}")
    else:
        L += [f"- 현재 λ={lam['현재_λ']} · MAPE "
              f"{nf((lam['현재_MAPE'] or 0) * 100, 1)}%",
              f"- 제안 λ=**{lam['제안_λ']}** · MAPE {nf(lam['제안_MAPE'] * 100, 1)}% "
              f"(개선 {nf((lam['개선'] or 0) * 100, 1)}%p)", "",
              "| λ | CV MAPE |", "|---:|---:|"]
        L += [f"| {x['λ']} | {nf(x['MAPE'] * 100, 1)}% |" for x in lam["격자"]]
    L.append("")

    L += ["## 3. κ (잠식계수)", ""]
    L += ([f"- {kap['실패']}", f"- 필요한 실측 항목: {', '.join(kap['필요항목'])}"]
          if "실패" in kap else
          [f"- 현재 κ={kap['현재_κ']} · 제안 κ=**{nf(kap['제안_κ'], 3)}** (표본 {kap['표본수']}건)",
           f"- {kap['주의']}"])
    L.append("")

    L += ["## 4. 횡단저항 (0.3)", "", f"- {cross['안내']}",
          f"- 확보된 실측 {cross['확보']}건", ""]

    mode_txt = "가능" if sw["ModeA_가능"] else f"불가 (앞으로 {sw['남은표본']}개 더 필요)"
    L += ["## 5. 모드 전환", "",
          f"- 유효표본 {sw['유효표본']} / 필요 {sw['필요']} → Mode A {mode_txt}", ""]

    L += ["## 6. 반영 제안", ""]
    if prop["변경제안"]:
        L += ["| 계수 | 현재 | 제안 |", "|---|---:|---:|"]
        L += [f"| {k} | {config.COEFFICIENTS[k][0]} | {v} |"
              for k, v in prop["변경제안"].items() if k in config.COEFFICIENTS]
    else:
        L.append("- 변경 제안 없음.")
    if prop["미교정"]:
        L += ["", f"- 여전히 미교정: {', '.join(prop['미교정'])}"]
    L += ["", "---", "", "※ 계수를 바꾸면 과거 심의 결과와 비교 불가능해집니다. "
          "변경 이력과 적용 시점을 반드시 남기십시오."]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="M6 사후 보정 루프")
    pipeline.add_common_args(ap, ROOT)
    ap.add_argument("--actuals", default=str(ROOT / "실적.example.csv"))
    ap.add_argument("--out", default=str(ROOT / "output" / "보정_제안.md"))
    ap.add_argument("--yaml", default=str(ROOT / "output" / "보정_제안.yaml"))
    args = ap.parse_args()

    data = pipeline.load_all(ROOT, args)
    rows = read_csv(Path(args.actuals)) if Path(args.actuals).exists() else []
    if not rows:
        print(f"실적 CSV 가 없습니다: {args.actuals}\n"
              "  개점 후 6·12개월 실매출이 없으면 M6 는 아무것도 교정할 수 없습니다.")
        return 1

    err = M6.error_log(rows)
    lam = lambda_search(data)
    kap = M6.recalibrate_kappa(rows)
    _, _, used = M4.valid_samples(pipeline.analyze_all(
        [], data["stores"], data["isos"], data["cells"], data["points"],
        data["competitors"], data["settings"])["기존점"])
    sw = M6.mode_switch(len(used))
    cross = M6.crossing_resistance_status(rows)
    prop = M6.proposal(err, lam, kap, sw, cross)

    write_text(Path(args.out), render(err, lam, kap, sw, cross, prop, data["settings"]))
    lines = ["# M6 보정 제안 — config.py 에 사람이 반영합니다",
             f"# MAPE {nf((err['MAPE'] or 0) * 100, 1)}% · 재적합필요 {err['재적합_필요']}"]
    lines += [f"{k}: {v}" for k, v in prop["변경제안"].items()]
    write_text(Path(args.yaml), "\n".join(lines) + "\n")

    print(f"실적 {len(err['기록'])}건 · MAPE {nf((err['MAPE'] or 0) * 100, 1)}% · "
          f"재적합 {'필요' if err['재적합_필요'] else '불필요'}")
    if "제안_λ" in lam:
        print(f"  λ {lam['현재_λ']} → 제안 {lam['제안_λ']} "
              f"(MAPE {nf((lam['현재_MAPE'] or 0) * 100, 1)}% → {nf(lam['제안_MAPE'] * 100, 1)}%)")
    print(f"  Mode A 표본 {sw['유효표본']}/{sw['필요']} · 제안 {prop['변경제안'] or '없음'}")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
