#!/usr/bin/env python3
"""
고객 상담 — 조건이 심의로 옮겨 가는 경로

이 화면은 **개인정보를 다루는 유일한 화면**이다. 그래서 여기서 고정하는 것 중 절반은
기능이 아니라 경계선이다.

  · 파이프라인으로 나가는 산출물에 개인정보가 없다
  · consult.py 는 개인정보 키를 아예 읽지 않는다
  · 화면의 손익분기와 파이프라인의 BEP 가 같은 식·같은 값이다
  · 조건에 맞는 후보지가 없으면 그렇게 말한다 (판정 기준을 낮추지 않는다)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import consult as CS               # noqa: E402
import m5_verdict as M5            # noqa: E402
from common import read_csv        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

COND = {"희망지역": ["성수", "강남"], "희망평수": 18, "희망상권": ["오피스", "복합"],
        "보증금_만원": 8000, "권리금_만원": 3000,
        "투자금형태": "현금+대출", "운영형태": "점주"}
PII = {"고객명": "홍길동", "고객전화번호": "010-1234-5678",
       "거주지": "서울 성동구", "근무지": "서울 중구"}


def settings():
    return yaml.safe_load((ROOT / "설정.example.yaml").read_text(encoding="utf-8"))


class TestPersonalDataStaysOut(unittest.TestCase):
    def test_consult_이_읽는_키에_개인정보가_없다(self):
        for k in CS.개인정보키:
            self.assertNotIn(k, CS.읽는키, f"{k} 를 파이프라인이 읽고 있습니다")

    def test_산출물에_개인정보가_실리지_않는다(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            src = out / "상담.json"
            src.write_text(json.dumps({"조건": {**COND, **PII}}, ensure_ascii=False),
                           encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(ROOT / "consult.py"), "--상담", str(src),
                 "--outdir", str(out / "o")], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            for f in (out / "o").rglob("*"):
                if not f.is_file():
                    continue
                text = f.read_text(encoding="utf-8-sig", errors="replace")
                for v in PII.values():
                    self.assertNotIn(v, text, f"{f.name} 에 개인정보가 실렸습니다: {v}")

    def test_개인정보가_있으면_알려준다(self):
        """조용히 무시하면 상담사가 그 파일을 아무 데나 둔다."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "상담.json"
            src.write_text(json.dumps({"조건": {**COND, **PII}}, ensure_ascii=False),
                           encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(ROOT / "consult.py"), "--상담", str(src),
                 "--outdir", str(Path(d) / "o")], capture_output=True, text=True, timeout=120)
            self.assertIn("개인정보", r.stdout)


class TestSettingsOverride(unittest.TestCase):
    def test_운영형태가_고정인건비를_바꾼다(self):
        st = settings()
        for 형태, 기대 in (("오토", 980), ("점주+알바", 620), ("점주", 260)):
            merged, _ = CS.apply_settings({**COND, "운영형태": 형태}, st)
            self.assertEqual(merged["운영"]["고정비"]["고정인건비_월_만원"], 기대, 형태)

    def test_투자금형태가_금융비용을_더한다(self):
        st = settings()
        base = st["운영"]["고정비"]["기타_월_만원"]
        현금, _ = CS.apply_settings({**COND, "투자금형태": "현금"}, st)
        self.assertEqual(현금["운영"]["고정비"]["기타_월_만원"], base)

        대출, _ = CS.apply_settings({**COND, "투자금형태": "현금+대출"}, st)
        # (8000+3000) × 0.5 × 0.06 ÷ 12 = 27.5
        self.assertAlmostEqual(대출["운영"]["고정비"]["기타_월_만원"], base + 27.5, places=6)

        리스, _ = CS.apply_settings({**COND, "투자금형태": "현금+대출+리스"}, st)
        self.assertAlmostEqual(리스["운영"]["고정비"]["기타_월_만원"], base + 27.5 + 45, places=6)

    def test_모르는_형태는_조용히_넘어가지_않는다(self):
        got = CS.인건비({"운영형태": "없는형태"}, settings())
        self.assertFalse(got["적용"])
        self.assertIn("없는형태", got["사유"])

    def test_설정_파일_자체는_바뀌지_않는다(self):
        st = settings()
        before = st["운영"]["고정비"]["고정인건비_월_만원"]
        CS.apply_settings(COND, st)
        self.assertEqual(st["운영"]["고정비"]["고정인건비_월_만원"], before)

    def test_고정비_변경이_BEP_를_실제로_움직인다(self):
        st = settings()
        site = {"월임대료_만원": 300, "관리비_만원": 36}
        beps = {}
        for 형태 in ("오토", "점주"):
            merged, _ = CS.apply_settings({**COND, "운영형태": 형태}, st)
            v = M5.variable_rate(merged)
            beps[형태] = M5.fixed_cost(site, merged)["F"] / (1 - v)
        self.assertGreater(beps["오토"], beps["점주"] * 1.3)


class TestFilter(unittest.TestCase):
    SITES = [
        {"후보지명": "성수 A", "주소": "서울 성동구 성수동", "전용면적_평": 18,
         "보증금_만원": 6000, "권리금_만원": 2000},
        {"후보지명": "성수 B", "주소": "서울 성동구 성수동", "전용면적_평": 40,
         "보증금_만원": 6000, "권리금_만원": 2000},
        {"후보지명": "부산 C", "주소": "부산 해운대구", "전용면적_평": 18,
         "보증금_만원": 6000, "권리금_만원": 2000},
        {"후보지명": "성수 D", "주소": "서울 성동구 성수동", "전용면적_평": 18,
         "보증금_만원": 40000, "권리금_만원": 20000},
    ]

    def test_평수와_지역과_투자금으로_거른다(self):
        통과, 제외 = CS.필터(COND, self.SITES, settings())
        self.assertEqual([s["후보지명"] for s in 통과], ["성수 A"])
        사유 = {s["후보지명"]: s["_제외사유"] for s in 제외}
        self.assertIn("평수", 사유["성수 B"])
        self.assertIn("지역", 사유["부산 C"])
        self.assertIn("초과", 사유["성수 D"])

    def test_제외_사유가_모든_행에_남는다(self):
        """필터는 점수를 깎는 게 아니라 목록에서 빼는 것이라, 이유가 없으면 되돌릴 수 없다."""
        _, 제외 = CS.필터(COND, self.SITES, settings())
        for s in 제외:
            self.assertTrue(s["_제외사유"].strip(), s["후보지명"])

    def test_조건이_비면_거르지_않는다(self):
        통과, 제외 = CS.필터({}, self.SITES, settings())
        self.assertEqual(len(통과), len(self.SITES))
        self.assertEqual(제외, [])

    def test_남은_후보지가_없으면_그렇게_말한다(self):
        """조건에 맞춘다고 판정 기준을 낮추면 안 된다."""
        좁은 = {**COND, "희망지역": ["제주"]}
        통과, 제외 = CS.필터(좁은, self.SITES, settings())
        self.assertEqual(통과, [])
        md = CS.render(좁은, settings(), [], 통과, 제외)
        self.assertIn("남은 후보지가 없습니다", md)
        self.assertIn("판정 기준을 낮추면 안 됩니다", md)


