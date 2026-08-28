#!/usr/bin/env python3
"""
통신사 유동인구 수집 · 반입 (전국)

M2 의 D_am 은 알고리즘에서 가장 크게 판정을 움직이는 값이다. 전국 후보지를 다루려면
전국 유동인구가 필요한데, **전국을 시간대별로 덮는 무료 공개 API 는 없다.** 확인한
사실이 이렇다:

  전국   KT PLIP · SKT 지오비전(전국 250개 시군구) · LG U+(50×50m 블록).
         셋 다 기업 계약이고 **공개 API 가 없다.** 계약하면 파일로 받으므로
         여기서는 '받아오는' 게 아니라 **반입(--import)** 한다. 지역별로 나눠 받은
         파일을 여러 개 한 번에 넣어 한 벌로 합칠 수 있다.
  지역   무료로 열린 것은 지역 단위로 파편화돼 있다. 서울 생활인구(KT LTE 시그널)가
         가장 쓸 만하고, 나머지는 공공데이터포털·빅데이터 플랫폼에 지자체별로
         흩어져 있으며 갱신이 끊긴 자료가 많다.

그래서 이 도구의 무게중심은 '전국 API 를 부른다' 가 아니라 **어디서 받았든 한 벌로
합치고, 어느 후보지가 비었는지 말해 주는 것**에 있다.

  python3 collect_carrier_flow.py --list
  python3 collect_carrier_flow.py --import 수도권.csv --import 영남.csv \
      --provider kt-plip --areas 집계구.csv
  python3 collect_carrier_flow.py --coverage --sites 후보지.csv          # ← 심의 전에 반드시
  SEOUL_OPENAPI_KEY=... python3 collect_carrier_flow.py --provider seoul-living --live \
      --areas 집계구.csv --date 20260801

⚠ **자료 공백이 시장 평가로 읽힌다 — 이게 전국으로 갈 때 가장 큰 위험이다.**
   유동인구가 없는 후보지는 D_am 이 0 이 된다. S 는 풀 안에서 min-max 정규화하고
   13개 지표 중 '오전유동' 과 '임대료대비객수효율' 둘이 D_am 에서 나오므로, 그
   후보지는 바닥에 깔린다. **상권이 나빠서가 아니라 자료를 못 받아서** 점수가
   낮아지는데 심의표만 보면 둘을 구분할 수 없다. `--coverage` 를 심의 전에 돌리고,
   빠진 지역을 채우거나 그 후보지를 풀에서 빼십시오.

⚠ **실측이 아니다.** 기지국 신호는 '그 구역에 있었다' 는 것이지 '그 앞을 걸어갔다' 가
   아니다. 명세가 요구하는 07~09시 현장 통행량 카운트를 대신하지 못하고, M2 가 이
   데이터를 쓰면 산출물에 그 사실이 경고로 남는다. 통신사 데이터의 값은 실측을
   대신하는 데 있는 게 아니라 **후보지를 추리는 단계에서 상권 단위보다 촘촘한 것**에
   있다.

⚠ **면적이 없으면 행을 만들지 않는다.** M2 는 영역 단위 값을 P5 면적비로 안분하므로
   구역 면적(단위면적_m2)이 반드시 필요하다. 면적을 추측해 나눈 값은 근거가 아니다.
   --areas 로 구역코드→면적 표를 주십시오. 이제 손으로 채우지 않아도 된다 —
   격자인구 쪽이 SGIS 경계에서 만들어 주고, 같은 표를 양쪽이 함께 쓴다:

       SGIS_KEY=... SGIS_SECRET=... python3 collect_grid_population.py \
           --make-areas --live --level 집계구 --sites 후보지.csv --areas 집계구.csv

   집계구·행정동 코드 체계는 전국 공통이라 표만 있으면 지역을 가리지 않는다.

⚠ **집계구를 쓰십시오** (--level 집계구). 행정동은 보통 1~3km² 인데 P5(도보 5분)는
   0.35km² 안팎이다. 중심점이 P5 안에 드는 행정동이 거의 없어 대부분 버려지고, 들어도
   면적비가 0.1 아래라 값이 뭉개진다. 집계구는 그보다 두 자릿수 작아 이 문제가 훨씬 덜하다.
   ⚠ 집계구 경계 주소는 아직 실제 호출로 확인하지 못했다(행정동은 확인됨).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import geo
from common import read_csv, to_f
from m2_demand import ALL, AM        # 시간대 표기는 M2 에서 가져온다 — 문자열이 어긋나면
                                     # 행은 멀쩡히 들어가고 D_am 만 0 이 된다

ROOT = Path(__file__).resolve().parent

# M2 가 먹는 유동인구.csv 와 같은 열. 여기에 통신사 표기를 위한 열을 덧붙인다.
HEADER = ["지점ID", "위도", "경도", "도로변", "시간대", "인원", "출처", "단위면적_m2",
          "구역코드", "구역명", "기준일"]

# ── 공급자 ────────────────────────────────────────────
# 각 공급자가 무엇을 주고 무엇을 요구하는지 한자리에 적는다. 화면에도 이대로 뜬다 —
# '어느 통신사를 쓸 수 있나' 는 질문에 코드를 읽지 않고 답할 수 있어야 한다.
PROVIDERS = {
    # ── 전국 · 계약형 ────────────────────────────────
    # 전국을 시간대별로 덮는 것은 지금 이 셋뿐이고, 셋 다 유료 계약이다.
    # 공개 API 가 없으므로 계약 후 받은 파일을 --import 로 넣는다.
    "kt-plip": {
        "이름": "KT PLIP (생활이동분석)",
        "통신사": "KT", "받는법": "반입", "키": "", "비용": "기업 계약",
        "범위": "전국", "단위": "행정동 · 계약 조건", "시간": "계약 조건",
        "주소": "https://enterprise.kt.com",
        "비고": "공개 API 없음. 전국을 덮으려면 이 경로가 현실적이다",
    },
    "skt-geovision": {
        "이름": "SKT 지오비전 (기업 계약)",
        "통신사": "SKT", "받는법": "반입", "키": "", "비용": "기업 계약",
        "범위": "전국 250개 시군구", "단위": "pCell · 행정동", "시간": "계약 조건",
        "주소": "https://puzzle.geovision.co.kr",
        "비고": "기지국 RU 단위 측위. 공개 API 없음 — --import 로 넣는다",
    },
    "lgu-flow": {
        "이름": "LG U+ 유동인구",
        "통신사": "LG U+", "받는법": "반입", "키": "", "비용": "기업 계약",
        "범위": "전국", "단위": "50×50m 블록 · 행정동", "시간": "계약 조건",
        "주소": "", "비고": "격자가 가장 촘촘하다. 공개 API 없음 — --import 로 넣는다",
    },

    # ── 지역 · 무료 ──────────────────────────────────
    # 무료로 열려 있는 것은 지역 단위로 파편화돼 있다. 후보지가 그 지역 밖이면
    # 아무것도 못 받는다 — 그 사실을 --coverage 가 후보지별로 말해 준다.
    "seoul-living": {
        "이름": "서울 생활인구 (KT LTE 시그널)",
        "통신사": "KT", "받는법": "API", "키": "SEOUL_OPENAPI_KEY", "비용": "무료",
        "범위": "서울시", "단위": "집계구 · 행정동", "시간": "1시간 (4일 전까지)",
        "주소": "https://data.seoul.go.kr",
        "비고": "서울시와 KT 가 함께 만든 자료. 무료 통신사 데이터는 사실상 이것뿐이다",
    },
    "skt-puzzle": {
        "이름": "SKT 지오비전 퍼즐 (공개 API)",
        "통신사": "SKT", "받는법": "API", "키": "SKT_OPENAPI_APPKEY",
        "비용": "앱키 발급 + 상품 승인 (무료 범위 있음)",
        "범위": "전국 (상품마다 다름)", "단위": "격자 · 행정동", "시간": "상품마다 다름",
        "주소": "https://openapi.sk.com",
        "비고": "엔드포인트와 응답 형식을 확인하지 못했다 — 지금은 --import 를 쓰십시오",
    },
    "public-portal": {
        "이름": "공공데이터포털 · 빅데이터 플랫폼 (지자체 파일)",
        "통신사": "지자체별 상이", "받는법": "반입", "키": "", "비용": "무료 (가입 필요)",
        "범위": "지자체별", "단위": "시군구 · 행정동", "시간": "자료마다 다름",
        "주소": "https://www.data.go.kr",
        "비고": "전국 통합본이 없고 지자체별로 흩어져 있다. 갱신이 끊긴 자료가 많으니 "
              "기준일을 확인하고 넣으십시오",
    },
}

# 서울 열린데이터광장 서비스명. 문서로 확인하지 못해 --service 로 갈아끼울 수 있게 둔다.
SEOUL_BASE = "http://openapi.seoul.go.kr:8088"
SEOUL_SERVICE = "SPOP_LOCAL_RESD_JACHI"

# 반입 파일의 열 이름은 통신사마다 다르다. 흔한 표기를 함께 받고, 못 찾으면
# --map 으로 직접 이어 준다. 추측해서 아무 열이나 집지 않는다.
IMPORT_FIELDS = {
    "구역코드": ["구역코드", "집계구코드", "집계구_코드", "TOT_REG_CD", "행정동코드",
              "ADM_CD", "adm_cd", "격자코드", "grid_id", "code"],
    "구역명": ["구역명", "행정동명", "ADM_NM", "adm_nm", "name", "지역명"],
    "인원": ["인원", "유동인구", "유동인구수", "생활인구", "생활인구수", "총생활인구수",
            "TOT_LVPOP_CO", "population", "value", "cnt"],
    "시간": ["시간", "시간대", "시간대구분", "TMZON_PD_SE", "hour", "hh"],
    "날짜": ["날짜", "기준일", "기준일자", "STDR_DE_ID", "date", "ymd"],
    "위도": ["위도", "lat", "LAT", "y"],
    "경도": ["경도", "lon", "lng", "LON", "x"],
    "면적": ["면적", "면적_m2", "area", "AREA", "구역면적"],
}


# 통신사 파일은 대개 엑셀을 거쳐 온다. 거기서 전각 숫자(３００)나 뒤에 붙은 단위가
# 섞여 들어오는데, common.to_f 는 손으로 적은 값을 너그럽게 읽도록 만든 함수라
# '318.２' 를 318.0 으로, '３００' 을 0 으로 조용히 바꾼다. 다른 모듈에는 그 관대함이
# 맞지만 **인원 수에는 맞지 않는다** — 잘린 숫자와 0 이 그대로 D_am 에 들어간다.
# 그래서 여기서는 따로 읽고, 못 읽으면 0 으로 만들지 말고 그 행을 버린다.
전각 = str.maketrans("０１２３４５６７８９．，", "0123456789.,")


def 숫자(v):
    """숫자로 읽거나 None. 애매하면 None 이다 — 0 으로 만들지 않는다."""
    s = str(v if v is not None else "").translate(전각).strip()
    s = s.replace(",", "").replace(" ", "")
    if s.endswith(("명", "인")):
        s = s[:-1]
    if not s:
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n == n and abs(n) != float("inf") else None


def pick(row: dict, names: list[str], extra: dict = None) -> str:
    """별칭 목록에서 처음 찾히는 값. --map 으로 준 이름을 먼저 본다."""
    for n in (extra or []):
        if n in row and str(row[n]).strip() != "":
            return str(row[n]).strip()
    for n in names:
        if n in row and str(row[n]).strip() != "":
            return str(row[n]).strip()
    return ""


def load_areas(path) -> dict:
    """구역코드 → {면적_m2, 위도, 경도}. 없으면 빈 표.

    면적은 M2 의 안분에 반드시 필요하고, 중심점 좌표는 그 구역이 P5 안인지 판단하는
    데 쓴다. 통계청 SGIS 집계구 경계에서 만들 수 있다.
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    out = {}
    for r in read_csv(p):
        code = pick(r, ["구역코드", "집계구코드", "TOT_REG_CD", "행정동코드", "ADM_CD", "code"])
        if not code:
            continue
        out[code] = {
            "면적_m2": 숫자(pick(r, IMPORT_FIELDS["면적"])) or 0.0,
            "위도": 숫자(pick(r, IMPORT_FIELDS["위도"])) or 0.0,
            "경도": 숫자(pick(r, IMPORT_FIELDS["경도"])) or 0.0,
        }
    return out


