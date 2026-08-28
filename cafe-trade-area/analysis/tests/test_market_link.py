#!/usr/bin/env python3
"""
실거래가는 참고 자료다 — 판정에 들어가지 않는다

법정동코드로 받아 온 매매 실거래가가 **판정을 움직이지 않는다**는 것을 고정한다.
한때 M5 의 보류 신호로 들어가 있었고, 그것을 뺐다. 이유:

  · 매매가는 임대 조건이 아니다. 상업용은 층·용도·전면에 따라 편차가 크다.
  · 매매가를 임대료로 바꾸는 연임대수익률이 미검증 계수다.
  · 그래서 검증되지 않은 환산이 보류를 만들면, 실거래 데이터가 **있는** 지역의
    후보지만 근거 없이 불리해진다. 데이터가 없는 지역은 그 신호를 받지 않으므로.

숫자는 계속 모으고 심의표에 참고로 싣는다. 제시 임대료가 지역 수준을 크게 벗어나면
실사에서 확인할 일이지, 알고리즘이 자동으로 깎을 일이 아니다.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_transactions as TX   # noqa: E402
import config as C                  # noqa: E402
import m5_verdict as M5             # noqa: E402
import pipeline                     # noqa: E402
from common import read_csv         # noqa: E402
from tests.test_pipeline import load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SETTINGS = {"운영": {"변동비": {"원재료율": 0.35, "로열티율": 0.03, "광고분담금율": 0.01,
                          "기타변동비율": 0.022},
                   "고정비": {"고정인건비_월_만원": 620, "기타_월_만원": 170}}}
CLEAN = {"근저당_과다": "N", "임대인_불일치": "N", "소송_계류": "N", "인허가_불가": "N"}


def expected_rent(unit: float, area_py: float) -> float:
    return unit * area_py * M5.PY_PER_M2 * C.c("상업용_연임대수익률") / 12.0


def judge(rent: float, area_py=20, S=90.0):
    """판정. market 인자가 없다 — 시세는 판정에 들어가지 않는다."""
    site = dict(CLEAN, 월임대료_만원=rent, 관리비_만원=30, 전용면적_평=area_py)
    F = rent + 30 + 620 + 170
    med = (F / (1 - 0.412)) * 3.0      # margin 은 넉넉히 — 다른 조건은 비운다
    return M5.judge(site, {"월매출_중앙": med, "월매출_하한": med},
                    SETTINGS, S, [], None)


class TestMarketIsNotAGate(unittest.TestCase):
    """시세가 판정을 움직이지 않는가."""

    def setUp(self):
        self.unit = 1000.0
        self.market = {"건수": 40, "만원_per_m2_중앙": self.unit}
        self.기대 = expected_rent(self.unit, 20)

    def test_판정_함수는_시세를_받지_않는다(self):
        """인자로도 받지 않아야 다시 슬그머니 들어오지 않는다."""
        import inspect
        params = list(inspect.signature(M5.judge).parameters)
        self.assertNotIn("market", params, f"judge 가 아직 시세를 받습니다: {params}")

    def test_시세를_아무리_크게_넘겨도_판정이_그대로다(self):
        싼것 = judge(self.기대 * 0.5)
        비싼것 = judge(self.기대 * 50)          # 시세만 보면 명백히 과한 임대료
        self.assertEqual(싼것["판정"], "통과")
        self.assertEqual(비싼것["판정"], "통과")
        self.assertEqual(비싼것["사유"], [])

    def test_판정_결과에_시세_흔적이_없다(self):
        r = judge(self.기대 * 50)
        self.assertNotIn("시세대조", r)
        self.assertFalse(any("시세" in x for x in r["사유"] + r["비고"]), r)

    def test_환산_자체는_남아_있다(self):
        """숫자를 버리는 게 아니라 판정에서 뺀 것이다. 참고 자료로는 계속 쓴다."""
        site = dict(CLEAN, 월임대료_만원=self.기대, 관리비_만원=30, 전용면적_평=20)
        mkt = M5.market_rent(site, self.market)
        self.assertIsNotNone(mkt)
        self.assertAlmostEqual(mkt["기대_월임대료_만원"], self.기대, delta=1e-9)
        self.assertEqual(mkt["건수"], 40)

    def test_표본이_적으면_참고_환산도_하지_않는다(self):
        n = int(C.c("시세대조_최소건수"))
        site = dict(CLEAN, 월임대료_만원=500, 관리비_만원=30, 전용면적_평=20)
        self.assertIsNone(M5.market_rent(site, {"건수": n - 1, "만원_per_m2_중앙": self.unit}))
        self.assertIsNotNone(M5.market_rent(site, {"건수": n, "만원_per_m2_중앙": self.unit}))

    def test_전용면적이_없으면_참고_환산도_하지_않는다(self):
        """면적이 비면 건물가치를 못 구한다. 0 으로 밀어붙이면 기대 임대료가 0 이 된다."""
        site = dict(CLEAN, 월임대료_만원=500, 관리비_만원=30, 전용면적_평="")
        self.assertIsNone(M5.market_rent(site, self.market))

    def test_보류_배수_계수가_사라졌다(self):
        """판정에서 뺐으므로 그 임계값도 있을 자리가 없다. 남겨 두면 콘솔에 노브가
        보이고, 아무것도 바뀌지 않는데 바뀌는 것처럼 읽힌다."""
        self.assertNotIn("시세대비_보류배수", C.COEFFICIENTS)


class TestSummaryLoading(unittest.TestCase):
    def test_CSV_를_지역코드별_요약으로_읽는다(self):
        rows = [{"지역코드": "11680", "거래금액_만원": 90000, "건물면적_m2": 100,
                 "만원_per_m2": 900, "거래일": "2026-01-02"},
                {"지역코드": "11680", "거래금액_만원": 110000, "건물면적_m2": 100,
                 "만원_per_m2": 1100, "거래일": "2026-03-02"},
                {"지역코드": "41135", "거래금액_만원": 50000, "건물면적_m2": 50,
                 "만원_per_m2": 1000, "거래일": "2026-02-02"}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "실거래가.csv"
            TX.write_rows(p, rows)
            got = TX.load_summaries(p)
        self.assertEqual(set(got), {"11680", "41135"})
        self.assertEqual(got["11680"]["건수"], 2)
        self.assertAlmostEqual(got["11680"]["만원_per_m2_중앙"], 1000.0)

    def test_단가를_못_읽은_행이_중앙값을_끌어내리지_않는다(self):
        rows = [{"지역코드": "11680", "거래금액_만원": 90000, "건물면적_m2": "",
                 "만원_per_m2": "", "거래일": "2026-01-02"},
                {"지역코드": "11680", "거래금액_만원": 100000, "건물면적_m2": 100,
                 "만원_per_m2": 1000, "거래일": "2026-02-02"}]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "실거래가.csv"
            TX.write_rows(p, rows)
            got = TX.load_summaries(p)
        self.assertAlmostEqual(got["11680"]["만원_per_m2_중앙"], 1000.0)

    def test_없는_파일은_빈_요약이다(self):
        self.assertEqual(TX.load_summaries(Path("/없는/경로/실거래가.csv")), {})

    def test_법정동코드_앞_다섯_자리가_조회_키다(self):
        self.assertEqual(TX.lawd("1168010100"), "11680")
        self.assertEqual(TX.lawd("11680"), "11680")
        self.assertEqual(TX.lawd(""), "")


class TestPipelineWiring(unittest.TestCase):
    """파이프라인이 후보지의 법정동코드로 지역 요약을 실제로 찾아 M5 에 넘기는가."""

    @classmethod
    def setUpClass(cls):
        cls.data = load()
        cls.단가 = 1200.0

    def _run(self, market):
        sites = [dict(r) for r in self.data["sites"]]
        for r in sites:
            r["법정동코드"] = "1120010300"          # 성동구 — 전부 같은 지역으로 둔다
        d = dict(self.data, sites=sites)
        return pipeline.analyze_all(**d, market=market)

    def test_지역코드로_요약을_찾아_참고_필드에_싣는다(self):
        """판정 안이 아니라 레코드 옆이다 — 참고 자료의 자리."""
        res = self._run({"11200": {"건수": 30, "만원_per_m2_중앙": self.단가}})
        대조 = [r["시세대조"] for r in res["후보지"]]
        self.assertTrue(all(x is not None for x in 대조), "시세 대조가 하나도 안 걸렸습니다")
        for r in res["후보지"]:
            기대 = expected_rent(self.단가, float(r["후보지"]["전용면적_평"]))
            self.assertAlmostEqual(r["시세대조"]["기대_월임대료_만원"], 기대, delta=1e-9)
            self.assertNotIn("시세대조", r["판정"])

    def test_다른_지역의_시세는_붙지_않는다(self):
        res = self._run({"41135": {"건수": 30, "만원_per_m2_중앙": self.단가}})
        self.assertTrue(all(r["시세대조"] is None for r in res["후보지"]))

    def test_법정동코드가_없으면_대조하지_않는다(self):
        res = pipeline.analyze_all(
            **self.data, market={"11200": {"건수": 30, "만원_per_m2_중앙": self.단가}})
        self.assertTrue(all(r["시세대조"] is None for r in res["후보지"]),
                        "법정동코드가 빈 예시 후보지에 시세가 붙었습니다")

    def test_시세가_있든_없든_판정이_같다(self):
        """법정동에서 온 값이 판정을 움직이면 안 된다 — 데이터가 있는 지역만
        불리해지는 일이 생긴다."""
        큰것 = self._run({"11200": {"건수": 30, "만원_per_m2_중앙": self.단가 * 100}})
        없음 = self._run({})
        self.assertEqual([r["판정"]["판정"] for r in 큰것["후보지"]],
                         [r["판정"]["판정"] for r in 없음["후보지"]])

    def test_시세가_없을_때와_판정이_같다(self):
        없이 = pipeline.analyze_all(**self.data)
        빈것 = pipeline.analyze_all(**self.data, market={})
        self.assertEqual([r["판정"]["판정"] for r in 없이["후보지"]],
                         [r["판정"]["판정"] for r in 빈것["후보지"]])


class TestFetchIsOptIn(unittest.TestCase):
    """수집은 명시적으로 켤 때만 일어난다 — 심의표를 뽑을 때마다 외부 API 를 두드리면
    키가 없는 환경에서 파이프라인이 실패하고, 요금제·쿼터도 사람 모르게 소모된다."""

    class Args:
        def __init__(self, path, collect=False):
            self.실거래 = str(path)
            self.실거래_수집 = collect
            self.실거래_개월 = 12

    def test_기본은_저장된_표만_읽는다(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "실거래가.csv"
            TX.write_rows(p, [{"지역코드": "11200", "거래금액_만원": 80000,
                               "건물면적_m2": 100, "만원_per_m2": 800,
                               "거래일": "2026-05-01"}])
            got = pipeline.load_market([], self.Args(p))
        self.assertEqual(got["11200"]["건수"], 1)

    def test_키가_없으면_수집을_켜도_조용히_건너뛴다(self):
        import os
        saved = os.environ.pop("DATA_GO_KR_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as d:
                got = pipeline.load_market(
                    [{"후보지명": "가", "법정동코드": "1120010300"}],
                    self.Args(Path(d) / "실거래가.csv", collect=True))
            self.assertEqual(got, {})
        finally:
            if saved is not None:
                os.environ["DATA_GO_KR_KEY"] = saved


class TestDocumentedHonestly(unittest.TestCase):
    """문서가 코드와 같은 말을 하는가. 여기가 어긋나면 '반영된다고 적혀 있는데
    반영되지 않는' 상태가 되고, 그것이 심의에서 가장 위험하다."""

    def test_보류_신호라고_말하는_문서가_남아_있지_않다(self):
        """판정에서 뺐다. '보류 신호로 쓰인다' 는 설명이 남아 있으면 거짓말이 된다."""
        for p in (ROOT / "collect_transactions.py", ROOT / "review_sites.py",
                  ROOT / "m5_verdict.py"):
            text = p.read_text(encoding="utf-8")
            for 거짓 in ("보류 신호로만", "보류로 잡습니다", "보류 신호로 들어간다"):
                self.assertNotIn(거짓, text, f"{p.name}: {거짓}")

    def test_참고_자료임을_말한다(self):
        for p in (ROOT / "collect_transactions.py", ROOT / "review_sites.py"):
            text = p.read_text(encoding="utf-8")
            self.assertIn("참고", text, p.name)
            self.assertIn("들어가지 않", text, p.name)

    def test_환산_계수가_미검증으로_공시된다(self):
        for name in ("상업용_연임대수익률", "시세대조_최소건수"):
            self.assertEqual(C.COEFFICIENTS[name][1], "ESTIMATED", name)
            self.assertIn(name, [k for k, _, _ in C.unvalidated()])


if __name__ == "__main__":
    unittest.main(verbosity=2)
