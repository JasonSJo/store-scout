#!/usr/bin/env python3
"""
M1 · 상권 획정 (Isochrone)

등시선 폴리곤 P5(5분)·P10(10분)을 확보하고 잔존율 R 을 낸다.

    R = area(P10) ÷ (π × 667m²)          667m = 4km/h × 10분

**등시선 자체는 이 모듈이 만들지 않는다.** OSM 보행 네트워크와 barrier 처리
(횡단보도 없는 6차선 이상·하천·철로·옹벽·경사 10% 초과)가 필요한 작업이라
파이프라인 밖에서 생성해 GeoJSON 으로 넣는다. 경로는 셋이다.

  1) `--iso 파일.geojson`      사전 생성된 등시선 (권장)
  2) `fetch_isochrones.py --live`  라우팅 API 로 생성 (barrier 는 API 설정에 의존)
  3) 폴백                       등시선이 없으면 원으로 대체하고 **열화 표시**

3번은 명세가 반경법 대비 오차 흡수의 핵심이라고 지목한 단계를 통째로 건너뛰는
것이므로, 결과물 전체에 경고가 따라붙고 심의에서 그대로 노출된다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import geo
from config import c

P5, P10 = "P5", "P10"
IDEAL_R = c("P10_이상반경_m")
IDEAL_AREA = math.pi * IDEAL_R ** 2
# 5분 등시선의 이상 반경 — 폴백에서만 쓴다
IDEAL_R5 = IDEAL_R / 2


def load_isochrones(path: Path) -> dict:
    """GeoJSON FeatureCollection → {(대상, 구간): [[lon, lat], ...]}

    각 Feature 의 properties 에 `대상`(후보지명 또는 점포명)과 `구간`(P5|P10)이 있어야 한다.
    """
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for f in data.get("features", []):
        pr = f.get("properties", {}) or {}
        name = str(pr.get("대상", "")).strip()
        band = str(pr.get("구간", "")).strip()
        gm = f.get("geometry", {}) or {}
        if not name or band not in (P5, P10) or gm.get("type") != "Polygon":
            continue
        rings = gm.get("coordinates") or []
        if rings:
            out[(name, band)] = rings[0]      # 외곽 링만 사용(홀 미지원)
    return out


def resolve(name: str, lat: float, lon: float, isos: dict, fallback_R: float = 0.0) -> dict:
    """한 대상의 P5·P10 을 로컬 평면 폴리곤으로 확정하고 R 을 계산한다.

    fallback_R: 등시선이 없을 때 현장 판단으로 넣는 잔존율(0~1). 이 값으로
    원의 면적을 깎아 흉내내지만, 어디까지나 열화 경로다.
    """
    warn = []
    have = (name, P10) in isos and (name, P5) in isos

    if have:
        p10 = geo.to_local(isos[(name, P10)], lat, lon)
        p5 = geo.to_local(isos[(name, P5)], lat, lon)
        source = "등시선"
    else:
        r = float(fallback_R) if fallback_R else 1.0
        r = max(0.05, min(1.0, r))
        # 면적을 R 배로 깎으려면 반지름은 √R 배
        p10 = geo.circle_poly(IDEAL_R * math.sqrt(r))
        p5 = geo.circle_poly(IDEAL_R5 * math.sqrt(r))
        source = "열화폴백"
        warn.append("⛔ 등시선 없음 — 원형 반경으로 대체했습니다. "
                    "명세상 오차 흡수의 핵심 단계(M1)를 건너뛴 상태이며 "
                    "단절 요소(6차선·하천·철로·경사)가 전혀 반영되지 않았습니다.")
        if not fallback_R:
            warn.append("⚠ 잔존율 R 도 미입력이라 1.0(이상 원형)으로 가정했습니다 — "
                        "실제보다 상권이 넓게 잡힙니다.")

    p10 = geo.prepare(p10)
    p5 = geo.prepare(p5)
    area10 = geo.shoelace_area(p10)
    R = area10 / IDEAL_AREA
    if source == "등시선" and R > 1.02:
        warn.append(f"⚠ 잔존율 R={R:.2f} 이 1 을 넘습니다 — 등시선 생성 시 "
                    f"보행속도나 시간 설정을 확인하십시오.")
    if R < 0.25:
        warn.append(f"⚠ 잔존율 R={R:.2f} — 단절이 심한 상권입니다. "
                    f"반경 안이어도 도달하지 못하는 면적이 큽니다.")

    return {
        "대상": name, "위도": lat, "경도": lon,
        "P5": p5, "P10": p10,
        "P5_면적_m2": geo.shoelace_area(p5), "P10_면적_m2": area10,
        "R": R, "출처": source, "경고": warn,
    }


def overlap_with(base: dict, other_name: str, other_lat: float, other_lon: float,
                 isos: dict, other_fallback_R: float = 0.0) -> float:
    """base 후보지 P10 중 다른 점포 P10 과 겹치는 면적 비율 (M5 카니발라이제이션 입력).

    두 폴리곤을 **base 의 원점 기준** 로컬 평면으로 맞춰 놓고 잰다.
    """
    other = resolve(other_name, other_lat, other_lon, isos, other_fallback_R)
    dx, dy = geo.project(base["위도"], base["경도"], other_lat, other_lon)
    shifted = geo.prepare([(x + dx, y + dy) for x, y in other["P10"]["poly"]])
    return geo.overlap_ratio(base["P10"], shifted)


def summary(a: dict) -> str:
    return (f"{a['대상']}: P10 {a['P10_면적_m2'] / 10000:,.1f}ha · "
            f"R={a['R']:.2f} · 출처={a['출처']}")
