#!/usr/bin/env python3
"""
통신사 유동인구 수집·반입

D_am 은 판정을 가장 크게 움직이는 값이다. 그래서 여기서 지키려는 것은 '데이터가
들어온다' 가 아니라 **잘못 들어오지 않는다** 는 쪽이다:

  · 시간대 문자열이 M2 와 어긋나면 행은 멀쩡히 들어가고 D_am 만 0 이 된다.
  · 인원을 못 읽었을 때 0 으로 바꾸면 그 구역이 '사람 없는 곳' 이 된다.
  · 면적을 모르는 구역을 넣으면 M2 가 버리고 경고만 쌓인다.
  · dry-run 이 인원 수를 지어내면 그 숫자가 심의표에 실려 실측으로 오인된다.
"""
from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_carrier_flow as CF   # noqa: E402
import geo                          # noqa: E402
import m2_demand as M2              # noqa: E402
from common import read_csv         # noqa: E402

AREAS = [
    {"구역코드": "1120058010001", "면적_m2": "42000", "위도": "37.5445", "경도": "127.0557"},
    {"구역코드": "1120058010002", "면적_m2": "38000", "위도": "37.5450", "경도": "127.0562"},
]


def write_csv(path: Path, rows: list[dict], cols: list[str] = None) -> Path:
    cols = cols or list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


class TestTimeBand(unittest.TestCase):
    def test_M2_와_같은_문자열을_쓴다(self):
        """직접 적으면 어긋났을 때 행은 들어가고 D_am 만 0 이 된다 — 조용한 실패다."""
        self.assertIs(CF.AM, M2.AM)
        self.assertIs(CF.ALL, M2.ALL)

    def test_07에서_09시만_오전이다(self):
        for v in ("07", "08", "09", "8", "08시", "08-09"):
            self.assertEqual(CF.시간대(v), M2.AM, v)
        for v in ("06", "10", "14", "23", "00"):
            self.assertEqual(CF.시간대(v), "", v)

    def test_시간이_없으면_전체로_본다(self):
        for v in ("", None, "합계"):
            self.assertEqual(CF.시간대(v), M2.ALL, repr(v))


class TestNumberParsing(unittest.TestCase):
    """엑셀을 거쳐 온 파일에는 전각 숫자와 단위가 섞인다."""

    def test_전각_숫자를_읽는다(self):
        self.assertEqual(CF.숫자("３００"), 300.0)
        self.assertEqual(CF.숫자("318.２"), 318.2)

    def test_읽지_못하면_0_이_아니라_None(self):
        """0 으로 바꾸면 그 구역이 '사람 없는 곳' 이 되어 D_am 을 끌어내린다."""
        for v in ("미상", "N/A", "-", "", None):
            self.assertIsNone(CF.숫자(v), repr(v))

    def test_쉼표와_단위를_받는다(self):
        self.assertEqual(CF.숫자("1,234"), 1234.0)
        self.assertEqual(CF.숫자("500명"), 500.0)


