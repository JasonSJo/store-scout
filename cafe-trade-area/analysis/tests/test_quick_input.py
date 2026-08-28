#!/usr/bin/env python3
"""
간편 입력 — 주소와 마진율만 받는 경로

이 경로의 위험은 명확하다: **모르는 값을 그럴듯한 숫자로 덮는 것**이다. 그래서 여기서
고정하는 것도 편의 기능이 아니라 그 방어선이다.

  · 치명 플래그를 절대 채우지 않는다 ('N' 은 실사해서 문제없었다는 뜻이다)
  · 모르는 조건을 유리한 쪽으로 가정하지 않는다
  · 사람이 넣은 값을 가정값으로 덮지 않는다
  · 웹과 CLI 의 자리표시자가 같다 (다르면 같은 주소가 화면과 파이프라인에서 갈린다)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quick_site as Q      # noqa: E402
from common import read_csv  # noqa: E402
from config import FATAL_KEYS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path(__file__).resolve().parent / "quick_dump.js"

BASE = {"주소": "서울 성동구 연무장길 42", "위도": 37.5445, "경도": 127.0557,
        "우편번호": "04782", "법정동코드": "1120010300", "후보지명": "",
        "출처": "테스트"}
MARKET = {"건수": 40, "만원_per_m2_중앙": 900.0}


class TestNeverFabricates(unittest.TestCase):
    def test_치명_플래그를_채우지_않는다(self):
        """'N' 은 '실사해서 문제없었다' 는 뜻이다. 실사하지 않은 것을 그렇게 적으면 거짓말이다."""
        row, src = Q.build_row(BASE, MARKET)
        for k in FATAL_KEYS:
            self.assertEqual(row[k], "", f"{k} 가 채워졌습니다")
            self.assertEqual(src[k]["분류"], "미확인")

    def test_모르는_조건을_유리하게_가정하지_않는다(self):
        """코너·주차·정차·방향적합을 Y 로 두면 Mode B 배점이 근거 없이 올라간다."""
        row, _ = Q.build_row(BASE, MARKET)
        for k in ("코너여부", "정차가능", "방향적합"):
            self.assertEqual(row[k], "N", f"{k} 를 유리한 쪽으로 가정했습니다")
        self.assertEqual(row["주차가능대수"], "0")

    def test_잔존율을_손으로_넣지_않는다(self):
        """R 을 넣으면 M1 등시선을 건너뛴 값이 되고, 그 사실이 산출물에서 사라진다."""
        row, src = Q.build_row(BASE, MARKET)
        self.assertEqual(row["잔존율_R"], "")
        self.assertEqual(src["잔존율_R"]["분류"], "미확보")

    def test_시세가_없으면_임대료를_지어내지_않는다(self):
        row, src = Q.build_row(BASE, None)
        self.assertEqual(row["월임대료_만원"], "")
        self.assertEqual(src["월임대료_만원"]["분류"], "미확보")

    def test_표본이_적으면_역산하지_않는다(self):
        row, _ = Q.build_row(BASE, {"건수": 2, "만원_per_m2_중앙": 900.0})
        self.assertEqual(row["월임대료_만원"], "")

    def test_모든_칸이_출처를_가진다(self):
        """분류 없는 칸이 있으면 사람이 그 값을 실측으로 오인한다."""
        row, src = Q.build_row(BASE, MARKET)
        for k in Q.COLUMNS:
            self.assertIn(k, src, f"{k} 에 출처가 없습니다")
            self.assertIn(src[k]["분류"],
                          ("자동수집", "역산", "가정", "미확인", "미확보"), k)


class TestMarginMapping(unittest.TestCase):
    BASE_V = {"원재료율": 0.35, "로열티율": 0.03, "광고분담금율": 0.01, "기타변동비율": 0.022}

    def test_변동비율이_1빼기_마진율이_된다(self):
        for m in (0.55, 0.4, 0.7):
            v, note = Q.variable_costs(m, dict(self.BASE_V))
            총 = sum(v[k] for k in ("원재료율", "로열티율", "광고분담금율", "기타변동비율"))
            self.assertAlmostEqual(총, 1 - m, places=9, msg=f"마진율 {m}")
            self.assertEqual(note, "")

    def test_계약항목은_건드리지_않는다(self):
        """로열티·광고분담금은 계약으로 정해진 값이다. 마진율에 맞춘다고 바꾸면 안 된다."""
        v, _ = Q.variable_costs(0.5, dict(self.BASE_V))
        for k in ("로열티율", "광고분담금율", "기타변동비율"):
            self.assertEqual(v[k], self.BASE_V[k], k)

    def test_불가능한_마진율은_경고한다(self):
        v, note = Q.variable_costs(0.98, dict(self.BASE_V))
        self.assertEqual(v["원재료율"], 0.0)
        self.assertIn("불가능", note)


class TestWebCliParity(unittest.TestCase):
    """웹의 자리표시자와 CLI 의 자리표시자가 갈리면 같은 주소가 화면과 파이프라인에서 다른 값을 갖는다."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 간편 입력 대조를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"quick_dump.js 실패:\n{p.stderr}")
        cls.js = json.loads(p.stdout)

    def test_자리표시자가_같다(self):
        self.assertEqual(set(self.js["가정"]), set(Q.ASSUMED),
                         "quick.js 와 quick_site.py 의 가정 항목이 다릅니다")
        for k, (v, why) in Q.ASSUMED.items():
            with self.subTest(칸=k):
                self.assertEqual(self.js["가정"][k]["값"], Q.fmt(v))
                self.assertEqual(self.js["가정"][k]["근거"], why)

    def test_치명_목록이_같다(self):
        self.assertEqual(self.js["치명"], FATAL_KEYS)

    def test_BEP_산술이_같다(self):
        """화면의 손익분기 매출과 파이프라인의 BEP 가 갈리면 안 된다."""
        폴백 = self.js["고정비폴백"]
        for s in self.js["표본"]:
            with self.subTest(마진율=s["마진율"], 임대료=s["임대료"]):
                m = s["마진율"] / 100 if s["마진율"] > 1 else s["마진율"]
                rent = s["임대료"]
                F = (rent + rent * self.js["관리비율"]
                     + 폴백["고정인건비_월_만원"] + 폴백["기타_월_만원"])
                self.assertAlmostEqual(s["공헌이익률"], m, places=9)
                self.assertAlmostEqual(s["F"], F, places=6)
                self.assertAlmostEqual(s["월BEP"], F / m, places=6)
                self.assertAlmostEqual(s["일BEP"], F / m / self.js["영업일수"], places=6)

    def test_화면_BEP_가_M5_의_BEP_와_같은_식이다(self):
        """M5 는 F/(1-v), 화면은 F/공헌이익률. 공헌이익률 = 1-v 이므로 같아야 한다."""
        import m5_verdict as M5
        for s in self.js["표본"]:
            m = s["마진율"] / 100 if s["마진율"] > 1 else s["마진율"]
            settings = {"운영": {"변동비": {"원재료율": round(1 - m, 9)},
                                "고정비": {"고정인건비_월_만원": self.js["고정비폴백"]["고정인건비_월_만원"],
                                        "기타_월_만원": self.js["고정비폴백"]["기타_월_만원"]}}}
            site = {"월임대료_만원": s["임대료"],
                    "관리비_만원": s["임대료"] * self.js["관리비율"]}
            fc = M5.fixed_cost(site, settings)
            v = M5.variable_rate(settings)
            self.assertAlmostEqual(fc["F"] / (1 - v), s["월BEP"], places=6)


