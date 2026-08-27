#!/usr/bin/env python3
"""
상담 기록

이 제품에서 **개인정보가 들어오는 유일한 자리**다. 나머지 표는 점포와 후보지 숫자만
다루지만 여기에는 고객의 성명·연락처·거주지·근무지가 들어온다. 그래서 다른 표와
다르게 규칙 넷을 더 짊어진다.

  1. 동의 없이 저장하지 않는다.
  2. 보관기간이 지나면 파기 대상으로 표시한다. 조용히 쌓아 두지 않는다.
  3. 목록에서 연락처는 가린다. 전체 열람은 감사 로그에 '개인정보 열람' 으로 남는다.
  4. **심의로는 조건만 간다.** 성명·연락처는 파이프라인에도 심의표에도 들어가지
     않는다 — 심의표는 사내 회람 문서라 고객 연락처가 들어갈 자리가 아니다.

상담 조건이 판정에 어떻게 닿는지는 두 갈래로 갈린다. 이 구분이 흐려지면
'상담에서 원하는 대로 적으면 판정이 좋아진다' 는 오해가 생긴다.

  알고리즘 — 운영형태·투자금형태. 고정비 F 를 바꾸고, F 가 바뀌면
             BEP → margin → 판정이 바뀐다. 상담 값 중 판정에 닿는 것은 이 둘뿐이다.
  필터     — 희망지역·평수·상권·보증금·권리금. 후보지를 **목록에서 뺀다.**
             점수를 깎는 게 아니다. 무엇이 왜 빠졌는지는 상담반영.md 에 남는다.

계산 자체(금융비용·인건비·필터)는 여기서 다시 구현하지 않는다. 원본은
analysis/consult.py 한 곳이고 jobs.py 가 그것을 서브프로세스로 부른다.
여기서 베껴 두면 두 곳이 조용히 갈라진다.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime

# analysis/consult.py 의 읽는키와 같아야 한다. 개인정보 키는 의도적으로 빠져 있다.
조건키 = ("희망평수", "희망상권", "희망지역", "보증금_만원", "권리금_만원",
        "투자금형태", "운영형태")
개인정보키 = ("고객명", "고객전화번호", "거주지", "근무지")

상권유형 = ("오피스", "주거", "학교", "병원", "메인", "복합")


def split_list(text: str) -> list[str]:
    """쉼표·줄바꿈·가운뎃점 아무거나로 나눈다. 상담사가 어떻게 적든 받는다."""
    return [x.strip() for x in re.split(r"[,\n·/]+", str(text or "")) if x.strip()]


def 조건(row) -> dict:
    """상담 행 → analysis/consult.py 가 먹는 조건 dict. 개인정보는 넣지 않는다."""
    r = dict(row)
    return {
        "희망지역": split_list(r.get("희망지역")),
        "희망상권": split_list(r.get("희망상권")),
        "희망평수": r.get("희망평수") or 0,
        "보증금_만원": r.get("보증금_만원") or 0,
        "권리금_만원": r.get("권리금_만원") or 0,
        "투자금형태": r.get("투자금형태") or "",
        "운영형태": r.get("운영형태") or "",
    }


def 조건_json(row) -> str:
    return json.dumps({"조건": 조건(row)}, ensure_ascii=False)


def 마스킹(전화: str) -> str:
    """목록에서 쓰는 표시용. 뒤 네 자리만 남긴다."""
    숫자 = re.sub(r"\D", "", str(전화 or ""))
    if len(숫자) < 4:
        return "—" if not 숫자 else "*" * len(숫자)
    return f"{'*' * (len(숫자) - 4)}{숫자[-4:]}"


def 보관개월(settings: dict) -> int:
    try:
        return max(1, int(((settings or {}).get("개인정보") or {}).get("보관개월", 12)))
    except (TypeError, ValueError):
        return 12


def 만료일(created_at: str, 개월: int) -> date | None:
    try:
        d = datetime.strptime(str(created_at)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    y, m = divmod((d.month - 1) + 개월, 12)
    # 말일 보정 — 1/31 + 1개월은 2/31 이 아니다
    return date(d.year + y, m + 1, min(d.day, calendar.monthrange(d.year + y, m + 1)[1]))


def 보관상태(row, settings: dict, 오늘: date | None = None) -> dict:
    """파기해야 할 때가 지났는가. 지났다고 자동으로 지우지는 않는다 —
    조용히 사라지면 상담사가 무엇이 없어졌는지 알 수 없다. 표시하고 사람이 지운다."""
    오늘 = 오늘 or date.today()
    개월 = 보관개월(settings)
    끝 = 만료일(dict(row).get("created_at", ""), 개월)
    if not 끝:
        return {"만료일": None, "남은일": None, "만료됨": False, "보관개월": 개월}
    남은 = (끝 - 오늘).days
    return {"만료일": 끝.isoformat(), "남은일": 남은, "만료됨": 남은 < 0, "보관개월": 개월}


def 요약(row) -> str:
    """목록·심의 화면에서 한 줄로 보이는 조건."""
    r, 조각 = dict(row), []
    지역 = split_list(r.get("희망지역"))
    if 지역:
        조각.append("·".join(지역[:3]))
    if r.get("희망평수"):
        조각.append(f"{float(r['희망평수']):g}평")
    상권 = split_list(r.get("희망상권"))
    if 상권:
        조각.append("·".join(상권))
    투자 = (r.get("보증금_만원") or 0) + (r.get("권리금_만원") or 0)
    if 투자:
        조각.append(f"{float(투자):,.0f}만원")
    if r.get("운영형태"):
        조각.append(str(r["운영형태"]))
    return " · ".join(조각) or "조건 없음"


def 반영예고(row, settings: dict) -> list[tuple[str, str]]:
    """이 상담을 붙이면 설정이 어떻게 바뀌는지 미리 보여 준다.

    실제 계산은 analysis/consult.py 가 하고, 여기서는 그 표의 값을 그대로 읽어
    **무엇이 바뀔지**만 말한다. 숫자를 여기서 다시 계산하면 두 곳이 갈라진다.
    """
    r = dict(row)
    out = []
    운영 = (settings.get("운영형태") or {}).get(str(r.get("운영형태") or ""))
    현재인건비 = ((settings.get("운영") or {}).get("고정비") or {}).get("고정인건비_월_만원")
    if 운영:
        out.append(("고정인건비",
                    f"{float(현재인건비 or 0):,.0f} → {float(운영['고정인건비_월_만원']):,.0f}만원 "
                    f"({r['운영형태']} — {운영.get('설명', '')})"))
    elif r.get("운영형태"):
        out.append(("고정인건비", f"⚠ 설정에 운영형태 '{r['운영형태']}' 가 없어 반영되지 않습니다"))

    투자 = (settings.get("투자금형태") or {}).get(str(r.get("투자금형태") or ""))
    if 투자:
        원금 = (float(r.get("보증금_만원") or 0) + float(r.get("권리금_만원") or 0)) \
            * float(투자.get("대출비율") or 0)
        월 = 원금 * float(투자.get("연금리") or 0) / 12.0 + float(투자.get("리스_월_만원") or 0)
        out.append(("월 금융비용",
                    f"기타 고정비에 {월:,.0f}만원 가산 ({r['투자금형태']} — "
                    f"차입 추정 {원금:,.0f}만원)"))
    elif r.get("투자금형태"):
        out.append(("월 금융비용", f"⚠ 설정에 투자금형태 '{r['투자금형태']}' 가 없어 반영되지 않습니다"))
    return out
