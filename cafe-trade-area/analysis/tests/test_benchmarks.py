#!/usr/bin/env python3
"""
브랜드 매출 벤치마크 — 공정위 정보공개서 공시

이 데이터의 위험은 **단위**와 **오해** 둘이다.
  · 공시 금액 단위는 천원이다. 만원으로 환산하지 않으면 벤치마크가 10배 어긋난다.
  · 브랜드×시도 평균 한 숫자를 기존점 실매출처럼 쓰면 M4 가 무의미해진다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_benchmarks as B     # noqa: E402
from common import read_csv        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

RAW = [{"yr": "2025", "brandNm": "테스트커피", "corpNm": "테스트(주)",
        "indutyMlsfcNm": "커피", "areaNm": "서울", "frcsCnt": "120",
        "avrgSlsAmt": "384000", "arUnitAvrgSlsAmt": "12000"}]


class TestUnits(unittest.TestCase):
    def test_천원을_만원으로_환산한다(self):
        got = B.normalize(RAW)[0]
        self.assertAlmostEqual(got["연평균매출_만원"], 38400.0)
        self.assertAlmostEqual(got["월평균매출_만원"], 3200.0)
        self.assertAlmostEqual(got["면적당_연매출_만원_per_m2"], 1200.0)

    def test_금액이_비면_빈칸으로_둔다(self):
        got = B.normalize([{"brandNm": "x"}])[0]
        self.assertEqual(got["연평균매출_만원"], "")
        self.assertEqual(got["월평균매출_만원"], "")

    def test_한글_필드명으로_와도_읽는다(self):
        got = B.normalize([{"브랜드명": "가", "평균매출금액": "120000", "시도": "부산"}])[0]
        self.assertEqual(got["브랜드"], "가")
        self.assertEqual(got["시도"], "부산")
        self.assertAlmostEqual(got["연평균매출_만원"], 12000.0)


class TestExpected(unittest.TestCase):
    def test_면적당_공시매출로_업계_수준을_만든다(self):
        rows = B.normalize(RAW)
        got = B.expected_monthly(20, rows)
        # 1200 만원/㎡/년 × 20평 × 3.305785 ÷ 12
        self.assertAlmostEqual(got["기대_월매출_만원"], 1200 * 20 * 3.305785 / 12, places=6)
        self.assertEqual(got["표본"], 1)

    def test_중앙값을_쓴다(self):
        """브랜드 몇 개가 표본을 통째로 끌어올린다 — 평균이면 대조선이 무너진다."""
        rows = [{"면적당_연매출_만원_per_m2": v} for v in (100, 200, 300, 9000)]
        got = B.expected_monthly(20, rows)
        self.assertAlmostEqual(got["면적당_중앙_만원_per_m2"], 250.0)

    def test_표본이_없으면_만들지_않는다(self):
        self.assertIsNone(B.expected_monthly(20, []))
        self.assertIsNone(B.expected_monthly(0, B.normalize(RAW)))


class TestParserSafety(unittest.TestCase):
    def test_오류코드를_오류로_읽는다(self):
        rows, err = B.parse('{"response":{"header":{"resultCode":"30",'
                            '"resultMsg":"SERVICE KEY IS NOT REGISTERED"}}}')
        self.assertEqual(rows, [])
        self.assertIn("30", err)

    def test_XML_로_오면_그렇게_알린다(self):
        rows, err = B.parse('<?xml version="1.0"?><response/>')
        self.assertEqual(rows, [])
        self.assertIn("XML", err)

    def test_중첩된_items_를_찾아낸다(self):
        body = ('{"response":{"header":{"resultCode":"00"},'
                '"body":{"items":[{"brandNm":"가"}]}}}')
        rows, err = B.parse(body)
        self.assertEqual(len(rows), 1)
        self.assertEqual(err, "")

    def test_빈_결과는_조용히_성공하지_않는다(self):
        rows, err = B.parse('{"response":{"header":{"resultCode":"00"},'
                            '"body":{"items":[]}}}')
        self.assertEqual(rows, [])
        self.assertTrue(err)


class TestDryRun(unittest.TestCase):
    def test_매출액을_지어내지_않는다(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "bm.csv"
            r = subprocess.run(
                [sys.executable, str(ROOT / "collect_benchmarks.py"),
                 "--out", str(out), "--summary", str(Path(d) / "s.md")],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(read_csv(out), [], "dry-run 이 매출액을 지어냈습니다")

    def test_기본_연도는_작년이다(self):
        """공시는 전년도 실적이 최신이다 — 올해를 물으면 빈 결과가 온다."""
        import datetime as dt
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(
                [sys.executable, str(ROOT / "collect_benchmarks.py"),
                 "--out", str(Path(d) / "bm.csv"), "--summary", str(Path(d) / "s.md")],
                capture_output=True, text=True, timeout=120)
            self.assertIn(str(dt.date.today().year - 1), r.stdout)

    def test_자사_브랜드를_두_번_조회하지_않는다(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(
                [sys.executable, str(ROOT / "collect_benchmarks.py"),
                 "--out", str(Path(d) / "bm.csv"), "--summary", str(Path(d) / "s.md")],
                capture_output=True, text=True, timeout=120)
            line = [x for x in r.stdout.splitlines() if "브랜드" in x][0]
            names = line.split(":")[-1].split(",")
            self.assertEqual(len(names), len(set(n.strip() for n in names)))


class TestDocumentedHonestly(unittest.TestCase):
    def test_기존점_실매출의_대체가_아니라고_적혀_있다(self):
        """이 데이터를 실매출로 오인하면 M4 검증이 통째로 무의미해진다."""
        src = (ROOT / "collect_benchmarks.py").read_text(encoding="utf-8")
        self.assertIn("기존점 실매출의 대체가 아니다", src)
        self.assertIn("Mode B", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
