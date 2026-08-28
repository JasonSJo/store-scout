#!/usr/bin/env python3
"""
M2 보조 · 유동인구 대용 수집 (서울시 상권분석서비스)

명세가 요구하는 것은 **07~09시 현장 통행량 실측 카운트**다. 이 도구는 그것을 만들지
못한다. 대신 서울시 상권분석서비스의 **길단위인구(상권 단위)** 를 받아 후보지가 속한
상권 값을 P5 면적비로 안분할 수 있는 형태로 내려준다.

  python3 collect_foot_traffic.py                       # dry-run (호출 없음)
  SEOUL_OPENAPI_KEY=... python3 collect_foot_traffic.py --live

⚠ **실측의 대체가 아니라 대용이다.** 세 겹의 오차가 겹친다.

  1. 영역 → 지점.  상권 전체 값을 P5 면적비로 안분한다. 균등분포를 가정하므로
     간선도로변 집중이 반영되지 않는다(config.유동_안분_집중계수, 기본 1.0 · 미검증).
  2. 시간대.  공개 데이터의 구간은 06~11시다. 명세의 07~09시보다 넓어 출근과
     무관한 통행이 섞이고, D_am 이 실제보다 크게 잡힌다.
  3. 도로변.  상권 단위 값에는 도로 좌·우 구분이 없다. 횡단저항을 적용할 수 없어
     M2 가 전부 '같은 편' 으로 계산하고 경고를 남긴다.

  세 오차 모두 D_am 을 **과대평가하는 방향**이다. 즉 이 값으로 나온 통과는
  낙관 쪽으로 치우쳐 있다. 최종 심의 전에는 실측 카운트로 교체해야 한다.

⚠ **서비스명과 응답 필드명이 실제 호출로 검증되지 않았다.** 서비스키가 없어 한 번도
   호출해 보지 못했다. 상권영역 서비스명(TbgisTrdarRelm)과 호출 형식은 문서에서
   확인했으나, 길단위인구 서비스명과 컬럼명은 관례를 따른 추정이다. 파서는 여러
   표기를 함께 받고 하나도 못 읽으면 응답 앞부분을 그대로 출력한다 —
   그 출력을 보고 --service / FIELDS 를 고치면 된다.
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

import geo
from common import read_csv, to_f, write_text

ROOT = Path(__file__).resolve().parent
BASE = "http://openapi.seoul.go.kr:8088"

# 상권영역 — 호출 형식과 서비스명은 문서에서 확인했다
SVC_AREA = "TbgisTrdarRelm"
# 길단위인구(상권) — 관례를 따른 추정. 다르면 --service-flow 로 갈아끼운다
SVC_FLOW = "VwsmTrdarFlpopQq"

HEADER = ["지점ID", "위도", "경도", "도로변", "시간대", "인원", "출처", "단위면적_m2",
          "상권코드", "상권명", "기준분기"]

# 응답 필드명 후보 — 표기가 바뀌어도 하나만 맞으면 읽힌다
AREA_FIELDS = {
    "상권코드": ["TRDAR_CD", "trdarCd", "상권_코드"],
    "상권명": ["TRDAR_CD_NM", "trdarCdNm", "상권_코드_명"],
    "엑스": ["XCNTS_VALUE", "xcntsValue", "엑스좌표_값"],
    "와이": ["YDNTS_VALUE", "ydntsValue", "와이좌표_값"],
    "면적": ["RELM_AR", "relmAr", "영역_면적"],
}
FLOW_FIELDS = {
    "상권코드": ["TRDAR_CD", "trdarCd", "상권_코드"],
    "상권명": ["TRDAR_CD_NM", "trdarCdNm", "상권_코드_명"],
    "기준분기": ["STDR_YYQU_CD", "stdrYyquCd", "기준_년분기_코드"],
    "전체": ["TOT_FLPOP_CO", "totFlpopCo", "총_유동인구_수"],
    # 06~11시 구간 — 명세의 07~09시보다 넓다
    "오전": ["TMZON_06_11_FLPOP_CO", "tmzon0611FlpopCo", "시간대_06_11_유동인구_수",
            "TMZON_2_FLPOP_CO"],
}

# 서울시 좌표계(EPSG:5181, 중부원점TM)를 위경도로 옮기는 근사식은 쓰지 않는다.
# 상권영역이 좌표계를 어떤 형식으로 주는지 확인하지 못했으므로, 값이 위경도 범위면
# 그대로 쓰고 아니면 그 행을 버린다 — 잘못 변환한 좌표는 상권을 통째로 옮긴다.
LAT_RANGE = (33.0, 39.0)
LON_RANGE = (124.0, 132.0)


def pick(item: dict, names: list[str]) -> str:
    for n in names:
        if n in item and str(item[n]).strip() != "":
            return str(item[n]).strip()
    return ""


def fetch(key: str, service: str, start: int, end: int, base: str = BASE):
    url = f"{base}/{urllib.parse.quote(key, safe='')}/json/{service}/{start}/{end}/"
    try:
        with urllib.request.urlopen(url, timeout=20,
                                    context=ssl.create_default_context()) as r:
            return r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except OSError as e:
        return "", f"네트워크 오류: {e}"


def parse(body: str, service: str) -> tuple[list[dict], str]:
    """서울 열린데이터광장은 오류도 200 으로 JSON 에 담아 보낸다."""
    try:
        doc = json.loads(body)
    except ValueError as e:
        return [], f"JSON 파싱 실패: {e}"
    node = doc.get(service) or next(
        (v for v in doc.values() if isinstance(v, dict) and "row" in v), None)
    if node is None:
        res = doc.get("RESULT") or {}
        return [], f"API 오류 {res.get('CODE', '?')}: {res.get('MESSAGE', body[:120])}"
    res = node.get("RESULT") or {}
    code = str(res.get("CODE", "")).strip()
    if code and code != "INFO-000":
        return [], f"API 오류 {code}: {res.get('MESSAGE', '')}"
    rows = node.get("row") or []
    return rows, "" if rows else "항목을 하나도 읽지 못했습니다"


def page_all(key: str, service: str, base: str, limit: int, log=None):
    """1000행씩 끊어 받는다(포털 상한). 한 페이지라도 실패하면 그대로 알린다."""
    out, problems, step = [], [], 1000
    for start in range(1, max(1, limit) + 1, step):
        end = min(start + step - 1, limit)
        body, err = fetch(key, service, start, end, base)
        if err:
            problems.append(f"{service} {start}-{end}: {err}")
            break
        rows, perr = parse(body, service)
        if perr and not rows:
            problems.append(f"{service} {start}-{end}: {perr}")
            if len(problems) == 1 and log:
                log("    ↓ 응답 앞부분 (형식이 다르면 이걸 보고 서비스명·FIELDS 를 고치십시오)")
                log("    " + body[:400].replace("\n", "\n    "))
            break
        out += rows
        if log:
            log(f"    {service} {start}-{end} … {len(rows)}건")
        if len(rows) < (end - start + 1):
            break
    return out, problems


def areas_of(rows: list[dict]) -> dict:
    """상권코드 → {위도, 경도, 면적_m2, 상권명}. 좌표가 위경도 범위 밖이면 버린다."""
    out = {}
    for r in rows:
        code = pick(r, AREA_FIELDS["상권코드"])
        x, y = to_f(pick(r, AREA_FIELDS["엑스"])), to_f(pick(r, AREA_FIELDS["와이"]))
        area = to_f(pick(r, AREA_FIELDS["면적"]))
        if not code or area <= 0:
            continue
        lat, lon = (y, x) if (LAT_RANGE[0] <= y <= LAT_RANGE[1]) else (0.0, 0.0)
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
            continue          # 좌표계를 확인하지 못했다 — 변환을 추측하지 않는다
        out[code] = {"위도": lat, "경도": lon, "면적_m2": area,
                     "상권명": pick(r, AREA_FIELDS["상권명"])}
    return out


def latest_by_area(rows: list[dict]) -> dict:
    """상권코드 → 가장 최근 분기의 유동인구 행."""
    out = {}
    for r in rows:
        code = pick(r, FLOW_FIELDS["상권코드"])
        if not code:
            continue
        q = pick(r, FLOW_FIELDS["기준분기"])
        cur = out.get(code)
        if cur is None or q > cur["기준분기"]:
            out[code] = {"기준분기": q,
                         "전체": to_f(pick(r, FLOW_FIELDS["전체"])),
                         "오전": to_f(pick(r, FLOW_FIELDS["오전"])),
                         "상권명": pick(r, FLOW_FIELDS["상권명"])}
    return out


def nearest(lat: float, lon: float, areas: dict, max_m: float) -> tuple[str, float]:
    """후보지를 감싸는 상권을 고른다. 폴리곤이 없으므로 중심거리로 고르고, 그 거리가
    상권 반경(면적에서 역산한 등가원)을 넘으면 매칭하지 않는다 — 옆 동네 상권 값을
    끌어다 쓰면 D_am 이 통째로 다른 곳의 숫자가 된다."""
    best, best_d = "", None
    for code, a in areas.items():
        dx, dy = geo.project(lat, lon, a["위도"], a["경도"])
        d = math.hypot(dx, dy)
        radius = math.sqrt(a["면적_m2"] / math.pi)
        if d > min(max_m, radius):
            continue
        if best_d is None or d < best_d:
            best, best_d = code, d
    return best, (best_d if best_d is not None else -1.0)


def rows_for(sites: list[dict], areas: dict, flows: dict, max_m: float):
    """후보지별로 유동인구 CSV 행을 만든다. 매칭 실패는 지어내지 않고 그대로 알린다."""
    out, missed = [], []
    for s in sites:
        name = (s.get("후보지명") or "").strip()
        lat, lon = to_f(s.get("위도")), to_f(s.get("경도"))
        if not name or not lat or not lon:
            continue
        code, dist = nearest(lat, lon, areas, max_m)
        f = flows.get(code) if code else None
        if not f:
            missed.append(name)
            continue
        a = areas[code]
        for band in ("오전", "전체"):
            if f[band] <= 0:
                continue
            out.append({
                "지점ID": name, "위도": lat, "경도": lon,
                "도로변": "",                       # 상권 단위 값에는 좌·우 구분이 없다
                "시간대": band, "인원": round(f[band]),
                "출처": "길단위인구_상권", "단위면적_m2": round(a["면적_m2"]),
                "상권코드": code, "상권명": a["상권명"] or f["상권명"],
                "기준분기": f["기준분기"],
            })
    return out, missed


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in HEADER} for r in rows])


def main() -> int:
    ap = argparse.ArgumentParser(description="유동인구 대용 수집 (서울시 상권분석서비스)")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--out", default=str(ROOT / "output" / "유동인구_대용.csv"))
    ap.add_argument("--summary", default=str(ROOT / "output" / "유동인구_대용.md"))
    ap.add_argument("--service-area", default=SVC_AREA, help="상권영역 서비스명")
    ap.add_argument("--service-flow", default=SVC_FLOW, help="길단위인구 서비스명")
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--limit", type=int, default=4000, help="서비스당 최대 수집 행 수")
    ap.add_argument("--max-m", type=float, default=800.0,
                    help="후보지-상권중심 최대 허용 거리(m)")
    ap.add_argument("--live", action="store_true", help="실제 호출 (SEOUL_OPENAPI_KEY 필요)")
    args = ap.parse_args()

    out = Path(args.out)
    sites = read_csv(Path(args.sites)) if Path(args.sites).exists() else []
    named = [s for s in sites if (s.get("후보지명") or "").strip()
             and to_f(s.get("위도")) and to_f(s.get("경도"))]

    if not args.live:
        # 통행량을 지어내지 않는다 — 심의표에 그대로 실려 실측으로 오인된다.
        write_rows(out, [])
        print(f"[dry-run] API 를 호출하지 않았습니다 — 빈 표만 만들었습니다: {out}")
        print(f"  좌표가 있는 후보지 {len(named)}곳: "
              + (", ".join(s["후보지명"] for s in named) or "없음"))
        print("  실제 수집: SEOUL_OPENAPI_KEY=... python3 collect_foot_traffic.py --live")
        print("  ⚠ 서울시 데이터입니다. 서울 밖 후보지는 매칭되지 않습니다.")
        return 0

    key = os.environ.get("SEOUL_OPENAPI_KEY", "").strip()
    if not key:
        print("SEOUL_OPENAPI_KEY 환경변수가 없습니다.\n"
              "  서울 열린데이터광장(data.seoul.go.kr)에서 인증키를 발급받으십시오.",
              file=sys.stderr)
        return 1
    if not named:
        print("좌표가 있는 후보지가 없습니다 — 입력 페이지에서 주소를 검색해 채우십시오.",
              file=sys.stderr)
        return 1

    print("  상권 영역 수집…")
    a_rows, a_prob = page_all(key, args.service_area, args.base, args.limit, log=print)
    print("  길단위인구 수집…")
    f_rows, f_prob = page_all(key, args.service_flow, args.base, args.limit, log=print)

    areas, flows = areas_of(a_rows), latest_by_area(f_rows)
    rows, missed = rows_for(named, areas, flows, args.max_m)
    write_rows(out, rows)

    L = ["# 유동인구 대용 (서울시 상권분석서비스 · 길단위인구)", "",
         f"상권 {len(areas)}개 · 유동인구 {len(flows)}개 · 후보지 매칭 "
         f"{len(named) - len(missed)}/{len(named)}", "",
         "> ⛔ **실측이 아닙니다.** 상권 전체 값을 P5 면적비로 안분하고, 시간대 구간은 "
         "06~11시로 명세의 07~09시보다 넓으며, 도로 좌·우 구분이 없습니다. "
         "세 오차 모두 D_am 을 **과대평가하는 방향**입니다.", "",
         "| 후보지 | 상권 | 기준분기 | 오전 | 전체 | 상권면적(㎡) |",
         "|---|---|---|---:|---:|---:|"]
    seen = {}
    for r in rows:
        seen.setdefault(r["지점ID"], {})[r["시간대"]] = r
    for name, bands in seen.items():
        any_r = next(iter(bands.values()))
        L.append(f"| {name} | {any_r['상권명']} | {any_r['기준분기']} | "
                 f"{bands.get('오전', {}).get('인원', 0):,} | "
                 f"{bands.get('전체', {}).get('인원', 0):,} | "
                 f"{any_r['단위면적_m2']:,} |")
    if missed:
        L += ["", f"> 매칭 실패 {len(missed)}곳: {', '.join(missed)} — "
                  "서울 밖이거나 상권 경계에서 벗어난 위치입니다. 값을 지어내지 않았습니다."]
    if a_prob or f_prob:
        L += ["", "## 수집 실패", ""] + [f"- {x}" for x in (a_prob + f_prob)]
    write_text(Path(args.summary), "\n".join(L) + "\n")

    print(f"  → {out} ({len(rows)}행) · {args.summary}")
    if missed:
        print(f"  ! 매칭 실패 {len(missed)}곳: {', '.join(missed)}", file=sys.stderr)
    for x in (a_prob + f_prob):
        print(f"  ⚠ {x}", file=sys.stderr)
    print("  🙋 실측이 아닙니다 — M2 가 면적비로 안분하고 경고를 남깁니다. "
          "최종 심의 전에는 07~09시 현장 카운트로 교체하십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
