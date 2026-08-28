#!/usr/bin/env python3
"""
M5 · 판정 로직

    F          = 월 고정비 (임대료 + 관리비 + 고정인건비 + 기타)
    v          = 변동비율 (원재료율 + 로열티율 + 광고분담금율)
    BEP        = F ÷ (1 - v)
    margin     = (R_median - BEP) ÷ R_median
    margin_low = (R_low    - BEP) ÷ R_low

    overlap = area(P10_후보 ∩ P10_기존점) ÷ area(P10_후보)
    잠식액  = overlap × 기존점_월매출 × κ

    IF   치명플래그 ≥ 1  OR  margin < 0.15                              → 부결
    ELIF margin < 0.30 OR S < 70 OR overlap > 0.30 OR margin_low < 0    → 보류
    ELSE                                                                → 통과

명세의 설계 원칙대로 **정량 점수는 보조이고 부결 트리거가 실질 방어선**이다.
특히 치명 플래그는 점수·매출과 무관하게 단독으로 부결시킨다.

기존점이 여럿이면 overlap 은 **최댓값**(가장 심하게 겹치는 한 점포)으로 판정하고,
잠식액은 **합계**로 공시한다. 판정은 최악의 한 점포 기준이 맞고, 금액은 전부 더해야
실제 자사 손실을 본다.
"""
from __future__ import annotations

from common import nf, to_f


def pf(v: float, n: int = 0) -> str:
    """퍼센트 표기. 파이썬 %-포맷은 은행가 반올림이라 JS 와 갈리므로 nf 를 통과시킨다."""
    return nf(v * 100, n) + "%"
from config import FATAL_FLAGS, c

TRUE_SET = ("Y", "YES", "예", "O", "TRUE", "1", "해당")


def is_flagged(v) -> bool:
    return str(v).strip().upper() in TRUE_SET


def fatal_flags(site: dict) -> list[str]:
    """후보지 CSV 의 플래그 열을 읽는다. 열이 아예 없으면 '미확인' 으로 따로 알린다."""
    hit = []
    for key, desc in FATAL_FLAGS:
        if is_flagged(site.get(key)):
            hit.append(desc)
    return hit


def flags_unchecked(site: dict) -> list[str]:
    """실사 전이라 칸이 비어 있는 치명 항목 — 통과 판정을 신뢰할 수 없다는 신호."""
    return [desc for key, desc in FATAL_FLAGS
            if str(site.get(key, "")).strip() == ""]


def variable_rate(settings: dict) -> float:
    v = (settings.get("운영", {}) or {}).get("변동비", {}) or {}
    return (to_f(v.get("원재료율"), 0.0) + to_f(v.get("로열티율"), 0.0)
            + to_f(v.get("광고분담금율"), 0.0) + to_f(v.get("기타변동비율"), 0.0))


def fixed_cost(site: dict, settings: dict) -> dict:
    f = (settings.get("운영", {}) or {}).get("고정비", {}) or {}
    rent = to_f(site.get("월임대료_만원"))
    mgmt = to_f(site.get("관리비_만원"))
    labor = to_f(f.get("고정인건비_월_만원"))
    etc = to_f(f.get("기타_월_만원"))
    return {"임대료": rent, "관리비": mgmt, "고정인건비": labor, "기타": etc,
            "F": rent + mgmt + labor + etc}


def cannibalization(overlaps: list[dict]) -> dict:
    """overlaps: [{점포명, overlap, 월매출_만원}, ...]"""
    kappa = c("잠식계수_카파")
    rows = []
    for o in overlaps:
        amt = o["overlap"] * to_f(o.get("월매출_만원")) * kappa
        rows.append({**o, "잠식액_만원": amt})
    return {
        "κ": kappa,
        "최대_overlap": max((r["overlap"] for r in rows), default=0.0),
        "잠식액_합_만원": sum(r["잠식액_만원"] for r in rows),
        "상세": sorted(rows, key=lambda r: -r["overlap"]),
    }


PY_PER_M2 = 3.305785          # 1평 = 3.305785㎡


def market_rent(site: dict, market: dict) -> dict | None:
    """지역 매매 시세로 기대 월임대료를 환산한다.

        건물가치 ≈ 지역_중앙_만원/㎡ × 전용면적_㎡
        기대_월임대료 ≈ 건물가치 × 연임대수익률 ÷ 12

    실거래가는 **매매가**라 임대 조건과 직접 비교할 수 없다. 그 간극을 메우는 것이
    연임대수익률이고, 이 값은 미검증 계수다(config.상업용_연임대수익률).
    표본이 적거나 면적·시세가 없으면 대조하지 않는다 — 없는 근거로 판단하지 않는다.

    ⚠ **판정에는 들어가지 않는다.** judge() 는 이 함수를 부르지 않는다. 산출물에
    참고 자료로 실을 때만 쓴다 — 검증되지 않은 환산으로 보류를 만들면, 실거래
    데이터가 있는 지역의 후보지만 근거 없이 불리해진다.
    """
    if not market:
        return None
    unit = to_f(market.get("만원_per_m2_중앙"))
    n = int(to_f(market.get("건수")))
    area_py = to_f(site.get("전용면적_평"))
    if unit <= 0 or area_py <= 0 or n < int(c("시세대조_최소건수")):
        return None
    value = unit * area_py * PY_PER_M2
    expected = value * c("상업용_연임대수익률") / 12.0
    if expected <= 0:
        return None
    rent = to_f(site.get("월임대료_만원"))
    return {
        "건수": n, "만원_per_m2_중앙": unit,
        "추정_건물가치_만원": value, "기대_월임대료_만원": expected,
        "제시_월임대료_만원": rent,
        "배수": (rent / expected) if expected else None,
    }


