#!/usr/bin/env python3
"""
요금제와 게이팅

좌석과 **월 분석 건수** 두 축으로 잰다. 좌석만으로 재면 조회만 하는 영업팀 인원이
비용을 밀어 올리고, 정작 비용이 드는 파이프라인 실행은 통제되지 않는다.

한도를 넘겼을 때 **막지 않고 알린다** 는 선택지도 있지만 막는 쪽으로 뒀다.
조용히 초과분을 청구하면 다음 달 청구서에서 신뢰를 잃는다.
"""
from __future__ import annotations

PLANS = {
    "starter": {"이름": "Starter", "좌석": 3, "월_분석": 30,
                "설명": "단일 브랜드, 출점 담당 1~2명"},
    "team": {"이름": "Team", "좌석": 10, "월_분석": 150,
             "설명": "운영팀 + 지역 영업팀"},
    "enterprise": {"이름": "Enterprise", "좌석": None, "월_분석": None,
                   "설명": "다브랜드·다지역, 계수 커스터마이즈"},
}
DEFAULT = "starter"

ROLES = ("관리자", "운영", "영업")
# 영업팀은 읽기와 상담만 한다. 파이프라인 실행은 운영팀 이상 —
# 분석 건수가 과금 단위라 아무나 돌리면 한도가 조용히 소진된다.
CAN_RUN = ("관리자", "운영")
CAN_MANAGE = ("관리자",)


def spec(plan: str) -> dict:
    return PLANS.get(plan, PLANS[DEFAULT])


def seat_check(plan: str, current: int) -> tuple[bool, str]:
    cap = spec(plan)["좌석"]
    if cap is None or current < cap:
        return True, ""
    return False, (f"{spec(plan)['이름']} 플랜의 좌석 {cap}개를 모두 썼습니다. "
                   f"비활성 사용자를 정리하거나 플랜을 올리십시오.")


def run_check(plan: str, used_this_month: int, requested: int) -> tuple[bool, str]:
    """requested = 이번 실행이 청구할 분석 건수(후보지 수)."""
    cap = spec(plan)["월_분석"]
    if cap is None:
        return True, ""
    if used_this_month + requested <= cap:
        return True, ""
    남음 = max(0, cap - used_this_month)
    return False, (f"이번 달 분석 한도({cap}건)를 넘습니다 — "
                   f"{used_this_month}건 사용, 남은 {남음}건, 요청 {requested}건. "
                   f"후보지를 줄여 나눠 돌리거나 플랜을 올리십시오.")


def used_this_month(con, org_id: int) -> int:
    row = con.execute(
        "SELECT COALESCE(SUM(billed_units),0) AS n FROM runs "
        "WHERE org_id = ? AND status IN ('완료','실행중') "
        "AND strftime('%Y-%m', started_at) = strftime('%Y-%m','now')",
        (org_id,)).fetchone()
    return int(row["n"])


def seats_used(con, org_id: int) -> int:
    row = con.execute(
        "SELECT COUNT(*) AS n FROM users WHERE org_id = ? AND active = 1",
        (org_id,)).fetchone()
    return int(row["n"])
