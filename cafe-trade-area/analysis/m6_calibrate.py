#!/usr/bin/env python3
"""
M6 · 사후 보정 루프

개점 후 6개월·12개월 실매출을 받아 다음을 갱신한다.

  1. 예측 오차 MAPE 기록 → 20% 초과가 3건 연속이면 모델 재적합
  2. λ(거리 마찰계수) 재추정
  3. Mode B → Mode A 전환 조건 확인 (유효 표본 15개)
  4. 방향성 보정 계수(0.3), 잠식 계수 κ(0.5) 실측 교정

**이 루프가 없으면 M4 Mode B 는 순환논리를 벗어날 수 없다.**

계수는 **자동 적용하지 않는다.** 제안서(보정_제안.md / .yaml)를 내고 사람이
config.py 에 반영한다. 심의 기준이 아무도 모르게 바뀌는 것이 더 위험하다.

입력: 실적.csv
  점포명,개점일,심의시_예측_중앙_만원,6개월_월매출_만원,12개월_월매출_만원,
  인접자사점,인접_overlap,인접_개점전_월매출_만원,인접_개점후_월매출_만원
"""
from __future__ import annotations

from common import read_csv, to_f
from config import c


def actual(row: dict) -> float:
    """12개월치가 있으면 그것을, 없으면 6개월치를 실적으로 본다."""
    v12 = to_f(row.get("12개월_월매출_만원"))
    return v12 if v12 > 0 else to_f(row.get("6개월_월매출_만원"))


def error_log(rows: list[dict]) -> dict:
    """개점일 순으로 예측 오차를 기록하고 재적합 트리거를 판정한다."""
    recs = []
    for r in rows:
        a, pred = actual(r), to_f(r.get("심의시_예측_중앙_만원"))
        if a <= 0 or pred <= 0:
            continue
        recs.append({
            "점포명": (r.get("점포명") or "").strip(),
            "개점일": (r.get("개점일") or "").strip(),
            "예측": pred, "실적": a,
            "오차율": (pred - a) / a,
            "APE": abs(pred - a) / a,
        })
    recs.sort(key=lambda x: x["개점일"])

    limit = c("재적합_MAPE")
    need = int(c("재적합_연속건수"))
    run = best = 0
    for x in recs:
        run = run + 1 if x["APE"] > limit else 0
        best = max(best, run)

    mape = sum(x["APE"] for x in recs) / len(recs) if recs else None
    bias = sum(x["오차율"] for x in recs) / len(recs) if recs else None
    return {
        "기록": recs, "MAPE": mape, "편향": bias,
        "연속초과_최대": best, "현재_연속초과": run,
        "재적합_필요": best >= need,
        "임계": limit, "연속기준": need,
    }


def recalibrate_lambda(mape_of_lambda, grid=None) -> dict:
    """λ 격자탐색. mape_of_lambda(λ) 는 그 λ 로 파이프라인을 다시 돌린 CV MAPE.

    좁은 격자를 훑는 단순 탐색이다. 표본이 수십 개인 단계에서 정교한 최적화는
    과적합만 부른다.
    """
    grid = grid or [1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]
    scored = []
    for lam in grid:
        m = mape_of_lambda(lam)
        if m is not None:
            scored.append({"λ": lam, "MAPE": m})
    if not scored:
        return {"실패": "λ 후보 전부에서 MAPE 를 계산하지 못했습니다(표본 부족)."}
    best = min(scored, key=lambda x: x["MAPE"])
    cur = c("거리마찰_람다")
    now = next((x["MAPE"] for x in scored if abs(x["λ"] - cur) < 1e-9), None)
    return {
        "격자": scored, "현재_λ": cur, "현재_MAPE": now,
        "제안_λ": best["λ"], "제안_MAPE": best["MAPE"],
        "개선": (now - best["MAPE"]) if now is not None else None,
    }