def 시간대(v: str) -> str:
    """통신사 자료의 시간 표기를 M2 의 구간으로 옮긴다.

    명세의 07~09시에 해당하는 것만 AM 으로 본다. 08시 한 시간만 있으면 그것도 AM 이다
    — 좁게 잡는 쪽이 D_am 을 부풀리지 않는다.

    반환값은 m2_demand 의 AM/ALL 을 그대로 쓴다. 여기서 따로 문자열을 적으면 어긋났을 때
    행은 멀쩡히 들어가고 D_am 만 0 이 된다 — 아무도 알아채지 못하는 종류의 실패다.
    """
    s = str(v or "").strip()
    if not s:
        return ALL
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ALL
    try:
        h = int(digits[:2]) if len(digits) >= 2 else int(digits)
    except ValueError:
        return ALL
    return AM if 7 <= h <= 9 else ""


def to_rows(records: list[dict], areas: dict, 출처: str, 기준일: str = "",
            mapping: dict = None) -> tuple[list[dict], dict]:
    """공급자 응답/반입 파일 → 유동인구 행. 만들 수 없는 행은 만들지 않는다."""
    mapping = mapping or {}
    rows, 버림 = [], {"면적없음": 0, "좌표없음": 0, "인원없음": 0,
                     "인원_숫자아님": 0, "시간대밖": 0}
    for r in records:
        code = pick(r, IMPORT_FIELDS["구역코드"], [mapping.get("구역코드")])
        raw = pick(r, IMPORT_FIELDS["인원"], [mapping.get("인원")])
        n = 숫자(raw)
        if n is None:
            # 읽지 못한 값을 0 으로 바꾸면 그 구역이 '사람 없는 곳' 이 된다
            버림["인원_숫자아님" if raw else "인원없음"] += 1
            continue
        if n <= 0:
            버림["인원없음"] += 1
            continue
        band = 시간대(pick(r, IMPORT_FIELDS["시간"], [mapping.get("시간")]))
        if band == "":
            버림["시간대밖"] += 1
            continue

        info = areas.get(code, {})
        면적 = 숫자(pick(r, IMPORT_FIELDS["면적"], [mapping.get("면적")])) or info.get("면적_m2", 0)
        lat = 숫자(pick(r, IMPORT_FIELDS["위도"], [mapping.get("위도")])) or info.get("위도", 0)
        lon = 숫자(pick(r, IMPORT_FIELDS["경도"], [mapping.get("경도")])) or info.get("경도", 0)

        # 면적을 모르면 M2 가 안분할 수 없다. 추측한 면적으로 나눈 값은 근거가 아니므로
        # 행 자체를 만들지 않는다 — 만들어 두면 산출물에 '버렸다' 는 경고만 쌓인다.
        if 면적 <= 0:
            버림["면적없음"] += 1
            continue
        if not (lat and lon):
            버림["좌표없음"] += 1
            continue

        rows.append({
            "지점ID": f"{출처}:{code}" if code else 출처,
            "위도": lat, "경도": lon,
            "도로변": "",          # 기지국 데이터에는 도로 좌·우 구분이 없다
            "시간대": band,
            "인원": round(n, 2),
            "출처": 출처,
            "단위면적_m2": round(면적, 1),
            "구역코드": code,
            "구역명": pick(r, IMPORT_FIELDS["구역명"], [mapping.get("구역명")]),
            "기준일": pick(r, IMPORT_FIELDS["날짜"], [mapping.get("날짜")]) or 기준일,
        })
    return rows, 버림