class TestImport(unittest.TestCase):
    """계약형 통신사 데이터 반입 — 공개 API 가 없어 이 경로가 실무의 기본이다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="carrier-"))
        self.areas = write_csv(self.tmp / "areas.csv", AREAS)

    def 반입(self, rows, cols=None, extra=None):
        src = write_csv(self.tmp / "in.csv", rows, cols)
        out = self.tmp / "out.csv"
        rc = CF.main(["--import", str(src), "--provider", "kt-plip",
                      "--areas", str(self.areas), "--out", str(out)] + (extra or []))
        self.assertEqual(rc, 0)
        return read_csv(out)

    def test_통신사_이름이_출처에_남는다(self):
        """M2 의 경고가 '어느 자료로 판정했는지' 를 이름으로 말해야 한다."""
        got = self.반입([{"집계구_코드": "1120058010001", "시간대구분": "08",
                       "총생활인구수": "412.7"}])
        self.assertEqual(len(got), 1)
        self.assertIn("KT", got[0]["출처"])
        self.assertEqual(got[0]["시간대"], M2.AM)
        self.assertEqual(float(got[0]["단위면적_m2"]), 42000.0)

    def test_면적을_모르면_행을_만들지_않는다(self):
        """추측한 면적으로 나눈 값은 근거가 아니다. M2 에 넘기면 버려지고 경고만 쌓인다."""
        got = self.반입([{"집계구_코드": "9999999999999", "시간대구분": "08",
                       "총생활인구수": "500"}])
        self.assertEqual(got, [])

    def test_읽지_못한_인원은_0_으로_넣지_않는다(self):
        got = self.반입([
            {"집계구_코드": "1120058010001", "시간대구분": "08", "총생활인구수": "미상"},
            {"집계구_코드": "1120058010002", "시간대구분": "08", "총생활인구수": "255"},
        ])
        self.assertEqual(len(got), 1)
        self.assertEqual(float(got[0]["인원"]), 255.0)

    def test_도로변을_지어내지_않는다(self):
        """기지국 데이터에는 도로 좌·우 구분이 없다. 채워 넣으면 M2 가 횡단저항을
        적용하고, 근거 없는 보정이 D_am 에 들어간다."""
        got = self.반입([{"집계구_코드": "1120058010001", "시간대구분": "08",
                       "총생활인구수": "412"}])
        self.assertEqual(got[0]["도로변"], "")

    def test_열_이름을_직접_이어_줄_수_있다(self):
        """통신사마다 열 이름이 다르다. 못 찾으면 추측하지 않고 사람이 잇는다."""
        got = self.반입(
            [{"zone": "1120058010001", "hh": "08", "cnt_x": "412"}],
            extra=["--map", "구역코드=zone", "--map", "인원=cnt_x", "--map", "시간=hh"])
        self.assertEqual(len(got), 1)
        self.assertEqual(float(got[0]["인원"]), 412.0)


class TestReachesM2(unittest.TestCase):
    """반입한 행이 실제로 D_am 에 도달하는가. 여기까지 봐야 '붙었다' 고 할 수 있다."""

    def test_D_am_에_들어가고_실측이_아니라고_말한다(self):
        tmp = Path(tempfile.mkdtemp(prefix="carrier-m2-"))
        areas = write_csv(tmp / "areas.csv", AREAS)
        src = write_csv(tmp / "in.csv", [
            {"집계구_코드": "1120058010001", "시간대구분": "08", "총생활인구수": "412.7"},
            {"집계구_코드": "1120058010002", "시간대구분": "08", "총생활인구수": "318.2"},
        ])
        out = tmp / "out.csv"
        CF.main(["--import", str(src), "--provider", "kt-plip",
                 "--areas", str(areas), "--out", str(out)])
        rows = read_csv(out)

        lat0, lon0 = 37.5445, 127.0557
        p5 = [geo.project(lat0, lon0, lat0 + dy, lon0 + dx)
              for dy, dx in [(0.003, -0.004), (0.003, 0.004),
                             (-0.003, 0.004), (-0.003, -0.004)]]
        got = M2.foot_traffic({"위도": lat0, "경도": lon0, "P5": p5}, rows, "A")

        self.assertGreater(got["D_am"], 0, "통신사 행이 D_am 에 닿지 않았습니다")
        self.assertEqual(got["안분_행"], 2)
        self.assertFalse(got["실측여부"])
        경고 = " ".join(got["경고"])
        self.assertIn("실측이 아닙니다", 경고)
        self.assertIn("KT", 경고, "어느 자료로 판정했는지 경고가 말하지 않습니다")


class TestDryRun(unittest.TestCase):
    def test_인원을_지어내지_않는다(self):
        """지어낸 유동인구가 심의표에 실리면 실측으로 오인된다."""
        tmp = Path(tempfile.mkdtemp(prefix="carrier-dry-"))
        out = tmp / "out.csv"
        rc = CF.main(["--provider", "seoul-living", "--out", str(out)])
        self.assertEqual(rc, 0)
        self.assertEqual(read_csv(out), [])

    def test_반입_전용_공급자는_라이브를_거절한다(self):
        tmp = Path(tempfile.mkdtemp(prefix="carrier-live-"))
        rc = CF.main(["--provider", "kt-plip", "--live",
                      "--out", str(tmp / "o.csv")])
        self.assertEqual(rc, 2)


class TestProviderTable(unittest.TestCase):
    """'어느 통신사를 쓸 수 있나' 에 코드를 읽지 않고 답할 수 있어야 한다."""

    def test_통신사_셋이_다_있다(self):
        통신사 = {p["통신사"] for p in CF.PROVIDERS.values()}
        for x in ("KT", "SKT", "LG U+"):
            self.assertIn(x, 통신사)

    def test_받는_법이_솔직하다(self):
        """공개 API 가 없는 것을 'API' 라고 적으면 붙였다고 착각하게 된다."""
        for key in ("kt-plip", "skt-geovision", "lgu-flow"):
            self.assertEqual(CF.PROVIDERS[key]["받는법"], "반입", key)
        self.assertEqual(CF.PROVIDERS["seoul-living"]["받는법"], "API")
        self.assertEqual(CF.PROVIDERS["seoul-living"]["비용"], "무료")

    def test_무료_공급자는_전국이_아니다(self):
        """전국을 시간대별로 덮는 무료 공개 API 는 없다. 있는 것처럼 적으면
        계약 없이 전국이 커버된다고 착각하게 된다."""
        for k, p in CF.PROVIDERS.items():
            if p["비용"].startswith("무료") and p["받는법"] == "API":
                self.assertNotEqual(p["범위"], "전국", k)

    def test_전국을_덮는_것은_계약형이다(self):
        전국 = [k for k, p in CF.PROVIDERS.items() if p["범위"].startswith("전국")
              and p["받는법"] == "반입"]
        self.assertTrue(전국, "전국 공급자가 하나도 없습니다")
        for k in 전국:
            self.assertIn("계약", CF.PROVIDERS[k]["비용"], k)

    def test_통신사_셋이_전국_경로를_가진다(self):
        """어느 통신사와 계약하든 붙일 자리가 있어야 한다."""
        전국통신사 = {p["통신사"] for p in CF.PROVIDERS.values()
                  if p["범위"].startswith("전국")}
        for x in ("KT", "SKT", "LG U+"):
            self.assertIn(x, 전국통신사, x)

    def test_목록에_실측이_아니라는_말이_있다(self):
        self.assertIn("실측이 아닙니다", CF.목록())


class TestNationwide(unittest.TestCase):
    """전국은 지역별 파일 여러 개로 온다. 합치는 과정에서 나는 사고를 막는다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="carrier-nat-"))
        self.areas = write_csv(self.tmp / "areas.csv", AREAS + [
            {"구역코드": "4113510300101", "면적_m2": "60000",
             "위도": "37.3595", "경도": "127.1052"},   # 성남
            {"구역코드": "2617010100101", "면적_m2": "55000",
             "위도": "35.1578", "경도": "129.0596"},   # 부산
        ])

    def test_여러_지역_파일을_한_벌로_합친다(self):
        a = write_csv(self.tmp / "seoul.csv",
                      [{"집계구_코드": "1120058010001", "시간대구분": "08", "총생활인구수": "412"}])
        b = write_csv(self.tmp / "busan.csv",
                      [{"집계구_코드": "2617010100101", "시간대구분": "08", "총생활인구수": "301"}])
        out = self.tmp / "out.csv"
        rc = CF.main(["--import", str(a), "--import", str(b), "--provider", "kt-plip",
                      "--areas", str(self.areas), "--out", str(out)])
        self.assertEqual(rc, 0)
        got = read_csv(out)
        self.assertEqual(len(got), 2)
        self.assertEqual({r["구역코드"] for r in got},
                         {"1120058010001", "2617010100101"})

    def test_겹친_구역을_두_번_더하지_않는다(self):
        """지역별 파일이 경계에서 겹치거나 같은 달을 두 번 받는 일이 흔하다.
        그대로 더하면 그 후보지만 D_am 이 배로 뛰어 근거 없이 좋아 보인다."""
        row = {"집계구_코드": "1120058010001", "시간대구분": "08",
               "총생활인구수": "412", "기준일자": "20260801"}
        a = write_csv(self.tmp / "a.csv", [row])
        b = write_csv(self.tmp / "b.csv", [dict(row)])
        out = self.tmp / "out.csv"
        CF.main(["--import", str(a), "--import", str(b), "--provider", "kt-plip",
                 "--areas", str(self.areas), "--out", str(out)])
        got = read_csv(out)
        self.assertEqual(len(got), 1, "같은 구역이 두 번 들어갔습니다")

    def test_같은_구역이라도_다른_시간대는_남긴다(self):
        rows = [{"집계구_코드": "1120058010001", "시간대구분": "08", "총생활인구수": "412"},
                {"집계구_코드": "1120058010001", "시간대구분": "", "총생활인구수": "9000"}]
        src = write_csv(self.tmp / "c.csv", rows)
        out = self.tmp / "out.csv"
        CF.main(["--import", str(src), "--provider", "kt-plip",
                 "--areas", str(self.areas), "--out", str(out)])
        got = read_csv(out)
        self.assertEqual({r["시간대"] for r in got}, {M2.AM, M2.ALL})


