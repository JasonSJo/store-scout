#!/usr/bin/env python3
"""
계수 입력 — 콘솔이 내보낸 계수.json 이 실제로 알고리즘을 움직이는지

콘솔에서 값을 넣을 수 있다는 것만으로는 부족하다. 그 파일을 파이프라인에 넣었을 때
판정이 실제로 달라지고, 어떤 계수가 사람이 넣은 값인지 산출물에 남아야 한다.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SETTINGS = {"운영": {"변동비": {"원재료율": 0.35, "로열티율": 0.03, "광고분담금율": 0.01,
                          "기타변동비율": 0.022},
                   "고정비": {"고정인건비_월_만원": 620, "기타_월_만원": 170}}}
SITE = {"월임대료_만원": 400, "관리비_만원": 30,
        "근저당_과다": "N", "임대인_불일치": "N", "소송_계류": "N", "인허가_불가": "N"}


def write(obj) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(obj, f, ensure_ascii=False)
    f.close()
    return Path(f.name)


class TestOverrides(unittest.TestCase):
    def setUp(self):
        # 계수 레지스트리는 모듈 전역이라 테스트마다 새로 읽어 서로 오염되지 않게 한다
        import config
        self.C = importlib.reload(config)
        import m5_verdict
        self.M5 = importlib.reload(m5_verdict)

    def tearDown(self):
        import config
        importlib.reload(config)
        import m5_verdict
        importlib.reload(m5_verdict)

    def test_파일이_없으면_아무것도_바뀌지_않는다(self):
        applied = self.C.apply_overrides(Path("/존재하지-않는-경로/계수.json"))
        self.assertEqual(applied, {})
        self.assertEqual(self.C.c("보류_점수"), 70.0)
        self.assertEqual(self.C.overridden(), [])

    def test_임계값_입력이_판정을_뒤집는다(self):
        rev = {"월매출_중앙": 9000.0, "월매출_하한": 8000.0}
        before = self.M5.judge(SITE, rev, SETTINGS, 55.0, [], None)
        self.assertEqual(before["판정"], "보류")           # S 55 < 70
        self.assertIn("S 55.0 < 70", "; ".join(before["사유"]))

        p = write({"계수": {"보류_점수": 50.0}})
        self.C.apply_overrides(p)
        after = self.M5.judge(SITE, rev, SETTINGS, 55.0, [], None)
        self.assertEqual(after["판정"], "통과")            # 임계가 내려가 게이트를 통과
        p.unlink()

    def test_잠식계수_입력이_잠식액에_반영된다(self):
        ov = [{"점포명": "기존점", "overlap": 0.4, "월매출_만원": 3000.0}]
        base = self.M5.cannibalization(ov)["잠식액_합_만원"]
        p = write({"계수": {"잠식계수_카파": 1.0}})
        self.C.apply_overrides(p)
        self.assertAlmostEqual(self.M5.cannibalization(ov)["잠식액_합_만원"], base * 2, places=9)
        p.unlink()

    def test_배점과_티어가중을_제자리에서_바꾼다(self):
        """다른 모듈이 import 로 참조하고 있으므로 새 객체로 갈아치우면 안 된다."""
        weights, tiers = self.C.MODE_B_WEIGHTS, self.C.BRAND_TIER_WEIGHT
        p = write({"ModeB배점": {"수요": {"오전유동": 25}}, "브랜드티어가중": {"저가형": 0.9}})
        self.C.apply_overrides(p)
        self.assertIs(weights, self.C.MODE_B_WEIGHTS)
        self.assertIs(tiers, self.C.BRAND_TIER_WEIGHT)
        self.assertEqual(self.C.MODE_B_WEIGHTS["수요"]["오전유동"], 25)
        self.assertEqual(self.C.BRAND_TIER_WEIGHT["저가형"], 0.9)
        p.unlink()

    def test_모르는_이름은_조용히_삼키지_않는다(self):
        for bad in ({"계수": {"없는계수": 1}},
                    {"브랜드티어가중": {"없는티어": 1}},
                    {"ModeB배점": {"없는축": {"x": 1}}},
                    {"ModeB배점": {"수요": {"없는항목": 1}}}):
            p = write(bad)
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                self.C.apply_overrides(p)
            p.unlink()

    def test_입력한_계수가_기록으로_남는다(self):
        p = write({"계수": {"거리마찰_람다": 1.8}})
        self.C.apply_overrides(p)
        self.assertEqual(self.C.overridden(), [("거리마찰_람다", 2.2, 1.8)])
        p.unlink()

    def test_운영계수는_설정에_얹힌다(self):
        import pipeline
        merged = pipeline.merge_ops(SETTINGS, {"변동비": {"원재료율": 0.42}})
        self.assertEqual(merged["운영"]["변동비"]["원재료율"], 0.42)
        self.assertEqual(merged["운영"]["변동비"]["로열티율"], 0.03)   # 나머지는 보존
        self.assertEqual(SETTINGS["운영"]["변동비"]["원재료율"], 0.35)  # 원본은 그대로


if __name__ == "__main__":
    unittest.main(verbosity=2)
