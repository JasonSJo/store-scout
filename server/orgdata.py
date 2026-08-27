#!/usr/bin/env python3
"""
조직 데이터 → 파이프라인 입력

이 모듈이 제품의 실질이다. 여기가 없으면 모든 조직이 예시 데이터로 심의를 받는다 —
화면만 격리되고 **판정은 남의 브랜드 숫자로 나온다.**

  기존점(stores)  → 기존점.csv   M4 회귀 표본 · Mode B 앵커
  설정(org_settings) → 설정.yaml  변동비·고정비·브랜드 티어
"""
from __future__ import annotations

import csv
import io
import json

import yaml

# 파이프라인의 기존점.csv 열 순서
STORE_COLS = ["점포명", "주소", "위도", "경도", "개점일", "기준점포", "월매출_만원",
              "일매출_만원", "전용면적_평", "좌석수", "층", "코너여부", "전면폭_m",
              "주차가능대수", "정차가능", "도로변", "방향적합", "보증금_만원",
              "월임대료_만원", "관리비_만원", "권리금_만원", "계약조건점수",
              "잔존율_R", "비고"]

기본설정 = {
    "브랜드": "", "자사브랜드티어": "동일가격대", "좌석수_기본": 24,
    "영업일수": 30, "보행네트워크": False,
    "운영": {
        "변동비": {"원재료율": 0.35, "로열티율": 0.03,
                 "광고분담금율": 0.01, "기타변동비율": 0.022},
        "고정비": {"고정인건비_월_만원": 620, "기타_월_만원": 170},
    },
    # 상담의 운영 형태 → 고정인건비를 통째로 바꾼다. 상담에서 받는 값 중 판정을
    # 가장 크게 움직인다. 표는 analysis/설정.example.yaml 과 같아야 한다 —
    # 갈리면 상담사가 화면에서 본 숫자와 파이프라인이 쓴 숫자가 달라진다.
    "운영형태": {
        "오토": {"고정인건비_월_만원": 980,
               "설명": "점주 미근무 — 전 시간대를 고용으로 채운다"},
        "점주+알바": {"고정인건비_월_만원": 620,
                  "설명": "점주가 주간을 맡고 나머지를 알바로 채운다 (기본값)"},
        "점주": {"고정인건비_월_만원": 260, "설명": "점주 단독 — 피크 시간만 알바"},
    },
    # 투자금 형태 → 월 금융비용이 고정비 '기타' 에 더해진다.
    # 대출 원금을 (보증금+권리금)으로 잡는 것은 시설자금·운전자금이 빠진 과소 추정이다.
    "투자금형태": {
        "현금": {"대출비율": 0.0, "연금리": 0.0, "리스_월_만원": 0,
               "설명": "차입 없음 — 월 금융비용 0"},
        "현금+대출": {"대출비율": 0.5, "연금리": 0.06, "리스_월_만원": 0,
                  "설명": "투자금의 절반을 차입한다고 가정"},
        "현금+대출+리스": {"대출비율": 0.5, "연금리": 0.06, "리스_월_만원": 45,
                     "설명": "차입에 더해 기기 리스료가 매월 붙는다"},
    },
    # 상담 조건으로 후보지를 거르는 기준. 알고리즘이 아니라 **필터**다 —
    # 여기서 걸러진 물건은 아예 심의에 올라오지 않는다.
    "상담필터": {"평수_허용오차": 0.3, "투자금_초과허용": 0.1},
    # 상담 기록의 개인정보 보관기간. 지나면 파기 대상으로 표시한다.
    "개인정보": {"보관개월": 12},
    "거버넌스": {
        "문서등급": "사내 한정 · 대외 배포 금지",
        "고지": ("본 산출물은 내부 의사결정 자료입니다. 가맹희망자에게 제공하는 "
               "예상매출액 산정서와 수치를 혼용하지 마십시오."),
    },
}


def load_settings(con, org_id: int) -> dict:
    row = con.execute("SELECT data FROM org_settings WHERE org_id = ?", (org_id,)).fetchone()
    saved = json.loads(row["data"]) if row and row["data"] else {}
    return merge(기본설정, saved)


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def save_settings(con, org_id: int, data: dict) -> None:
    con.execute(
        "INSERT INTO org_settings (org_id, data) VALUES (?,?) "
        "ON CONFLICT(org_id) DO UPDATE SET data=excluded.data, updated_at=datetime('now')",
        (org_id, json.dumps(data, ensure_ascii=False)))


def settings_yaml(con, org_id: int) -> str:
    return yaml.safe_dump(load_settings(con, org_id), allow_unicode=True, sort_keys=False)


def stores_csv(con, org_id: int) -> str:
    """조직의 기존점을 파이프라인이 먹는 CSV 로. 일매출은 월매출에서 나눈다."""
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM stores WHERE org_id = ? ORDER BY id", (org_id,))]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=STORE_COLS)
    w.writeheader()
    for r in rows:
        월 = r.get("월매출_만원")
        w.writerow({c: ("" if r.get(c) is None else r.get(c, "")) for c in STORE_COLS}
                   | {"일매출_만원": round(월 / 30, 2) if 월 else ""})
    return buf.getvalue()


def readiness(con, org_id: int) -> dict:
    """온보딩이 끝났는가. 끝나지 않았으면 무엇이 남았는지 말한다."""
    rows = [dict(r) for r in con.execute(
        "SELECT 기준점포, 월매출_만원, 위도, 경도 FROM stores WHERE org_id = ?", (org_id,))]
    실매출 = [r for r in rows if (r["월매출_만원"] or 0) > 0]
    좌표 = [r for r in 실매출 if r["위도"] and r["경도"]]
    기준 = [r for r in 좌표 if str(r["기준점포"]).upper().startswith(("Y", "예", "O"))]
    st = load_settings(con, org_id)
    브랜드 = bool(str(st.get("브랜드", "")).strip())

    할일 = []
    if not 브랜드:
        할일.append(("설정", "브랜드 이름을 넣으십시오", "/settings"))
    if len(좌표) < 2:
        할일.append(("기존점", f"실매출과 좌표가 있는 기존점이 {len(좌표)}곳입니다 — "
                            f"최소 2곳이 필요합니다", "/stores"))
    elif not 기준:
        할일.append(("기존점", "기준점포를 1곳 이상 지정하십시오 — "
                            "Mode B 앵커링이 이것으로 성립합니다", "/stores"))
    return {
        "기존점": len(rows), "실매출": len(실매출), "좌표": len(좌표), "기준점포": len(기준),
        "브랜드": 브랜드, "할일": 할일, "준비됨": not 할일,
        "모드": "A(회귀)" if len(좌표) >= 15 else ("B(앵커링)" if 기준 else "—"),
    }
