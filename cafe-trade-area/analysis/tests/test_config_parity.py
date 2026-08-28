#!/usr/bin/env python3
"""
계수 레지스트리 — 파이썬 ↔ 웹앱 대조

app/js/config.js 는 config.py 의 웹앱 대응물이다. 콘솔에서 계수를 입력받는 이상
두 레지스트리의 **명세 기본값·검증상태·설명이 갈리면 안 된다** — 화면에 뜬 '명세값'
과 파이프라인이 쓰는 값이 다르면 심의 자리에서 잘못된 기준으로 판단하게 된다.

node 가 없으면 건너뛴다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C          # noqa: E402

DUMP = Path(__file__).resolve().parent / "cfg_dump.js"


class TestConfigParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 계수 대조를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"cfg_dump.js 실패:\n{p.stderr}")
        cls.js = json.loads(p.stdout)

    def test_같은_계수를_같은_값으로_가진다(self):
        self.assertEqual(set(self.js["계수"]), set(C.COEFFICIENTS),
                         "config.py 와 config.js 의 계수 목록이 다릅니다")
        for name, (value, state, desc) in C.COEFFICIENTS.items():
            with self.subTest(계수=name):
                got = self.js["계수"][name]
                self.assertAlmostEqual(got["값"], value, places=9)
                self.assertEqual(got["상태"], state)
                self.assertEqual(got["설명"], desc)

    def test_브랜드티어가중이_같다(self):
        self.assertEqual(self.js["브랜드티어가중"], C.BRAND_TIER_WEIGHT)

    def test_ModeB_배점이_같고_합이_100이다(self):
        self.assertEqual(self.js["ModeB배점"], C.MODE_B_WEIGHTS)
        self.assertEqual(sum(sum(v.values()) for v in C.MODE_B_WEIGHTS.values()), 100)

    def test_M5_계수만_콘솔에서_즉시_반영된다(self):
        """콘솔이 다시 계산하는 것은 M5 뿐이다. 다른 모듈 계수를 '즉시 반영' 으로
        표시하면 파이프라인을 돌리지 않고도 반영된 것처럼 오인하게 된다."""
        for name, meta in self.js["계수"].items():
            with self.subTest(계수=name):
                if meta["반영"] == "콘솔":
                    self.assertEqual(meta["모듈"], "M5",
                                     f"{name} 은 M5 가 아닌데 즉시 반영으로 표시돼 있습니다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
