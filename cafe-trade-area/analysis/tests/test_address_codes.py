#!/usr/bin/env python3
"""
우편번호·법정동코드 — 입력에서 산출물까지 실제로 도달하는지

입력 페이지가 주소 검색으로 받아 두 값을 CSV 에 싣는다. 실으라고 해 놓고 파이프라인이
버리면 아무 데도 남지 않으므로, 심의표와 심의결과.json 까지 도달하는지 확인한다.

두 값은 M1~M6 계산에 들어가지 않는다(좌표로 격자·경쟁을 잡는다). 계산에 안 쓰는 값을
쓰는 것처럼 보이게 하지 않으려고, 어떤 모듈도 읽지 않는다는 사실도 함께 고정한다.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "후보지.example.csv"
CODES = ("우편번호", "법정동코드")
# 후보지 행을 읽어 계산하는 모듈
CALC = ["m1_area.py", "m2_demand.py", "m3_huff.py", "m4_revenue.py", "m5_verdict.py"]


class TestAddressCodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SITES.open(encoding="utf-8-sig", newline="") as f:
            cls.header = next(csv.reader(f))

    def test_후보지_CSV_에_열이_있다(self):
        for c in CODES:
            with self.subTest(열=c):
                self.assertIn(c, self.header)

    def test_주소_바로_뒤에_온다(self):
        """읽는 사람이 주소와 함께 보도록 붙여 둔다."""
        i = self.header.index("주소")
        self.assertEqual(self.header[i + 1:i + 3], list(CODES))

    def test_계산_모듈은_읽지_않는다(self):
        """계산에 안 쓰는 값이다. 쓰기 시작하면 이 테스트가 먼저 알려 준다."""
        for mod in CALC:
            src = (ROOT / mod).read_text(encoding="utf-8")
            for c in CODES:
                with self.subTest(모듈=mod, 열=c):
                    self.assertNotIn(c, src)

    def test_심의표와_JSON_까지_도달한다(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            sites = t / "후보지.csv"
            rows = list(csv.DictReader(SITES.open(encoding="utf-8-sig", newline="")))
            rows[0]["우편번호"] = "04782"
            rows[0]["법정동코드"] = "1120012400"
            with sites.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=self.header)
                w.writeheader()
                w.writerows(rows)

            md, js = t / "심의표.md", t / "심의결과.json"
            p = subprocess.run(
                [sys.executable, "review_sites.py", "--sites", str(sites),
                 "--out", str(md), "--json", str(js),
                 "--계수", str(t / "없는계수.json")],
                cwd=ROOT, capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stderr)

            report = md.read_text(encoding="utf-8")
            self.assertIn("04782", report, "심의표에 우편번호가 없습니다")
            self.assertIn("1120012400", report, "심의표에 법정동코드가 없습니다")

            data = json.loads(js.read_text(encoding="utf-8"))
            first = [s for s in data["후보지"] if s["이름"] == rows[0]["후보지명"]][0]
            self.assertEqual(first["입력"]["우편번호"], "04782")
            self.assertEqual(first["입력"]["법정동코드"], "1120012400")


if __name__ == "__main__":
    unittest.main(verbosity=2)
