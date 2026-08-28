#!/usr/bin/env python3
"""
예시 데이터 생성기 — 합성 데이터임을 분명히 하기 위한 도구

명세가 요구하는 입력(등시선·100m 격자인구·시간대별 유동인구·경쟁점 티어·
기존점 실매출)은 서로 맞물려 있어서 손으로 적으면 반드시 어긋난다. 그래서
**하나의 생성기가 전부 만든다.** 생성기를 커밋해 두는 이유는 이 데이터가
실측이 아니라 합성이라는 사실을 코드로 남기기 위해서다.

  python3 make_fixtures.py

기존점 실매출은 '참 모델'에서 만들고 로그정규 잡음을 얹는다. 그래야 Mode A
회귀가 복원할 대상이 실제로 존재하고, MAPE 가 현실적인 크기(10~20%)로 나온다.
실제 데이터로 교체할 때는 같은 열 이름만 맞추면 된다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# (이름, 위도, 경도, 유형, 잔존율기준, 경쟁밀도)
#   유형: office / retail / resi / campus / mixed
CANDIDATES = [
    ("성수 연무장길", 37.5445, 127.0557, "mixed",  0.62, 30),
    ("강남역 11번출구", 37.4979, 127.0276, "office", 0.55, 58),
    ("목동 7단지 상가", 37.5262, 126.8752, "resi",   0.74, 12),
    ("홍대 어울마당로", 37.5572, 126.9245, "retail", 0.58, 71),
    ("판교 유스페이스", 37.4020, 127.1086, "office", 0.66, 33),
    ("신림 별빛거리", 37.4842, 126.9296, "campus", 0.52, 44),
]

STORES = [
    ("카페하다 왕십리점", 37.5613, 127.0380, "mixed",  0.60, 26),
    ("카페하다 역삼점", 37.5006, 127.0364, "office", 0.57, 49),
    ("카페하다 서초점", 37.4837, 127.0324, "office", 0.61, 38),
    ("카페하다 잠실새내점", 37.5114, 127.0864, "retail", 0.59, 41),
    ("카페하다 건대입구점", 37.5405, 127.0700, "campus", 0.54, 52),
    ("카페하다 상암점", 37.5796, 126.8893, "office", 0.70, 21),
    ("카페하다 여의도점", 37.5216, 126.9243, "office", 0.63, 35),
    ("카페하다 종로3가점", 37.5704, 126.9917, "mixed",  0.50, 47),
    ("카페하다 사당점", 37.4765, 126.9816, "mixed",  0.56, 39),
    ("카페하다 노원점", 37.6542, 127.0568, "resi",   0.72, 24),
    ("카페하다 수유점", 37.6377, 127.0255, "resi",   0.69, 22),
    ("카페하다 화곡점", 37.5416, 126.8404, "resi",   0.75, 18),
    ("카페하다 부천중동점", 37.5035, 126.7660, "retail", 0.68, 27),
    ("카페하다 분당서현점", 37.3853, 127.1234, "mixed",  0.71, 29),
    ("카페하다 안양범계점", 37.3894, 126.9506, "retail", 0.67, 31),
    ("카페하다 일산라페스타점", 37.6584, 126.7699, "retail", 0.73, 25),
]

# 유형별 배후 성격 (세대수, 직장인구) 격자 한 칸 기준 대략치
PROFILE = {
    "office": (14, 210), "retail": (34, 85), "resi": (58, 22),
    "campus": (46, 40),  "mixed":  (30, 95),
}
RIVAL_BRANDS = [("메가MGC커피", "저가형"), ("컴포즈커피", "저가형"), ("빽다방", "저가형"),
                ("더벤티", "저가형"), ("매머드커피", "저가형"), ("이디야커피", "저가형"),
                ("스타벅스", "동일가격대"), ("투썸플레이스", "동일가격대"),
                ("할리스커피", "동일가격대"), ("커피빈", "동일가격대"),
                ("폴바셋", "스페셜티"), ("블루보틀", "스페셜티"),
                ("파리바게뜨", "비커피"), ("뚜레쥬르", "비커피")]

M_LAT = 110540.0


def rng(*parts) -> random.Random:
    """이름으로 시드를 만든다 — 파이썬 hash() 는 실행마다 달라져 쓸 수 없다."""
    h = hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def m_lon(lat):
    return 111320.0 * math.cos(math.radians(lat))


def offset(lat, lon, dx, dy):
    return (lat + dy / M_LAT, lon + dx / m_lon(lat))


# ── 등시선 ────────────────────────────────────────────────────────
def isochrone(name, lat, lon, radius, R_target, band):
    """방사형 반경을 각도별로 흔들고 일부 섹터를 잘라 barrier(하천·철로·대로)를 흉내낸다."""
    r = rng(name, band, "iso")
    n = 72
    cuts = [(r.uniform(0, 2 * math.pi), r.uniform(0.35, 0.9)) for _ in range(r.randint(1, 3))]
    pts = []
    for k in range(n):
        th = 2 * math.pi * k / n
        f = 1.0 + 0.12 * math.sin(3 * th + r.random()) + r.uniform(-0.06, 0.06)
        for c_th, c_w in cuts:
            d = abs((th - c_th + math.pi) % (2 * math.pi) - math.pi)
            if d < c_w:
                f *= 0.34 + 0.66 * (d / c_w)     # 섹터 중심일수록 깊게 깎인다
        rr = radius * f
        la, lo = offset(lat, lon, rr * math.cos(th), rr * math.sin(th))
        pts.append([round(lo, 6), round(la, 6)])
    pts.append(pts[0])
    return pts


def scale_to_R(name, lat, lon, R_target, band, ideal):
    """목표 잔존율에 맞도록 반경을 이분탐색으로 맞춘다(면적 기준)."""
    import geo
    lo, hi = ideal * 0.3, ideal * 1.4
    for _ in range(24):
        mid = (lo + hi) / 2
        ring = isochrone(name, lat, lon, mid, R_target, band)
        local = geo.to_local(ring, lat, lon)
        R = geo.shoelace_area(local) / (math.pi * 667.0 ** 2)
        if band == "P5":
            R *= 4      # P5 는 이상 면적의 1/4 기준으로 본다
        if R < R_target:
            lo = mid
        else:
            hi = mid
    return isochrone(name, lat, lon, (lo + hi) / 2, R_target, band)


def build_isochrones(all_locs):
    feats = []
    for name, lat, lon, kind, R, dens in all_locs:
        for band, ideal in (("P10", 667.0), ("P5", 333.5)):
            ring = scale_to_R(name, lat, lon, R, band, ideal)
            feats.append({
                "type": "Feature",
                "properties": {"대상": name, "구간": band, "생성": "합성(예시)"},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            })
    return {"type": "FeatureCollection",
            "properties": {"주의": "합성 예시 데이터입니다. 실제 OSM 보행 네트워크 등시선이 아닙니다."},
            "features": feats}


# ── 격자 인구 ─────────────────────────────────────────────────────
def build_cells(all_locs):
    seen, rows = set(), []
    for name, lat, lon, kind, R, dens in all_locs:
        base_h, base_w = PROFILE[kind]
        r = rng(name, "cells")
        for i in range(-7, 8):
            for j in range(-7, 8):
                clat, clon = offset(lat, lon, i * 100, j * 100)
                gid = f"G{round(clat * 10000)}_{round(clon * 10000)}"
                if gid in seen:
                    continue
                seen.add(gid)
                # 중심에서 멀수록 옅어진다
                fall = math.exp(-((i * i + j * j) ** 0.5) / 6.0)
                rows.append({
                    "격자ID": gid,
                    "중심위도": round(clat, 6), "중심경도": round(clon, 6),
                    "한변_m": 100,
                    "세대수": max(0, round(base_h * fall * r.uniform(0.55, 1.5))),
                    "직장인구": max(0, round(base_w * fall * r.uniform(0.5, 1.6))),
                })
    return rows


# ── 유동인구 ──────────────────────────────────────────────────────
def build_points(all_locs):
    rows = []
    for name, lat, lon, kind, R, dens in all_locs:
        r = rng(name, "foot")
        scale = {"office": 2.4, "retail": 2.0, "campus": 1.7, "mixed": 1.5, "resi": 0.7}[kind]
        for idx in range(4):
            dx, dy = r.uniform(-180, 180), r.uniform(-180, 180)
            plat, plon = offset(lat, lon, dx, dy)
            side = "A" if idx % 2 == 0 else "B"
            am = round(1600 * scale * r.uniform(0.6, 1.4))
            rows.append({"출처": "실측", "단위면적_m2": "",
                         "지점ID": f"{name}-{idx}", "위도": round(plat, 6), "경도": round(plon, 6),
                         "도로변": side, "시간대": "오전", "인원": am})
            rows.append({"출처": "실측", "단위면적_m2": "",
                         "지점ID": f"{name}-{idx}", "위도": round(plat, 6), "경도": round(plon, 6),
                         "도로변": side, "시간대": "전체", "인원": round(am * r.uniform(4.5, 6.5))})
            if idx == 0:
                rows.append({"출처": "실측", "단위면적_m2": "",
                         "지점ID": f"{name}-{idx}", "위도": round(plat, 6), "경도": round(plon, 6),
                             "도로변": side, "시간대": "주말",
                             "인원": round(am * r.uniform(0.8, 2.6))})
                rows.append({"출처": "실측", "단위면적_m2": "",
                         "지점ID": f"{name}-{idx}", "위도": round(plat, 6), "경도": round(plon, 6),
                             "도로변": side, "시간대": "야간",
                             "인원": round(am * r.uniform(0.3, 1.5))})
    return rows


# ── 경쟁점 ────────────────────────────────────────────────────────
def build_competitors(all_locs, store_names):
    rows, seen = [], set()
    for name, lat, lon, kind, R, dens in all_locs:
        r = rng(name, "comp")
        for k in range(dens):
            th = r.uniform(0, 2 * math.pi)
            rad = 600 * math.sqrt(r.random())
            clat, clon = offset(lat, lon, rad * math.cos(th), rad * math.sin(th))
            brand, tier = RIVAL_BRANDS[r.randrange(len(RIVAL_BRANDS))]
            label = f"{brand} {name.split()[0]}{k + 1}점"
            if label in seen:
                continue
            seen.add(label)
            rows.append({"상호": label, "브랜드": brand, "티어": tier,
                         "위도": round(clat, 6), "경도": round(clon, 6),
                         "좌석수": r.choice([12, 16, 20, 24, 30, 40, 55]), "자사": "N"})
    # 자사 기존점도 경쟁 지도 위에 올라가야 후보지가 자기 브랜드와도 경쟁한다
    for name, lat, lon, kind, R, dens in all_locs:
        if name in store_names:
            rows.append({"상호": name, "브랜드": "카페하다", "티어": "동일가격대",
                         "위도": lat, "경도": lon, "좌석수": 28, "자사": "Y"})
    return rows


# ── 후보지 · 기존점 속성 ──────────────────────────────────────────
def site_attrs(name, kind, dens, r):
    rent_base = {"office": 26, "retail": 22, "campus": 17, "mixed": 19, "resi": 12}[kind]
    area = r.choice([16, 18, 20, 22, 24, 26])
    return {
        "전용면적_평": area,
        "좌석수": r.choice([18, 22, 26, 30, 34]),
        "층": 1 if r.random() < 0.85 else 2,
        "코너여부": "Y" if r.random() < 0.42 else "N",
        "전면폭_m": round(r.uniform(4.0, 11.0), 1),
        "주차가능대수": r.choice([0, 0, 0, 2, 4, 8]),
        "정차가능": "Y" if r.random() < 0.5 else "N",
        "도로변": "A" if r.random() < 0.55 else "B",
        "방향적합": "Y" if r.random() < 0.5 else "N",
        "보증금_만원": round(area * rent_base * r.uniform(12, 18) / 10) * 10,
        "월임대료_만원": round(area * rent_base * r.uniform(0.85, 1.2)),
        "관리비_만원": round(area * r.uniform(0.8, 1.6)),
        "권리금_만원": round(r.uniform(0, 8000) / 100) * 100,
        "계약조건점수": r.choice([1, 2, 3, 3, 4, 5]),
    }


# ── 기존점 실매출 (참 모델 + 잡음) ────────────────────────────────
TRUE_BETA = {
    "logW": 0.34, "logH": 0.16, "logD": 0.31,
    "S": 1.15, "방향": 0.10, "코너": 0.09, "log전면": 0.14,
}
NOISE_SIGMA = 0.13          # 로그 공간 표준편차 → LOOCV MAPE 대략 15~17%
TARGET_MEDIAN_DAILY = 105.0  # 만원/일 — 국내 프랜차이즈 카페 중위 수준(월 ~3,150만원)


def _lg_partial(W, H, D, S, direction, corner, front):
    b = TRUE_BETA
    return (b["logW"] * math.log(max(W, 1)) + b["logH"] * math.log(max(H, 1))
            + b["logD"] * math.log(max(D, 1)) + b["S"] * S
            + b["방향"] * direction + b["코너"] * corner
            + b["log전면"] * math.log(max(front, 1)))


def solve_const(parts: list[float]) -> float:
    """절편을 손으로 정하면 매출이 몇 자릿수씩 틀어진다. 표본 중앙값이
    TARGET_MEDIAN_DAILY 에 오도록 절편을 역산한다."""
    parts = sorted(parts)
    n = len(parts)
    med = parts[n // 2] if n % 2 else (parts[n // 2 - 1] + parts[n // 2]) / 2
    return math.log(TARGET_MEDIAN_DAILY) - med


def true_daily_sales(name, const, W, H, D, S, direction, corner, front):
    r = rng(name, "sales")
    lg = const + _lg_partial(W, H, D, S, direction, corner, front)
    return math.exp(lg + r.gauss(0, NOISE_SIGMA))


def write_csv(path: Path, rows: list[dict], header: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


SITE_HEADER = ["후보지명", "주소", "우편번호", "법정동코드", "위도", "경도",
               "전용면적_평", "좌석수", "층", "코너여부",
               "전면폭_m", "주차가능대수", "정차가능", "도로변", "방향적합",
               "보증금_만원", "월임대료_만원", "관리비_만원", "권리금_만원", "계약조건점수",
               "잔존율_R", "근저당_과다", "임대인_불일치", "소송_계류", "인허가_불가", "비고"]

STORE_HEADER = ["점포명", "주소", "위도", "경도", "개점일", "기준점포", "월매출_만원", "일매출_만원",
                "전용면적_평", "좌석수", "층", "코너여부", "전면폭_m", "주차가능대수", "정차가능",
                "도로변", "방향적합", "보증금_만원", "월임대료_만원", "관리비_만원",
                "권리금_만원", "계약조건점수", "잔존율_R", "비고"]

ADDRESSES = {
    "성수 연무장길": "서울 성동구 연무장길 42", "강남역 11번출구": "서울 강남구 강남대로 396",
    "목동 7단지 상가": "서울 양천구 목동서로 130", "홍대 어울마당로": "서울 마포구 어울마당로 66",
    "판교 유스페이스": "경기 성남시 분당구 삼평동 682", "신림 별빛거리": "서울 관악구 남부순환로 1614",
}


def main():
    import geo
    import m1_area as M1
    import m2_demand as M2
    import m3_huff as M3
    from config import tier_of

    all_locs = CANDIDATES + STORES
    store_names = {s[0] for s in STORES}

    print("등시선 생성 중…")
    iso_geo = build_isochrones(all_locs)
    (ROOT / "등시선.example.geojson").write_text(
        json.dumps(iso_geo, ensure_ascii=False, indent=1), encoding="utf-8")

    print("격자 인구 · 유동인구 · 경쟁점 생성 중…")
    cells = build_cells(all_locs)
    points = build_points(all_locs)
    comps = build_competitors(all_locs, store_names)
    write_csv(ROOT / "격자인구.example.csv", cells,
              ["격자ID", "중심위도", "중심경도", "한변_m", "세대수", "직장인구"])
    write_csv(ROOT / "유동인구.example.csv", points,
              ["지점ID", "위도", "경도", "도로변", "시간대", "인원", "출처", "단위면적_m2"])
    write_csv(ROOT / "경쟁점.example.csv", comps,
              ["상호", "브랜드", "티어", "위도", "경도", "좌석수", "자사"])

    isos = M1.load_isochrones(ROOT / "등시선.example.geojson")
    comp_objs = M3.load_competitors(ROOT / "경쟁점.example.csv")

    def features(name, lat, lon, attrs):
        area = M1.resolve(name, lat, lon, isos, 0)
        dem = M2.demand(area, cells, points, attrs["도로변"])
        rivals = [k for k in comp_objs if k["상호"] != name]
        sh = M3.share(area, M3.attraction(attrs["좌석수"], "동일가격대"), rivals, cells, False)
        return area, dem, sh

    print("후보지 속성 생성 중…")
    site_rows = []
    for name, lat, lon, kind, R, dens in CANDIDATES:
        r = rng(name, "attrs")
        a = site_attrs(name, kind, dens, r)
        row = {"후보지명": name, "주소": ADDRESSES.get(name, ""),
               # 우편번호·법정동코드는 입력 페이지가 주소 검색으로 채운다.
               # 예시 데이터는 비워 둔다 — 지어내면 실제 지번과 어긋난다.
               "우편번호": "", "법정동코드": "",
               "위도": lat, "경도": lon,
               "잔존율_R": "", **a,
               # 치명 항목은 실사 결과를 적는 칸이다. 예시는 대부분 'N'(확인 완료).
               "근저당_과다": "N", "임대인_불일치": "N", "소송_계류": "N", "인허가_불가": "N",
               "비고": f"{kind} 상권"}
        site_rows.append(row)
    # 치명 플래그가 실제로 작동하는 예를 하나 남긴다
    site_rows[3]["소송_계류"] = "Y"
    site_rows[3]["비고"] = "retail 상권 · 명도 분쟁 계류(실사 확인)"
    # 실사 전이라 비어 있는 예도 하나
    for k in ("근저당_과다", "임대인_불일치", "소송_계류", "인허가_불가"):
        site_rows[5][k] = ""
    site_rows[5]["비고"] = "campus 상권 · 권리관계 실사 미완"
    write_csv(ROOT / "후보지.example.csv", site_rows, SITE_HEADER)

    print("기존점 실매출 생성 중(참 모델 + 잡음)…")
    prepared = []
    for name, lat, lon, kind, R, dens in STORES:
        r = rng(name, "attrs")
        a = site_attrs(name, kind, dens, r)
        area, dem, sh = features(name, lat, lon, a)
        prepared.append((name, lat, lon, kind, a, dem, sh))
    const = solve_const([
        _lg_partial(d["W"], d["H"], d["D_am_adj"], s_["S"],
                    1.0 if a["방향적합"] == "Y" else 0.0,
                    1.0 if a["코너여부"] == "Y" else 0.0, a["전면폭_m"])
        for _, _, _, _, a, d, s_ in prepared])
    print(f"  참 모델 절편 = {const:.3f} (일매출 중앙값 {TARGET_MEDIAN_DAILY:.0f}만원 기준)")

    store_rows = []
    for idx, (name, lat, lon, kind, a, dem, sh) in enumerate(prepared):
        daily = true_daily_sales(name, const, dem["W"], dem["H"], dem["D_am_adj"], sh["S"],
                                 1.0 if a["방향적합"] == "Y" else 0.0,
                                 1.0 if a["코너여부"] == "Y" else 0.0, a["전면폭_m"])
        monthly = daily * 30
        store_rows.append({
            "점포명": name, "주소": "", "위도": lat, "경도": lon,
            "개점일": f"202{3 + idx // 6}-{(idx % 12) + 1:02d}-01",
            "기준점포": "Y" if idx in (1, 5) else "N",
            "월매출_만원": round(monthly, 1), "일매출_만원": round(daily, 2),
            "잔존율_R": "", **a, "비고": f"{kind} 상권",
        })
    write_csv(ROOT / "기존점.example.csv", store_rows, STORE_HEADER)
    write_csv(ROOT / "기존점.example_초기.csv", store_rows[:4], STORE_HEADER)

    print(f"\n완료 — 후보지 {len(site_rows)} · 기존점 {len(store_rows)} · "
          f"격자 {len(cells)} · 유동지점 {len(points)} · 경쟁점 {len(comps)}")
    print("  ⚠ 전부 합성 데이터입니다. 실측이 아닙니다.")


if __name__ == "__main__":
    main()
