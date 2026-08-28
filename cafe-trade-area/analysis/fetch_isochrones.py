#!/usr/bin/env python3
"""
M1 보조 · 등시선 생성 (라우팅 API)

OSM 보행 네트워크로 P5·P10 등시선을 만들어 GeoJSON 으로 저장한다.
기본은 dry-run 이며, `--live` 를 붙일 때만 외부 API 를 호출한다.

  준비: https://openrouteservice.org 에서 무료 키 발급 후
        export ORS_API_KEY="발급받은키"

  python3 fetch_isochrones.py                       # dry-run (호출 없음)
  python3 fetch_isochrones.py --live --out 등시선.geojson

⚠ API 가 만드는 등시선에는 명세가 요구한 barrier 처리(횡단보도 없는 6차선 이상·
하천·철로·옹벽·경사 10% 초과)가 **자동으로 반영되지 않는다.** 라우팅 프로파일이
보행 통행 가능성을 어디까지 반영하는지 확인하고, 필요하면 생성된 폴리곤을
GIS 에서 직접 잘라야 한다. 이 도구는 그 사실을 결과 파일에 기록한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import read_csv, to_f

ROOT = Path(__file__).resolve().parent
API = "https://api.openrouteservice.org/v2/isochrones/foot-walking"
BANDS = {"P5": 300, "P10": 600}     # 초


def fetch(key: str, lat: float, lon: float) -> dict | None:
    body = json.dumps({
        "locations": [[lon, lat]],
        "range": [BANDS["P5"], BANDS["P10"]],
        "range_type": "time",
        "location_type": "start",
        "attributes": ["area"],
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ! API 오류 {e.code} — 키/쿼터를 확인하세요", file=sys.stderr)
    except OSError as e:
        print(f"  ! 네트워크 오류: {e}", file=sys.stderr)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="등시선 생성 (OSM 보행 네트워크)")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--stores", default=str(ROOT / "기존점.example.csv"))
    ap.add_argument("--out", default=str(ROOT / "output" / "등시선.geojson"))
    ap.add_argument("--live", action="store_true", help="실제 API 호출(ORS_API_KEY 필요)")
    args = ap.parse_args()

    targets = []
    for path, key in ((args.sites, "후보지명"), (args.stores, "점포명")):
        p = Path(path)
        if not p.exists():
            continue
        for r in read_csv(p):
            name = (r.get(key) or "").strip()
            lat, lon = to_f(r.get("위도")), to_f(r.get("경도"))
            if name and lat and lon:
                targets.append((name, lat, lon))

    if not args.live:
        print(f"[dry-run] 대상 {len(targets)}곳. API 호출 없음.")
        print("          실제 생성: export ORS_API_KEY=... 후 --live")
        print("          이미 만들어 둔 등시선이 있으면 --iso 로 바로 넣으면 됩니다.")
        return 0

    key = os.environ.get("ORS_API_KEY", "").strip()
    if not key:
        print("ORS_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    feats = []
    for name, lat, lon in targets:
        print(f"  · {name}")
        data = fetch(key, lat, lon)
        if not data:
            continue
        for f in data.get("features", []):
            val = (f.get("properties", {}) or {}).get("value")
            band = next((b for b, sec in BANDS.items() if sec == val), None)
            if not band:
                continue
            feats.append({"type": "Feature",
                          "properties": {"대상": name, "구간": band, "생성": "ORS foot-walking"},
                          "geometry": f["geometry"]})
        time.sleep(1.5)      # 무료 쿼터 레이트리밋 여유

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "type": "FeatureCollection",
        "properties": {"주의": "barrier(횡단보도 없는 6차선 이상·하천·철로·옹벽·경사 10% 초과) "
                             "처리는 자동 반영되지 않았습니다. GIS 에서 확인·보정하십시오."},
        "features": feats}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✅ 등시선 {len(feats)}개 → {out}")
    print("   ⚠ barrier 처리는 별도 확인이 필요합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
