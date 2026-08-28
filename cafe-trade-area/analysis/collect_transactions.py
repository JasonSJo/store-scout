#!/usr/bin/env python3
"""
심의 보조 · 국토교통부 실거래가 수집

후보지의 **법정동코드**로 국토교통부 상업업무용 부동산 매매 실거래가를 받아
지역 시세 요약을 만든다. 입력 페이지가 주소 검색으로 법정동코드를 채워 두면
그 값이 그대로 조회 키가 된다(앞 5자리 = 지역코드 LAWD_CD).

  python3 collect_transactions.py                     # dry-run (호출 없음)
  DATA_GO_KR_KEY=... python3 collect_transactions.py --live --months 12

⚠ **알고리즘에 들어가지 않는다 — 참고 자료다.** 매출 추정(M1~M4)에도, 판정(M5)에도
   쓰이지 않는다. 매매 실거래가는 임대 조건이 아니고, 상업용 매물은 층·용도·전면에
   따라 편차가 커서 매출의 설명변수가 될 수 없다. 매매가를 임대료로 바꾸는
   연임대수익률도 미검증 계수다.

   한때 M5 의 보류 신호로 들어가 있었고 그것을 뺐다. 검증되지 않은 환산이 보류를
   만들면, 실거래 데이터가 **있는** 지역의 후보지만 근거 없이 불리해지기 때문이다 —
   데이터가 없는 지역은 애초에 그 신호를 받지 않는다.

   숫자는 계속 모아 심의표에 참고로 싣는다. 제시 임대료가 지역 수준을 크게 벗어나면
   실사에서 확인할 일이지, 알고리즘이 자동으로 깎을 일이 아니다.

⚠ **엔드포인트와 응답 필드명은 실제 호출로 검증되지 않았다.** 공공데이터포털이
   서비스 주소와 태그명을 바꾼 이력이 있어, 파서는 여러 표기를 함께 받아들이고
   하나도 못 읽으면 응답 앞부분을 그대로 출력한다. 형식이 다르면 그 출력을 보고
   ENDPOINT / FIELDS 를 고치면 된다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from common import read_csv, write_text

ROOT = Path(__file__).resolve().parent

# 국토교통부 상업업무용 부동산 매매 신고 자료 (공공데이터포털)
ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"

# 응답 태그명 후보 — 포털이 표기를 바꿔도 하나만 맞으면 읽힌다
FIELDS = {
    "거래금액": ["거래금액", "dealAmount"],
    "건물면적": ["건물면적", "buildingAr", "buildingAreaSqm"],
    "대지면적": ["대지면적", "plottageAr"],
    "년": ["년", "dealYear"],
    "월": ["월", "dealMonth"],
    "일": ["일", "dealDay"],
    "법정동": ["법정동", "umdNm"],
    "용도지역": ["용도지역", "landUse"],
    "건물주용도": ["건물주용도", "buildingUse", "mainPurpsNm"],
    "층": ["층", "floor"],
    "건축년도": ["건축년도", "buildYear"],
}
HEADER = ["지역코드", "법정동", "거래일", "거래금액_만원", "건물면적_m2",
          "만원_per_m2", "건물주용도", "용도지역", "층", "건축년도"]


def num(v) -> float:
    """'1,250' · ' 1250 ' 같은 표기를 숫자로. 못 읽으면 0."""
    try:
        return float(str(v or "").replace(",", "").strip())
    except ValueError:
        return 0.0


def lawd(bcode: str) -> str:
    """법정동코드 앞 5자리가 지역코드(LAWD_CD)다. 10자리를 그대로 넣으면 조회되지 않는다."""
    digits = "".join(ch for ch in str(bcode or "") if ch.isdigit())
    return digits[:5] if len(digits) >= 5 else ""


def months_back(n: int) -> list[str]:
    """오늘부터 거슬러 n개월치 YYYYMM. 실거래는 신고 지연이 있어 당월은 비어 있을 수 있다."""
    today = dt.date.today()
    out, y, m = [], today.year, today.month
    for _ in range(max(1, n)):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def pick(item: ET.Element, names: list[str]) -> str:
    for n in names:
        el = item.find(n)
        if el is not None and (el.text or "").strip():
            return (el.text or "").strip()
    return ""


def parse(xml_text: str) -> tuple[list[dict], str]:
    """(항목들, 오류메시지). 포털은 오류도 200 으로 XML 에 담아 보낸다."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return [], f"XML 파싱 실패: {e}"

    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or ""
    msg = root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg") or ""
    if code and code.strip() not in ("00", "0", "000"):
        return [], f"API 오류 {code.strip()}: {msg.strip()}"

    rows = []
    for item in root.iter("item"):
        get = lambda k: pick(item, FIELDS[k])
        amount = num(get("거래금액"))
        area = num(get("건물면적"))
        y, m, d = get("년"), get("월"), get("일")
        if not (amount and y and m):
            continue
        rows.append({
            "법정동": get("법정동"),
            "거래일": f"{int(y):04d}-{int(m):02d}-{int(d or 1):02d}",
            "거래금액_만원": amount,
            "건물면적_m2": area,
            "만원_per_m2": round(amount / area, 2) if area else "",
            "건물주용도": get("건물주용도"),
            "용도지역": get("용도지역"),
            "층": get("층"),
            "건축년도": get("건축년도"),
        })
    return rows, "" if rows else "항목을 하나도 읽지 못했습니다"