class TestEndToEnd(unittest.TestCase):
    """간편 입력으로 만든 CSV 를 파이프라인이 실제로 읽는가."""

    def test_내보낸_CSV_를_심의가_완주한다(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            r = subprocess.run(
                [sys.executable, str(ROOT / "quick_site.py"),
                 "--위도", "37.5445", "--경도", "127.0557",
                 "--법정동코드", "1120010300", "--이름", "테스트 후보지",
                 "--마진율", "0.55", "--outdir", str(out),
                 "--실거래", str(out / "없음.csv")],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            sites = out / "sites.csv"
            self.assertTrue(sites.exists())

            rows = read_csv(sites)
            self.assertEqual(len(rows), 1)
            self.assertEqual(list(rows[0].keys()), Q.COLUMNS,
                             "내보낸 열이 후보지 CSV 열과 다릅니다")

            j = subprocess.run(
                [sys.executable, str(ROOT / "review_sites.py"),
                 "--sites", str(sites), "--settings", str(out / "설정.yaml"),
                 "--out", str(out / "심의표.md"), "--json", str(out / "심의결과.json")],
                capture_output=True, text=True, timeout=300)
            self.assertEqual(j.returncode, 0, j.stderr)
            self.assertTrue((out / "심의표.md").exists())
            self.assertIn("간편 입력", (out / "출처표.md").read_text(encoding="utf-8"))

            # 심의표만 읽는 사람도 입력이 가정값이었다는 것을 알아야 한다
            표 = (out / "심의표.md").read_text(encoding="utf-8")
            self.assertIn("가정값이 섞인 입력", 표)
            self.assertIn("테스트 후보지", 표)
            self.assertIn("출점 결정의 근거가 되지 않습니다", 표)

    def test_보통_입력에는_경고가_붙지_않는다(self):
        """모든 심의표에 경고가 뜨면 경고가 배경이 되고 아무도 읽지 않는다."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            j = subprocess.run(
                [sys.executable, str(ROOT / "review_sites.py"),
                 "--out", str(out / "심의표.md"), "--json", str(out / "r.json")],
                capture_output=True, text=True, timeout=300)
            self.assertEqual(j.returncode, 0, j.stderr)
            self.assertNotIn("가정값이 섞인 입력",
                             (out / "심의표.md").read_text(encoding="utf-8"))

    def test_열_목록이_후보지_CSV_와_같다(self):
        header = list(read_csv(ROOT / "후보지.example.csv")[0].keys())
        self.assertEqual(Q.COLUMNS, header,
                         "quick_site.COLUMNS 가 후보지.example.csv 헤더와 다릅니다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
