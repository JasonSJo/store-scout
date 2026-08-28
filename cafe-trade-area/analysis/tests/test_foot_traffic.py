#!/usr/bin/env python3
"""
유동인구 대용 — 영역 단위 값을 지점 값으로 쓰는 경로

이 경로의 위험은 하나로 요약된다: **영역 값을 지점 값처럼 더하면 D_am 이 수십 배로
부풀고 모든 후보지가 통과한다.** 그래서 여기서 고정하는 것은 안분 산술과, 안분이
일어났다는 사실이 산출물에서 사라지지 않는다는 점이다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_foot_traffic as FT   # noqa: E402
import config as C                  # noqa: E402
import geo                          # noqa: E402
import m1_area as M1                # noqa: E402
import m2_demand as M2              # noqa: E402
from common import read_csv         # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def area_at(lat=37.5445, lon=127.0557):
    isos = M1.load_isochrones(ROOT / "등시선.example.geojson")
    return M1.resolve("성수 연무장길", lat, lon, isos)


def row(인원, 단위면적, 출처="길단위인구_상권", 시간대="오전", 도로변="A", **kw):
    a = kw.pop("area", None) or area_at()
    return {"지점ID": "x", "위도": a["위도"], "경도": a["경도"], "도로변": 도로변,
            "시간대": 시간대, "인원": 인원, "출처": 출처, "단위면적_m2": 단위면적}


class TestApportionment(unittest.TestCase):
    def setUp(self):
        self.area = area_at()
        self.p5 = geo.shoelace_area(self.area["P5"])

    def test_영역값은_P5_면적비로_안분된다(self):
        단위 = self.p5 * 4          # P5 가 상권의 1/4
        d = M2.foot_traffic(self.area, [row(40000, 단위, area=self.area)], "A")
        self.assertAlmostEqual(d["D_am"], 40000 * 0.25 * C.c("유동_안분_집중계수"),
                               delta=1.0)

    def test_단위면적이_없으면_점_실측으로_그대로_더한다(self):
        d = M2.foot_traffic(self.area, [row(3000, "", 출처="실측", area=self.area)], "A")
        self.assertEqual(d["D_am"], 3000)
        self.assertTrue(d["실측여부"])
        self.assertEqual(d["안분_행"], 0)

    def test_영역값인데_면적을_모르면_버린다(self):
        """추측한 면적으로 나눈 값은 근거가 아니다. 지어내느니 버리는 쪽이 맞다."""
        d = M2.foot_traffic(self.area, [row(40000, "", area=self.area)], "A")
        self.assertEqual(d["D_am"], 0)
        self.assertEqual(d["면적미상_행"], 1)
        self.assertTrue(any("버렸습니다" in w for w in d["경고"]))

    def test_상권이_P5보다_작으면_전부_들어간다(self):
        """면적비가 1 을 넘으면 원래 값보다 커진다 — 1 로 자른다."""
        d = M2.foot_traffic(self.area, [row(1000, self.p5 / 10, area=self.area)], "A")
        self.assertAlmostEqual(d["D_am"], 1000 * C.c("유동_안분_집중계수"), delta=1.0)

    def test_안분하면_경고가_반드시_남는다(self):
        d = M2.foot_traffic(self.area, [row(40000, self.p5 * 4, area=self.area)], "A")
        self.assertFalse(d["실측여부"])
        self.assertTrue(any("실측이 아닙니다" in w for w in d["경고"]), d["경고"])
        self.assertTrue(any("07~09시" in w for w in d["경고"]), d["경고"])

    def test_집중계수를_바꾸면_안분값이_같이_움직인다(self):
        단위 = self.p5 * 4
        base = M2.foot_traffic(self.area, [row(40000, 단위, area=self.area)], "A")["D_am"]
        orig = C.COEFFICIENTS["유동_안분_집중계수"]
        C.COEFFICIENTS["유동_안분_집중계수"] = (2.0, orig[1], orig[2])
        try:
            got = M2.foot_traffic(self.area, [row(40000, 단위, area=self.area)], "A")["D_am"]
        finally:
            C.COEFFICIENTS["유동_안분_집중계수"] = orig
        self.assertAlmostEqual(got, base * 2, delta=1.0)

    def test_실측_데이터에는_안분_경고가_붙지_않는다(self):
        """모든 산출물에 경고가 뜨면 경고가 배경이 되고 아무도 읽지 않는다."""
        pts = M2.load_points(ROOT / "유동인구.example.csv")
        d = M2.foot_traffic(self.area, pts, "A")
        self.assertTrue(d["실측여부"])
        self.assertFalse(any("실측이 아닙니다" in w for w in d["경고"]), d["경고"])


class TestAreaMatching(unittest.TestCase):
    """옆 동네 상권 값을 끌어다 쓰면 D_am 이 통째로 다른 곳의 숫자가 된다."""

    AREAS = {
        "A1": {"위도": 37.5445, "경도": 127.0557, "면적_m2": 300000, "상권명": "가까움"},
        "A2": {"위도": 37.5600, "경도": 127.0900, "면적_m2": 300000, "상권명": "멂"},
    }

    def test_가장_가까운_상권을_고른다(self):
        code, d = FT.nearest(37.5445, 127.0557, self.AREAS, 800.0)
        self.assertEqual(code, "A1")
        self.assertLess(d, 50)

    def test_상권_반경_밖이면_매칭하지_않는다(self):
        far = {"A2": self.AREAS["A2"]}
        code, _ = FT.nearest(37.5445, 127.0557, far, 800.0)
        self.assertEqual(code, "")

    def test_매칭_실패는_행을_만들지_않는다(self):
        sites = [{"후보지명": "먼곳", "위도": "35.1", "경도": "129.0"}]
        rows, missed = FT.rows_for(sites, self.AREAS, {"A1": {}}, 800.0)
        self.assertEqual(rows, [])
        self.assertEqual(missed, ["먼곳"])

    def test_좌표계를_확인하지_못한_행은_버린다(self):
        """위경도 범위 밖 좌표를 추측 변환하면 상권이 통째로 옮겨간다."""
        got = FT.areas_of([{"TRDAR_CD": "X", "XCNTS_VALUE": "197123.4",
                            "YDNTS_VALUE": "451234.5", "RELM_AR": "300000"}])
        self.assertEqual(got, {})

    def test_위경도로_오면_그대로_쓴다(self):
        got = FT.areas_of([{"TRDAR_CD": "X", "XCNTS_VALUE": "127.0557",
                            "YDNTS_VALUE": "37.5445", "RELM_AR": "300000"}])
        self.assertEqual(got["X"]["위도"], 37.5445)
        self.assertEqual(got["X"]["경도"], 127.0557)

    def test_가장_최근_분기를_고른다(self):
        got = FT.latest_by_area([
            {"TRDAR_CD": "X", "STDR_YYQU_CD": "20251", "TOT_FLPOP_CO": "100"},
            {"TRDAR_CD": "X", "STDR_YYQU_CD": "20263", "TOT_FLPOP_CO": "200"},
            {"TRDAR_CD": "X", "STDR_YYQU_CD": "20252", "TOT_FLPOP_CO": "150"},
        ])
        self.assertEqual(got["X"]["기준분기"], "20263")
        self.assertEqual(got["X"]["전체"], 200)


class TestParserSafety(unittest.TestCase):
    def test_오류를_200에_담아_보내도_오류로_읽는다(self):
        rows, err = FT.parse('{"RESULT":{"CODE":"INFO-200","MESSAGE":"데이터 없음"}}', "X")
        self.assertEqual(rows, [])
        self.assertIn("INFO-200", err)

    def test_깨진_JSON_은_조용히_성공하지_않는다(self):
        rows, err = FT.parse("<html>error</html>", "X")
        self.assertEqual(rows, [])
        self.assertTrue(err)

    def test_정상_응답을_읽는다(self):
        body = '{"X":{"RESULT":{"CODE":"INFO-000"},"row":[{"TRDAR_CD":"1"}]}}'
        rows, err = FT.parse(body, "X")
        self.assertEqual(len(rows), 1)
        self.assertEqual(err, "")

    def test_dry_run_은_통행량을_만들지_않는다(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "유동_대용.csv"
            r = subprocess.run(
                [sys.executable, str(ROOT / "collect_foot_traffic.py"),
                 "--out", str(out), "--summary", str(Path(d) / "s.md")],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(read_csv(out), [], "dry-run 이 통행량을 지어냈습니다")


class TestPipelineIntegration(unittest.TestCase):
    def test_대용_데이터로도_심의가_완주하고_경고가_남는다(self):
        import pipeline
        from tests.test_pipeline import load
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "유동_대용.csv"
            sites = read_csv(ROOT / "후보지.example.csv")
            rows = [{"지점ID": s["후보지명"], "위도": s["위도"], "경도": s["경도"],
                     "도로변": "", "시간대": band, "인원": n,
                     "출처": "길단위인구_상권", "단위면적_m2": 350000,
                     "상권코드": "X", "상권명": "t", "기준분기": "20261"}
                    for s in sites if s["후보지명"]
                    for band, n in (("오전", 42000), ("전체", 210000))]
            FT.write_rows(p, rows)

            data = load()
            data["points"] = M2.load_points(p)
            res = pipeline.analyze_all(**data)
            self.assertTrue(res["후보지"])
            경고 = " ".join(w for r in res["후보지"] for w in r["경고"])
            self.assertIn("실측이 아닙니다", 경고)
            for r in res["후보지"]:
                self.assertGreater(r["수요"]["D_am"], 0)
                self.assertFalse(r["수요"]["실측여부"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
