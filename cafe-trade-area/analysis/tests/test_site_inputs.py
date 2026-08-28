#!/usr/bin/env python3
"""
후보지 입력값 — 콘솔이 편집하게 열어 둔 필드가 실제와 맞는지

콘솔은 필드마다 '즉시 반영 / 재실행 필요 / 미사용' 을 표시한다. 이 표시가 실제
코드와 어긋나면 심의 자리에서 반영되지 않은 값을 반영된 것으로 착각하게 된다.
그래서 표시를 파이프라인 소스와 직접 대조한다.

node 가 없으면 건너뛴다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C          # noqa: E402
from common import read_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "tests" / "inputs_dump.js"

# 후보지 행을 읽는 모듈들. 여기 어디에도 안 나오면 알고리즘에 안 들어가는 값이다.
MODULES = ["m1_area.py", "m2_demand.py", "m3_huff.py", "m4_revenue.py",
           "m5_verdict.py", "pipeline.py"]


class TestSiteInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 입력값 대조를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"inputs_dump.js 실패:\n{p.stderr}")
        data = json.loads(p.stdout)
        cls.fields = data["필드"]
        cls.fatal = data["치명"]
        cls.src = {m: (ROOT / m).read_text(encoding="utf-8") for m in MODULES}
        cls.header = list(read_csv(ROOT / "후보지.example.csv")[0].keys())

    def test_모든_편집_필드가_후보지_CSV_에_있다(self):
        """CSV 에 없는 열을 편집하게 열어 두면 내보낸 파일이 원본과 어긋난다."""
        for name in self.fields:
            with self.subTest(필드=name):
                self.assertIn(name, self.header)

    def test_치명_플래그_목록이_config_와_같다(self):
        self.assertEqual(self.fatal, C.FATAL_KEYS)

    def test_즉시반영_필드는_M5_가_실제로_읽는다(self):
        """'즉시 반영' 은 콘솔이 M5 를 다시 계산해 반영한다는 뜻이다.
        M5 가 읽지 않는 값에 이 표시가 붙으면 거짓말이 된다."""
        m5 = self.src["m5_verdict.py"]
        for name, meta in self.fields.items():
            if meta["반영"] != "콘솔":
                continue
            with self.subTest(필드=name):
                if name in C.FATAL_KEYS:
                    continue          # config.FATAL_FLAGS 를 통해 읽는다
                self.assertIn(name, m5, f"{name} 이 m5_verdict.py 에 없습니다")

    def test_미사용_필드는_어떤_모듈도_읽지_않는다(self):
        """'알고리즘에 들어가지 않는 값' 이라는 화면 문구를 소스로 검증한다."""
        for name, meta in self.fields.items():
            if meta["반영"] != "미사용":
                continue
            for mod, src in self.src.items():
                with self.subTest(필드=name, 모듈=mod):
                    self.assertNotIn(name, src,
                                     f"{name} 을 {mod} 이 읽고 있습니다 — '미사용' 표시가 틀렸습니다")

    def test_재실행필요_필드는_M5_밖에서_쓰인다(self):
        """'재실행 필요' 는 파이프라인 모듈이 읽지만 콘솔은 못 돌린다는 뜻이다.
        어디서도 안 읽히면 '미사용' 으로 표시해야 한다."""
        for name, meta in self.fields.items():
            if meta["반영"] != "파이프라인":
                continue
            hit = [m for m, src in self.src.items() if name in src]
            with self.subTest(필드=name):
                self.assertTrue(hit, f"{name} 을 읽는 모듈이 없습니다 — '미사용' 이어야 합니다")

    def test_월임대료는_M4_와_M5_양쪽에_들어간다(self):
        """콘솔이 즉시 반영하는 것은 M5 쪽뿐이라는 사실이 설명에 남아 있어야 한다."""
        self.assertIn("월임대료_만원", self.src["m4_revenue.py"])
        self.assertIn("월임대료_만원", self.src["m5_verdict.py"])
        self.assertIn("M4", self.fields["월임대료_만원"]["모듈"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