class TestCoverage(unittest.TestCase):
    """전국을 다루면 커버리지가 반드시 듬성듬성해진다. 그 사실을 심의 전에 말한다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="carrier-cov-"))
        self.sites = write_csv(self.tmp / "sites.csv", [
            {"후보지명": "성수 연무장길", "위도": "37.5445", "경도": "127.0557"},
            {"후보지명": "부산 서면", "위도": "35.1578", "경도": "129.0596"},
        ])
        self.flow = write_csv(self.tmp / "flow.csv", [{
            "지점ID": "x", "위도": "37.5445", "경도": "127.0557", "도로변": "",
            "시간대": M2.AM, "인원": "412", "출처": "KT PLIP",
            "단위면적_m2": "42000", "구역코드": "1", "구역명": "", "기준일": "20260801",
        }], cols=CF.HEADER)

    def 실행(self, extra=None):
        return CF.main(["--coverage", "--sites", str(self.sites),
                        "--flow", str(self.flow)] + (extra or []))

    def test_빠진_후보지가_있으면_strict_에서_실패한다(self):
        """CI 나 스크립트가 이걸로 심의 실행을 막을 수 있어야 한다."""
        self.assertEqual(self.실행(), 0)
        self.assertEqual(self.실행(["--strict"]), 1)

    def test_전부_있으면_strict_에서도_통과한다(self):
        full = write_csv(self.tmp / "sites2.csv", [
            {"후보지명": "성수 연무장길", "위도": "37.5445", "경도": "127.0557"}])
        rc = CF.main(["--coverage", "--sites", str(full), "--flow", str(self.flow),
                      "--strict"])
        self.assertEqual(rc, 0)

    def test_데이터_공백이_시장_평가로_읽힌다고_경고한다(self):
        """D_am 은 S 의 13개 지표 중 둘('오전유동'·'임대료대비객수효율')에 들어가고
        S 는 풀 안 min-max 정규화다. 자료가 없으면 그 후보지가 바닥에 깔리는데,
        심의표만 보면 상권이 나쁜 것과 구분되지 않는다."""
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            self.실행()
        finally:
            sys.stdout = old
        말 = buf.getvalue()
        self.assertIn("D_am 이 0", 말)
        self.assertIn("자료를 못 받아서", 말)
        self.assertIn("부산 서면", 말)

    def test_유동인구_파일이_없어도_죽지_않는다(self):
        rc = CF.main(["--coverage", "--sites", str(self.sites),
                      "--flow", str(self.tmp / "없는파일.csv")])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
