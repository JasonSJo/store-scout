#!/usr/bin/env python3
"""
M5 판정 산술 — 파이썬 ↔ 웹앱 대조

콘솔이 다시 구현하는 모듈은 M5 하나뿐이다(M1~M4 는 등시선·격자인구·회귀표본이
필요해 브라우저에서 재현하지 않고 파이프라인 산출을 읽는다). 그래서 파리티
검사도 M5 로 좁혔다. 대신 이 하나는 무작위 케이스로 넓게 훑는다 — 판정이
갈리는 경계(margin 0.15/0.30, S 70, overlap 0.30)를 반드시 지나가도록 만든다.

node 가 없으면 건너뛴다.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C          # noqa: E402
import m5_verdict as M5     # noqa: E402

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "m5_runner.js"
TOL = 1e-9

SETTINGS = {"운영": {"변동비": {"원재료율": 0.35, "로열티율": 0.03, "광고분담금율": 0.01,
                          "기타변동비율": 0.022},
                   "고정비": {"고정인건비_월_만원": 620, "기타_월_만원": 170}}}


def build_cases(n=400):
    """경계를 반드시 밟도록 설계한 무작위 케이스."""
    rnd = random.Random(20260826)
    cases = []
    kappa = C.c("잠식계수_카파")
    for i in range(n):
        rent = rnd.choice([120, 250, 400, 620, 900])
        site = {"월임대료_만원": rent, "관리비_만원": rnd.choice([0, 20, 45])}
        for key, _ in C.FATAL_FLAGS:
            roll = rnd.random()
            site[key] = "Y" if roll < 0.04 else ("" if roll < 0.14 else "N")
        F = rent + site["관리비_만원"] + 620 + 170
        bep = F / (1 - (0.35 + 0.03 + 0.01 + 0.022))
        # BEP 근처를 집중적으로 훑어 margin 임계를 넘나들게 한다
        med = bep * rnd.choice([0.7, 0.9, 1.0, 1.05, 1.15, 1.18, 1.30, 1.45, 2.0, 3.0])
        low = med * rnd.uniform(0.6, 1.0)
        overlaps = [{"점포명": f"o{k}", "overlap": round(rnd.uniform(0, 0.6), 4),
                     "월매출_만원": rnd.uniform(500, 6000)}
                    for k in range(rnd.choice([0, 0, 1, 2, 3]))]
        # 전용면적은 판정에 들어가지 않지만(시세 대조를 뺐다) 값이 있고 없고가
        # 다른 경로를 타지 않는지 확인하기 위해 계속 섞는다.
        site["전용면적_평"] = rnd.choice(["", 12, 18, 25, 40])
        cases.append({
            "site": site,
            "revenue": {"월매출_중앙": med, "월매출_하한": low},
            "settings": SETTINGS,
            "S": round(rnd.uniform(30, 95), 2),
            "overlaps": overlaps,
            "kappa": kappa,
            "sPoolMax": rnd.choice([None, 63.0, 82.0]),
        })
    # 임계값 정확히 위/아래를 명시적으로 넣는다
    base = {"월임대료_만원": 400, "관리비_만원": 30,
            "근저당_과다": "N", "임대인_불일치": "N", "소송_계류": "N", "인허가_불가": "N"}
    F = 400 + 30 + 620 + 170
    bep = F / (1 - 0.412)
    for m in (0.1499, 0.15, 0.1501, 0.2999, 0.30, 0.3001):
        med = bep / (1 - m)
        cases.append({"site": dict(base), "revenue": {"월매출_중앙": med, "월매출_하한": med},
                      "settings": SETTINGS, "S": 90.0, "overlaps": [],
                      "kappa": C.c("잠식계수_카파"), "sPoolMax": None})
    for s in (69.99, 70.0, 70.01):
        cases.append({"site": dict(base), "revenue": {"월매출_중앙": 9000, "월매출_하한": 8000},
                      "settings": SETTINGS, "S": s, "overlaps": [],
                      "kappa": C.c("잠식계수_카파"), "sPoolMax": None})
    for ov in (0.2999, 0.30, 0.3001):
        cases.append({"site": dict(base), "revenue": {"월매출_중앙": 9000, "월매출_하한": 8000},
                      "settings": SETTINGS, "S": 90.0,
                      "overlaps": [{"점포명": "x", "overlap": ov, "월매출_만원": 3000}],
                      "kappa": C.c("잠식계수_카파"), "sPoolMax": None})
    # 시세 대조는 판정에서 뺐다. 임계도 사라졌으므로 밟을 경계가 없다.
    # (시세가 판정을 움직이지 않는다는 것은 test_market_link.py 가 지킨다)
    return cases


class TestM5Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 M5 대조를 건너뜁니다")
        cls.cases = build_cases()
        p = subprocess.run(["node", str(RUNNER)], input=json.dumps(cls.cases, ensure_ascii=False),
                           capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            raise AssertionError(f"m5_runner.js 실패:\n{p.stderr}")
        cls.js = json.loads(p.stdout)

    def test_all_cases_match(self):
        self.assertEqual(len(self.js), len(self.cases))
        for i, (c, j) in enumerate(zip(self.cases, self.js)):
            with self.subTest(case=i):
                py = M5.judge(c["site"], c["revenue"], c["settings"], c["S"],
                              c["overlaps"], c["sPoolMax"])
                self.assertEqual(py["판정"], j["판정"], f"case {i} 판정")
                self.assertEqual(py["사유"], j["사유"], f"case {i} 사유")
                self.assertEqual(py["비고"], j["비고"], f"case {i} 비고")
                self.assertEqual(py["치명플래그"], j["치명플래그"])
                self.assertEqual(py["치명_미확인"], j["치명_미확인"])
                for k, got in (("변동비율", j["변동비율"]), ("BEP_만원", j["BEP_만원"]),
                               ("margin", j["margin"]), ("margin_low", j["margin_low"]),
                               ("순증_월매출_만원", j["순증_월매출_만원"])):
                    if py[k] is None or got is None:
                        self.assertEqual(py[k], got, f"case {i} {k}")
                    else:
                        self.assertAlmostEqual(py[k], got, delta=TOL, msg=f"case {i} {k}")
                self.assertAlmostEqual(py["고정비"]["F"], j["F"], delta=TOL)
                self.assertAlmostEqual(py["카니발"]["최대_overlap"], j["최대_overlap"], delta=TOL)
                self.assertAlmostEqual(py["카니발"]["잠식액_합_만원"], j["잠식액_합_만원"], delta=TOL)
                # 시세는 양쪽 판정 어디에도 없어야 한다
                self.assertNotIn("시세대조", py, f"case {i}")

    def test_cases_actually_cover_all_verdicts(self):
        """케이스가 세 판정을 전부 밟지 않으면 이 테스트는 무의미하다."""
        got = {j["판정"] for j in self.js}
        self.assertEqual(got, set(C.VERDICTS), f"판정 커버리지 부족: {got}")

    def test_cases_cover_degeneracy_and_unchecked_notes(self):
        notes = " ".join(x for j in self.js for x in j["비고"])
        self.assertIn("S 게이트 축퇴", notes)
        self.assertIn("미확인", notes)

    def test_시세가_판정에_남아_있지_않다(self):
        """양쪽(파이썬·JS) 모두에서 사라졌는지 본다. 한쪽에만 남으면 화면과 CLI 의
        판정이 갈린다 — 같은 후보지를 두 곳에서 보고 다른 답을 받는다."""
        for j in self.js:
            self.assertNotIn("시세대조", j)
            self.assertFalse(any("시세" in x for x in j["사유"] + j["비고"]), j)


if __name__ == "__main__":
    unittest.main(verbosity=2)