def fetch(key: str, region: str, ym: str, endpoint: str, rows_per_page: int = 200):
    q = urllib.parse.urlencode({
        "serviceKey": key, "LAWD_CD": region, "DEAL_YMD": ym,
        "numOfRows": rows_per_page, "pageNo": 1,
    }, safe="%")           # 포털 키는 이미 URL 인코딩되어 발급되는 경우가 많다
    url = f"{endpoint}?{q}"
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, timeout=15, context=ctx) as r:
            return r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return "", f"HTTP {e.code}"
    except OSError as e:
        return "", f"네트워크 오류: {e}"


def summarize(rows: list[dict]) -> dict:
    """중앙값을 쓴다 — 상업용은 대형 거래 한 건이 평균을 통째로 끌어올린다."""
    unit = sorted(r["만원_per_m2"] for r in rows if isinstance(r["만원_per_m2"], (int, float)))
    amt = sorted(r["거래금액_만원"] for r in rows)
    mid = lambda xs: (xs[len(xs) // 2] if len(xs) % 2
                      else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2) if xs else None
    return {
        "건수": len(rows),
        "만원_per_m2_중앙": mid(unit),
        "거래금액_만원_중앙": mid(amt),
        "최근_거래일": max((r["거래일"] for r in rows), default=""),
    }


def regions_of(sites: list[dict], name_key: str = "후보지명") -> dict:
    """후보지 CSV → {지역코드: [후보지명, ...]}. 법정동코드가 없는 행은 조회할 수 없다."""
    out = {}
    for r in sites:
        name = (r.get(name_key) or "").strip()
        code = lawd(r.get("법정동코드"))
        if name and code:
            out.setdefault(code, []).append(name)
    return out


def gather(key: str, regions: dict, months: int, endpoint: str = ENDPOINT,
           log=None) -> tuple[list[dict], list[str]]:
    """지역코드별로 최근 N개월을 훑어 (거래행, 실패구간) 을 낸다.

    한 구간이 실패해도 나머지는 계속 모은다 — 신고 지연으로 특정 월이 비는 것은 정상이다.
    """
    all_rows, problems = [], []
    for region, names in regions.items():
        got = 0
        if log:
            log(f"  · {region} ({'·'.join(names)})")
        for ym in months_back(months):
            body, err = fetch(key, region, ym, endpoint)
            if err:
                problems.append(f"{region} {ym}: {err}")
                continue
            rows, perr = parse(body)
            if perr and not rows:
                problems.append(f"{region} {ym}: {perr}")
                if len(problems) == 1 and log:   # 첫 실패의 실제 응답을 보여준다
                    log("    ↓ 응답 앞부분 (형식이 다르면 이걸 보고 FIELDS 를 고치십시오)")
                    log("    " + body[:400].replace("\n", "\n    "))
                continue
            for r in rows:
                r["지역코드"] = region
            all_rows += rows
            got += len(rows)
        if log:
            log(f"    {got}건")
    return all_rows, problems


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in HEADER} for r in rows])


