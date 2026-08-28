#!/usr/bin/env python3
"""
실거래가 수집 — 파서와 안전장치

실제 호출로 검증하지 못한 연동이다(서비스키 없음). 그래서 최소한 **응답을 어떻게
다루는지**는 고정한다: 포털이 오류를 200 으로 XML 에 담아 보내는 것, 태그명이 바뀔 수
있는 것, 금액에 쉼표가 섞이는 것, 항목을 하나도 못 읽었을 때 조용히 성공하지 않는 것.

⚠ 아래 XML 은 **가정한 스키마**다. 실제 응답이 다르면 이 테스트는 통과해도 수집은
   실패한다 — 그 경우 collect_transactions.py 가 응답 앞부분을 출력하므로 그것을 보고
   FIELDS 를 고치고 이 픽스처도 함께 고쳐야 한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_transactions as T   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def envelope(items: str, code: str = "00") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>{code}</resultCode><resultMsg>OK</resultMsg></header>
<body><items>{items}</items><numOfRows>10</numOfRows><totalCount>1</totalCount></body>
</response>"""


ITEM_KO = """<item>
  <거래금액> 45,000 </거래금액><건물면적>132.5</건물면적><대지면적>80.1</대지면적>
  <년>2026</년><월>7</월><일>3</일><법정동> 성수동2가 </법정동>
  <용도지역>준공업지역</용도지역><건물주용도>제2종근린생활시설</건물주용도>
  <층>1</층><건축년도>1998</건축년도>
</item>"""

# 포털이 영문 태그로 바꾼 경우
ITEM_EN = """<item>
  <dealAmount>30,000</dealAmount><buildingAr>66.0</buildingAr>
  <dealYear>2026</dealYear><dealMonth>6</dealMonth><dealDay>15</dealDay>
  <umdNm>역삼동</umdNm><buildingUse>근린생활시설</buildingUse><floor>2</floor>
</item>"""


class TestParse(unittest.TestCase):
    def test_한글_태그를_읽는다(self):
        rows, err = T.parse(envelope(ITEM_KO))
        self.assertEqual(err, "")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["거래금액_만원"], 45000.0)      # 쉼표·공백 제거
        self.assertEqual(r["건물면적_m2"], 132.5)
        self.assertEqual(r["거래일"], "2026-07-03")        # 한 자리 월·일을 채운다
        self.assertEqual(r["법정동"], "성수동2가")
        self.assertAlmostEqual(r["만원_per_m2"], round(45000 / 132.5, 2))

    def test_영문_태그도_읽는다(self):
        """포털이 표기를 바꾼 이력이 있어 후보를 여러 개 둔다."""
        rows, err = T.parse(envelope(ITEM_EN))
        self.assertEqual(err, "")
        self.assertEqual(rows[0]["거래금액_만원"], 30000.0)
        self.assertEqual(rows[0]["거래일"], "2026-06-15")

    def test_면적이_없으면_단가를_비워_둔다(self):
        """0 으로 나누지 않고, 없는 값을 0 으로 적지도 않는다."""
        rows, _ = T.parse(envelope(
            "<item><거래금액>1000</거래금액><년>2026</년><월>1</월><일>2</일></item>"))
        self.assertEqual(rows[0]["만원_per_m2"], "")

    def test_오류를_200_으로_받아도_오류로_다룬다(self):
        """포털은 인증 실패도 HTTP 200 + XML 로 보낸다. 성공으로 세면 빈 표가 남는다."""
        rows, err = T.parse(envelope("", code="30"))
        self.assertEqual(rows, [])
        self.assertIn("API 오류 30", err)

    def test_항목이_없으면_조용히_성공하지_않는다(self):
        rows, err = T.parse(envelope(""))
        self.assertEqual(rows, [])
        self.assertTrue(err)

    def test_깨진_XML_을_예외로_흘리지_않는다(self):
        rows, err = T.parse("<not xml")
        self.assertEqual(rows, [])
        self.assertIn("파싱 실패", err)

    def test_필수값이_빠진_항목은_버린다(self):
        """금액이나 날짜가 없으면 요약을 오염시킨다."""
        rows, _ = T.parse(envelope("<item><건물면적>10</건물면적></item>" + ITEM_KO))
        self.assertEqual(len(rows), 1)


class TestHelpers(unittest.TestCase):
    def test_지역코드는_법정동코드_앞_5자리(self):
        self.assertEqual(T.lawd("1120012400"), "11200")
        self.assertEqual(T.lawd("11200"), "11200")
        for bad in ("", "1120", "abcd", None):
            with self.subTest(입력=bad):
                self.assertEqual(T.lawd(bad), "")

    def test_개월_역산이_연도를_넘는다(self):
        ms = T.months_back(14)
        self.assertEqual(len(ms), 14)
        self.assertEqual(len(set(ms)), 14, "중복된 달이 있습니다")
        for m in ms:
            with self.subTest(달=m):
                self.assertRegex(m, r"^\d{4}(0[1-9]|1[0-2])$")

    def test_중앙값으로_요약한다(self):
        """상업용은 대형 거래 한 건이 평균을 통째로 끌어올린다."""
        rows = [{"만원_per_m2": v, "거래금액_만원": v * 100, "거래일": f"2026-0{i+1}-01"}
                for i, v in enumerate([10.0, 20.0, 900.0])]
        s = T.summarize(rows)
        self.assertEqual(s["건수"], 3)
        self.assertEqual(s["만원_per_m2_중앙"], 20.0)
        self.assertEqual(s["최근_거래일"], "2026-03-01")

    def test_빈_입력에도_터지지_않는다(self):
        s = T.summarize([])
        self.assertEqual(s["건수"], 0)
        self.assertIsNone(s["만원_per_m2_중앙"])


class TestCLI(unittest.TestCase):
    def run_cli(self, *args, env=None):
        e = dict(os.environ)
        e.pop("DATA_GO_KR_KEY", None)
        e.update(env or {})
        return subprocess.run([sys.executable, "collect_transactions.py", *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=120, env=e)

    def test_dry_run_은_네트워크를_쓰지_않고_금액을_지어내지_않는다(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "실거래가.csv"
            p = self.run_cli("--out", str(out))
            self.assertEqual(p.returncode, 0, p.stderr)
            body = out.read_text(encoding="utf-8-sig").strip().splitlines()
            self.assertEqual(len(body), 1, "dry-run 이 거래 행을 만들었습니다 — 실측으로 오인됩니다")
            self.assertIn("지역코드", body[0])

    def test_live_는_키가_없으면_거부한다(self):
        p = self.run_cli("--live")
        self.assertEqual(p.returncode, 1)
        self.assertIn("DATA_GO_KR_KEY", p.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
