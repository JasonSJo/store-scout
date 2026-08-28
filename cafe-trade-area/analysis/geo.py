#!/usr/bin/env python3
"""
지오메트리 — 등시선 폴리곤 연산

상권 획정(M1)·격자 교차(M2)·중첩률(M5)에 쓰는 최소한의 지오메트리다.
shapely 를 쓰지 않는 이유는 두 가지다.

  1. 저장소가 표준 라이브러리 + PyYAML 만으로 돌아가야 한다.
  2. **같은 연산이 웹앱(app/js/geo.js)에도 있어야 하고 결과가 한 자리도
     달라선 안 된다.** 그래서 면적 교차 같은 어려운 연산은 정확한 기하
     알고리즘 대신 **고정 격자 표본**으로 푼다. 표본 격자는 전역 좌표에
     못 박혀 있어(anchored) 부동소수점 잡음과 무관하게 재현된다.

좌표는 전부 후보지 기준 로컬 평면(m)으로 투영해서 다룬다. 상권 규모(≤1km)
에서는 이 근사의 오차가 격자 표본 간격보다 훨씬 작다.
"""
from __future__ import annotations

import math

EARTH_R = 6371000.0
M_PER_DEG_LAT = 110540.0
LATTICE_STEP_M = 10.0      # 중첩률·격자 교차 표본 간격
CELL_SUB_N = 5             # 100m 격자 한 칸을 5×5 로 나눠 포함률을 잰다


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 사이 거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def m_per_deg_lon(lat0: float) -> float:
    return 111320.0 * math.cos(math.radians(lat0))


def project(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """(lat, lon) → 원점 (lat0, lon0) 기준 로컬 평면 좌표 (x=동쪽 m, y=북쪽 m)."""
    return ((lon - lon0) * m_per_deg_lon(lat0), (lat - lat0) * M_PER_DEG_LAT)


def to_local(ring: list, lat0: float, lon0: float) -> list[tuple[float, float]]:
    """GeoJSON 링([[lon, lat], ...]) → 로컬 평면 좌표 목록."""
    return [project(lat0, lon0, float(p[1]), float(p[0])) for p in ring]


def shoelace_area(poly) -> float:
    """단순 폴리곤 면적(m²). 방향과 무관하게 양수."""
    if isinstance(poly, dict):
        poly = poly["poly"]
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def prepare(poly: list[tuple[float, float]]) -> dict:
    """폴리곤 사전 처리 — 격자 수천 칸을 훑기 전에 한 번만 계산한다.

    내접반지름 r_in(원점에서 각 변까지 최단거리)과 외접반지름 r_out 을 미리 재 두면,
    격자 한 칸이 명백히 안이거나 명백히 밖일 때 부분표본 25회를 통째로 건너뛴다.
    등시선은 원점(후보지) 둘레의 star-shaped 폴리곤이라 이 판정이 성립한다.
    """
    n = len(poly)
    r_out = max((math.hypot(x, y) for x, y in poly), default=0.0)
    r_in = float("inf")
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        seg = dx * dx + dy * dy
        if seg == 0:
            d = math.hypot(x1, y1)
        else:
            t = max(0.0, min(1.0, -(x1 * dx + y1 * dy) / seg))
            d = math.hypot(x1 + t * dx, y1 + t * dy)
        r_in = min(r_in, d)
    return {"poly": poly, "bbox": bbox(poly),
            "r_in": 0.0 if r_in == float("inf") else r_in, "r_out": r_out}


def bbox(poly) -> tuple[float, float, float, float]:
    if isinstance(poly, dict):
        return poly["bbox"]
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_poly(x: float, y: float, poly) -> bool:
    """레이 캐스팅. 경계 위의 점은 어느 쪽으로 떨어져도 무방하다(표본이므로)."""
    if isinstance(poly, dict):
        p = poly
        d = math.hypot(x, y)
        if d <= p["r_in"]:
            return True
        if d >= p["r_out"]:
            return False
        poly = p["poly"]
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xc = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xc:
                inside = not inside
        j = i
    return inside


def lattice(poly, step: float = LATTICE_STEP_M):
    """폴리곤 bbox 를 덮는 표본점. 전역 격자에 못 박아 재현성을 보장한다."""
    x0, y0, x1, y1 = poly["bbox"] if isinstance(poly, dict) else bbox(poly)
    ix0, iy0 = math.ceil(x0 / step), math.ceil(y0 / step)
    ix1, iy1 = math.floor(x1 / step), math.floor(y1 / step)
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            yield (ix * step, iy * step)


def sampled_area(poly, step: float = LATTICE_STEP_M) -> float:
    """표본 기반 면적(m²). shoelace 와 비교해 표본 밀도를 검증할 때 쓴다."""
    n = sum(1 for x, y in lattice(poly, step) if point_in_poly(x, y, poly))
    return n * step * step


def overlap_ratio(a, b, step: float = LATTICE_STEP_M) -> float:
    """area(a ∩ b) ÷ area(a). 분자·분모를 같은 표본으로 세어 자기일관적이다.

    bbox 가 겹치지 않으면 표본을 한 점도 찍지 않고 0 을 돌려준다 — 실제로는
    대부분의 점포 쌍이 멀리 떨어져 있어 이 조기 탈출이 대부분을 처리한다.
    """
    ax0, ay0, ax1, ay1 = a["bbox"] if isinstance(a, dict) else bbox(a)
    bx0, by0, bx1, by1 = b["bbox"] if isinstance(b, dict) else bbox(b)
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return 0.0
    inside_a = 0
    inside_both = 0
    for x, y in lattice(a["poly"] if isinstance(a, dict) else a, step):
        if not point_in_poly(x, y, a):
            continue
        inside_a += 1
        if point_in_poly(x, y, b):
            inside_both += 1
    return inside_both / inside_a if inside_a else 0.0


def cell_coverage(cx: float, cy: float, size: float,
                  poly, n: int = CELL_SUB_N) -> float:
    """정사각 격자 한 칸(중심 cx, cy · 한 변 size)이 폴리곤에 덮인 면적비 0~1.

    격자 인구를 등시선으로 자를 때(M2) 쓴다. n×n 부분표본이라 해상도는
    1/n² 단위지만, 100m 격자·n=5 면 4% 단위로 충분히 매끄럽다.
    prepare() 결과를 넘기면 명백히 안/밖인 칸을 표본 없이 즉시 판정한다.
    """
    if isinstance(poly, dict):
        p = poly
        poly = p["poly"]
        d = math.hypot(cx, cy)
        half_diag = size * 0.7071067811865476        # size/2 × √2
        if d + half_diag <= p["r_in"]:
            return 1.0
        if d - half_diag >= p["r_out"]:
            return 0.0
    hit = 0
    for i in range(n):
        for j in range(n):
            px = cx - size / 2 + size * (i + 0.5) / n
            py = cy - size / 2 + size * (j + 0.5) / n
            if point_in_poly(px, py, poly):
                hit += 1
    return hit / (n * n)


def circle_poly(radius_m: float, n: int = 72) -> list[tuple[float, float]]:
    """원점 중심 원 폴리곤(로컬 평면). 등시선이 없을 때의 열화 폴백."""
    return [(radius_m * math.cos(2 * math.pi * k / n),
             radius_m * math.sin(2 * math.pi * k / n)) for k in range(n)]


def centroid(poly) -> tuple[float, float]:
    if isinstance(poly, dict):
        poly = poly["poly"]
    n = len(poly)
    if n == 0:
        return (0.0, 0.0)
    return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
