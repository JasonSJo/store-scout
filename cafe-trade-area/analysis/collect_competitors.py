#!/usr/bin/env python3
"""
M3 보조 · 경쟁점 수집

카카오 로컬 API 로 후보지·기존점 주변 카페(CE7)를 모아 경쟁점.csv 를 만든다.
브랜드에서 **티어**(동일가격대/저가형/스페셜티/비커피)를 추정해 채운다 —
티어는 M3 흡인력의 브랜드가중을 좌우하므로 현장 실사로 검증해야 한다.

  python3 collect_competitors.py                    # dry-run (예시 복사)
  python3 collect_competitors.py --live --radius 700
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import read_csv, to_f
from config import tier_of

ROOT = Path(__file__).resolve().parent
API = "https://dapi.kakao.com/v2/local/search/category.json"
HEADER = ["상호", "브랜드", "티어", "위도", "경도", "좌석수", "자사"]
BRANDS = ["스타벅스", "투썸", "커피빈", "블루보틀", "폴바셋", "메가", "컴포즈", "빽다방",
          "더벤티", "감성커피", "매머드", "이디야", "할리스", "파리바게뜨", "뚜레쥬르"]


def brand_of(name: str) -> str:
    return next((b for b in BRANDS if b in name), "개인")


def fetch(key, lat, lon, radius):
    out, page = [], 1
    while page <= 3:
        q = urllib.parse.urlencode({"category_group_code": "CE7", "x": lon, "y": lat,
                                    "radius": int(radius), "page": page, "size": 15,
                                    "sort": "distance"})
        req = urllib.request.Request(f"{API}?{q}", headers={"Authorization": f"KakaoAK {key}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            print(f"  ! API 오류 {e.code}", file=sys.stderr)
            break
        except OSError as e:
            print(f"  ! 네트워크 오류: {e}", file=sys.stderr)
            break
        out += data.get("documents", [])
        if data.get("meta", {}).get("is_end", True):
            break
        page += 1
        time.sleep(0.2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="경쟁점 수집")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--stores", default=str(ROOT / "기존점.example.csv"))
    ap.add_argument("--out", default=str(ROOT / "output" / "경쟁점.csv"))
    ap.add_argument("--radius", type=int, default=700)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not args.live:
        sample = ROOT / "경쟁점.example.csv"
        rows = read_csv(sample) if sample.exists() else []
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            w.writeheader()
            w.writerows([{k: r.get(k, "") for k in HEADER} for r in rows])
        print(f"[dry-run] 예시 경쟁점 {len(rows)}건 복사 → {out} (API 호출 없음)")
        return 0

    key = os.environ.get("KAKAO_REST_KEY", "").strip()
    if not key:
        print("KAKAO_REST_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    targets = []
    for path, k in ((args.sites, "후보지명"), (args.stores, "점포명")):
        p = Path(path)
        if p.exists():
            for r in read_csv(p):
                if (r.get(k) or "").strip() and to_f(r.get("위도")):
                    targets.append(((r.get(k) or "").strip(), to_f(r["위도"]), to_f(r["경도"])))

    seen, rows = set(), []
    for name, lat, lon in targets:
        print(f"  · {name} 반경 {args.radius}m")
        for d in fetch(key, lat, lon, args.radius):
            if d.get("id") in seen:
                continue
            seen.add(d.get("id"))
            place = d.get("place_name", "")
            brand = brand_of(place)
            rows.append({"상호": place, "브랜드": brand, "티어": tier_of(brand),
                         "위도": d.get("y"), "경도": d.get("x"), "좌석수": "", "자사": "N"})

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"\n✅ 경쟁점 {len(rows)}건 → {out}")
    print("   🙋 티어와 좌석수는 현장 실사로 검증하십시오 — M3 흡인력을 좌우합니다.")
    print("   🙋 자사 기존점은 `자사=Y` 로 표시해야 자기잠식이 계산됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