# ── API 공급자 ────────────────────────────────────────
def fetch_seoul(key: str, service: str, start: int, end: int,
                date: str, base: str = SEOUL_BASE) -> tuple[str, str]:
    url = (f"{base}/{urllib.parse.quote(key, safe='')}/json/{service}/"
           f"{start}/{end}/{urllib.parse.quote(date)}")
    try:
        with urllib.request.urlopen(url, timeout=25,
                                    context=ssl.create_default_context()) as r:
            return r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except OSError as e:
        return "", f"네트워크 오류: {e}"


def parse_seoul(body: str, service: str) -> tuple[list[dict], str]:
    """열린데이터광장은 오류도 HTTP 200 + JSON 으로 보낸다."""
    try:
        doc = json.loads(body)
    except ValueError as e:
        return [], f"JSON 파싱 실패: {e}"
    node = doc.get(service) or next(
        (v for v in doc.values() if isinstance(v, dict) and "row" in v), None)
    if node is None:
        msg = json.dumps(doc, ensure_ascii=False)[:400]
        return [], f"예상한 형태가 아닙니다: {msg}"
    result = node.get("RESULT") or {}
    code = str(result.get("CODE", ""))
    if code and code != "INFO-000":
        return [], f"{code} {result.get('MESSAGE', '')}"
    rows = node.get("row") or []
    return (rows, "") if rows else ([], "행이 없습니다")


