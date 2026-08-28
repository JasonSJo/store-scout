#!/usr/bin/env python3
"""
M4 · 매출 추정 — 2모드 분기

    Mode A (유효표본 n ≥ 15)  로그선형 회귀. 출력은 점추정이 아니라 예측구간.
    Mode B (n < 15)          기준점포 앵커링. 배점 S 로 실매출을 비례 조정.

**Mode B 는 순환논리에 가깝다.** 가중치를 임의로 정하고, 그 가중치로 만든 S 로
매출을 추정하고, 그 추정치로 통과를 판단한다. 검증되는 것은 사후 실적뿐이다.
그래서 Mode B 결과에는 그 사실이 경고로 따라붙고, 최종 방어선은 M5 의
부결 트리거(치명 플래그·안전마진)에 둔다.

출력 단위: 일매출·월매출 모두 만원.
"""
from __future__ import annotations

import math

import ols
from common import to_f
from config import MODE_B_WEIGHTS, c, weights_flat

MODE_A, MODE_B = "A", "B"


# ── Mode B · 지표 정규화와 배점 ────────────────────────────────────
def indicators(rec: dict) -> dict:
    """분석 결과 한 건에서 배점용 원지표를 뽑는다. 값이 클수록 좋은 방향으로 통일한다."""
    d, s, area = rec["수요"], rec["경쟁"], rec["상권"]
    site = rec["후보지"]
    rent = to_f(site.get("월임대료_만원"))
    same = d["D_am_같은편"]
    total_am = d["D_am"] or 1.0
    return {
        "배후주거세대": d["H"],
        "직장인구": d["W"],
        "오전유동": d["D_am_adj"],
        "주말야간유입": d["주말야간"],
        # 출근 동선이 후보지 쪽으로 흐르는 정도 — 같은 편 비율
        "출근동선방향": same / total_am,
        "코너전면가시성": (3.0 if str(site.get("코너여부", "")).upper().startswith(("Y", "O")) else 0.0)
                    + min(10.0, to_f(site.get("전면폭_m"))),
        "1층접근성": 1.0 if int(to_f(site.get("층"), 1)) == 1 else 0.0,
        "주차정차": to_f(site.get("주차가능대수")) + (2.0 if str(site.get("정차가능", "")).upper().startswith(("Y", "O")) else 0.0),
        # 경쟁은 적을수록 좋다 → 음수로 뒤집어 정규화한다
        "동일티어밀도": -s["동일가격대_수"],
        "저가브랜드밀집": -s["저가형_수"],
        "유효상권잔존율": area["R"],
        "임대료대비객수효율": (d["D_am_adj"] / rent) if rent > 0 else 0.0,
        "계약조건": to_f(site.get("계약조건점수")),
    }


def score_pool(records: list[dict]) -> None:
    """후보지 + 기준점포를 **한 풀 안에서** min-max 정규화해 S(0~100)를 매긴다.

    명세대로 이 배점은 절대 척도가 아니라 상대 비교용이다. 기준점포가 같은 풀에
    들어가야 앵커링(S ÷ S_기준점포)이 의미를 갖는다.
    """
    if not records:
        return
    raw = [indicators(r) for r in records]
    keys = list(weights_flat().keys())
    lo = {k: min(x[k] for x in raw) for k in keys}
    hi = {k: max(x[k] for x in raw) for k in keys}

    for rec, x in zip(records, raw):
        detail, total = {}, 0.0
        for axis, items in MODE_B_WEIGHTS.items():
            for k, w in items.items():
                span = hi[k] - lo[k]
                # 풀 전체가 같은 값이면 변별력이 없다 → 배점의 절반을 준다
                norm = 0.5 if span == 0 else (x[k] - lo[k]) / span
                pts = w * norm
                detail[k] = {"원값": x[k], "정규화": norm, "배점": w, "점수": pts}
                total += pts
        rec["S"] = total
        rec["S_상세"] = detail
        rec["S_축"] = {
            axis: sum(detail[k]["점수"] for k in items)
            for axis, items in MODE_B_WEIGHTS.items()
        }

    # 게이트 축퇴 진단 —
    # S 는 풀 내 min-max 정규화라 모든 지표에서 동시에 1등이어야 100 에 닿는다.
    # 그래서 풀 최댓값이 임계값에 못 미치면 'S < 70' 보류 조건이 전 후보지에
    # 무조건 걸려 변별력을 잃는다. 조용히 통과시키지 말고 진단으로 알린다.
    top = max(r["S"] for r in records)
    gate = c("보류_점수")
    for rec in records:
        rec["S_풀최대"] = top
        rec["S_게이트_축퇴"] = top < gate


# ── Mode A · 로그선형 회귀 ─────────────────────────────────────────
FEATURES = ["log(W)", "log(H)", "log(D_am_adj)", "S_huff", "방향적합", "코너", "log(전면폭)"]


def _row(rec: dict) -> list[float] | None:
    d, site = rec["수요"], rec["후보지"]
    W, H, D = d["W"], d["H"], d["D_am_adj"]
    front = to_f(site.get("전면폭_m"))
    if min(W, H, D, front) <= 0:
        return None      # 로그를 못 취하는 표본은 유효표본에서 제외한다
    return [
        1.0, math.log(W), math.log(H), math.log(D),
        rec["경쟁"]["S"],
        1.0 if str(site.get("방향적합", "")).upper().startswith(("Y", "O")) else 0.0,
        1.0 if str(site.get("코너여부", "")).upper().startswith(("Y", "O")) else 0.0,
        math.log(front),
    ]


