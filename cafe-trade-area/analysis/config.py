#!/usr/bin/env python3
"""
계수 레지스트리 — 점포개발 심의 알고리즘 v1.0

명세의 모든 계수를 한곳에 모으고, 각 계수가 **실증된 값인지 실무 판단값인지**를
코드에 명시한다. 미검증 계수는 리포트에 그대로 표시되어 심의 자리에서 숨지 않는다.
M6 사후 보정 루프가 교정하는 대상도 여기다.

단위: 금액은 만원, 객단가는 원, 거리는 m.
app/js/config.js 와 같은 값이어야 한다 (tests/test_parity.py 가 대조).
"""
from __future__ import annotations

import json
from pathlib import Path

# ── 계수 검증 상태 ────────────────────────────────────────────────
#   MEASURED  실적 데이터로 추정·검증됨
#   ESTIMATED 실무 판단 초기값 — M6 로 교정해야 함
#   DERIVED   다른 값에서 기계적으로 유도됨(검증 대상 아님)
MEASURED, ESTIMATED, DERIVED = "MEASURED", "ESTIMATED", "DERIVED"

COEFFICIENTS = {
    # M1
    "보행속도_kmh": (4.0, DERIVED, "명세 고정값 — 등시선 기준 보행속도"),
    "P10_이상반경_m": (667.0, DERIVED, "4km/h × 10분. 잔존율 R 의 분모"),
    "경사_배제_퍼센트": (10.0, ESTIMATED, "이 경사를 넘는 링크는 barrier 처리"),

    # M2
    "횡단저항": (0.3, ESTIMATED, "반대편 유동인구의 유효 반영률 — 실측 캘리브레이션 필요"),

    # M2 · 유동인구 대용 안분
    "유동_안분_집중계수": (1.0, ESTIMATED,
                    "행정동·상권 단위 유동인구를 P5 면적비로 안분할 때 곱하는 보정. "
                    "1.0 은 균등분포 가정이고, 실제 통행량은 간선도로변에 몰린다. "
                    "M6 가 실측 카운트(실적.csv 의 실측_같은편_오전)를 확보하면 교정한다"),

    # M3
    "거리마찰_람다": (2.2, ESTIMATED, "Huff 거리 마찰계수 — 실적으로 반드시 캘리브레이션"),
    "흡인력_좌석지수": (0.5, ESTIMATED, "A = 좌석수^0.5 × 브랜드가중"),
    "보행우회계수": (1.3, ESTIMATED, "보행 네트워크 거리 미확보 시 직선거리에 곱하는 우회율"),

    # M5
    "잠식계수_카파": (0.5, ESTIMATED, "중첩 상권 내 자사 점포 간 수요 분할률"),
    "부결_마진": (0.15, DERIVED, "margin 이 이 값 미만이면 부결 (명세 고정)"),
    "보류_마진": (0.30, DERIVED, "margin 이 이 값 미만이면 보류 (명세 고정)"),
    "보류_점수": (70.0, DERIVED, "S 가 이 값 미만이면 보류 (명세 고정)"),
    "보류_중첩": (0.30, DERIVED, "overlap 이 이 값 초과면 보류 (명세 고정)"),

    # M4
    "ModeA_최소표본": (15, DERIVED, "유효 표본이 이 수 이상이면 회귀(Mode A)"),
    "ModeA_GBM검토_표본": (40, DERIVED, "이 수 이상이면 Gradient Boosting 과 성능 비교"),
    "예측구간_하한분위": (0.25, DERIVED, "명세 고정"),
    "예측구간_중앙분위": (0.50, DERIVED, "심의 기준값"),
    "예측구간_상한분위": (0.75, DERIVED, "명세 고정"),
    "ModeB_예측구간_폭": (0.25, ESTIMATED,
                      "Mode B 는 잔차 표본이 없어 구간을 만들 수 없다. "
                      "M6 가 실적 MAPE 를 확보하면 그 값으로 대체된다"),

    # 지역 시세 대조 (실거래가) — **판정 미사용, 참고 자료 전용**
    # 법정동코드로 받아 온 매매 실거래가를 임대료로 환산해 심의표에 참고로 싣는다.
    # 판정에는 넣지 않는다: 매매가는 층·용도·전면 편차를 담지 못하고, 환산에 쓰는
    # 연임대수익률이 미검증이다. 검증되지 않은 환산으로 보류를 만들면 실거래
    # 데이터가 있는 지역의 후보지만 근거 없이 불리해진다.
    "상업용_연임대수익률": (0.045, ESTIMATED,
                     "지역 매매 시세를 기대 임대료로 환산할 때 쓰는 연 수익률. "
                     "판정에는 쓰이지 않고 참고 표시에만 쓴다"),
    "시세대조_최소건수": (5, ESTIMATED,
                   "지역 실거래가 이 건수 미만이면 대조하지 않는다. "
                   "표본이 적으면 중앙값이 한두 건에 끌려다닌다. 판정 미사용"),

    # M6
    "재적합_MAPE": (0.20, DERIVED, "MAPE 가 이 값을 넘는 건이 3연속이면 재적합"),
    "재적합_연속건수": (3, DERIVED, "명세 고정"),
}