def write_rows(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in HEADER} for r in rows])
    return path


def dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    """같은 (구역코드, 시간대, 기준일) 이 여러 파일에 겹쳐 오는 일이 흔하다.
    지역별로 나눠 받은 파일이 경계에서 겹치거나, 같은 달을 두 번 받거나.
    그대로 더하면 D_am 이 겹친 만큼 부풀고, 그 후보지만 근거 없이 좋아 보인다."""
    본것, out, 중복 = set(), [], 0
    for r in rows:
        k = (r["구역코드"], r["시간대"], r["기준일"])
        if k in 본것:
            중복 += 1
            continue
        본것.add(k)
        out.append(r)
    return out, 중복


def coverage(sites_path: Path, flow_path: Path, radius: float,
             strict: bool = False) -> int:
    """후보지별로 유동인구 데이터가 있는가.

    전국을 다루면 커버리지가 반드시 듬성듬성해진다. 그런데 **데이터가 없는 후보지는
    D_am 이 0 이 되고, S 는 풀 안 min-max 정규화라 그 후보지가 바닥에 깔린다.**
    S 의 13개 지표 중 '오전유동' 과 '임대료대비객수효율' 둘이 D_am 에서 나오기
    때문이다. 상권이 나빠서가 아니라 **자료를 못 받아서** 점수가 낮아지는데,
    심의표만 보면 둘을 구분할 수 없다.

    그래서 심의를 돌리기 전에 여기서 먼저 말한다. P5 는 등시선이라야 정확하지만
    사전 점검이므로 도보 5분 반경으로 근사한다(그 사실을 화면에도 적는다).
    """
    if not sites_path.exists():
        print(f"후보지 파일이 없습니다: {sites_path}", file=sys.stderr)
        return 1
    sites = read_csv(sites_path)
    flow = read_csv(flow_path) if flow_path.exists() else []

    표 = []
    빈곳 = 0
    for st in sites:
        lat, lon = to_f(st.get("위도")), to_f(st.get("경도"))
        name = str(st.get("후보지명", "")).strip() or "(이름 없음)"
        if not (lat and lon):
            표.append((name, "좌표 없음", 0, 0, set()))
            빈곳 += 1
            continue
        n_am = n_all = 0
        출처 = set()
        for r in flow:
            flat, flon = to_f(r.get("위도")), to_f(r.get("경도"))
            if not (flat and flon):
                continue
            x, y = geo.project(lat, lon, flat, flon)
            if (x * x + y * y) ** 0.5 > radius:
                continue
            출처.add(str(r.get("출처", "")).strip())
            if str(r.get("시간대", "")).strip() == AM:
                n_am += 1
            else:
                n_all += 1
        표.append((name, "", n_am, n_all, 출처))
        if n_am == 0:
            빈곳 += 1

    print(f"유동인구 커버리지 — 후보지 {len(sites)}곳 · 반경 {radius:g}m "
          f"(도보 5분 근사, 실제 P5 는 등시선으로 계산됩니다)")
    print(f"{'후보지':<24} {'오전':>5} {'전체':>5}  출처")
    for name, 문제, n_am, n_all, 출처 in 표:
        src = 문제 or (", ".join(sorted(x for x in 출처 if x)) or "—")
        mark = " " if n_am else "!"
        print(f"{mark}{name:<23} {n_am:>5} {n_all:>5}  {src}")

    if 빈곳:
        print()
        print(f"⛔ {빈곳}곳에 오전 유동인구 데이터가 없습니다.")
        print("   이대로 심의를 돌리면 그 후보지는 D_am 이 0 이 됩니다. S 는 풀 안에서")
        print("   min-max 정규화하므로 바닥에 깔리고, 13개 지표 중 '오전유동' 과")
        print("   '임대료대비객수효율' 둘이 그 값에서 나옵니다 —")
        print("   **상권이 나빠서가 아니라 자료를 못 받아서 점수가 낮아집니다.**")
        print("   심의표만 보면 그 둘을 구분할 수 없습니다.")
        print()
        print("   할 수 있는 것:")
        print("   · 그 지역 자료를 마저 받아 --import 로 합치십시오(여러 파일을 한 번에).")
        print("   · 못 받으면 그 후보지를 이번 풀에서 빼십시오 — 자료가 있는 후보지끼리")
        print("     비교해야 S 가 뜻을 갖습니다.")
        print("   · 무료로 열린 것은 지역별로 흩어져 있습니다(--list 참고). 전국을")
        print("     시간대별로 덮으려면 통신사 계약이 현실적입니다.")
    else:
        print("\n모든 후보지에 오전 유동인구가 있습니다.")
    return 1 if (strict and 빈곳) else 0


