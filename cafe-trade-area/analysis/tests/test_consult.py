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


def _화면이_내는_조건csv(cond: dict) -> str:
    """web/app/consultation/page.tsx 의 조건내려받기() 와 같은 바이트를 만든다 —
    BOM · CRLF · 머리글은 읽는키 순서 · 목록은 · 로 잇는다."""
    def cell(v):
        v = "·".join(v) if isinstance(v, list) else str(v)
        return '"' + v.replace('"', '""') + '"' if any(c in v for c in ',"\n\r') else v
    head = list(CS.읽는키)
    return "\ufeff" + ",".join(head) + "\r\n" + ",".join(cell(cond.get(k, "")) for k in head) + "\r\n"


def _화면이_내는_상담카드csv(cond: dict, pii: dict) -> str:
    rows = [("항목", "값"), ("작성시각", "2026-09-03T10:17:52.648Z")]
    rows += [(k, pii[k]) for k in ("고객명", "고객전화번호", "거주지", "근무지")]
    rows += [(f"희망지역_{i + 1}순위", a) for i, a in enumerate(cond["희망지역"])]
    rows += [("희망평수", str(cond["희망평수"])), ("희망상권", "·".join(cond["희망상권"])),
             ("보증금_만원", str(cond["보증금_만원"])), ("권리금_만원", str(cond["권리금_만원"])),
             ("매매총예산_만원", "30000"), ("월세상한_만원", "350"),
             ("투자금형태", cond["투자금형태"]), ("운영형태", cond["운영형태"])]
    return "\ufeff" + "\r\n".join(",".join(r) for r in rows) + "\r\n"