def c(name: str) -> float:
    """계수 값. 이름이 없으면 즉시 실패한다 — 오타로 0 이 흘러드는 것을 막는다."""
    if name not in COEFFICIENTS:
        raise KeyError(f"등록되지 않은 계수: {name}")
    return COEFFICIENTS[name][0]


def unvalidated() -> list[tuple[str, float, str]]:
    """미검증(ESTIMATED) 계수 목록 — 리포트 말미에 그대로 싣는다."""
    return [(k, v[0], v[2]) for k, v in COEFFICIENTS.items() if v[1] == ESTIMATED]


# ── 콘솔 입력값 덮어쓰기 ──────────────────────────────────────────
# 심의 콘솔(app/)의 '계수' 탭에서 내보낸 계수.json 을 얹는다. 어떤 계수가 명세값이
# 아니라 사람이 넣은 값인지가 심의에서 제일 중요하므로, 덮어쓴 항목은 OVERRIDDEN 에
# 남겨 리포트가 그대로 싣는다.
OVERRIDDEN: dict[str, tuple[float, float]] = {}   # 이름 -> (명세값, 입력값)


def apply_overrides(path) -> dict:
    """계수.json 을 읽어 레지스트리에 얹는다. 파일이 없으면 아무것도 하지 않는다.

    반환: {"계수": [...], "브랜드티어가중": [...], "ModeB배점": [...], "운영": {...}}
    운영 항목은 설정.yaml 소관이라 여기서 병합하지 않고 그대로 돌려준다
    (pipeline.load_all 이 설정에 얹는다).
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"계수 파일을 읽지 못했습니다: {p} — {e}")

    applied = {"계수": [], "브랜드티어가중": [], "ModeB배점": [], "운영": data.get("운영", {}) or {}}

    for name, value in (data.get("계수") or {}).items():
        if name not in COEFFICIENTS:
            raise SystemExit(f"등록되지 않은 계수: {name} ({p})")
        old, state, desc = COEFFICIENTS[name]
        COEFFICIENTS[name] = (float(value), state, desc)
        OVERRIDDEN[name] = (old, float(value))
        applied["계수"].append(name)

    for tier, value in (data.get("브랜드티어가중") or {}).items():
        if tier not in BRAND_TIER_WEIGHT:
            raise SystemExit(f"등록되지 않은 브랜드 티어: {tier} ({p})")
        old = BRAND_TIER_WEIGHT[tier]
        BRAND_TIER_WEIGHT[tier] = float(value)          # 참조 유지를 위해 제자리 수정
        OVERRIDDEN[f"브랜드티어가중.{tier}"] = (old, float(value))
        applied["브랜드티어가중"].append(tier)

    for axis, items in (data.get("ModeB배점") or {}).items():
        if axis not in MODE_B_WEIGHTS:
            raise SystemExit(f"등록되지 않은 배점 축: {axis} ({p})")
        for key, value in (items or {}).items():
            if key not in MODE_B_WEIGHTS[axis]:
                raise SystemExit(f"등록되지 않은 배점 항목: {axis}.{key} ({p})")
            old = MODE_B_WEIGHTS[axis][key]
            MODE_B_WEIGHTS[axis][key] = float(value)
            OVERRIDDEN[f"ModeB배점.{axis}.{key}"] = (old, float(value))
            applied["ModeB배점"].append(f"{axis}.{key}")

    # 운영 계수는 설정.yaml 소관이라 여기서 병합하지 않지만, 사람이 넣은 값이라는
    # 사실은 똑같이 남겨야 한다 — 명세값 자리는 설정 파일이 쥐고 있으므로 병합하는
    # 쪽(pipeline.merge_ops)이 채운다.
    return applied


def overridden() -> list[tuple[str, float, float]]:
    """콘솔에서 입력해 명세값을 대체한 계수 — (이름, 명세값, 입력값)."""
    return [(k, v[0], v[1]) for k, v in OVERRIDDEN.items()]


# ── M3 브랜드 티어 가중 (교차탄력) ────────────────────────────────
# 실증 근거가 아닌 실무 판단값이다.
BRAND_TIER_WEIGHT = {
    "동일가격대": 1.0,
    "저가형": 0.6,
    "스페셜티": 0.4,
    "비커피": 0.3,
}
TIER_UNVALIDATED = True

# 상호에서 티어를 추정할 때 쓰는 사전. 현장 실사로 티어를 직접 채우는 것이 우선이고,
# 이 사전은 비어 있는 칸을 메우는 폴백이다.
TIER_BY_BRAND = {
    "메가": "저가형", "컴포즈": "저가형", "빽다방": "저가형", "더벤티": "저가형",
    "감성커피": "저가형", "매머드": "저가형", "이디야": "저가형",
    "스타벅스": "동일가격대", "투썸": "동일가격대", "할리스": "동일가격대",
    "커피빈": "동일가격대", "엔제리너스": "동일가격대",
    "블루보틀": "스페셜티", "폴바셋": "스페셜티", "테라로사": "스페셜티",
    "파리바게뜨": "비커피", "뚜레쥬르": "비커피", "설빙": "비커피",
}


def tier_of(brand: str, given: str = "") -> str:
    """현장 실사로 적어 넣은 티어가 있으면 그것을 쓰고, 없으면 상호로 추정한다."""
    g = (given or "").strip()
    if g in BRAND_TIER_WEIGHT:
        return g
    name = brand or ""
    for key, tier in TIER_BY_BRAND.items():
        if key in name:
            return tier
    return "동일가격대"   # 모르면 가장 세게 경쟁한다고 본다(보수적)


# ── M4 Mode B 배점 (수요 40 · 접근성 30 · 경쟁 20 · 비용계약 10) ──
# 실증 회귀가 아닌 임의 설정값. 후보지 간 **상대 비교용**으로만 유효하다.
MODE_B_WEIGHTS = {
    "수요": {
        "배후주거세대": 10,
        "직장인구": 10,
        "오전유동": 15,
        "주말야간유입": 5,
    },
    "접근성": {
        "출근동선방향": 10,
        "코너전면가시성": 8,
        "1층접근성": 7,
        "주차정차": 5,
    },
    "경쟁": {
        "동일티어밀도": 8,
        "저가브랜드밀집": 7,
        "유효상권잔존율": 5,
    },
    "비용계약": {
        "임대료대비객수효율": 5,
        "계약조건": 5,
    },
}
MODE_B_UNVALIDATED = True


def axis_total(axis: str) -> int:
    return sum(MODE_B_WEIGHTS[axis].values())


def weights_flat() -> dict[str, int]:
    out = {}
    for axis, items in MODE_B_WEIGHTS.items():
        for k, v in items.items():
            out[k] = v
    return out


# ── M5 치명 플래그 (1건이라도 해당하면 즉시 부결) ─────────────────
FATAL_FLAGS = [
    ("근저당_과다", "등기부상 근저당 과다 또는 선순위 권리로 보증금 회수 불확실"),
    ("임대인_불일치", "임대인이 실소유자와 불일치 (전대차 구조·자기거래 정황)"),
    ("소송_계류", "소송·명도 분쟁 계류 중인 물건"),
    ("인허가_불가", "용도지역·정화조 용량 등으로 휴게음식점 인허가 불가"),
]
FATAL_KEYS = [k for k, _ in FATAL_FLAGS]

VERDICTS = ("통과", "보류", "부결")
