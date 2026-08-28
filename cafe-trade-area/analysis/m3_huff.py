#!/usr/bin/env python3
"""
M3 · 경쟁 배분 (Huff 모델)

    S_i = (A_i / d_i^λ) ÷ Σ_j (A_j / d_j^λ)
    A   = 좌석수^0.5 × 브랜드가중
    λ   = 2.2  [미검증]

명세의 식은 **수요 원점 하나**에 대한 정의다. 실제로는 상권 안에 수요가 흩어져
있으므로, M2 가 만든 격자 수요를 원점으로 삼아 칸마다 점유율을 구하고 수요로
가중평균한다. 같은 식을 상권 전체에 적용한 것이며, 결과가 한 점에서 잰 값보다
안정적이다. 비교를 위해 수요중심 한 점에서 잰 `S_점` 도 함께 낸다.

거리 d 는 **보행 네트워크 거리**여야 한다. 네트워크가 없으면 직선거리에
우회계수(1.3, 미검증)를 곱해 대용하고 결과에 경고를 붙인다.
"""
from __future__ import annotations

import geo
from common import read_csv, to_f
from config import BRAND_TIER_WEIGHT, c, tier_of

MIN_D = 25.0   # 거리 0 에서 발산하는 것을 막는 하한(m) — 점포 앞 도달거리


def attraction(seats: float, tier: str) -> float:
    """A = 좌석수^0.5 × 브랜드가중. 좌석 정보가 없으면 업계 통상 24석으로 본다."""
    s = seats if seats > 0 else 24.0
    return (s ** c("흡인력_좌석지수")) * BRAND_TIER_WEIGHT.get(tier, 1.0)


def load_competitors(path) -> list[dict]:
    rows = read_csv(path) if path else []
    out = []
    for r in rows:
        lat, lon = to_f(r.get("위도")), to_f(r.get("경도"))
        if not lat or not lon:
            continue
        tier = tier_of(r.get("브랜드") or r.get("상호", ""), r.get("티어", ""))
        out.append({
            "상호": (r.get("상호") or "").strip(),
            "브랜드": (r.get("브랜드") or "").strip(),
            "티어": tier,
            "위도": lat, "경도": lon,
            "좌석수": to_f(r.get("좌석수")),
            "A": attraction(to_f(r.get("좌석수")), tier),
            "자사": str(r.get("자사", "")).strip().upper() in ("Y", "예", "O", "1"),
        })
    return out


def _walk_d(lat0, lon0, lat1, lon1, network_ok: bool) -> float:
    d = geo.haversine(lat0, lon0, lat1, lon1)
    if not network_ok:
        d *= c("보행우회계수")
    return max(MIN_D, d)


def share(area: dict, site_attr: float, competitors: list[dict],
          cells: list[dict], network_ok: bool = False) -> dict:
    """후보지의 수요가중 Huff 점유율."""
    lat0, lon0 = area["위도"], area["경도"]
    lam = c("거리마찰_람다")

    def util(a_val, dist):
        return a_val / (dist ** lam)

    # 상권(P10) 안에서 수요가 있는 격자만 원점으로 쓴다
    origins = []
    for row in cells:
        clat, clon = to_f(row.get("중심위도")), to_f(row.get("중심경도"))
        if not clat or not clon:
            continue
        size = to_f(row.get("한변_m"), 100.0) or 100.0
        cx, cy = geo.project(lat0, lon0, clat, clon)
        frac = geo.cell_coverage(cx, cy, size, area["P10"])
        if frac <= 0:
            continue
        # 커피 수요 대리지표: 직장인구를 세대수보다 무겁게 본다(이용빈도 차이)
        w = (to_f(row.get("세대수")) * 1.0 + to_f(row.get("직장인구")) * 1.6) * frac
        if w > 0:
            origins.append((clat, clon, w))

    total_w = sum(o[2] for o in origins)
    weighted = 0.0
    for clat, clon, w in origins:
        u_site = util(site_attr, _walk_d(clat, clon, lat0, lon0, network_ok))
        u_rest = sum(util(k["A"], _walk_d(clat, clon, k["위도"], k["경도"], network_ok))
                     for k in competitors)
        denom = u_site + u_rest
        if denom > 0:
            weighted += w * (u_site / denom)
    s_weighted = weighted / total_w if total_w else 0.0

    # 비교용: 수요중심 한 점에서 잰 명세 원식
    if origins:
        cx = sum(o[0] * o[2] for o in origins) / total_w
        cy = sum(o[1] * o[2] for o in origins) / total_w
    else:
        cx, cy = lat0, lon0
    u_site = util(site_attr, _walk_d(cx, cy, lat0, lon0, network_ok))
    u_rest = sum(util(k["A"], _walk_d(cx, cy, k["위도"], k["경도"], network_ok))
                 for k in competitors)
    s_point = u_site / (u_site + u_rest) if (u_site + u_rest) > 0 else 0.0

    tiers = {}
    for k in competitors:
        tiers[k["티어"]] = tiers.get(k["티어"], 0) + 1

    warn = []
    if not network_ok:
        warn.append(f"⚠ 보행 네트워크 거리 미확보 — 직선거리 × {c('보행우회계수')} 로 "
                    f"대용했습니다. 단절이 있는 상권에서 점유율이 과대평가됩니다.")
    if not competitors:
        warn.append("⛔ 경쟁점 데이터 없음 — 점유율이 100% 로 나옵니다. 심의 불가.")
    if not origins:
        warn.append("⛔ 상권 안에 수요 격자가 없습니다 — S 를 신뢰할 수 없습니다.")

    return {
        "S": s_weighted, "S_점": s_point,
        "λ": lam, "A_후보": site_attr,
        "경쟁점수": len(competitors), "티어분포": tiers,
        "수요원점": len(origins), "네트워크거리": network_ok,
        "경고": warn,
    }


def density(area: dict, competitors: list[dict], tier: str = "") -> int:
    """P10 안의 경쟁점 수. tier 를 주면 해당 티어만 센다 (Mode B 배점용)."""
    lat0, lon0 = area["위도"], area["경도"]
    n = 0
    for k in competitors:
        x, y = geo.project(lat0, lon0, k["위도"], k["경도"])
        if geo.point_in_poly(x, y, area["P10"]) and (not tier or k["티어"] == tier):
            n += 1
    return n