class TestCsvInput(unittest.TestCase):
    """화면이 CSV 를 내리므로 파이프라인도 CSV 를 읽어야 한다.

    여기서 지키는 것: 화면이 만든 바이트 그대로 넣었을 때 JSON 으로 넣은 것과
    **같은 조건 dict** 가 나온다. 목록 칸이 문자열로 남으면 필터가 조용히
    아무것도 거르지 않는다 — 그래서 목록으로 돌아오는지를 따로 본다."""

    def _load(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "조건.csv"
            src.write_text(text, encoding="utf-8", newline="")
            return CS.load_consult(src)

    def test_조건csv_가_JSON_과_같은_조건이_된다(self):
        got = self._load(_화면이_내는_조건csv(COND))
        self.assertEqual(got["희망지역"], COND["희망지역"])
        self.assertEqual(got["희망상권"], COND["희망상권"])
        self.assertEqual(got["투자금형태"], COND["투자금형태"])
        self.assertEqual(got["운영형태"], COND["운영형태"])
        for k in ("희망평수", "보증금_만원", "권리금_만원"):
            self.assertEqual(CS.to_f(got[k]), float(COND[k]), k)
        self.assertEqual(set(got), set(CS.읽는키))

    def test_목록_칸이_목록으로_돌아온다(self):
        """'서울특별시 강남구·경기도 고양시' 한 칸 → 두 원소. 문자열로 남으면
        필터가 글자 하나하나를 지역으로 본다."""
        got = self._load(_화면이_내는_조건csv({**COND, "희망지역": ["서울특별시 강남구", "경기도 고양시"]}))
        self.assertEqual(got["희망지역"], ["서울특별시 강남구", "경기도 고양시"])
        self.assertIsInstance(got["희망상권"], list)

    def test_상권_하나만_골라도_목록이다(self):
        """화면의 희망상권은 라디오라 하나만 온다. 원소 하나짜리 목록이어야 한다."""
        got = self._load(_화면이_내는_조건csv({**COND, "희망상권": ["오피스"]}))
        self.assertEqual(got["희망상권"], ["오피스"])

    def test_빈_칸은_빈_값이다(self):
        got = self._load(_화면이_내는_조건csv({**COND, "권리금_만원": "", "희망지역": []}))
        self.assertEqual(got["희망지역"], [])
        self.assertEqual(CS.to_f(got["권리금_만원"]), 0.0)

    def test_쉼표와_따옴표가_든_칸도_읽힌다(self):
        got = self._load(_화면이_내는_조건csv({**COND, "희망지역": ['성수 "A"동, 1층']}))
        self.assertEqual(got["희망지역"], ['성수 "A"동, 1층'])

    def test_CSV_로_끝까지_돈다(self):
        """subprocess 로 실제 CLI. 필터가 실제로 거르는지까지 본다 —
        희망평수 18 ±30% 밖의 후보지가 빠져야 한다."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "조건.csv"
            src.write_text(_화면이_내는_조건csv(COND), encoding="utf-8", newline="")
            r = subprocess.run(
                [sys.executable, str(ROOT / "consult.py"), "--상담", str(src),
                 "--outdir", str(Path(d) / "o")], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("개인정보", r.stdout, "조건.csv 에는 개인정보가 없어야 한다")
            남은 = read_csv(Path(d) / "o" / "sites.csv")
            전체 = read_csv(ROOT / "후보지.example.csv")
            self.assertLess(len(남은), len(전체), "필터가 아무것도 거르지 않았다")
            for s in 남은:
                self.assertTrue(18 * 0.7 <= CS.to_f(s["전용면적_평"]) <= 18 * 1.3, s["전용면적_평"])
            조건 = json.loads((Path(d) / "o" / "조건.json").read_text(encoding="utf-8"))
            self.assertEqual(조건["희망지역"], COND["희망지역"])

    def test_상담카드를_넣으면_경고하고_개인정보는_싣지_않는다(self):
        """잘못된 파일을 넣는 실수는 난다. 그때 조용히 지나가면 고객 연락처가
        심의 자료로 나간다."""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "상담카드_홍길동.csv"
            src.write_text(_화면이_내는_상담카드csv(COND, PII), encoding="utf-8", newline="")
            cond = CS.load_consult(src)
            self.assertEqual(cond["희망지역"], COND["희망지역"], "N순위 칸이 목록으로 모여야 한다")
            self.assertEqual(cond["희망상권"], COND["희망상권"])
            r = subprocess.run(
                [sys.executable, str(ROOT / "consult.py"), "--상담", str(src),
                 "--outdir", str(Path(d) / "o")], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("개인정보", r.stdout)
            for f in (Path(d) / "o").rglob("*"):
                if f.is_file():
                    text = f.read_text(encoding="utf-8-sig", errors="replace")
                    for v in PII.values():
                        self.assertNotIn(v, text, f"{f.name} 에 개인정보가 실렸습니다: {v}")

    def test_JSON_은_여전히_읽힌다(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "상담.json"
            src.write_text(json.dumps({"조건": COND}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(CS.load_consult(src), COND)

    def test_화면과_파이프라인의_열_이름이_같다(self):
        """web/ 쪽 테스트(test_saas)도 같은 것을 지킨다. 여기서 한 번 더 —
        이 저장소에서 analysis/ 만 따로 돌리는 사람도 있다."""
        page = ROOT.parent.parent / "web" / "app" / "consultation" / "page.tsx"
        if not page.exists():
            self.skipTest("web/ 이 없는 체크아웃")
        글 = page.read_text(encoding="utf-8")
        블록 = 글[글.index("function 조건내려받기"):]
        시작 = 블록.index("csv([") + len("csv([")
        머리 = re.findall(r"'([^']+)'", 블록[시작:블록.index("]", 시작)])
        self.assertEqual(머리, list(CS.읽는키))


class TestRegionMatch(unittest.TestCase):
    """화면은 시·도를 정식 명칭으로 보내고('서울특별시 강남구'), 후보지 주소는
    사람이 줄여 적는다('서울 강남구 …'). 통째 포함으로 보면 전부 빠진다 —
    브라우저가 실제로 내린 조건.csv 로 돌려 후보지 6곳이 6곳 다 빠지는 것을 봤다."""

    def test_정식_시도명이_줄인_주소에_맞는다(self):
        self.assertTrue(CS.지역맞음("서울특별시 강남구", "서울 강남구 강남대로 396"))
        self.assertTrue(CS.지역맞음("서울특별시 강남구", "서울특별시 강남구 역삼동 1"))
        self.assertTrue(CS.지역맞음("경기도 성남시", "경기 성남시 분당구 삼평동 682"))
        self.assertTrue(CS.지역맞음("충청북도 청주시", "충북 청주시 흥덕구 1"))
        self.assertTrue(CS.지역맞음("전북특별자치도 전주시", "전라북도 전주시 완산구 1"))

    def test_구가_다르면_아니다(self):
        self.assertFalse(CS.지역맞음("경기도 고양시", "경기 성남시 분당구 삼평동 682"))
        self.assertFalse(CS.지역맞음("서울특별시 강남구", "서울 성동구 연무장길 42"))

    def test_옛_한_낱말_지역도_그대로_된다(self):
        self.assertTrue(CS.지역맞음("강남", "서울 강남구 강남대로 396"))
        self.assertFalse(CS.지역맞음("강남", "서울 마포구 어울마당로 66"))

    def test_빈_희망은_아무것도_안_맞는다(self):
        self.assertFalse(CS.지역맞음("", "서울 강남구"))

    def test_실제_화면_조건으로_강남역이_지역_사유로_빠지지_않는다(self):
        cond = {"희망평수": "22", "희망상권": ["오피스"],
                "희망지역": ["서울특별시 강남구", "경기도 고양시"],
                "보증금_만원": "8000", "권리금_만원": "6000",
                "투자금형태": "현금+대출+리스", "운영형태": "점주+알바"}
        sites = read_csv(ROOT / "후보지.example.csv")
        통과, 제외 = CS.필터(cond, sites, settings())
        이름 = {s["후보지명"]: s for s in 통과 + 제외}
        강남 = 이름["강남역 11번출구"]
        self.assertNotIn("희망 지역", 강남.get("_제외사유", ""), 강남.get("_제외사유"))
        for s in 제외:
            if s["후보지명"] != "강남역 11번출구":
                self.assertIn("희망 지역", s.get("_제외사유", ""),
                              f"{s['후보지명']} 는 강남·고양이 아닌데 지역 사유가 없다")

