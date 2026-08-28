#!/usr/bin/env python3
"""
간편 입력 — 주소와 마진율만으로 심의 입력 한 벌을 만든다.

    python3 quick_site.py --주소 "서울 성동구 연무장길 42" --마진율 0.55

후보지 CSV 는 26개 열을 요구한다. 그 중 **사람이 반드시 알아야 하는 것은 둘뿐**이고
(어디인가 · 얼마를 남기는가), 나머지는 받아오거나 가정할 수 있다. 이 도구가 그 둘을
받아 나머지를 채우고, **칸마다 어디서 온 값인지**를 출처표로 남긴다.

    자동수집  외부 API 에서 실제로 받아온 값 (좌표·법정동코드·지역 시세)
    역산      받아온 값에서 계산한 값 (지역 시세 → 추정 임대료)
    가정      아무 근거 없이 넣은 자리표시자 — 실사로 반드시 대체해야 한다
    미확인    빈칸으로 둔 값 (치명 플래그) — 가정으로도 채우지 않는다

⚠ **이것으로 나오는 판정은 잠정이다.** 유동인구 실측과 기존점 실적은 외부에서 받아올
   수 없어 채워지지 않는다. 그 둘이 없으면 M2 의 D_am 과 M4 의 매출 추정이 서 있을
   자리가 없고, 파이프라인은 그 사실을 경고로 낸다. 이 도구는 경고를 지우지 않는다 —
   빈칸을 그럴듯한 숫자로 덮는 것이 심의에서 제일 위험하기 때문이다.
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

import yaml

import collect_transactions as TX
from common import read_csv, to_f, write_json, write_text
from m5_verdict import PY_PER_M2
from config import FATAL_KEYS, c

ROOT = Path(__file__).resolve().parent
GEOCODE = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 후보지 CSV 열 순서 — 후보지.example.csv 와 같아야 한다
COLUMNS = ["후보지명", "주소", "우편번호", "법정동코드", "위도", "경도", "전용면적_평",
           "좌석수", "층", "코너여부", "전면폭_m", "주차가능대수", "정차가능", "도로변",
           "방향적합", "보증금_만원", "월임대료_만원", "관리비_만원", "권리금_만원",
           "계약조건점수", "잔존율_R", "근저당_과다", "임대인_불일치", "소송_계류",
           "인허가_불가", "비고"]

# 받아올 수 없는 칸의 자리표시자. **불리한 쪽으로 잡는다** — 모르는 조건을 유리하게
# 가정하면 통과가 쉬워지고, 그 통과는 실사에서 뒤집힌다.
# (코너·주차·정차·방향적합을 'Y' 로 두면 Mode B 배점이 근거 없이 올라간다.)
ASSUMED = {
    "전용면적_평": (20, "지역 평균대 소형 상가. 시세 대조의 건물가치 환산에 쓰인다"),
    "좌석수": (24, "설정의 좌석수_기본과 같은 값. M3 흡인력 A"),
    "층": (1, "1층 가정 — 2층 이상이면 Mode B 1층접근성 배점이 달라진다"),
    "코너여부": ("N", "모르면 코너가 아니다 (유리한 쪽으로 가정하지 않는다)"),
    "전면폭_m": (6.0, "소형 상가 전면 통상값"),
    "주차가능대수": (0, "모르면 없다"),
    "정차가능": ("N", "모르면 불가"),
    "도로변": ("A", "같은편 가정 — 반대편이면 횡단저항으로 D_am 이 깎인다"),
    "방향적합": ("N", "출근 동선 방향은 현장에서만 확인된다"),
    "계약조건점수": (3, "5점 만점의 중간"),
}

# 판정을 만들지만 근거는 없는 칸 — 절대 채우지 않는다
NEVER_FILLED = {
    "보증금_만원": "알고리즘에 들어가지 않는다. 협상 전이면 비워 두는 것이 맞다",
    "권리금_만원": "알고리즘에 들어가지 않는다",
    "잔존율_R": "등시선을 받으면 계산된다. 손으로 넣으면 M1 을 건너뛴 값이 된다",
}


def fmt(v) -> str:
    """CSV 에 쓸 표기. 6.0 은 '6' 으로 적는다 — 자바스크립트의 String(6.0) 과 같아야
    웹에서 내보낸 CSV 와 CLI 가 만든 CSV 가 글자까지 같아진다."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def http_json(url: str, headers: dict) -> tuple[dict | None, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15,
                                    context=ssl.create_default_context()) as r:
            return json.loads(r.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except (OSError, ValueError) as e:
        return None, f"요청 실패: {e}"


def geocode(key: str, query: str) -> tuple[dict | None, str]:
    """주소 → 좌표·법정동코드·우편번호. 주소 검색을 먼저 하고 안 되면 장소 검색.

    후보지는 '그 자리'가 기준이라 주소 결과를 장소 결과보다 앞에 둔다
    (input/js/place.js 의 검색 순서와 같은 이유·같은 순서다).
    """
    q = urllib.parse.urlencode({"query": query, "size": 5})
    head = {"Authorization": f"KakaoAK {key}"}

    body, err = http_json(f"{GEOCODE}?{q}", head)
    if body and body.get("documents"):
        d = body["documents"][0]
        road = d.get("road_address") or {}
        addr = d.get("address") or {}
        return {
            "주소": road.get("address_name") or addr.get("address_name") or query,
            "위도": to_f(d.get("y")), "경도": to_f(d.get("x")),
            "우편번호": (road.get("zone_no") or "").strip(),
            "법정동코드": (addr.get("b_code") or road.get("b_code") or "").strip(),
            "후보지명": (road.get("building_name") or "").strip(),
            "출처": "카카오 주소 검색",
        }, ""

    body, err2 = http_json(f"{KEYWORD}?{q}", head)
    if body and body.get("documents"):
        d = body["documents"][0]
        return {
            "주소": (d.get("road_address_name") or d.get("address_name") or query).strip(),
            "위도": to_f(d.get("y")), "경도": to_f(d.get("x")),
            # 장소 검색은 우편번호·법정동코드를 주지 않는다
            "우편번호": "", "법정동코드": "",
            "후보지명": (d.get("place_name") or "").strip(),
            "출처": "카카오 장소 검색",
        }, ""
    return None, err or err2 or "검색 결과가 없습니다"


def name_from(addr: str) -> str:
    """건물명이 없을 때 주소 뒤 두 토막으로 이름을 만든다 (place.js 의 suggestName 과 같은 규칙)."""
    parts = [p for p in str(addr or "").split() if p]
    return " ".join(parts[-2:]) if len(parts) >= 2 else (parts[0] if parts else "후보지")


def rent_from_market(area_py: float, market: dict | None) -> float | None:
    """지역 매매 시세 → 추정 월임대료. m5_verdict.market_rent 의 **역방향**이다.

        건물가치 ≈ 중앙 만원/㎡ × 전용면적_평 × 3.305785
        기대 월임대료 ≈ 건물가치 × 상업용_연임대수익률 ÷ 12

    같은 환산식을 쓰므로, 이렇게 채운 임대료로는 M5 의 시세 대조가 당연히 통과한다.
    자기가 만든 값을 자기가 검사하는 셈이라 그 통과에는 아무 의미가 없다 —
    출처표와 심의표가 이 사실을 명시한다.
    """
    if not market or area_py <= 0:
        return None
    unit = to_f(market.get("만원_per_m2_중앙"))
    n = int(to_f(market.get("건수")))
    if unit <= 0 or n < int(c("시세대조_최소건수")):
        return None
    value = unit * area_py * PY_PER_M2
    rent = value * c("상업용_연임대수익률") / 12.0
    return round(rent) if rent > 0 else None


def variable_costs(margin: float, base: dict) -> tuple[dict, str]:
    """마진율(공헌이익률) → 변동비 4항목.

    v = 1 - 마진율 이다. 로열티·광고분담금·기타는 계약으로 정해진 값이라 설정값을
    그대로 두고, 나머지를 원재료율로 돌린다 — 그래야 각 줄의 뜻이 유지된다.

    ⚠ 이 저장소에서 'margin' 은 (매출-BEP)÷매출 로 **결과**를 가리킨다. 여기서 받는
       마진율은 **입력**인 공헌이익률(1-변동비율)이다. 이름이 겹치므로 산출물에서는
       '공헌이익률' 로 적는다.
    """
    fixed = (to_f(base.get("로열티율")) + to_f(base.get("광고분담금율"))
             + to_f(base.get("기타변동비율")))
    v = 1.0 - margin
    material = v - fixed
    note = ""
    if material < 0:
        note = (f"공헌이익률 {margin:.0%} 는 로열티·광고·기타 변동비 합 {fixed:.1%} 만으로도 "
                f"불가능합니다 — 원재료율을 0 으로 두고 계산합니다. 계약 조건을 확인하십시오.")
        material = 0.0
    return {**base, "원재료율": round(material, 6)}, note


def build_row(loc: dict, market: dict | None) -> tuple[dict, dict]:
    """후보지 1행과 칸별 출처표를 함께 만든다."""
    row = {k: "" for k in COLUMNS}
    src: dict[str, dict] = {}

    for k in ("주소", "위도", "경도", "우편번호", "법정동코드"):
        row[k] = loc.get(k, "")
        src[k] = {"분류": "자동수집" if row[k] != "" else "미확보", "출처": loc.get("출처", "")}
    row["후보지명"] = loc.get("후보지명") or name_from(loc.get("주소", ""))
    src["후보지명"] = {"분류": "자동수집" if loc.get("후보지명") else "가정",
                    "출처": loc.get("출처", "") if loc.get("후보지명") else "주소 뒤 두 토막"}

    for k, (v, why) in ASSUMED.items():
        row[k] = fmt(v)
        src[k] = {"분류": "가정", "출처": why}

    rent = rent_from_market(to_f(row["전용면적_평"]), market)
    if rent:
        row["월임대료_만원"] = rent
        src["월임대료_만원"] = {
            "분류": "역산",
            "출처": f"지역 실거래 {market['건수']}건 중앙 "
                  f"{market['만원_per_m2_중앙']:,.1f}만원/㎡ → 연수익률 "
                  f"{c('상업용_연임대수익률'):.1%} 환산 (가정 면적 {row['전용면적_평']}평)"}
        row["관리비_만원"] = round(rent * 0.12)
        src["관리비_만원"] = {"분류": "가정", "출처": "추정 임대료의 12% (통상 관리비 비율)"}
    else:
        src["월임대료_만원"] = {"분류": "미확보",
                           "출처": "지역 실거래가가 없어 역산하지 못했습니다 — "
                                 "고정비 F 가 과소평가되므로 반드시 실제 임대료를 넣으십시오"}
        src["관리비_만원"] = {"분류": "미확보", "출처": "임대료를 모르면 함께 모릅니다"}

    for k in FATAL_KEYS:
        row[k] = ""            # 'N' 으로 채우지 않는다 — 실사하지 않은 위험이 통과로 흘러간다
        src[k] = {"분류": "미확인", "출처": "등기·임대인·소송·인허가 실사로만 확인됩니다"}

    for k, why in NEVER_FILLED.items():
        src[k] = {"분류": "미확보", "출처": why}

    row["비고"] = "간편 입력(quick_site.py) — 가정값 포함"
    src["비고"] = {"분류": "가정", "출처": "생성 표시"}
    return row, src


def render(row: dict, src: dict, margin: float, note: str, market) -> str:
    order = {"자동수집": 0, "역산": 1, "가정": 2, "미확인": 3, "미확보": 4}
    rows = sorted(((k, src.get(k, {})) for k in COLUMNS),
                  key=lambda kv: (order.get(kv[1].get("분류"), 9), COLUMNS.index(kv[0])))
    n = {}
    for _, m in rows:
        n[m.get("분류", "?")] = n.get(m.get("분류", "?"), 0) + 1

    L = ["# 간편 입력 결과 — 출처표", "",
         f"**{row.get('후보지명')}** · {row.get('주소')}", "",
         f"공헌이익률 {margin:.0%} → 변동비율 {1 - margin:.1%}", ""]
    if note:
        L += [f"> ⚠ {note}", ""]
    L += ["| 분류 | 칸 수 | 뜻 |", "|---|---:|---|",
          f"| 자동수집 | {n.get('자동수집', 0)} | 외부 API 에서 실제로 받아온 값 |",
          f"| 역산 | {n.get('역산', 0)} | 받아온 값에서 계산한 값 |",
          f"| 가정 | {n.get('가정', 0)} | **근거 없는 자리표시자 — 실사로 대체해야 합니다** |",
          f"| 미확인 | {n.get('미확인', 0)} | 빈칸으로 둔 치명 항목 |",
          f"| 미확보 | {n.get('미확보', 0)} | 채우지 못한 값 |", "",
          "## 칸별 출처", "", "| 칸 | 값 | 분류 | 근거 |", "|---|---|---|---|"]
    for k, m in rows:
        v = row.get(k, "")
        L.append(f"| {k} | {v if v != '' else '—'} | {m.get('분류', '?')} | {m.get('출처', '')} |")

    L += ["", "---", "", "## 이 입력으로는 확정할 수 없는 것", "",
          "채우지 못한 칸이 아니라, **외부에서 받아올 방법이 아예 없는 것들**입니다.", "",
          "- **유동인구 D_am** — 명세가 07~09시 현장 실측 카운트를 요구합니다. "
          "공개 데이터로 대체할 수 있는 값이 아니며, M2 수요의 핵심 변수입니다.",
          "- **기존점 실매출** — 회사 내부 자료입니다. 이것이 없으면 M4 는 회귀(Mode A)도 "
          "앵커링(Mode B)도 못 하고, 매출 추정이 없으면 margin·BEP 판정이 서지 않습니다.",
          "- **치명 항목 4종** — 등기·임대인·소송·인허가는 실사로만 확인됩니다. "
          "빈칸으로 두었으므로 판정이 '통과' 로 나와도 잠정입니다.", "",
          "> 위 셋이 채워지기 전의 산출물은 **후보지를 걸러내는 용도**입니다. "
          "출점 결정의 근거로 쓰지 마십시오.", ""]
    if market:
        L += ["", f"> 지역 실거래 {market['건수']}건으로 임대료를 역산했습니다. "
                  "M5 의 시세 대조는 **같은 환산식의 역방향**이라 이 임대료로는 반드시 "
                  "통과합니다 — 그 통과에는 의미가 없습니다. 실제 임대료를 넣어야 "
                  "대조가 성립합니다.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="주소와 마진율만으로 심의 입력 만들기")
    ap.add_argument("--주소", dest="주소", help="검색할 주소 또는 건물명")
    ap.add_argument("--마진율", dest="마진율", type=float, required=True,
                    help="공헌이익률 (0~1 또는 0~100). 변동비율 v = 1 - 마진율")
    ap.add_argument("--위도", dest="위도", type=float, help="주소 검색 없이 좌표를 직접 넣을 때")
    ap.add_argument("--경도", dest="경도", type=float)
    ap.add_argument("--법정동코드", dest="법정동코드", default="",
                    help="좌표를 직접 넣을 때 지역 시세 조회용")
    ap.add_argument("--이름", dest="이름", default="")
    ap.add_argument("--실거래", dest="실거래", default=str(ROOT / "output" / "실거래가.csv"))
    ap.add_argument("--설정", dest="설정", default=str(ROOT / "설정.example.yaml"))
    ap.add_argument("--outdir", default=str(ROOT / "output" / "quick"))
    args = ap.parse_args()

    margin = args.마진율 / 100.0 if args.마진율 > 1 else args.마진율
    if not 0 < margin < 1:
        print("마진율은 0 과 1 사이여야 합니다 (예: 0.55 또는 55).", file=sys.stderr)
        return 1

    if args.주소:
        key = os.environ.get("KAKAO_REST_KEY", "").strip()
        if not key:
            print("KAKAO_REST_KEY 환경변수가 없습니다.\n"
                  "  주소 검색 없이 쓰려면 --위도/--경도 로 좌표를 직접 넣으십시오\n"
                  "  (입력 페이지에서 주소를 검색하면 좌표가 화면에 나옵니다).", file=sys.stderr)
            return 1
        loc, err = geocode(key, args.주소)
        if not loc:
            print(f"주소를 찾지 못했습니다: {err}", file=sys.stderr)
            return 1
    elif args.위도 and args.경도:
        loc = {"주소": args.이름 or f"{args.위도},{args.경도}", "위도": args.위도,
               "경도": args.경도, "우편번호": "", "법정동코드": args.법정동코드,
               "후보지명": args.이름, "출처": "좌표 직접 입력"}
    else:
        print("--주소 또는 --위도/--경도 중 하나가 필요합니다.", file=sys.stderr)
        return 1

    code = TX.lawd(loc.get("법정동코드"))
    market = TX.load_summaries(Path(args.실거래)).get(code) if code else None

    row, src = build_row(loc, market)
    settings = yaml.safe_load(Path(args.설정).read_text(encoding="utf-8")) or {}
    ops = dict(settings.get("운영", {}) or {})
    var, note = variable_costs(margin, dict(ops.get("변동비", {}) or {}))
    ops["변동비"] = var
    settings["운영"] = ops
    settings.setdefault("간편입력", {})["공헌이익률"] = margin

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "sites.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerow(row)
    (out / "설정.yaml").write_text(
        yaml.safe_dump(settings, allow_unicode=True, sort_keys=False), encoding="utf-8")
    write_json(out / "출처.json", {"후보지": row, "출처": src, "공헌이익률": margin,
                                 "지역시세": market})
    write_text(out / "출처표.md", render(row, src, margin, note, market))

    kinds = {}
    for m in src.values():
        kinds[m["분류"]] = kinds.get(m["분류"], 0) + 1
    print(f"{row['후보지명']} · {row['주소']}")
    print(f"  공헌이익률 {margin:.0%} → 변동비율 {1 - margin:.1%}")
    if note:
        print(f"  ⚠ {note}")
    print("  " + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    print(f"  → {out}/sites.csv · 설정.yaml · 출처표.md")
    print()
    print("  다음: python3 review_sites.py \\")
    print(f"          --sites {out}/sites.csv --settings {out}/설정.yaml")
    print("  ⚠ 가정값이 섞인 입력입니다. 나오는 판정은 후보지를 걸러내는 용도이며,")
    print("     유동인구 실측과 기존점 실적 없이는 출점 결정의 근거가 되지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
