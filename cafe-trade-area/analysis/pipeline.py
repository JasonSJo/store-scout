#!/usr/bin/env python3
"""
파이프라인 — M1 → M2 → M3 → M4 → M5 오케스트레이션

    M1 상권 획정 → M2 수요 변수 → M3 경쟁 배분 → M4 매출 추정
                                                  ↓
                                         M5 판정 로직 → M6 사후 보정

후보지와 기존점을 **같은 절차**로 처리한다. 기존점도 M1~M3 를 거쳐야
Mode A 회귀의 설명변수가 만들어지고, Mode B 앵커링의 S 가 같은 척도에 놓인다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

import m1_area as M1
import m2_demand as M2
import m3_huff as M3
import m4_revenue as M4
import m5_verdict as M5
import config as C
import collect_transactions as TX
from common import read_csv, to_f
from config import tier_of


def load_settings(path) -> dict:
    p = Path(path)
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def _build(rec_row: dict, name_key: str, isos: dict, cells: list, points: list,
           competitors: list, settings: dict, is_store: bool) -> dict:
    name = (rec_row.get(name_key) or "").strip()
    lat, lon = to_f(rec_row.get("위도")), to_f(rec_row.get("경도"))
    area = M1.resolve(name, lat, lon, isos, to_f(rec_row.get("잔존율_R")))
    dem = M2.demand(area, cells, points, str(rec_row.get("도로변", "")).strip())

    seats = to_f(rec_row.get("좌석수")) or to_f(settings.get("좌석수_기본"), 24)
    own_tier = tier_of(settings.get("브랜드", ""), settings.get("자사브랜드티어", ""))
    attr = M3.attraction(seats, own_tier)

    # 자기 자신은 경쟁 상대가 아니다 — 기존점 분석 시 같은 이름의 POI 를 뺀다
    rivals = [k for k in competitors if not (is_store and k["상호"] == name)]
    comp = M3.share(area, attr, rivals, cells,
                    bool(settings.get("보행네트워크", False)))
    comp["동일가격대_수"] = M3.density(area, rivals, "동일가격대")
    comp["저가형_수"] = M3.density(area, rivals, "저가형")
    comp["반경내_경쟁"] = M3.density(area, rivals)

    return {
        "이름": name, "후보지": rec_row, "기존점": is_store,
        "상권": area, "수요": dem, "경쟁": comp,
        "경고": list(area["경고"]) + list(dem.get("경고", [])) + list(comp["경고"]),
    }


def analyze_all(sites: list[dict], stores: list[dict], isos: dict, cells: list,
                points: list, competitors: list, settings: dict,
                measured_mape: float = None, market: dict = None) -> dict:
    """후보지 전체를 심의 가능한 형태로 만든다.

    market 은 {지역코드: 실거래가 요약}. 후보지의 법정동코드 앞 5자리로 찾아
    **참고 자료로만** 레코드에 싣는다(rec["시세대조"]). 판정에는 넘기지 않는다.
    비어 있으면 대조를 건너뛴다 — 없는 근거로 판단하지 않는다.
    """
    days = to_f(settings.get("영업일수"), 30) or 30

    cand = [_build(r, "후보지명", isos, cells, points, competitors, settings, False)
            for r in sites if (r.get("후보지명") or "").strip()]
    exist = [_build(r, "점포명", isos, cells, points, competitors, settings, True)
             for r in stores if (r.get("점포명") or "").strip()]

    # 배점 S 는 후보지와 기존점을 한 풀에서 정규화해야 앵커링이 성립한다
    M4.score_pool(cand + exist)

    model = M4.fit_mode_a(exist)
    anchors = [e for e in exist
               if str(e["후보지"].get("기준점포", "")).upper().startswith(("Y", "예", "O"))]
    if not anchors:
        anchors = [e for e in exist if to_f(e["후보지"].get("월매출_만원")) > 0][:2]

    own_stores = [e for e in exist if to_f(e["후보지"].get("월매출_만원")) > 0]

    for rec in cand:
        rec["매출"] = M4.estimate(rec, model, anchors, days, measured_mape)
        overlaps = []
        for st in own_stores:
            ov = M1.overlap_with(rec["상권"], st["이름"],
                                 to_f(st["후보지"].get("위도")),
                                 to_f(st["후보지"].get("경도")),
                                 isos, to_f(st["후보지"].get("잔존율_R")))
            if ov > 0:
                overlaps.append({"점포명": st["이름"], "overlap": ov,
                                 "월매출_만원": to_f(st["후보지"].get("월매출_만원"))})
        # 지역 실거래가는 **판정에 넘기지 않는다.** 참고 자료로만 레코드에 남긴다 —
        # 매매가를 임대료로 환산한 값이라 층·용도·전면 편차를 담지 못하고, 환산
        # 계수가 미검증이다. 검증되지 않은 환산이 보류를 만들면 실거래 데이터가
        # 있는 지역의 후보지만 근거 없이 불리해진다.
        rec["시세"] = mkt = (market or {}).get(TX.lawd(rec["후보지"].get("법정동코드")))
        rec["시세대조"] = M5.market_rent(rec["후보지"], mkt)
        rec["판정"] = M5.judge(rec["후보지"], rec["매출"], settings, rec.get("S", 0.0),
                              overlaps, rec.get("S_풀최대"))
        rec["경고"] += list(rec["매출"].get("경고", []))

    return {
        "후보지": cand, "기존점": exist, "모델": model, "기준점포": anchors,
        "설정": settings, "영업일수": days,
        "모드": M4.MODE_A if (model and "beta" in model) else M4.MODE_B,
    }


def merge_ops(settings: dict, ops: dict, record: bool = False) -> dict:
    """콘솔이 입력한 운영 계수를 설정에 얹는다. 설정 파일 자체는 건드리지 않는다.

    record=True 면 어떤 값이 설정 파일 값을 대체했는지 계수 레지스트리에 남긴다
    (심의표의 '콘솔에서 입력한 계수' 절이 이것을 읽는다).
    """
    if not ops:
        return settings
    out = dict(settings)
    cur = dict(out.get("운영", {}) or {})
    for group in ("변동비", "고정비"):
        if not ops.get(group):
            continue
        base = cur.get(group, {}) or {}
        if record:
            for k, v in ops[group].items():
                if base.get(k) != v:
                    C.OVERRIDDEN[f"운영.{group}.{k}"] = (base.get(k), v)
        cur[group] = {**base, **ops[group]}
    out["운영"] = cur
    return out


def load_all(base: Path, args) -> dict:
    """CLI 들이 공유하는 입력 로딩. 없는 파일은 조용히 빈 값으로 둔다(경고는 각 모듈이 낸다)."""
    settings = load_settings(args.settings)
    # 심의 콘솔에서 내보낸 계수.json 이 있으면 계수 레지스트리와 운영 설정에 얹는다.
    applied = C.apply_overrides(getattr(args, "계수", None) or default_coef_path(base))
    settings = merge_ops(settings, applied.get("운영"), record=True)
    sites = read_csv(Path(args.sites)) if Path(args.sites).exists() else []
    return {
        "sites": sites,
        "stores": read_csv(Path(args.stores)) if Path(args.stores).exists() else [],
        "cells": M2.load_cells(Path(args.cells)) if Path(args.cells).exists() else [],
        "points": M2.load_points(Path(args.points)) if Path(args.points).exists() else [],
        "competitors": M3.load_competitors(Path(args.competitors)) if Path(args.competitors).exists() else [],
        "isos": M1.load_isochrones(Path(args.iso)) if args.iso and Path(args.iso).exists() else {},
        "settings": settings,
        "market": load_market(sites, args),
    }


def load_market(sites: list[dict], args) -> dict:
    """M5 시세 대조에 쓸 {지역코드: 실거래가 요약} 을 준비한다.

    --실거래-수집 이 켜져 있고 DATA_GO_KR_KEY 가 있으면 국토교통부 API 를 직접
    호출해 CSV 를 새로 쓰고, 그렇지 않으면 이미 있는 CSV 를 읽는다. 어느 쪽도
    안 되면 빈 dict — 그러면 M5 는 대조를 통째로 건너뛴다. **금액을 지어내지 않는다.**
    """
    path = Path(getattr(args, "실거래", "") or "")
    if getattr(args, "실거래_수집", False):
        key = os.environ.get("DATA_GO_KR_KEY", "").strip()
        regions = TX.regions_of(sites)
        if not key:
            print("! DATA_GO_KR_KEY 가 없어 실거래가를 수집하지 않았습니다 — "
                  "저장된 표가 있으면 그것만 씁니다.", file=sys.stderr)
        elif not regions:
            print("! 후보지에 법정동코드가 없어 실거래가를 조회할 수 없습니다 — "
                  "입력 페이지에서 주소를 검색해 채우십시오.", file=sys.stderr)
        else:
            rows, problems = TX.gather(key, regions, int(getattr(args, "실거래_개월", 12)),
                                       log=print)
            if rows:
                TX.write_rows(path, rows)
                print(f"  실거래 {len(rows)}건 → {path}")
            if problems:
                print(f"  ⚠ 실거래 수집 실패 {len(problems)}구간 (첫 건: {problems[0]})",
                      file=sys.stderr)
    return TX.load_summaries(path)


# 콘솔이 내보내는 파일명은 ASCII(coefficients.json)다 — 브라우저·OS 에 따라
# 비ASCII 다운로드명이 통째로 버려지기 때문이다. 손으로 만든 계수.json 도 그대로 받는다.
COEF_NAMES = ("계수.json", "coefficients.json")


def default_coef_path(base: Path) -> Path:
    for name in COEF_NAMES:
        if (base / name).exists():
            return base / name
    return base / COEF_NAMES[0]


def add_common_args(ap, base: Path):
    ap.add_argument("--sites", default=str(base / "후보지.example.csv"))
    ap.add_argument("--stores", default=str(base / "기존점.example.csv"))
    ap.add_argument("--cells", default=str(base / "격자인구.example.csv"))
    ap.add_argument("--points", default=str(base / "유동인구.example.csv"))
    ap.add_argument("--competitors", default=str(base / "경쟁점.example.csv"))
    ap.add_argument("--iso", default=str(base / "등시선.example.geojson"))
    ap.add_argument("--settings", default=str(base / "설정.example.yaml"))
    # 심의 콘솔 '계수' 탭에서 내보낸 파일. 없으면 명세 기본값으로 돈다.
    ap.add_argument("--계수", dest="계수", default=str(default_coef_path(base)),
                    help="콘솔에서 입력한 계수 override "
                         "(기본: 계수.json 또는 coefficients.json, 없으면 무시)")
    # M5 지역 시세 대조에 쓰는 국토교통부 실거래가. 파일이 없으면 대조를 건너뛴다.
    ap.add_argument("--실거래", dest="실거래", default=str(base / "output" / "실거래가.csv"),
                    help="실거래가 CSV (collect_transactions.py 산출물)")
    ap.add_argument("--실거래-수집", dest="실거래_수집", action="store_true",
                    help="분석 전에 국토교통부 API 로 실거래가를 직접 받아온다 "
                         "(DATA_GO_KR_KEY 필요)")
    ap.add_argument("--실거래-개월", dest="실거래_개월", type=int, default=12,
                    help="--실거래-수집 시 훑을 최근 개월 수 (기본 12)")
    return ap
