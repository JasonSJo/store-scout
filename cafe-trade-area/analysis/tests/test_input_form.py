#!/usr/bin/env python3
"""
데이터 입력 폼 — 내보낸 CSV 를 파이프라인이 그대로 먹는지

input/ 페이지는 후보지 CSV 를 만드는 유일한 화면이다. 폼 항목과 CSV 열이 하나라도
어긋나면 사람이 열심히 채운 파일을 파이프라인이 읽지 못한다. 그래서 열 목록·순서를
실제 예시 CSV 와 대조하고, 화면에 표시하는 '모듈' 표기도 소스와 맞는지 본다.

node 가 없으면 건너뛴다.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DUMP = ROOT / "tests" / "input_form_dump.js"
SITES = ROOT / "후보지.example.csv"

# 후보지 행을 읽는 모듈. 여기 어디에도 없으면 알고리즘에 들어가지 않는 값이다.
MODULES = ["m1_area.py", "m2_demand.py", "m3_huff.py", "m4_revenue.py",
           "m5_verdict.py", "pipeline.py"]


class TestInputForm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 입력 폼 대조를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"input_form_dump.js 실패:\n{p.stderr}")
        cls.form = json.loads(p.stdout)
        with SITES.open(encoding="utf-8-sig", newline="") as f:
            cls.header = next(csv.reader(f))
        cls.src = {m: (ROOT / m).read_text(encoding="utf-8") for m in MODULES}

    def test_열_목록과_순서가_예시_CSV_와_같다(self):
        """순서까지 같아야 한다 — 내보낸 파일이 기존 파일과 나란히 놓여도 헷갈리지 않는다."""
        self.assertEqual(self.form["열"], self.header)

    def test_모든_열이_폼에_있다(self):
        """열이 폼에 없으면 그 값은 영영 입력할 수 없다."""
        for col in self.header:
            with self.subTest(열=col):
                self.assertIn(col, self.form["항목"])

    def test_폼에만_있는_항목은_없다(self):
        for k in self.form["항목"]:
            with self.subTest(항목=k):
                self.assertIn(k, self.header)

    def test_모든_항목이_어느_그룹엔가_속한다(self):
        """그룹에서 빠진 항목은 화면에 렌더되지 않아 입력할 수 없다."""
        placed = [k for g in self.form["그룹"] for k in g["항목"]]
        self.assertEqual(sorted(placed), sorted(self.form["항목"].keys()))
        self.assertEqual(len(placed), len(set(placed)), "한 항목이 두 그룹에 있습니다")

    def test_치명_플래그가_config_와_같다(self):
        self.assertEqual(self.form["치명"], C.FATAL_KEYS)

    def test_필수_항목은_판정에_반드시_필요한_값이다(self):
        """필수로 막는 값은 없으면 실제로 심의가 불가능한 것이어야 한다.
        이름(구분)·좌표(M1~M3 시작점)·월임대료(BEP 계산)."""
        req = {k for k, v in self.form["항목"].items() if v["필수"]}
        self.assertEqual(req, {"후보지명", "위도", "경도", "월임대료_만원"})

    def test_미사용_표기한_항목은_어떤_모듈도_읽지_않는다(self):
        """화면에 '—' 로 적어 둔 항목이 실제로는 쓰이고 있으면 거짓말이 된다."""
        for k, v in self.form["항목"].items():
            if v["모듈"] not in ("—",):
                continue
            for mod, src in self.src.items():
                with self.subTest(항목=k, 모듈=mod):
                    self.assertNotIn(k, src, f"{k} 을 {mod} 이 읽고 있습니다")

    def test_모듈을_적은_항목은_그_모듈이_실제로_읽는다(self):
        """'M5' 라 적어 두고 M5 가 안 읽으면 입력자가 잘못된 기대를 갖는다."""
        for k, v in self.form["항목"].items():
            mods = [m.strip() for m in v["모듈"].split("·")]
            if v["모듈"] in ("—", "표시용"):
                continue
            # 치명 플래그는 m5_verdict 가 config.FATAL_FLAGS 를 통해 읽으므로
            # 모듈 파일에 이름이 그대로 나오지 않는다. 목록 일치는 위 테스트가 본다.
            if k in C.FATAL_KEYS:
                continue
            hit = [m for m, src in self.src.items() if k in src]
            with self.subTest(항목=k):
                self.assertTrue(hit, f"{k} 을 읽는 모듈이 없는데 '{v['모듈']}' 이라 적혀 있습니다")
            if "M5" in mods:
                with self.subTest(항목=k, 확인="M5"):
                    self.assertIn(k, self.src["m5_verdict.py"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