def judge(site: dict, revenue: dict, settings: dict, S: float,
          overlaps: list[dict], s_pool_max: float = None) -> dict:
    """3단 판정. 매출 추정이 실패해도 판정 자체는 내린다(치명 플래그는 매출과 무관).

    **지역 실거래가(법정동 기반)는 판정에 들어가지 않는다.** 매매가를 임대료로
    환산한 값이라 층·용도·전면 편차를 담지 못하고, 환산에 쓰는 연임대수익률이
    미검증 계수다. 검증되지 않은 환산이 보류를 만들면, 데이터가 있는 지역의
    후보지만 근거 없이 불리해진다. 시세는 market_rent() 로 따로 계산해
    **참고 자료로만** 싣는다(review_sites.py).
    """
    v = variable_rate(settings)
    fc = fixed_cost(site, settings)
    F = fc["F"]
    bep = F / (1 - v) if v < 1 else None

    r_med = revenue.get("월매출_중앙")
    r_low = revenue.get("월매출_하한")
    margin = ((r_med - bep) / r_med) if (bep is not None and r_med) else None
    margin_low = ((r_low - bep) / r_low) if (bep is not None and r_low) else None

    can = cannibalization(overlaps)
    overlap = can["최대_overlap"]
    fatal = fatal_flags(site)
    unchecked = flags_unchecked(site)

    reasons = []
    if fatal:
        reasons += [f"치명: {x}" for x in fatal]
    if bep is None:
        reasons.append("변동비율이 100% 이상 — 어떤 매출에서도 흑자 불가")
    if margin is not None and margin < c("부결_마진"):
        reasons.append(f"margin {pf(margin, 1)} < {pf(c('부결_마진'))}")

    if fatal or bep is None or (margin is not None and margin < c("부결_마진")):
        verdict = "부결"
    else:
        hold = []
        if margin is None:
            hold.append("매출 추정 실패 — margin 계산 불가")
        else:
            if margin < c("보류_마진"):
                hold.append(f"margin {pf(margin, 1)} < {pf(c('보류_마진'))}")
            if margin_low is not None and margin_low < 0:
                hold.append(f"하한 시나리오 적자 (margin_low {pf(margin_low, 1)})")
        if S < c("보류_점수"):
            hold.append(f"S {nf(S, 1)} < {nf(c('보류_점수'))}")
        if overlap > c("보류_중첩"):
            hold.append(f"자사 상권 중첩 {pf(overlap)} > {pf(c('보류_중첩'))}")
        verdict = "보류" if hold else "통과"
        reasons += hold

    notes = []
    if s_pool_max is not None and s_pool_max < c("보류_점수"):
        notes.append(
            f"⛔ S 게이트 축퇴 — 풀 전체 S 최댓값이 {nf(s_pool_max, 1)} 로 임계값 "
            f"{nf(c('보류_점수'))} 에 못 미칩니다. S 는 풀 내 min-max 정규화라 모든 지표에서 "
            f"동시에 1등이어야 100 에 닿습니다. 지금 조건에서는 'S < {nf(c('보류_점수'))}' 이 모든 후보지에 "
            f"무조건 걸려 변별력이 없습니다. 임계값을 포트폴리오 기준(예: 기준점포 S)으로 "
            f"재설정하거나 정규화 방식을 바꾸는 결정이 필요합니다.")
    if verdict == "통과" and unchecked:
        notes.append(f"⛔ 치명 항목 {len(unchecked)}건이 미확인 상태입니다 — "
                     f"등기·임대인·소송·인허가 실사를 마치기 전의 '통과'는 잠정입니다.")
    if can["잠식액_합_만원"] > 0:
        notes.append(f"자사 기존점 잠식 추정 {nf(can['잠식액_합_만원'])}만원/월 "
                     f"(κ={can['κ']} 미검증) — 신규 매출에서 차감해 순증을 보십시오.")

    return {
        "판정": verdict, "사유": reasons, "비고": notes,
        "치명플래그": fatal, "치명_미확인": unchecked,
        "변동비율": v, "고정비": fc, "BEP_만원": bep,
        "margin": margin, "margin_low": margin_low,
        "S": S, "카니발": can,
        "순증_월매출_만원": (r_med - can["잠식액_합_만원"]) if r_med else None,
    }