def 목록() -> str:
    L = ["# 통신사 유동인구 공급자", "",
         "| 키 | 이름 | 통신사 | 받는 법 | 비용 | 범위 | 단위 | 비고 |",
         "|---|---|---|---|---|---|---|---|"]
    for k, p in PROVIDERS.items():
        L.append(f"| `{k}` | {p['이름']} | {p['통신사']} | {p['받는법']} | {p['비용']} | "
                 f"{p['범위']} | {p['단위']} | {p['비고']} |")
    L += ["",
          "**받는 법이 `반입` 인 것은 공개 API 가 없습니다.** 계약 후 받은 파일을 "
          "`--import 파일 --provider 키` 로 넣으십시오. 열 이름이 달라도 흔한 표기는 "
          "알아서 찾고, 못 찾으면 `--map 인원=컬럼명` 으로 이어 줍니다.", "",
          "**어느 경로든 실측이 아닙니다.** 기지국 신호는 '그 구역에 있었다' 이지 "
          "'그 앞을 걸어갔다' 가 아닙니다. M2 가 쓰면 산출물에 그 사실이 경고로 남습니다."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="통신사 유동인구를 받거나 반입한다")
    ap.add_argument("--list", action="store_true", help="공급자 목록을 보여 준다")
    ap.add_argument("--provider", default="seoul-living", choices=sorted(PROVIDERS))
    ap.add_argument("--import", dest="import_paths", action="append", default=[],
                    help="계약으로 받은 파일(CSV). 여러 번 줄 수 있다 — 지역별로 나눠 "
                         "받은 파일을 한 벌로 합친다")
    ap.add_argument("--coverage", action="store_true",
                    help="후보지별로 유동인구 데이터가 있는지 확인한다 (--sites 필요)")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--flow", default=str(ROOT / "output" / "유동인구_통신사.csv"))
    ap.add_argument("--radius", type=float, default=333.0,
                    help="커버리지 확인 반경 m (도보 5분 근사, 기본 333)")
    ap.add_argument("--strict", action="store_true",
                    help="데이터 없는 후보지가 하나라도 있으면 0 이 아닌 코드로 끝낸다")
    ap.add_argument("--areas", help="구역코드→면적·중심점 표 (CSV)")
    ap.add_argument("--map", action="append", default=[],
                    help="열 이름 잇기. 예: --map 인원=총생활인구수")
    ap.add_argument("--date", default="", help="기준일 YYYYMMDD (API 공급자용)")
    ap.add_argument("--service", default=SEOUL_SERVICE, help="서울 열린데이터광장 서비스명")
    ap.add_argument("--rows", type=int, default=1000, help="API 한 번에 받을 행 수")
    ap.add_argument("--live", action="store_true", help="실제로 호출한다(기본은 dry-run)")
    ap.add_argument("--out", default=str(ROOT / "output" / "유동인구_통신사.csv"))
    args = ap.parse_args(argv)

    if args.list:
        print(목록())
        return 0

    prov = PROVIDERS[args.provider]
    mapping = {}
    for m in args.map:
        if "=" in m:
            k, v = m.split("=", 1)
            mapping[k.strip()] = v.strip()
    areas = load_areas(args.areas)
    out = Path(args.out)

    if args.coverage:
        return coverage(Path(args.sites), Path(args.flow), args.radius, args.strict)

    # ── 반입 ──────────────────────────────────────
    if args.import_paths:
        records, 원본 = [], 0
        for one in args.import_paths:
            p = Path(one)
            if not p.exists():
                print(f"파일이 없습니다: {p}", file=sys.stderr)
                return 1
            got = read_csv(p)
            원본 += len(got)
            records += got
        rows, 버림 = to_rows(records, areas, prov["이름"], mapping=mapping)
        # 같은 구역이 여러 파일에 겹쳐 오면 합계가 부풀어 D_am 이 배로 뛴다
        rows, 중복 = dedupe(rows)
        write_rows(rows, out)
        print(f"반입 {prov['이름']} — 파일 {len(args.import_paths)}개 · "
              f"읽은 행 {원본} · 만든 행 {len(rows)}")
        if 중복:
            print(f"  겹친 구역 {중복}건은 한 번만 넣었습니다 — 그대로 두면 D_am 이 "
                  f"겹친 만큼 부풀어 오릅니다")
        for k, v in 버림.items():
            if v:
                print(f"  버림 {k} {v}건")
        if 버림["인원_숫자아님"]:
            print("  🙋 인원 칸을 숫자로 읽지 못한 행이 있습니다(전각 숫자·단위 표기 등). "
                  "0 으로 바꾸지 않고 버렸습니다 — 0 으로 두면 사람이 없는 구역이 됩니다.")
        if 버림["면적없음"]:
            print("  🙋 면적을 모르는 구역은 행을 만들지 않았습니다. M2 는 영역 값을 "
                  "P5 면적비로 안분하므로 구역 면적이 필요합니다 — --areas 로 "
                  "구역코드→면적 표를 주십시오(통계청 SGIS 집계구 경계).")
        print(f"  → {out}")
        print("  다음: --coverage 로 후보지별 데이터 유무를 확인하십시오 — "
              "빠진 후보지는 D_am 이 0 이 되고, 그게 시장 평가처럼 읽힙니다.")
        return 0

    # ── API ───────────────────────────────────────
    if prov["받는법"] != "API":
        print(f"{prov['이름']} 는 공개 API 가 없습니다. 계약으로 받은 파일을 "
              f"--import 로 넣으십시오.", file=sys.stderr)
        return 2

    key = os.environ.get(prov["키"], "").strip()
    if not args.live:
        write_rows([], out)
        print(f"dry-run — {prov['이름']} 를 호출하지 않았습니다.")
        print(f"  키 {prov['키']} {'있음' if key else '없음'} · 비용 {prov['비용']}")
        print(f"  실제로 받으려면: {prov['키']}=... python3 {Path(__file__).name} "
              f"--provider {args.provider} --live --areas 집계구.csv")
        print("  ※ dry-run 은 인원 수를 만들어 내지 않습니다 — 지어낸 유동인구가 "
              "심의표에 실리면 실측으로 오인됩니다.")
        print(f"  → {out} (빈 표)")
        return 0

    if not key:
        print(f"{prov['키']} 가 없습니다. {prov['주소']} 에서 발급하십시오.", file=sys.stderr)
        return 2
    if args.provider != "seoul-living":
        print(f"{prov['이름']} 의 엔드포인트를 아직 확인하지 못했습니다. "
              f"지금은 --import 로 넣으십시오.", file=sys.stderr)
        return 2
    if not args.date:
        print("--date YYYYMMDD 가 필요합니다 (4일 전까지 조회됩니다).", file=sys.stderr)
        return 2

    body, err = fetch_seoul(key, args.service, 1, args.rows, args.date)
    if err:
        print(f"호출 실패: {err}", file=sys.stderr)
        return 1
    records, perr = parse_seoul(body, args.service)
    if perr:
        print(f"응답을 읽지 못했습니다: {perr}", file=sys.stderr)
        print("--- 응답 앞부분 ---", file=sys.stderr)
        print(body[:800], file=sys.stderr)
        print(f"이 출력을 보고 --service 나 IMPORT_FIELDS 를 고치십시오.", file=sys.stderr)
        return 1

    rows, 버림 = to_rows(records, areas, prov["이름"], 기준일=args.date, mapping=mapping)
    write_rows(rows, out)
    print(f"{prov['이름']} — 받은 행 {len(records)} · 만든 행 {len(rows)}")
    for k, v in 버림.items():
        if v:
            print(f"  버림 {k} {v}건")
    print(f"  → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