def valid_samples(stores: list[dict]) -> tuple[list[list[float]], list[float], list[dict]]:
    """실매출이 있고 로그 변환 가능한 기존점만 회귀 표본으로 쓴다."""
    X, y, used = [], [], []
    for rec in stores:
        sales = to_f(rec["후보지"].get("일매출_만원"))
        if sales <= 0:
            monthly = to_f(rec["후보지"].get("월매출_만원"))
            days = to_f(rec["후보지"].get("영업일수"), 30) or 30
            sales = monthly / days if monthly > 0 else 0.0
        row = _row(rec)
        if sales <= 0 or row is None:
            continue
        X.append(row)
        y.append(math.log(sales))
        used.append(rec)
    return X, y, used


def fit_mode_a(stores: list[dict]) -> dict | None:
    X, y, used = valid_samples(stores)
    n = len(y)
    if n < int(c("ModeA_최소표본")):
        return None
    try:
        beta = ols.fit(X, y)
    except ols.SingularMatrix as e:
        return {"실패": str(e), "표본수": n}
    folds = 0 if n < 40 else 5           # 명세: 표본이 작으면 LOOCV, 충분하면 5-fold
    cv = ols.cross_validate(X, y, folds)
    note = []
    if n >= int(c("ModeA_GBM검토_표본")):
        note.append(f"표본 {n}개 — 명세상 Gradient Boosting 과 성능 비교를 검토할 구간입니다.")
    return {
        "beta": beta, "특징": FEATURES, "표본수": n,
        "R2": ols.r_squared(X, y, beta),
        "CV": cv, "메모": note,
        "잔차": cv["잔차"],
    }


def predict_mode_a(rec: dict, model: dict, days: float) -> dict:
    row = _row(rec)
    if row is None:
        return {"실패": "설명변수 결측(W·H·D_am_adj·전면폭 중 0 이하)"}
    center = ols.predict(model["beta"], row)
    resid = model["잔차"]
    q = lambda p: ols.quantile(resid, p)
    lo = math.exp(center + q(c("예측구간_하한분위")))
    md = math.exp(center + q(c("예측구간_중앙분위")))
    hi = math.exp(center + q(c("예측구간_상한분위")))
    return {
        "모드": MODE_A,
        "일매출_하한": lo, "일매출_중앙": md, "일매출_상한": hi,
        "월매출_하한": lo * days, "월매출_중앙": md * days, "월매출_상한": hi * days,
        "표본수": model["표본수"], "R2": model["R2"],
        "MAPE": model["CV"]["MAPE"], "검증": model["CV"]["방식"],
        "경고": list(model.get("메모", [])),
    }


# ── Mode B · 앵커링 ────────────────────────────────────────────────
def predict_mode_b(rec: dict, anchors: list[dict], days: float, band: float = None) -> dict:
    """추정매출 = 기준점포_실매출 × (S ÷ S_기준점포). 기준점포가 여럿이면 중앙값."""
    S = rec.get("S", 0.0)
    ests = []
    used = []
    for a in anchors:
        a_S = a.get("S", 0.0)
        monthly = to_f(a["후보지"].get("월매출_만원"))
        if a_S <= 0 or monthly <= 0:
            continue
        ests.append(monthly * (S / a_S))
        used.append({"기준점포": a["후보지"].get("점포명") or a["후보지"].get("후보지명"),
                     "S": a_S, "월매출_만원": monthly})
    if not ests:
        return {"모드": MODE_B, "실패": "기준점포가 없습니다 — 실적이 안정된 기존점 1~2개를 "
                                     "`기준점포=Y` 로 지정하십시오. 지정 없이는 Mode B 로 "
                                     "매출을 추정할 수 없습니다.",
                "S": S}
    ests.sort()
    md = ols.quantile(ests, 0.5)
    w = c("ModeB_예측구간_폭") if band is None else band
    warn = [
        "⚠ Mode B 는 임의 배점 S 로 실매출을 비례 조정한 값입니다. 배점의 타당성은 "
        "사후 실적으로만 검증됩니다 — 심의 참고자료로만 쓰고, 통과 여부는 M5 의 "
        "부결 트리거로 판단하십시오.",
    ]
    if band is None:
        warn.append(f"⚠ 예측구간 ±{w:.0%} 는 잔차 표본이 아니라 미검증 가정값입니다 "
                    f"(M6 가 실적 MAPE 로 대체).")
    else:
        warn.append(f"예측구간 ±{w:.0%} 는 M6 가 실적에서 측정한 MAPE 입니다.")
    return {
        "모드": MODE_B, "S": S,
        "월매출_하한": md * (1 - w), "월매출_중앙": md, "월매출_상한": md * (1 + w),
        "일매출_하한": md * (1 - w) / days, "일매출_중앙": md / days,
        "일매출_상한": md * (1 + w) / days,
        "기준점포": used, "구간폭": w, "경고": warn,
    }


def estimate(rec: dict, model: dict | None, anchors: list[dict],
             days: float, measured_mape: float = None) -> dict:
    """Mode A 가 가능하면 A, 아니면 B. 실패해도 그 사실을 결과로 돌려준다."""
    if model and "beta" in model:
        out = predict_mode_a(rec, model, days)
        if "실패" not in out:
            return out
        out["모드"] = MODE_A
        return out
    reason = None
    if model and "실패" in model:
        reason = f"Mode A 적합 실패({model['실패']}) → Mode B 로 전환"
    out = predict_mode_b(rec, anchors, days, measured_mape)
    if reason:
        out.setdefault("경고", []).insert(0, "⚠ " + reason)
    return out
