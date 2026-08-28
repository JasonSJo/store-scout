#!/usr/bin/env python3
"""
통합 테스트 — 동봉한 예시 데이터로 파이프라인 전체를 돌린다.

모듈 단위 테스트가 통과해도 배선이 틀리면 산출물이 엉킨다. 여기서는
실제 CSV/GeoJSON 을 읽어 M1~M5 를 끝까지 태우고, 결과가 현실 범위에
있는지와 판정 분기가 실제로 갈리는지를 본다.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C          # noqa: E402
import m1_area as M1        # noqa: E402
import m2_demand as M2      # noqa: E402
import m3_huff as M3        # noqa: E402
import m4_revenue as M4     # noqa: E402
import pipeline             # noqa: E402
from common import read_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load(stores_file="기존점.example.csv"):
    return dict(
        sites=read_csv(ROOT / "후보지.example.csv"),
        stores=read_csv(ROOT / stores_file),
        cells=M2.load_cells(ROOT / "격자인구.example.csv"),
        points=M2.load_points(ROOT / "유동인구.example.csv"),
        competitors=M3.load_competitors(ROOT / "경쟁점.example.csv"),
        isos=M1.load_isochrones(ROOT / "등시선.example.geojson"),
        settings=pipeline.load_settings(ROOT / "설정.example.yaml"),
    )


class TestFixtures(unittest.TestCase):
    def test_every_location_has_both_isochrones(self):
        isos = M1.load_isochrones(ROOT / "등시선.example.geojson")
        names = {n for n, _ in isos}
        for row in read_csv(ROOT / "후보지.example.csv"):
            self.assertIn((row["후보지명"], "P5"), isos)
            self.assertIn((row["후보지명"], "P10"), isos)
        for row in read_csv(ROOT / "기존점.example.csv"):
            self.assertIn((row["점포명"], "P10"), isos)
        self.assertGreaterEqual(len(names), 22)

    def test_isochrone_R_in_plausible_range(self):
        isos = M1.load_isochrones(ROOT / "등시선.example.geojson")
        for row in read_csv(ROOT / "후보지.example.csv"):
            a = M1.resolve(row["후보지명"], float(row["위도"]), float(row["경도"]), isos)
            self.assertEqual(a["출처"], "등시선")
            self.assertTrue(0.2 < a["R"] < 1.0, f"{row['후보지명']} R={a['R']}")
            self.assertLess(a["P5_면적_m2"], a["P10_면적_m2"])

    def test_existing_store_sales_are_realistic(self):
        v = sorted(float(r["월매출_만원"]) for r in read_csv(ROOT / "기존점.example.csv"))
        self.assertGreater(v[0], 800)
        self.assertLess(v[-1], 12000)

    def test_competitor_tiers_are_known(self):
        for r in M3.load_competitors(ROOT / "경쟁점.example.csv"):
            self.assertIn(r["티어"], C.BRAND_TIER_WEIGHT)


class TestModeA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = pipeline.analyze_all(**{k: v for k, v in load().items()})

    def test_mode_a_activates(self):
        self.assertEqual(self.res["모드"], "A")
        self.assertGreaterEqual(self.res["모델"]["표본수"], int(C.c("ModeA_최소표본")))

    def test_model_quality(self):
        m = self.res["모델"]
        self.assertGreater(m["R2"], 0.7)
        self.assertLess(m["CV"]["MAPE"], C.c("재적합_MAPE"),
                        "예시 모델의 CV MAPE 가 재적합 임계를 넘습니다")

    def test_every_candidate_gets_a_verdict(self):
        for r in self.res["후보지"]:
            self.assertIn(r["판정"]["판정"], C.VERDICTS)
            self.assertIsNotNone(r["판정"]["BEP_만원"])

    def test_prediction_intervals_ordered_and_realistic(self):
        for r in self.res["후보지"]:
            p = r["매출"]
            self.assertLess(p["월매출_하한"], p["월매출_중앙"])
            self.assertLess(p["월매출_중앙"], p["월매출_상한"])
            self.assertTrue(800 < p["월매출_중앙"] < 12000,
                            f"{r['이름']} {p['월매출_중앙']}")

    def test_verdicts_discriminate(self):
        kinds = {r["판정"]["판정"] for r in self.res["후보지"]}
        self.assertGreaterEqual(len(kinds), 2, "예시 데이터가 판정을 변별하지 못합니다")

    def test_fatal_flag_site_is_rejected(self):
        hit = [r for r in self.res["후보지"] if r["후보지"].get("소송_계류") == "Y"]
        self.assertTrue(hit)
        for r in hit:
            self.assertEqual(r["판정"]["판정"], "부결")
            self.assertTrue(r["판정"]["치명플래그"])

    def test_unchecked_site_is_flagged(self):
        hit = [r for r in self.res["후보지"] if r["후보지"].get("소송_계류") == ""]
        self.assertTrue(hit)
        for r in hit:
            self.assertEqual(len(r["판정"]["치명_미확인"]), 4)

    def test_cannibalization_detected_for_dense_area(self):
        ov = max(r["판정"]["카니발"]["최대_overlap"] for r in self.res["후보지"])
        self.assertGreater(ov, 0.0, "자사 기존점과의 중첩이 한 건도 잡히지 않았습니다")

    def test_s_gate_degeneracy_is_surfaced(self):
        """명세의 S<70 임계가 이 풀에서 축퇴한다는 사실이 결과에 남아야 한다."""
        r = self.res["후보지"][0]
        self.assertTrue(r["S_게이트_축퇴"])
        self.assertTrue(any("S 게이트 축퇴" in x for x in r["판정"]["비고"]))


class TestModeB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = pipeline.analyze_all(**load("기존점.example_초기.csv"))

    def test_mode_b_activates_below_threshold(self):
        self.assertEqual(self.res["모드"], "B")

    def test_anchored_to_reference_stores(self):
        for r in self.res["후보지"]:
            self.assertEqual(r["매출"]["모드"], "B")
            self.assertTrue(r["매출"]["기준점포"])

    def test_circularity_warning_present(self):
        for r in self.res["후보지"]:
            self.assertTrue(any("참고자료" in w for w in r["매출"]["경고"]),
                            "Mode B 결과에 순환논리 경고가 없습니다")

    def test_band_is_flagged_as_assumption(self):
        w = " ".join(self.res["후보지"][0]["매출"]["경고"])
        self.assertIn("미검증 가정값", w)


class TestCLI(unittest.TestCase):
    """CLI 가 실제로 파일을 만들고 통제 문구를 인쇄하는지."""

    def run_tool(self, *args):
        p = subprocess.run([sys.executable, *args], cwd=ROOT,
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return p.stdout

    def test_review_writes_outputs_with_governance_header(self):
        self.run_tool("review_sites.py")
        md = (ROOT / "output" / "심의표.md").read_text(encoding="utf-8")
        self.assertIn("대외 배포 금지", md)
        self.assertIn("예상매출액 산정서", md)
        self.assertIn("미검증 계수", md)
        self.assertTrue((ROOT / "output" / "심의결과.json").exists())

    def test_report_marks_internal_only(self):
        self.run_tool("build_report.py", "--site", "판교")
        md = next((ROOT / "output" / "reports").glob("심의리포트_판교*.md")).read_text(encoding="utf-8")
        self.assertIn("사내 한정", md)
        self.assertIn("M6", md)
        self.assertNotIn("가맹 희망자에게 제출", md)

    def test_calibrate_proposes_without_applying(self):
        before = C.c("거리마찰_람다")
        out = self.run_tool("calibrate.py")
        self.assertIn("제안", out)
        self.assertEqual(C.c("거리마찰_람다"), before, "M6 가 계수를 자동 적용했습니다")
        self.assertIn("사람이 반영", (ROOT / "output" / "보정_제안.yaml").read_text(encoding="utf-8"))

    def test_collectors_are_dry_run_by_default(self):
        out = self.run_tool("fetch_isochrones.py")
        self.assertIn("dry-run", out)
        out = self.run_tool("collect_competitors.py")
        self.assertIn("dry-run", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