def recalibrate_kappa(rows: list[dict]) -> dict:
    """κ 실측 = 실제 잠식액 ÷ (overlap × 개점전 인접점 매출).

    개점 전후 인접 자사점 매출이 둘 다 있는 건만 쓴다. 계절성·전사 추세를
    걷어내지 않은 값이므로 참고치이며, 건수가 적으면 신뢰하지 않는다.
    """
    obs = []
    for r in rows:
        ov = to_f(r.get("인접_overlap"))
        before = to_f(r.get("인접_개점전_월매출_만원"))
        after = to_f(r.get("인접_개점후_월매출_만원"))
        if ov <= 0 or before <= 0 or after <= 0:
            continue
        drop = before - after
        if drop <= 0:
            obs.append({"점포명": r.get("점포명"), "κ": 0.0, "감소": drop,
                        "overlap": ov, "비고": "감소 없음"})
            continue
        obs.append({"점포명": r.get("점포명"), "κ": drop / (ov * before),
                    "감소": drop, "overlap": ov, "비고": ""})
    if not obs:
        return {"실패": "개점 전후 인접 자사점 매출이 있는 건이 없습니다 — κ 교정 불가.",
                "필요항목": ["인접자사점", "인접_overlap",
                          "인접_개점전_월매출_만원", "인접_개점후_월매출_만원"]}
    ks = sorted(x["κ"] for x in obs)
    med = ks[len(ks) // 2] if len(ks) % 2 else (ks[len(ks) // 2 - 1] + ks[len(ks) // 2]) / 2
    return {"관측": obs, "현재_κ": c("잠식계수_카파"), "제안_κ": med, "표본수": len(obs),
            "주의": "계절성·전사 추세 미보정 값입니다. 표본이 5건 미만이면 반영을 보류하십시오."}


def mode_switch(valid_samples: int) -> dict:
    need = int(c("ModeA_최소표본"))
    return {
        "유효표본": valid_samples, "필요": need,
        "ModeA_가능": valid_samples >= need,
        "남은표본": max(0, need - valid_samples),
    }


def crossing_resistance_status(rows: list[dict]) -> dict:
    """횡단저항(0.3) 교정 가능 여부. 필요한 실측 항목이 없으면 그 사실을 명시한다."""
    have = sum(1 for r in rows if to_f(r.get("실측_같은편_오전")) > 0
               and to_f(r.get("실측_반대편_오전")) > 0)
    if have < 3:
        return {"교정불가": True, "확보": have,
                "필요항목": ["실측_같은편_오전", "실측_반대편_오전"],
                "안내": "07~09시 현장 통행량을 도로 좌·우로 나눠 센 실측치가 최소 3건 "
                       "필요합니다. 이 값 없이는 횡단저항 0.3 이 계속 미검증으로 남습니다."}
    return {"교정불가": False, "확보": have,
            "안내": "실측 표본이 확보되었습니다. 회귀에 좌·우 유동을 따로 넣어 "
                   "계수비로 횡단저항을 추정하십시오."}


def proposal(err: dict, lam: dict, kap: dict, sw: dict, cross: dict) -> dict:
    """사람이 검토할 계수 변경 제안. 자동 적용하지 않는다."""
    changes = {}
    if "제안_λ" in lam and lam.get("개선") is not None and lam["개선"] > 0.005:
        changes["거리마찰_람다"] = lam["제안_λ"]
    if "제안_κ" in kap and kap.get("표본수", 0) >= 5:
        changes["잠식계수_카파"] = round(kap["제안_κ"], 3)
    if err.get("MAPE") is not None:
        changes["ModeB_예측구간_폭"] = round(err["MAPE"], 3)
    return {
        "변경제안": changes,
        "재적합_필요": err.get("재적합_필요", False),
        "ModeA_전환가능": sw["ModeA_가능"],
        "미교정": [x for x in ("횡단저항",) if cross.get("교정불가")],
    }