def load_summaries(path: Path) -> dict:
    """저장된 실거래가 CSV → {지역코드: 요약}. 심의표가 참고 표로 싣는다(판정 미사용).

    금액을 못 읽은 행은 버린다 — 0원 거래가 중앙값을 끌어내리면 참고 기대 임대료가
    실제보다 낮아져, 멀쩡한 후보지가 비싼 것처럼 보인다.
    """
    if not path or not Path(path).exists():
        return {}
    by_code: dict[str, list[dict]] = {}
    for r in read_csv(Path(path)):
        code = (r.get("지역코드") or "").strip()
        amt = num(r.get("거래금액_만원"))
        if not code or not amt:
            continue
        unit = num(r.get("만원_per_m2"))
        by_code.setdefault(code, []).append({
            # 면적을 못 읽어 단가가 비는 행은 '' 로 둔다. 0 을 넣으면 중앙값이 끌려 내려가
            # 기대 임대료가 낮아지고 멀쩡한 후보지가 '시세 초과' 로 보류된다.
            "만원_per_m2": unit if unit > 0 else "",
            "거래금액_만원": amt,
            "거래일": (r.get("거래일") or "").strip(),
        })
    return {code: summarize(rows) for code, rows in by_code.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="국토교통부 실거래가 수집 (심의 참고용)")
    ap.add_argument("--sites", default=str(ROOT / "후보지.example.csv"))
    ap.add_argument("--out", default=str(ROOT / "output" / "실거래가.csv"))
    ap.add_argument("--summary", default=str(ROOT / "output" / "실거래가_요약.md"))
    ap.add_argument("--months", type=int, default=12, help="최근 N개월 (기본 12)")
    ap.add_argument("--endpoint", default=ENDPOINT, help="포털이 주소를 바꾸면 여기서 교체")
    ap.add_argument("--live", action="store_true", help="실제 호출 (DATA_GO_KR_KEY 필요)")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    sites = read_csv(Path(args.sites)) if Path(args.sites).exists() else []
    regions = regions_of(sites)

    if not args.live:
        # 실거래 금액을 지어내지 않는다 — 심의표에 그대로 실리면 실측으로 오인된다.
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=HEADER).writeheader()
        print(f"[dry-run] API 를 호출하지 않았습니다 — 빈 표만 만들었습니다: {out}")
        if regions:
            print(f"  조회 가능한 지역코드 {len(regions)}개: "
                  + ", ".join(f"{c}({'·'.join(v)})" for c, v in regions.items()))
        else:
            print("  ! 후보지에 법정동코드가 없습니다 — 입력 페이지에서 주소를 검색해 채우십시오.")
        print("  실제 수집: DATA_GO_KR_KEY=... python3 collect_transactions.py --live")
        return 0

    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY 환경변수가 없습니다.\n"
              "  공공데이터포털(data.go.kr)에서 '국토교통부_상업업무용 부동산 매매 신고 자료'\n"
              "  활용신청 후 발급받은 서비스키를 넣으십시오.", file=sys.stderr)
        return 1
    if not regions:
        print("후보지에 법정동코드가 없습니다 — 입력 페이지에서 주소를 검색해 채우십시오.",
              file=sys.stderr)
        return 1

    all_rows, problems = gather(key, regions, args.months, args.endpoint, log=print)
    write_rows(out, all_rows)

    lines = ["# 지역 실거래가 요약 (심의 참고)", "",
             f"국토교통부 상업업무용 부동산 매매 신고 자료 · 최근 {args.months}개월", "",
             "> **판정에도 매출 추정에도 들어가지 않습니다 — 참고 자료입니다.** "
             "매매가는 임대 조건이 아니고, 상업용은 층·용도·전면에 따라 편차가 크며, "
             "매매가를 임대료로 바꾸는 연임대수익률이 미검증 계수입니다. "
             "제시 임대료가 지역 수준을 크게 벗어나면 실사에서 확인하십시오.", "",
             "| 지역코드 | 후보지 | 건수 | 중앙 만원/㎡ | 중앙 거래금액(만원) | 최근 거래 |",
             "|---|---|---:|---:|---:|---|"]
    for region, names in regions.items():
        s = summarize([r for r in all_rows if r.get("지역코드") == region])
        u = f"{s['만원_per_m2_중앙']:,.1f}" if s["만원_per_m2_중앙"] else "—"
        a = f"{s['거래금액_만원_중앙']:,.0f}" if s["거래금액_만원_중앙"] else "—"
        lines.append(f"| {region} | {'·'.join(names)} | {s['건수']} | {u} | {a} | "
                     f"{s['최근_거래일'] or '—'} |")
    if problems:
        lines += ["", "## 수집하지 못한 구간", ""] + [f"- {p}" for p in problems[:20]]
        if len(problems) > 20:
            lines.append(f"- … 외 {len(problems) - 20}건")
    write_text(Path(args.summary), "\n".join(lines) + "\n")

    print(f"\n✅ 실거래 {len(all_rows)}건 → {out}")
    print(f"   요약: {args.summary}")
    if problems:
        print(f"   ⚠ 수집 실패 {len(problems)}구간 — 요약 말미를 보십시오.", file=sys.stderr)
    if not all_rows:
        print("   ! 한 건도 못 받았습니다. 서비스키 승인 상태와 엔드포인트를 확인하십시오.",
              file=sys.stderr)
        return 2
    print("   🙋 매매 실거래가는 임대 조건이 아닙니다 — 판정에도 매출 추정에도 "
          "들어가지 않고, 심의표에 참고로만 실립니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
