#!/usr/bin/env python3
"""
격자 인구 수집 (통계청 SGIS · 전국)

M2 의 배후 수요 H(세대수)·W(직장인구)는 격자인구.csv 에서 온다. 지금까지 이 파일은
사람이 준비해야 했고, 그래서 **전국 어디든 후보지를 넣기 전에 손작업이 하나 있었다.**
SGIS 는 전국 격자 센서스를 무료 API 로 준다. 여기를 이으면 그 손작업이 사라진다.

  python3 collect_grid_population.py --sites 후보지.csv                 # dry-run
  SGIS_KEY=... SGIS_SECRET=... python3 collect_grid_population.py --live

유동인구와 달리 **추정이 아니다.** 거주·사업체는 등록 데이터라 기지국 신호처럼
'있었을 것' 을 세는 값이 아니다. 그래서 M2 도 이 값에는 대용 경고를 붙이지 않는다.
전국 어디서나 같은 방식으로 나오므로 지역 편차 걱정도 없다.

실제 호출로 확인한 것 (2026-08)

  ✅ 인증  consumer_key/secret → result.accessToken · 토큰 수명 4시간
  ✅ 세대수 stats/household.json?adm_cd=11&year=2023
           → {"result":[{"household_cnt":"4141659","adm_cd":"11","adm_nm":"서울특별시"}]}
  ✅ 종사자수 stats/company.json?adm_cd=11&low_search=1
           → 25개 구가 각각 {"tot_worker":"198800","adm_cd":"11040","adm_nm":"성동구"}
  ✅ 경계   boundary/hadmarea.geojson?adm_cd=11&low_search=1
           → Polygon + properties{x,y,adm_cd,adm_nm}. 좌표는 UTM-K(EPSG:5179).
             면적과 중심점이 여기서 나오므로 --areas 를 손으로 채우지 않아도 된다.

  처음에는 좌표 사각형(bbox)으로 격자를 받는 줄 알았는데 **틀렸다.** 실제로는
  행정구역 코드로 부르고 좌표도 면적도 주지 않는다. 그 가정을 따르던 코드는
  걷어냈다 — 반증된 가정을 남겨 두면 어느 쪽이 맞는지 헷갈린다.

  ⚠ 그리고 그 행정구역 코드는 **법정동코드가 아니다.** 성동구는 법정동 11200 인데
    SGIS 로는 11040 이고, SGIS 11200 은 동작구다. 앞자리를 잘라 쓰면 오류 하나 없이
    다른 구의 인구가 들어온다. 그래서 코드는 SGIS 목록에서 이름으로 찾는다.

  확인이 덜 된 자리는 --probe 로 눌러 본다:

      SGIS_KEY=... SGIS_SECRET=... python3 collect_grid_population.py --probe

⚠ dry-run 은 인구 수를 지어내지 않는다 (빈 표만 만든다).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 구역코드→면적·중심점 표는 유동인구 쪽과 같은 형식이다. 구현을 둘로 두면
# 한쪽만 고쳐져 같은 CSV 가 두 도구에서 다르게 읽히는 일이 생긴다.
from collect_carrier_flow import load_areas
from common import read_csv, to_f

ROOT = Path(__file__).resolve().parent

# 인증은 **실제 호출로 확인했다.** 응답은 이렇게 온다:
#   {"result":{"accessToken":"<UUID>","accessTimeout":"<ms epoch>"},
#    "errCd":0,"errMsg":"Success","id":"API_0101","trId":"..."}
# 토큰 수명은 4시간(accessTimeout - 발급시각). 한 번 실행이 그보다 길 일은 없지만,
# 오래 걸리는 배치를 돌린다면 재발급이 필요하다.
#
# ⚠ 통계청이 국가데이터처로 개편되면서 개발지원센터 주소가 sgis.kostat.go.kr →
#   sgis.mods.go.kr 로 옮겨 갔다. API 호스트도 함께 바뀌었을 수 있어 두 곳을 다
#   눌러 본다 — 한쪽만 박아 두면 '키가 잘못됐나' 하고 엉뚱한 데를 찾게 된다.
SGIS_HOSTS = ["https://sgisapi.kostat.go.kr", "https://sgisapi.mods.go.kr"]
AUTH_PATH = "/OpenAPI3/auth/authentication.json"
AUTH_URL = SGIS_HOSTS[0] + AUTH_PATH

# 자료 조회는 아직 확인 중이다. SGIS 통계 API 는 좌표 사각형이 아니라
# **adm_cd(행정구역코드) + year** 로 부르는 형태이고(household.json 은 household_cnt 를,
# population.json 은 population 을 준다), 격자 단위 상품이 따로 있는지는 문서를
# 열지 못해 확정하지 못했다. 그래서 후보 엔드포인트를 여러 개 두고 --probe 로
# 실제 키를 써서 어느 것이 답하는지 한 번에 알아본다.
DATA_URL = "https://sgisapi.kostat.go.kr/OpenAPI3/stats/household.json"

# ── KOSIS (국가통계포털) ──────────────────────────────
# SGIS 와 같은 자리를 채우는 두 번째 길. 전국·무료이고 주민등록인구와
# 전국사업체조사(종사자수)가 있다. 어려운 것은 호출이 아니라 **어느 통계표(tblId)를
# 쓸지 고르는 것**이라, 목록 조회를 probe 에 넣어 눈으로 고르게 한다.
KOSIS_LIST_URL = "https://kosis.kr/openapi/statisticsList.do"
KOSIS_DATA_URL = "https://kosis.kr/openapi/statisticsData.do"

# 목록에서 훑어볼 분류. vwCd=MT_ZTITLE 는 주제별 목록이다.
# ⚠ 분류 코드는 추측하지 않는다. 실제 응답을 보니 A_1 은 '인구·가구' 가 아니라
#   '인구이동' 이었다. 코드를 외워 박는 대신 --find 로 트리를 훑어 찾는다.
KOSIS_LIST_PROBES = [
    ("주제별 최상위", {"vwCd": "MT_ZTITLE"}),
    ("A 아래", {"vwCd": "MT_ZTITLE", "parentListId": "A"}),
]

# 응답 한 줄은 둘 중 하나다. 이 구분이 트리 탐색의 전부다.
#   통계표   TBL_ID 가 있다 → 실제로 조회할 수 있는 표
#   하위목록 LIST_ID 만 있다 → 더 내려가야 하는 폴더
def is_table(row: dict) -> bool:
    return bool(str(row.get("TBL_ID", "")).strip())


def is_folder(row: dict) -> bool:
    return not is_table(row) and bool(str(row.get("LIST_ID", "")).strip())

CANDIDATES = [
    ("가구(행정동)", "https://sgisapi.kostat.go.kr/OpenAPI3/stats/household.json",
     "adm_cd", "household_cnt 세대수"),
    ("인구(행정동)", "https://sgisapi.kostat.go.kr/OpenAPI3/stats/population.json",
     "adm_cd", "population 총인구"),
    ("인구 검색", "https://sgisapi.kostat.go.kr/OpenAPI3/stats/searchpopulation.json",
     "adm_cd", "population · avg_age"),
    ("사업체(행정동)", "https://sgisapi.kostat.go.kr/OpenAPI3/stats/company.json",
     "adm_cd", "종사자수 = W 후보"),
    ("행정구역 단계", "https://sgisapi.kostat.go.kr/OpenAPI3/addr/stage.json",
     "none", "adm_cd 목록 — 좌표→코드 변환의 출발점"),
    ("창업 인구요약", "https://sgisapi.kostat.go.kr/OpenAPI3/startupbiz/pplsummary.json",
     "bbox", "격자/영역 인구 (형식 미확인)"),

    # 경계 API — 이게 되면 --areas 표를 손으로 채우지 않아도 된다.
    # 행정동·집계구 경계를 받으면 면적과 중심점이 도형에서 바로 나온다.
    ("행정동 경계", "https://sgisapi.kostat.go.kr/OpenAPI3/boundary/hadmarea.geojson",
     "boundary", "면적·중심점 → --areas 자동 생성"),
    ("집계구 경계", "https://sgisapi.kostat.go.kr/OpenAPI3/boundary/jagurodarea.geojson",
     "boundary", "집계구 경계 (가장 촘촘) → --areas 자동 생성"),
]

# M2 가 먹는 격자인구.csv 열
HEADER = ["격자ID", "중심위도", "중심경도", "한변_m", "세대수", "직장인구"]

# 응답 표기가 바뀌어도 하나만 맞으면 읽힌다
FIELDS = {
    "격자ID": ["grid_id", "GRID_ID", "격자ID", "cell_id"],
    "위도": ["lat", "y", "중심위도", "point_y"],
    "경도": ["lon", "lng", "x", "중심경도", "point_x"],
    "세대수": ["hshld_cnt", "household_cnt", "세대수", "hh_cnt", "ho_cnt"],
    "직장인구": ["corp_worker_cnt", "worker_cnt", "직장인구", "employee_cnt", "tot_worker"],
    "한변": ["grid_size", "한변_m", "cell_size"],
}

# 후보지 반경 몇 m 까지 격자를 받을지. P10(도보 10분 ≈ 667m)을 덮어야 M2 의
# 면적 가중 교차가 성립한다. 넉넉히 잡되 요청 수가 폭발하지 않게.
DEFAULT_RADIUS = 800.0


def pick(item: dict, names: list[str]) -> str:
    for n in names:
        if n in item and str(item[n]).strip() != "":
            return str(item[n]).strip()
    return ""


def bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """후보지 주변 사각형. 위도 1도 ≈ 111km, 경도는 위도에 따라 줄어든다."""
    dlat = radius_m / 111_000.0
    dlon = radius_m / (111_000.0 * max(0.1, math.cos(math.radians(lat))))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def sites_bboxes(sites: list[dict], radius: float) -> list[dict]:
    """후보지마다 조회 영역 하나. 좌표가 없는 후보지는 건너뛴다 —
    주소만으로는 격자를 고를 수 없고, 추측한 좌표로 받은 인구는 근거가 아니다."""
    out = []
    for s in sites:
        lat, lon = to_f(s.get("위도")), to_f(s.get("경도"))
        name = str(s.get("후보지명", "")).strip()
        if not (lat and lon):
            continue
        y1, x1, y2, x2 = bbox(lat, lon, radius)
        out.append({"이름": name, "위도": lat, "경도": lon,
                    "minx": x1, "miny": y1, "maxx": x2, "maxy": y2})
    return out


def get_token(key: str, secret: str, url: str = AUTH_URL) -> tuple[str, str]:
    q = urllib.parse.urlencode({"consumer_key": key, "consumer_secret": secret})
    try:
        with urllib.request.urlopen(f"{url}?{q}", timeout=20,
                                    context=ssl.create_default_context()) as r:
            doc = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except (OSError, ValueError) as e:
        return "", f"{type(e).__name__}: {e}"
    # 오류도 HTTP 200 으로 온다. errMsg 를 그대로 전하는 편이 원인을 빨리 짚는다.
    if str(doc.get("errCd", "0")) not in ("0", "None", ""):
        return "", f"errCd {doc.get('errCd')} {doc.get('errMsg', '')}"
    tok = ((doc.get("result") or {}).get("accessToken") or "").strip()
    if not tok:
        return "", f"토큰이 없습니다: {json.dumps(doc, ensure_ascii=False)[:300]}"
    return tok, ""


# ── 실제 응답으로 확인된 것 ──────────────────────────
# stats/household.json?accessToken=..&adm_cd=11&year=2023
#   {"result":[{"household_cnt":"4141659","avg_family_member_cnt":"2.2",
#               "family_member_cnt":8908911,"all_household_cnt":4141659,
#               "adm_cd":"11","adm_nm":"서울특별시"}],
#    "errCd":0,"errMsg":"Success","id":"API_0305","trId":"..."}
#
# 좌표도 면적도 주지 않는다. adm_cd 와 값뿐이다. 그래서 처음 세운 bbox 가정은
# 버리고, KOSIS 와 같은 모양으로 간다 — adm_cd 로 부르고 --areas 로 좌표·면적을 잇는다.
SGIS_STATS = {
    "세대수": ("/OpenAPI3/stats/household.json",
            ["household_cnt", "all_household_cnt", "hshld_cnt"]),
    "직장인구": ("/OpenAPI3/stats/company.json",
             ["tot_worker", "worker_cnt", "corp_worker_cnt", "employee_cnt"]),
}


def fetch_sgis_stats(token: str, base: str, path: str, adm_cd: str,
                     year: str, low_search: str = "0") -> tuple[list, str]:
    """SGIS 통계 한 종류를 행정구역 코드로 부른다.

    low_search=1 이면 그 아래 단계(시도→시군구, 시군구→행정동)로 쪼개 준다.
    """
    q = urllib.parse.urlencode({
        "accessToken": token, "adm_cd": adm_cd,
        "year": year, "low_search": low_search,
    })
    url = base + path
    try:
        with urllib.request.urlopen(f"{url}?{q}", timeout=25,
                                    context=ssl.create_default_context()) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except OSError as e:
        return [], f"네트워크 오류: {e}"
    try:
        doc = json.loads(body)
    except ValueError as e:
        return [], f"JSON 파싱 실패: {e} · 앞부분 {body[:200]}"
    # SGIS 는 오류도 HTTP 200 으로 보낸다
    if str(doc.get("errCd", "0")) not in ("0", "None", ""):
        return [], f"errCd {doc.get('errCd')} {doc.get('errMsg', '')}"
    rows = doc.get("result")
    if not isinstance(rows, list) or not rows:
        return [], f"자료가 비었습니다: {json.dumps(doc, ensure_ascii=False)[:200]}"
    return rows, ""


def sgis_to_cells(rows: list, areas: dict, 항목: str,
                  후보키: list[str]) -> tuple[list[dict], dict]:
    """SGIS 통계 행 → 격자인구 행. 좌표·면적은 --areas 에서 잇는다."""
    out, 버림 = [], {"코드없음": 0, "값없음": 0, "면적없음": 0}
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = str(r.get("adm_cd") or "").strip()
        if not code:
            버림["코드없음"] += 1
            continue
        n = 0.0
        for k in 후보키:
            if str(r.get(k, "")).strip() != "":
                n = to_f(r.get(k))
                break
        if n <= 0:
            버림["값없음"] += 1
            continue
        info = areas.get(code) or areas.get(code[:5]) or {}
        면적, lat, lon = info.get("면적_m2", 0), info.get("위도", 0), info.get("경도", 0)
        if not (면적 > 0 and lat and lon):
            버림["면적없음"] += 1
            continue
        out.append({
            "격자ID": f"SGIS:{code}",
            "중심위도": round(lat, 6), "중심경도": round(lon, 6),
            "한변_m": round(면적 ** 0.5, 1),
            "세대수": round(n, 1) if 항목 == "세대수" else 0,
            "직장인구": round(n, 1) if 항목 == "직장인구" else 0,
        })
    return out, 버림


# ── 후보지 → SGIS 행정구역코드 ──────────────────────────
# ⚠ 여기가 이 파일에서 가장 조용히 틀릴 수 있는 자리였다.
#
#   법정동코드 앞 5자리를 SGIS adm_cd 로 그대로 쓰면 **다른 구의 인구를 받는다.**
#   두 체계는 이름만 비슷하고 값이 다르다:
#
#       성동구   법정동 11200 · SGIS 11040
#       동작구   법정동 11590 · SGIS 11200      ← 법정동 성동구 = SGIS 동작구
#
#   실제 응답(company.json?adm_cd=11&low_search=1)에서 성동구가 11040 으로 온 것을
#   보고 알았다. 앞자리를 자르는 코드는 오류를 내지 않는다 — 멀쩡한 숫자가 들어오고,
#   배후 수요 H·W 가 엉뚱한 구의 것으로 채워질 뿐이다.
#
# 그래서 코드는 **SGIS 에게 물어서** 정한다. 시도 아래를 low_search=1 로 받아
# 이름으로 맞추고, 못 맞추면 그 후보지는 넣지 않는다.
시도줄임 = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "세종시": "세종",
    "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "제주도": "제주",
}

# 시도 코드는 두 체계가 같은 것으로 알려져 있지만 **그대로 믿지 않는다.** 강원은
# 42→51, 전북은 45→52 로 바뀌었고 SGIS 가 어느 쪽을 쓰는지는 연도마다 다르다.
# 그래서 후보를 여럿 두고, 받아 온 이름이 주소와 맞을 때만 그 코드를 쓴다.
시도후보 = {
    "서울": ["11"], "부산": ["26"], "대구": ["27"], "인천": ["28"],
    "광주": ["29"], "대전": ["30"], "울산": ["31"], "세종": ["36"],
    "경기": ["41"], "강원": ["51", "42"], "충북": ["43"], "충남": ["44"],
    "전북": ["52", "45"], "전남": ["46"], "경북": ["47"], "경남": ["48"],
    "제주": ["50"],
}


def 시도짧게(name: str) -> str:
    s = str(name or "").strip()
    return 시도줄임.get(s, s)


def 주소쪼개기(주소: str) -> tuple[str, list[str]]:
    """주소 → (시도 줄임말, 시군구 후보 이름들).

    시군구는 한 토막일 때도('성동구') 두 토막일 때도('성남시 분당구') 있다. SGIS 는
    두 토막짜리를 '성남시분당구' 로 붙여 쓴다. 긴 쪽을 먼저 대 본다 — '성남시' 로
    먼저 맞추면 수정·중원·분당이 다 걸린다.

    붙이는 것은 **'○○시 ○○구/군' 일 때뿐이다.** '강남구 강남대로' 처럼 뒤가 도로명인
    주소까지 붙이면 있지도 않은 이름을 만들어 헛호출을 하고, 무엇을 찾는지도 흐려진다.
    """
    tok = [t for t in str(주소 or "").replace("\t", " ").split() if t]
    if not tok:
        return "", []
    시도 = 시도짧게(tok[0])
    뒤 = tok[1:3]
    후보 = []
    if len(뒤) >= 2 and 뒤[0].endswith("시") and 뒤[1][-1] in "구군":
        후보.append(뒤[0] + 뒤[1])
    if 뒤:
        후보.append(뒤[0])
    return 시도, 후보


def 이름맞나(sgis_nm: str, 후보: str) -> bool:
    s = str(sgis_nm or "").replace(" ", "")
    c = str(후보 or "").replace(" ", "")
    if not (s and c):
        return False
    return s == c or s.endswith(c) or c.endswith(s)


def resolve_regions(token: str, base: str, year: str,
                    sites: list[dict]) -> tuple[list[dict], list[str]]:
    """후보지를 SGIS 행정구역코드로 옮긴다. 못 옮긴 것은 말하고 버린다.

    법정동코드는 **어느 시도인지 짐작하는 데만** 쓴다. 시군구 코드는 SGIS 가
    돌려준 목록에서 이름으로 찾는다 — 그래야 두 체계가 어긋나도 조용히 틀리지 않는다.
    """
    path = SGIS_STATS["세대수"][0]
    묶음, 문제 = {}, []
    for st in sites:
        주소 = str(st.get("주소") or "").strip()
        이름 = str(st.get("후보지명") or "").strip() or "(이름 없음)"
        시도, 시군구후보 = 주소쪼개기(주소)
        if not (시도 and 시군구후보):
            문제.append(f"{이름}: 주소에서 시도·시군구를 읽지 못했습니다 "
                       f"({주소 or '주소 없음'})")
            continue
        b = "".join(ch for ch in str(st.get("법정동코드") or "") if ch.isdigit())
        힌트 = [b[:2]] if len(b) >= 2 else []
        묶음.setdefault((시도, tuple(힌트)), []).append((이름, 시군구후보))

    풀림, 캐시 = {}, {}
    for (시도, 힌트), 것들 in 묶음.items():
        코드후보 = list(힌트) + [c for c in 시도후보.get(시도, []) if c not in 힌트]
        if not 코드후보:
            문제.append(f"{시도}: 아는 시도가 아닙니다 — "
                       f"{', '.join(n for n, _ in 것들)}")
            continue

        하위, 쓴코드 = None, ""
        for cd in 코드후보:
            if cd in 캐시:
                하위, 쓴코드 = 캐시[cd], cd
                break
            # ① 이 코드가 정말 그 시도인지 이름으로 확인한다
            위, err = fetch_sgis_stats(token, base, path, cd, year, "0")
            if err or not 위:
                continue
            받은시도 = 시도짧게(str((위[0] or {}).get("adm_nm") or ""))
            if 받은시도 != 시도:
                continue
            # ② 그 아래 시군구 목록을 받는다
            아래, err = fetch_sgis_stats(token, base, path, cd, year, "1")
            if err or not 아래:
                continue
            캐시[cd] = 아래
            하위, 쓴코드 = 아래, cd
            break

        if not 하위:
            문제.append(f"{시도}: SGIS 에서 시도 코드를 확인하지 못했습니다 "
                       f"(눌러 본 코드 {', '.join(코드후보)})")
            continue

        for 이름, 시군구후보 in 것들:
            골라짐 = ""
            for want in 시군구후보:
                맞은 = [r for r in 하위
                       if 이름맞나(r.get("adm_nm"), want)]
                if len(맞은) == 1:
                    골라짐 = str(맞은[0].get("adm_cd") or "").strip()
                    # 같은 구역에 후보지가 여럿이면 한 줄에 모은다. 여기서 새로
                    # 만들어 덮으면 앞 후보지가 목록에서 사라진다.
                    자리 = 풀림.setdefault(골라짐, {
                        "adm_cd": 골라짐,
                        "adm_nm": str(맞은[0].get("adm_nm") or "").strip(),
                        "시도코드": 쓴코드,
                        "후보지": [],
                    })
                    자리["후보지"].append(이름)
                    break
                if len(맞은) > 1:
                    문제.append(
                        f"{이름}: '{want}' 에 맞는 구역이 {len(맞은)}개입니다 "
                        f"({', '.join(str(m.get('adm_nm')) for m in 맞은[:4])})")
                    골라짐 = "-"
                    break
            if not 골라짐:
                문제.append(f"{이름}: {시도} 안에서 "
                           f"'{시군구후보[0]}' 를 찾지 못했습니다")

    return list(풀림.values()), 문제


# ── 경계 → 면적·중심점 ────────────────────────────────
# boundary/hadmarea.geojson 이 답한다는 것을 실제 호출로 확인했다:
#   {"type":"FeatureCollection","features":[{"geometry":{"type":"Polygon",
#     "coordinates":[[[953651.32,1959043.14],…]]},
#     "properties":{"x":"953858","y":"1955185","adm_cd":"11010",
#                   "adm_nm":"서울특별시 종로구"}}]}
#
# 좌표는 위경도가 아니라 **UTM-K(EPSG:5179)** 다. 그대로 위도·경도 칸에 넣으면
# M2 가 그 구역을 지구 반대편으로 보고 P10 과 절대 겹치지 않는다 — H·W 가 0 이
# 되고 그것이 '배후가 없는 자리' 라는 판단으로 읽힌다. 그래서 되돌려 놓는다.
#
# 면적은 되돌릴 필요가 없다. EPSG:5179 는 미터 좌표계라 다각형 넓이가 곧 m² 다.
_5179 = {
    "a": 6378137.0, "f": 1 / 298.257222101,
    "lat0": math.radians(38.0), "lon0": math.radians(127.5),
    "k0": 0.9996, "FE": 1_000_000.0, "FN": 2_000_000.0,
}


def _meridian_arc(a: float, e2: float, lat: float) -> float:
    return a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * lat
                - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024)
                * math.sin(2 * lat)
                + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * lat)
                - (35 * e2 ** 3 / 3072) * math.sin(6 * lat))


def tm5179_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """UTM-K(EPSG:5179) 좌표 → (위도, 경도). 횡메르카토르 역변환."""
    p = _5179
    a, f, k0 = p["a"], p["f"], p["k0"]
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    M = _meridian_arc(a, e2, p["lat0"]) + (y - p["FN"]) / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    lat1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    C1 = ep2 * math.cos(lat1) ** 2
    T1 = math.tan(lat1) ** 2
    s = math.sin(lat1)
    N1 = a / math.sqrt(1 - e2 * s * s)
    R1 = a * (1 - e2) / (1 - e2 * s * s) ** 1.5
    D = (x - p["FE"]) / (N1 * k0)
    lat = lat1 - (N1 * math.tan(lat1) / R1) * (
        D ** 2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2)
        * D ** 6 / 720)
    lon = p["lon0"] + (
        D
        - (1 + 2 * T1 + C1) * D ** 3 / 6
        + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2)
        * D ** 5 / 120) / math.cos(lat1)
    return math.degrees(lat), math.degrees(lon)


def ring_area(ring: list) -> float:
    """구두끈 공식. 부호는 버린다 — 감는 방향은 여기서 뜻이 없다."""
    n = len(ring)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def geom_area_m2(geom: dict) -> float:
    """Polygon·MultiPolygon 넓이. 첫 고리는 겉, 나머지는 구멍이라 뺀다."""
    if not isinstance(geom, dict):
        return 0.0
    t = geom.get("type")
    coords = geom.get("coordinates") or []
    폴리들 = coords if t == "MultiPolygon" else ([coords] if t == "Polygon" else [])
    tot = 0.0
    for poly in 폴리들:
        if not poly:
            continue
        tot += ring_area(poly[0]) - sum(ring_area(h) for h in poly[1:])
    return max(0.0, tot)


# 경계는 단계별로 있다. 유동인구 쪽은 **집계구**를 써야 한다 — 행정동은 1~3km² 인데
# P5(도보 5분)는 0.35km² 안팎이라 중심점이 P5 안에 드는 행정동이 거의 없다.
# ⚠ 실제 호출로 확인한 것은 hadmarea 뿐이다. 나머지는 --probe 로 눌러 보고 쓰십시오.
BOUNDARY = {
    "시군구": ("/OpenAPI3/boundary/hadmarea.geojson", "확인됨"),
    "행정동": ("/OpenAPI3/boundary/hadmarea.geojson", "확인됨 (low_search 로 내려간다)"),
    "집계구": ("/OpenAPI3/boundary/jagurodarea.geojson", "미확인"),
}


def fetch_boundary(token: str, base: str, adm_cd: str, year: str,
                   low_search: str = "0",
                   path: str = "/OpenAPI3/boundary/hadmarea.geojson"
                   ) -> tuple[list, str]:
    q = urllib.parse.urlencode({
        "accessToken": token, "adm_cd": adm_cd,
        "year": year, "low_search": low_search,
    })
    try:
        with urllib.request.urlopen(f"{base + path}?{q}", timeout=40,
                                    context=ssl.create_default_context()) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except OSError as e:
        return [], f"네트워크 오류: {e}"
    try:
        doc = json.loads(body)
    except ValueError as e:
        return [], f"JSON 파싱 실패: {e} · 앞부분 {body[:200]}"
    if str(doc.get("errCd", "0")) not in ("0", "None", ""):
        return [], f"errCd {doc.get('errCd')} {doc.get('errMsg', '')}"
    feats = doc.get("features")
    if not isinstance(feats, list) or not feats:
        return [], f"경계가 비었습니다: {json.dumps(doc, ensure_ascii=False)[:200]}"
    return feats, ""


def areas_from_boundary(features: list) -> tuple[dict, list[str]]:
    """경계 GeoJSON → 구역코드별 {면적_m2, 위도, 경도}. --areas 를 손으로 안 채워도 된다.

    중심점은 properties.x/y 를 먼저 쓴다(통계청이 계산한 대표점). 없으면 겉고리의
    평균으로 대신하되, 어느 쪽이든 EPSG:5179 → 위경도 변환을 거친다.
    """
    out, 문제 = {}, []
    for ft in features:
        if not isinstance(ft, dict):
            continue
        props = ft.get("properties") or {}
        code = str(props.get("adm_cd") or "").strip()
        if not code:
            continue
        면적 = geom_area_m2(ft.get("geometry") or {})
        x, y = to_f(props.get("x")), to_f(props.get("y"))
        if not (x and y):
            ring = (((ft.get("geometry") or {}).get("coordinates") or [[]])[0]) or []
            ring = ring[0] if ring and isinstance(ring[0][0], (list, tuple)) else ring
            if ring:
                x = sum(p[0] for p in ring) / len(ring)
                y = sum(p[1] for p in ring) / len(ring)
        if not (x and y and 면적 > 0):
            문제.append(f"{code} {props.get('adm_nm', '')}: 면적이나 중심점이 없습니다")
            continue
        lat, lon = tm5179_to_wgs84(x, y)
        out[code] = {"면적_m2": 면적, "위도": lat, "경도": lon,
                     "구역명": str(props.get("adm_nm") or "").strip()}
    return out, 문제


def write_areas(areas: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["구역코드", "구역명", "면적_m2", "위도", "경도", "비고"])
        for code in sorted(areas):
            a = areas[code]
            w.writerow([code, a.get("구역명", ""), round(a["면적_m2"], 1),
                        round(a["위도"], 6), round(a["경도"], 6),
                        "SGIS 경계에서 계산"])
    return path


def dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    """후보지 조회 영역이 겹치면 같은 격자가 여러 번 온다. 그대로 두면 H·W 가
    겹친 만큼 부풀어 그 후보지의 배후 수요가 근거 없이 커진다."""
    본것, out, 중복 = set(), [], 0
    for r in rows:
        if r["격자ID"] in 본것:
            중복 += 1
            continue
        본것.add(r["격자ID"])
        out.append(r)
    return out, 중복


def write_rows(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in HEADER} for r in rows])
    return path


def _probe_one(token: str, url: str, params: dict, timeout: int = 20) -> dict:
    """엔드포인트 하나를 눌러 보고 결과를 그대로 담아 온다. 판단은 사람이 한다."""
    q = urllib.parse.urlencode({**params, "accessToken": token})
    full = f"{url}?{q}"
    try:
        with urllib.request.urlopen(full, timeout=timeout,
                                    context=ssl.create_default_context()) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "말": f"HTTP {e.code}"}
    except OSError as e:
        return {"ok": False, "status": 0, "말": f"{type(e).__name__}: {e}"}

    try:
        doc = json.loads(body)
    except ValueError:
        return {"ok": False, "status": status, "말": "JSON 이 아님",
                "앞부분": body[:300]}

    errcd = str(doc.get("errCd", "0"))
    if errcd not in ("0", "None", ""):
        return {"ok": False, "status": status,
                "말": f"errCd {errcd} {doc.get('errMsg', '')}"}

    res = doc.get("result")
    첫 = None
    if isinstance(res, list) and res:
        첫 = res[0]
    elif isinstance(res, dict):
        첫 = res
    return {"ok": True, "status": status, "말": "응답 있음",
            "건수": len(res) if isinstance(res, list) else 1,
            "필드": sorted(첫)[:25] if isinstance(첫, dict) else None,
            "표본": json.dumps(첫, ensure_ascii=False)[:400] if 첫 else "",
            "앞부분": body[:300] if 첫 is None else ""}


def probe(key: str, secret: str, auth_url: str, adm_cd: str, year: str,
          box: dict = None) -> int:
    """키를 가지고 실제로 눌러 보고, 무엇이 답하는지 그대로 출력한다.

    SGIS 문서를 이 환경에서 열 수 없어 자료 엔드포인트를 확정하지 못했다. 추측으로
    코드를 더 쌓는 대신, 키가 있는 곳에서 한 번 돌리면 진실이 나오게 만든다.
    이 출력을 그대로 붙여 주면 연동을 정확히 맞출 수 있다.
    """
    if not (key and secret):
        print("SGIS_KEY / SGIS_SECRET 이 필요합니다.", file=sys.stderr)
        print("  발급: sgis.kostat.go.kr → 개발지원센터 → 오픈API → 인증키 신청",
              file=sys.stderr)
        return 2

    print("SGIS 연동 점검")
    # 개편으로 호스트가 옮겨 갔을 수 있다. 지정한 주소를 먼저 보고, 안 되면 다른 곳도.
    후보 = [auth_url] + [h + AUTH_PATH for h in SGIS_HOSTS
                        if h + AUTH_PATH != auth_url]
    token, 쓴주소 = "", ""
    for one in 후보:
        print(f"  인증 시도  {one}")
        token, err = get_token(key, secret, one)
        if token:
            쓴주소 = one
            break
        print(f"    ✕ {err}")
    if not token:
        print("\n어느 호스트에서도 토큰을 받지 못했습니다.")
        print("  · 키와 시크릿이 맞는지, 승인이 끝났는지 확인하십시오.")
        print("  · 개발지원센터가 sgis.mods.go.kr 로 옮겨 갔습니다. 그곳 문서에 적힌")
        print("    API 주소가 다르면 --auth-url 로 넣어 주십시오.")
        return 1
    print(f"  ✓ 토큰 발급됨 ({len(token)}자) — {쓴주소}")
    # 자료 주소도 인증이 통한 호스트에 맞춘다
    베이스 = 쓴주소.split("/OpenAPI3")[0]

    print("\n후보 엔드포인트를 하나씩 눌러 봅니다. 이 표가 연동을 확정하는 근거입니다.")
    작동 = []
    for 이름, url, kind, 설명 in CANDIDATES:
        url = 베이스 + url.split(".go.kr", 1)[1] if ".go.kr" in url else url
        if kind == "adm_cd":
            params = {"adm_cd": adm_cd, "year": year}
        elif kind == "bbox" and box:
            params = {"minx": box["minx"], "miny": box["miny"],
                      "maxx": box["maxx"], "maxy": box["maxy"]}
        elif kind == "bbox":
            params = {}
        elif kind == "boundary":
            # 경계는 연도와 행정구역 코드로 부르는 형태로 알려져 있다
            params = {"year": year, "adm_cd": adm_cd, "low_search": "1"}
        else:
            params = {}
        got = _probe_one(token, url, params)
        mark = "✓" if got["ok"] else "✕"
        print(f"\n{mark} {이름}  ({설명})")
        print(f"   {url}")
        if params:
            print(f"   파라미터 {params}")
        print(f"   → {got['말']}")
        if got.get("필드"):
            print(f"   필드 {got['필드']}")
        if got.get("표본"):
            print(f"   표본 {got['표본']}")
        if got.get("앞부분"):
            print(f"   응답 앞부분 {got['앞부분']}")
        if got["ok"]:
            작동.append(이름)

    print("\n" + "─" * 60)
    if 작동:
        print(f"응답한 엔드포인트: {', '.join(작동)}")
        print("이 출력을 그대로 전달해 주시면 FIELDS 와 DATA_URL 을 정확히 맞추겠습니다.")
        print("특히 볼 것:")
        print("  · 세대수(household_cnt)와 직장인구(종사자수)에 해당하는 필드명")
        print("  · 좌표나 격자 단위가 있는지 — 있으면 시군구 안분 문제가 사라진다")
        print("  · **경계**가 응답하는지 — 되면 --areas 표를 손으로 채우지 않아도 된다")
    else:
        print("응답한 엔드포인트가 없습니다. 인증은 됐으므로 키 문제는 아니고, "
              "주소나 파라미터가 다릅니다.")
        print("SGIS 개발지원센터의 '데이터 API' 문서에서 실제 주소를 확인해 "
              "--data-url 로 넣어 주십시오.")
    return 0 if 작동 else 1


def kosis_fetch(api_key: str, org_id: str, tbl_id: str, itm_id: str,
                obj_l1: str, prd_se: str, prd_de: str,
                url: str = KOSIS_DATA_URL) -> tuple[list, str]:
    """KOSIS 자료 조회. 표를 고르는 것은 사람이 하고(--probe), 여기서는 받아만 온다.

    통계표마다 항목(itmId)과 분류(objL1)가 달라 상수로 박을 수 없다. 그래서 전부
    인자로 받는다 — probe 로 표를 고른 뒤 플래그만 바꿔 부르면 코드는 그대로다.
    """
    q = urllib.parse.urlencode({
        "method": "getList", "apiKey": api_key, "format": "json", "jsonVD": "Y",
        "orgId": org_id, "tblId": tbl_id,
        "itmId": itm_id or "ALL", "objL1": obj_l1 or "ALL",
        "prdSe": prd_se, **({"startPrdDe": prd_de, "endPrdDe": prd_de} if prd_de
                            else {"newEstPrdCnt": "1"}),
    })
    try:
        with urllib.request.urlopen(f"{url}?{q}", timeout=30,
                                    context=ssl.create_default_context()) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except OSError as e:
        return [], f"네트워크 오류: {e}"
    try:
        doc = json.loads(body)
    except ValueError as e:
        return [], f"JSON 파싱 실패: {e} · 응답 앞부분: {body[:300]}"
    # KOSIS 는 오류도 HTTP 200 + JSON 으로 보낸다
    if isinstance(doc, dict) and doc.get("errMsg"):
        return [], f"{doc.get('err')} {doc.get('errMsg')}"
    rows = doc if isinstance(doc, list) else doc.get("result") or []
    if not rows:
        return [], f"자료가 비었습니다: {json.dumps(doc, ensure_ascii=False)[:300]}"
    return rows, ""


# KOSIS 응답의 흔한 표기. 통계표마다 다르므로 여러 개를 함께 받는다.
KOSIS_FIELDS = {
    "코드": ["C1", "C1_OBJ_NM_ENG", "objL1", "C1_OBJ_NM"],
    "이름": ["C1_NM", "C1_OBJ_NM", "PRD_DE"],
    "값": ["DT", "dt", "값"],
    "단위": ["UNIT_NM", "unit"],
    "시점": ["PRD_DE", "prdDe"],
}


def kosis_to_cells(rows: list, areas: dict, 항목: str) -> tuple[list[dict], dict]:
    """KOSIS 행 → 격자인구.csv 행. 구역 면적·중심점 표(--areas)가 있어야 한다.

    KOSIS 는 행정구역 코드와 값만 주고 좌표도 면적도 주지 않는다. M2 는 둘 다
    필요하다(중심점으로 P10 과 겹치는지 보고, 면적으로 안분한다). 그래서 표가 없는
    구역은 행을 만들지 않는다 — 면적을 추측해 나눈 값은 근거가 아니다.

    항목 은 이 표가 무엇을 담는지 — "세대수" 또는 "직장인구".
    """
    out, 버림 = [], {"코드없음": 0, "값없음": 0, "면적없음": 0}
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = pick(r, KOSIS_FIELDS["코드"])
        if not code:
            버림["코드없음"] += 1
            continue
        n = to_f(pick(r, KOSIS_FIELDS["값"]))
        if n <= 0:
            버림["값없음"] += 1
            continue
        info = areas.get(code) or areas.get(code[:5]) or {}
        면적, lat, lon = info.get("면적_m2", 0), info.get("위도", 0), info.get("경도", 0)
        if not (면적 > 0 and lat and lon):
            버림["면적없음"] += 1
            continue
        out.append({
            "격자ID": f"KOSIS:{code}",
            "중심위도": round(lat, 6), "중심경도": round(lon, 6),
            # 정사각형으로 환산한 한 변. M2 가 이 값으로 겹친 면적을 잰다.
            # 300m 를 넘으면 M2 가 '격자가 아니다' 경고를 남긴다.
            "한변_m": round(면적 ** 0.5, 1),
            "세대수": round(n, 1) if 항목 == "세대수" else 0,
            "직장인구": round(n, 1) if 항목 == "직장인구" else 0,
        })
    return out, 버림


def merge_cells(a: list[dict], b: list[dict]) -> list[dict]:
    """같은 구역의 세대수 표와 직장인구 표를 한 행으로 합친다."""
    by = {}
    for r in a + b:
        cur = by.setdefault(r["격자ID"], dict(r))
        cur["세대수"] = max(to_f(cur.get("세대수")), to_f(r.get("세대수")))
        cur["직장인구"] = max(to_f(cur.get("직장인구")), to_f(r.get("직장인구")))
    return list(by.values())


def kosis_list(api_key: str, params: dict) -> tuple[list, str]:
    """통계표 목록 한 번 조회. 폴더와 표가 섞여 돌아온다."""
    q = urllib.parse.urlencode({
        "method": "getList", "apiKey": api_key,
        "format": "json", "jsonVD": "Y", **params,
    })
    try:
        with urllib.request.urlopen(f"{KOSIS_LIST_URL}?{q}", timeout=25,
                                    context=ssl.create_default_context()) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except OSError as e:
        return [], f"{type(e).__name__}: {e}"
    try:
        doc = json.loads(body)
    except ValueError:
        return [], f"JSON 이 아님: {body[:200]}"
    if isinstance(doc, dict) and doc.get("errMsg"):
        return [], f"{doc.get('err')} {doc.get('errMsg')}"
    items = doc if isinstance(doc, list) else doc.get("result") or []
    return [x for x in items if isinstance(x, dict)], ""


def kosis_find(api_key: str, 낱말: list[str], vw_cd: str = "MT_ZTITLE",
               root: str = "", 최대깊이: int = 4, 최대호출: int = 60) -> int:
    """통계표 트리를 훑어 이름에 낱말이 든 표를 찾는다.

    분류 코드를 외워 박지 않기 위해서다. 실제로 A_1 은 '인구·가구' 가 아니라
    '인구이동' 이었고, 그런 추측은 맞는지 확인할 방법이 없다. 폴더(LIST_ID)를 따라
    내려가며 표(TBL_ID) 이름을 보는 편이 확실하다.

    호출 수에 상한을 둔다 — 남의 API 를 넓이 우선으로 훑는 일이라 예의가 필요하다.
    """
    if not api_key:
        print("KOSIS_API_KEY 가 필요합니다.", file=sys.stderr)
        return 2
    낱말 = [w.strip() for w in 낱말 if w.strip()]
    if not 낱말:
        print("--find 에 찾을 낱말을 주십시오. 예: --find 세대 --find 종사자",
              file=sys.stderr)
        return 2

    print(f"KOSIS 통계표 검색 — 낱말 {', '.join(낱말)} · 최대 {최대호출}회 호출")
    큐 = [(root, [], 0)]
    본폴더, 찾음, 호출 = set(), [], 0

    while 큐 and 호출 < 최대호출:
        parent, 길, depth = 큐.pop(0)
        if parent in 본폴더 or depth > 최대깊이:
            continue
        본폴더.add(parent)
        params = {"vwCd": vw_cd}
        if parent:
            params["parentListId"] = parent
        rows, err = kosis_list(api_key, params)
        호출 += 1
        if err:
            if depth == 0:
                print(f"  ✕ 최상위 조회 실패 — {err}", file=sys.stderr)
                return 1
            continue

        for r in rows:
            이름 = str(r.get("TBL_NM") or r.get("LIST_NM") or "")
            if is_table(r):
                if any(w in 이름 for w in 낱말):
                    찾음.append({"TBL_ID": r.get("TBL_ID"), "ORG_ID": r.get("ORG_ID"),
                                "이름": 이름, "길": " > ".join(길)})
            elif is_folder(r):
                # 폴더는 이름이 맞거나, 아직 아무것도 못 찾았으면 들어가 본다
                큐.append((str(r.get("LIST_ID")), 길 + [이름], depth + 1))

    print(f"  호출 {호출}회 · 폴더 {len(본폴더)}곳 확인")
    if not 찾음:
        print("\n찾은 표가 없습니다. 낱말을 넓혀 보십시오(예: --find 가구, --find 사업체).")
        print("  --최대호출 을 늘리면 더 깊이 훑습니다.")
        return 1

    print(f"\n찾은 통계표 {len(찾음)}개:")
    for f in 찾음[:40]:
        print(f"  ORG_ID={f['ORG_ID']} TBL_ID={f['TBL_ID']}")
        print(f"    {f['이름']}")
        if f["길"]:
            print(f"    경로: {f['길']}")
    if len(찾음) > 40:
        print(f"  … 외 {len(찾음) - 40}개")
    print("\n쓸 표를 골라 넣으십시오:")
    print("  --tbl-id-household <세대수 표>  --tbl-id-worker <종사자수 표>")
    return 0


def kosis_probe(api_key: str) -> int:
    """KOSIS 통계표 목록을 훑는다.

    KOSIS 는 호출 자체는 쉽지만 **어느 통계표를 쓸지** 고르는 데서 막힌다. 표가
    수만 개이고 이름이 비슷해서, 코드에 tblId 를 박아 두면 그게 맞는 표인지 아무도
    확인하지 못한다. 그래서 목록을 그대로 보여 주고 사람이 고르게 한다.
    """
    if not api_key:
        print("KOSIS_API_KEY 가 필요합니다.", file=sys.stderr)
        print("  발급: https://kosis.kr/openapi/index/index.jsp (무료)", file=sys.stderr)
        return 2

    print("KOSIS 통계표 목록 조회")
    print(f"  {KOSIS_LIST_URL}")
    찾음 = 0
    for 이름, extra in KOSIS_LIST_PROBES:
        q = urllib.parse.urlencode({
            "method": "getList", "apiKey": api_key,
            "format": "json", "jsonVD": "Y", **extra,
        })
        try:
            with urllib.request.urlopen(f"{KOSIS_LIST_URL}?{q}", timeout=25,
                                        context=ssl.create_default_context()) as r:
                body = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            print(f"\n✕ {이름} — HTTP {e.code}")
            continue
        except OSError as e:
            print(f"\n✕ {이름} — {type(e).__name__}: {e}")
            continue

        try:
            doc = json.loads(body)
        except ValueError:
            print(f"\n✕ {이름} — JSON 이 아님")
            print(f"   응답 앞부분 {body[:300]}")
            continue

        # KOSIS 는 오류도 200 + JSON 으로 보낸다
        if isinstance(doc, dict) and doc.get("errMsg"):
            print(f"\n✕ {이름} — {doc.get('err')} {doc.get('errMsg')}")
            continue
        items = doc if isinstance(doc, list) else doc.get("result") or []
        if not items:
            print(f"\n✕ {이름} — 목록이 비었습니다  {json.dumps(doc, ensure_ascii=False)[:200]}")
            continue

        찾음 += 1
        print(f"\n✓ {이름} — {len(items)}건  (파라미터 {extra})")
        for it in items[:12]:
            if not isinstance(it, dict):
                continue
            print("   " + " · ".join(
                f"{k}={it[k]}" for k in ("ORG_ID", "TBL_ID", "LIST_ID", "TBL_NM", "LIST_NM")
                if k in it))

    print("\n" + "─" * 60)
    if 찾음:
        print("쓸 통계표를 고르십시오. H 는 세대수(주민등록 또는 인구총조사 가구),")
        print("W 는 전국사업체조사의 종사자수입니다.")
        print("고른 표의 ORG_ID 와 TBL_ID 를 알려 주시면 조회까지 이어 놓겠습니다.")
        print(f"  자료 조회는 {KOSIS_DATA_URL} 에 orgId·tblId·objL1=ALL·itmId·prdSe 로 부릅니다.")
    else:
        print("목록을 하나도 받지 못했습니다. 키가 승인됐는지 확인하십시오.")
    return 0 if 찾음 else 1


def sgis_run(args, sites: list[dict], out: Path) -> int:
    """SGIS 에서 세대수·종사자수를 받아 격자인구.csv 를 만든다.

    두 가지를 SGIS 에게 **물어서** 정한다. 짐작하지 않는다:

      · 행정구역코드  후보지 주소의 시군구 이름을 SGIS 목록에서 찾는다.
                    법정동코드 앞자리를 잘라 쓰면 다른 구를 받는다(성동 11200 →
                    SGIS 로는 동작구다).
      · 면적·중심점  boundary/hadmarea.geojson 에서 계산한다. --areas 를 주면
                    그것을 먼저 쓰고, 없으면 여기서 만들어 파일로도 남긴다.

    --low-search 1 을 주면 행정동까지 쪼개 받는다 — 시군구는 한 변이 4km 를 넘어
    M2 가 '격자가 아니다' 경고를 낸다.
    """
    key = os.environ.get("SGIS_KEY", "").strip()
    secret = os.environ.get("SGIS_SECRET", "").strip()
    areas = load_areas(args.areas)

    if not args.live:
        write_rows([], out)
        읽힘 = [주소쪼개기(str(st.get("주소") or "")) for st in sites]
        됨 = [f"{a} {b[0]}" for a, b in 읽힘 if a and b]  # 가장 좁게 잡은 이름
        print("dry-run — SGIS 를 호출하지 않았습니다.")
        print(f"  후보지 {len(sites)}곳 · 주소에서 시군구를 읽은 것 {len(됨)}곳"
              + (f" ({', '.join(sorted(set(됨))[:6])})" if 됨 else ""))
        print("  ※ 행정구역코드는 SGIS 목록에서 이름으로 찾습니다 — "
              "법정동코드 앞자리를 쓰지 않습니다(다른 구가 됩니다).")
        print(f"  키 {'있음' if key and secret else '없음'} · "
              f"구역 면적표 {len(areas)}건"
              + ("" if areas else " (없으면 경계 API 에서 자동으로 만듭니다)"))
        print("  ※ dry-run 은 인구 수를 만들어 내지 않습니다.")
        print(f"  → {out} (빈 표)")
        return 0

    if not (key and secret):
        print("SGIS_KEY / SGIS_SECRET 이 필요합니다.", file=sys.stderr)
        return 2

    # 인증 — 호스트가 옮겨 갔을 수 있어 두 곳을 다 본다
    후보 = [args.auth_url] + [h + AUTH_PATH for h in SGIS_HOSTS
                            if h + AUTH_PATH != args.auth_url]
    token, 베이스, err = "", "", ""
    for one in 후보:
        token, err = get_token(key, secret, one)
        if token:
            베이스 = one.split("/OpenAPI3")[0]
            break
    if not token:
        print(f"토큰 발급 실패 — {err}", file=sys.stderr)
        return 1

    지역, 문제 = resolve_regions(token, 베이스, args.year, sites)
    for m in 문제:
        print(f"  🙋 {m}", file=sys.stderr)
    if not 지역:
        print("후보지를 SGIS 행정구역코드로 옮기지 못했습니다. "
              "주소가 '서울 성동구 …' 처럼 시도부터 시작하는지 보십시오.",
              file=sys.stderr)
        return 1
    for z in 지역:
        print(f"  ✓ {z['adm_nm']} = SGIS {z['adm_cd']}"
              f"  ← {', '.join(z.get('후보지', []))}")
    코드 = [z["adm_cd"] for z in 지역]

    # 면적·중심점 — 주지 않았으면 경계에서 만든다
    if not areas:
        만든것 = {}
        for adm in 코드:
            feats, err = fetch_boundary(token, 베이스, adm, args.year,
                                        args.low_search)
            if err:
                print(f"  ✕ 경계 {adm} — {err}", file=sys.stderr)
                continue
            got, 빠진 = areas_from_boundary(feats)
            만든것.update(got)
            for m in 빠진:
                print(f"      {m}", file=sys.stderr)
        if 만든것:
            areas = 만든것
            표 = Path(args.areas) if args.areas else out.parent / "행정구역.csv"
            write_areas(만든것, 표)
            print(f"  ✓ 경계에서 면적·중심점 {len(만든것)}개 구역 → {표}")
        else:
            print("면적·중심점을 얻지 못했습니다. 경계 API 가 답하지 않으면 "
                  "--areas 로 표를 넣어 주십시오.", file=sys.stderr)
            print("  뼈대 만들기: --make-areas --sites 후보지.csv", file=sys.stderr)
            return 1

    묶음 = []
    for 항목, (path, 키들) in SGIS_STATS.items():
        cells_all = []
        for adm in 코드:
            rows, err = fetch_sgis_stats(token, 베이스, path, adm,
                                         args.year, args.low_search)
            if err:
                print(f"  ✕ {항목} {adm} — {err}", file=sys.stderr)
                continue
            cells, 버림 = sgis_to_cells(rows, areas, 항목, 키들)
            cells_all += cells
            if 버림["면적없음"]:
                print(f"      {adm}: 면적표에 없는 구역 {버림['면적없음']}개를 건너뜀")
        if cells_all:
            print(f"  ✓ {항목} — {len(cells_all)}개 구역")
            묶음.append(cells_all)

    if not 묶음:
        print("한 항목도 받지 못했습니다.", file=sys.stderr)
        return 1
    cells = merge_cells(묶음[0], 묶음[1] if len(묶음) > 1 else [])
    cells, 중복 = dedupe(cells)
    write_rows(cells, out)
    print(f"SGIS 격자인구 — 구역 {len(cells)}개 → {out}")
    큰것 = [c for c in cells if to_f(c["한변_m"]) > 300]
    if 큰것:
        print(f"  🙋 {len(큰것)}개 구역이 한 변 300m 를 넘습니다 — M2 가 안분 경고를 "
              f"냅니다. --low-search 1 로 더 잘게 받으면 줄어듭니다.")
    return 0


def make_areas(sites: list[dict], out: Path) -> int:
    """후보지에 필요한 구역코드만 골라 --areas 표의 뼈대를 만든다.

    전국 229개 시군구 표를 통째로 만들 필요가 없다. 이번 심의에 올린 후보지가
    속한 구역만 채우면 되고, 그게 보통 몇 개다. 어느 코드가 필요한지 여기서
    짚어 주면 사람이 그 줄만 채우면 된다.

    면적과 중심점은 **비워서 낸다.** 여기서 지어내면 그 값으로 배후 수요가 안분되고,
    아무도 그게 추측이었다는 걸 모르게 된다. 어디서 받아 채우는지는 함께 적는다.

    ⚠ 여기 적히는 코드는 **법정동코드** 앞 5자리다. SGIS 는 다른 코드를 쓴다
      (성동구: 법정동 11200 · SGIS 11040). SGIS 쪽은 이 표가 필요 없다 —
      --source sgis --live 가 경계 API 에서 스스로 만든다.
    """
    코드 = {}
    for st in sites:
        b = "".join(ch for ch in str(st.get("법정동코드") or "") if ch.isdigit())
        이름 = str(st.get("후보지명", "")).strip()
        주소 = str(st.get("주소", "")).strip()
        if len(b) >= 5:
            코드.setdefault(b[:5], []).append(이름)
        else:
            코드.setdefault("", []).append(f"{이름} ({주소 or '주소 없음'})")

    없는것 = 코드.pop("", [])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["구역코드", "구역명", "면적_m2", "위도", "경도", "비고"])
        for code, names in sorted(코드.items()):
            w.writerow([code, "", "", "", "", "후보지: " + ", ".join(sorted(set(names)))])

    print(f"--areas 뼈대를 만들었습니다 — 시군구 {len(코드)}개 → {out}")
    print("  (코드는 법정동코드 앞 5자리입니다. SGIS 코드가 아닙니다 — "
          "SGIS 는 --live 가 경계에서 스스로 만듭니다.)")
    for code, names in sorted(코드.items()):
        print(f"  {code}  ← {', '.join(sorted(set(names)))}")
    if 없는것:
        print(f"\n  ⚠ 법정동코드가 없는 후보지 {len(없는것)}곳: {', '.join(없는것)}")
        print("     입력 화면에서 주소를 검색하면 자동으로 채워집니다.")
    print("\n면적_m2 · 위도 · 경도는 비워 뒀습니다. 지어내면 그 값으로 배후 수요가")
    print("안분되고 아무도 그게 추측이었다는 걸 모르게 됩니다. 아래에서 채우십시오:")
    print("  · 면적  KOSIS '지적통계 — 행정구역별 국토이용현황' 또는")
    print("          행정안전부 행정구역 경계(data.go.kr)에서 계산")
    print("  · 중심점 같은 경계 파일의 도형 중심(centroid)")
    print("\n채운 뒤: --areas 로 넣으면 KOSIS·통신사 유동인구 양쪽에서 같이 씁니다.")
    return 0


def make_areas_live(args, sites: list[dict], out: Path) -> int:
    """SGIS 경계에서 --areas 표를 실제로 채워 낸다.

    이 표는 **두 도구가 같이 쓴다.** 통신사 유동인구(collect_carrier_flow.py)도 구역
    면적이 없으면 행을 만들지 않는데, 지금까지 그 표를 사람이 채워야 했다. 격자인구
    쪽에서 이미 경계를 받고 있으므로 여기서 한 번 만들면 양쪽이 끝난다.

    유동인구에는 --level 집계구 를 쓰십시오. 행정동은 1~3km² 인데 P5(도보 5분)는
    0.35km² 안팎이라, 중심점이 P5 안에 드는 행정동이 거의 없어 대부분 버려집니다.
    """
    key = os.environ.get("SGIS_KEY", "").strip()
    secret = os.environ.get("SGIS_SECRET", "").strip()
    if not (key and secret):
        print("SGIS_KEY / SGIS_SECRET 이 필요합니다.", file=sys.stderr)
        return 2

    후보 = [args.auth_url] + [h + AUTH_PATH for h in SGIS_HOSTS
                            if h + AUTH_PATH != args.auth_url]
    token, 베이스, err = "", "", ""
    for one in 후보:
        token, err = get_token(key, secret, one)
        if token:
            베이스 = one.split("/OpenAPI3")[0]
            break
    if not token:
        print(f"토큰 발급 실패 — {err}", file=sys.stderr)
        return 1

    지역, 문제 = resolve_regions(token, 베이스, args.year, sites)
    for m in 문제:
        print(f"  🙋 {m}", file=sys.stderr)
    if not 지역:
        print("후보지를 SGIS 행정구역코드로 옮기지 못했습니다.", file=sys.stderr)
        return 1

    path, 확인 = BOUNDARY.get(args.level, BOUNDARY["행정동"])
    low = "1" if args.level in ("행정동", "집계구") else "0"
    print(f"경계 {args.level} ({확인}) — {path}")
    모은것 = {}
    for z in 지역:
        feats, err = fetch_boundary(token, 베이스, z["adm_cd"], args.year, low, path)
        if err:
            print(f"  ✕ {z['adm_nm']} ({z['adm_cd']}) — {err}", file=sys.stderr)
            continue
        got, 빠진 = areas_from_boundary(feats)
        모은것.update(got)
        print(f"  ✓ {z['adm_nm']} — 구역 {len(got)}개")
        for m in 빠진:
            print(f"      {m}", file=sys.stderr)

    if not 모은것:
        print("경계를 하나도 받지 못했습니다.", file=sys.stderr)
        if 확인 == "미확인":
            print(f"  {args.level} 경계 주소는 아직 확인되지 않았습니다. "
                  f"--probe 로 눌러 보십시오.", file=sys.stderr)
        return 1

    write_areas(모은것, out)
    큰것 = [a for a in 모은것.values() if a["면적_m2"] > 300 * 300]
    print(f"\n구역 {len(모은것)}개 → {out}")
    print("  이 표는 격자인구와 통신사 유동인구 양쪽에서 같이 씁니다.")
    if 큰것:
        평균 = sum(a["면적_m2"] for a in 큰것) / len(큰것) / 1e6
        print(f"  🙋 {len(큰것)}개 구역이 한 변 300m 를 넘습니다 (평균 {평균:.2f}km²). "
              f"M2 가 안분 경고를 냅니다.")
        if args.level != "집계구":
            print("     유동인구에 쓸 표라면 --level 집계구 로 더 잘게 받으십시오 — "
                  "P5(도보 5분)는 0.35km² 안팎이라 행정동은 대부분 버려집니다.")
    return 0


def kosis_run(args, out: Path) -> int:
    """KOSIS 에서 세대수·종사자수를 받아 격자인구.csv 를 만든다."""
    api_key = os.environ.get("KOSIS_API_KEY", "").strip()
    areas = load_areas(args.areas)

    if not args.live:
        write_rows([], out)
        print("dry-run — KOSIS 를 호출하지 않았습니다.")
        print(f"  키 KOSIS_API_KEY {'있음' if api_key else '없음'} · 비용 무료")
        print(f"  구역 면적표 {len(areas)}건" if areas
              else "  구역 면적표 없음 — --areas 로 구역코드→면적·중심점 표가 필요합니다")
        print("  쓸 통계표를 먼저 고르십시오:")
        print(f"    KOSIS_API_KEY=... python3 {Path(__file__).name} --source kosis --probe")
        print("  고른 뒤:")
        print(f"    KOSIS_API_KEY=... python3 {Path(__file__).name} --source kosis --live \\")
        print("        --areas 행정구역.csv --tbl-id-household DT_xxx --tbl-id-worker DT_yyy")
        print("  ※ dry-run 은 인구 수를 만들어 내지 않습니다.")
        print(f"  → {out} (빈 표)")
        return 0

    if not api_key:
        print("KOSIS_API_KEY 가 필요합니다. https://kosis.kr/openapi/index/index.jsp",
              file=sys.stderr)
        return 2
    if not (args.tbl_id_household or args.tbl_id_worker):
        print("--tbl-id-household 나 --tbl-id-worker 중 하나는 있어야 합니다.",
              file=sys.stderr)
        print("  --probe 로 통계표를 먼저 고르십시오.", file=sys.stderr)
        return 2
    자리표시자 = [t for t in (args.tbl_id_household, args.tbl_id_worker)
              if t and ("x" * 3 in t.lower() or "y" * 3 in t.lower())]
    if 자리표시자:
        print(f"통계표 ID 가 아직 자리표시자입니다: {', '.join(자리표시자)}",
              file=sys.stderr)
        print("  문서의 DT_xxxx / DT_yyyy 는 예시 자리입니다. --probe 로 실제 표를 "
              "고른 뒤 그 TBL_ID 를 넣으십시오.", file=sys.stderr)
        return 2
    if not areas:
        print("--areas 로 구역코드→면적·중심점 표가 필요합니다.", file=sys.stderr)
        print("  KOSIS 는 행정구역 코드와 값만 주고 좌표도 면적도 주지 않습니다. "
              "M2 는 둘 다 필요합니다(중심점으로 P10 과 겹치는지 보고, 면적으로 안분).",
              file=sys.stderr)
        return 2

    묶음 = []
    for tbl, 항목 in ((args.tbl_id_household, "세대수"), (args.tbl_id_worker, "직장인구")):
        if not tbl:
            continue
        rows, err = kosis_fetch(api_key, args.org_id, tbl, args.itm_id,
                                args.obj_l1, args.prd_se, args.prd_de)
        if err:
            print(f"  ✕ {항목} ({tbl}) — {err}", file=sys.stderr)
            continue
        cells, 버림 = kosis_to_cells(rows, areas, 항목)
        print(f"  ✓ {항목} ({tbl}) — 받은 행 {len(rows)} · 만든 행 {len(cells)}")
        for k, v in 버림.items():
            if v:
                print(f"      버림 {k} {v}건")
        묶음.append(cells)

    if not 묶음:
        print("한 표도 받지 못했습니다.", file=sys.stderr)
        return 1
    cells = merge_cells(묶음[0], 묶음[1] if len(묶음) > 1 else [])
    write_rows(cells, out)
    큰것 = [c for c in cells if to_f(c["한변_m"]) > 300]
    print(f"KOSIS 격자인구 — 구역 {len(cells)}개 → {out}")
    if 큰것:
        print(f"  🙋 {len(큰것)}개 구역이 한 변 300m 를 넘습니다. M2 가 P10 과 겹친 "
              f"면적비로 안분하면서 '격자가 아니다' 경고를 남깁니다 — 구역 안에서 "
              f"사람이 고르게 산다고 가정한 값입니다.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="통계청 SGIS 격자 인구를 받는다 (전국)")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--radius", type=float, default=DEFAULT_RADIUS,
                    help=f"--probe 의 bbox 후보를 부를 때 쓰는 반경 m (기본 {DEFAULT_RADIUS:g})")
    ap.add_argument("--live", action="store_true", help="실제로 호출한다(기본은 dry-run)")
    ap.add_argument("--source", default="sgis", choices=("sgis", "kosis"),
                    help="어느 기관에서 받을지. 둘 다 전국·무료이고 같은 자리를 채운다")
    ap.add_argument("--probe", action="store_true",
                    help="키로 인증한 뒤 후보 엔드포인트를 하나씩 눌러 보고 무엇이 "
                         "답하는지 그대로 출력한다. 이 출력이 연동을 확정하는 근거다")
    ap.add_argument("--adm-cd", default="11", help="--probe 에서 쓸 행정구역코드 (기본 11 = 서울)")
    ap.add_argument("--year", default="2023", help="--probe 에서 쓸 기준연도")
    # KOSIS 조회 — probe 로 표를 고른 뒤 여기에 넣는다. 코드를 고칠 필요가 없다.
    ap.add_argument("--areas", help="구역코드→면적·중심점 표 (CSV). KOSIS 조회에 필요하다")
    ap.add_argument("--make-areas", action="store_true",
                    help="--areas 표를 만든다. --live 를 함께 주면 SGIS 경계에서 "
                         "면적·중심점까지 채우고, 없으면 뼈대만 만든다")
    ap.add_argument("--level", default="행정동",
                    choices=tuple(BOUNDARY),
                    help="--make-areas --live 에서 받을 경계 단계. 유동인구에 쓸 "
                         "표라면 집계구 (기본 행정동)")
    ap.add_argument("--org-id", default="101", help="KOSIS 기관코드 (통계청=101)")
    ap.add_argument("--tbl-id-household", default="", help="세대수 통계표 ID")
    ap.add_argument("--tbl-id-worker", default="", help="종사자수 통계표 ID")
    ap.add_argument("--itm-id", default="ALL", help="KOSIS 항목 ID")
    ap.add_argument("--obj-l1", default="ALL", help="KOSIS 분류(행정구역) — 기본 전체")
    ap.add_argument("--prd-se", default="Y", help="수록주기 (Y=연간)")
    ap.add_argument("--prd-de", default="", help="기준시점 (비우면 최신 1건)")
    ap.add_argument("--find", action="append", default=[],
                    help="통계표 이름에서 찾을 낱말. 여러 번 줄 수 있다. "
                         "예: --find 세대 --find 종사자")
    ap.add_argument("--low-search", default="0",
                    help="1 이면 그 아래 단계(시군구→행정동)로 쪼개 받는다")
    ap.add_argument("--max-calls", type=int, default=60,
                    help="--find 가 쓸 최대 호출 수 (남의 API 다)")
    ap.add_argument("--auth-url", default=AUTH_URL)
    ap.add_argument("--out", default=str(ROOT / "output" / "격자인구.csv"))
    args = ap.parse_args(argv)

    sites_path = Path(args.sites)
    if not sites_path.exists():
        print(f"후보지 파일이 없습니다: {sites_path}", file=sys.stderr)
        return 1
    sites = read_csv(sites_path)
    boxes = sites_bboxes(sites, args.radius)
    out = Path(args.out)

    좌표없음 = len(sites) - len(boxes)
    key = os.environ.get("SGIS_KEY", "").strip()
    secret = os.environ.get("SGIS_SECRET", "").strip()

    if args.make_areas:
        표 = Path(args.areas or (ROOT / "output" / "행정구역.csv"))
        if args.live:
            return make_areas_live(args, sites, 표)
        return make_areas(sites, 표)

    if args.find:
        return kosis_find(os.environ.get("KOSIS_API_KEY", "").strip(),
                          args.find, 최대호출=args.max_calls)

    if args.probe:
        if args.source == "kosis":
            return kosis_probe(os.environ.get("KOSIS_API_KEY", "").strip())
        return probe(key, secret, args.auth_url, args.adm_cd, args.year,
                     boxes[0] if boxes else None)

    if args.source == "kosis":
        return kosis_run(args, out)
    return sgis_run(args, sites, out)


if __name__ == "__main__":
    raise SystemExit(main())
