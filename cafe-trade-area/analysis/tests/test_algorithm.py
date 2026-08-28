#!/usr/bin/env python3
"""
점포개발 심의 알고리즘 v1.0 — 모듈 단위 테스트 (표준 라이브러리 unittest)

    python3 -m unittest discover -s tests -t .
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as C          # noqa: E402
import geo                  # noqa: E402
import m1_area as M1        # noqa: E402
import m2_demand as M2      # noqa: E402
import m3_huff as M3        # noqa: E402
import m4_revenue as M4     # noqa: E402
import m5_verdict as M5     # noqa: E402
import m6_calibrate as M6   # noqa: E402
import ols                  # noqa: E402

SETTINGS = {
    "브랜드": "테스트", "영업일수": 30, "좌석수_기본": 24,
    "운영": {"변동비": {"원재료율": 0.35, "로열티율": 0.03, "광고분담금율": 0.01},
           "고정비": {"고정인건비_월_만원": 620, "기타_월_만원": 170}},
}


class TestConfig(unittest.TestCase):
    def test_mode_b_weights_sum_100(self):
        self.assertEqual(sum(C.axis_total(a) for a in C.MODE_B_WEIGHTS), 100)
        self.assertEqual(C.axis_total("수요"), 40)
        self.assertEqual(C.axis_total("접근성"), 30)
        self.assertEqual(C.axis_total("경쟁"), 20)
        self.assertEqual(C.axis_total("비용계약"), 10)

    def test_spec_constants(self):
        """명세에 못 박힌 값이 조용히 바뀌지 않도록 고정한다."""
        self.assertEqual(C.c("거리마찰_람다"), 2.2)
        self.assertEqual(C.c("횡단저항"), 0.3)
        self.assertEqual(C.c("잠식계수_카파"), 0.5)
        self.assertEqual(C.c("부결_마진"), 0.15)
        self.assertEqual(C.c("보류_마진"), 0.30)
        self.assertEqual(C.c("보류_점수"), 70.0)
        self.assertEqual(C.c("보류_중첩"), 0.30)
        self.assertEqual(int(C.c("ModeA_최소표본")), 15)
        self.assertAlmostEqual(C.c("P10_이상반경_m"), 4000 / 60 * 10, delta=0.5)

    def test_unknown_coefficient_fails_loudly(self):
        with self.assertRaises(KeyError):
            C.c("없는계수")

    def test_estimated_coefficients_are_listed(self):
        names = {k for k, _, _ in C.unvalidated()}
        for k in ("거리마찰_람다", "횡단저항", "잠식계수_카파"):
            self.assertIn(k, names, f"{k} 는 미검증으로 표시되어야 한다")

    def test_tier_defaults_to_strongest_competitor(self):
        self.assertEqual(C.tier_of("메가MGC커피 성수점"), "저가형")
        self.assertEqual(C.tier_of("이름없는카페"), "동일가격대")
        self.assertEqual(C.tier_of("메가", "스페셜티"), "스페셜티")   # 실사값 우선


class TestGeo(unittest.TestCase):
    def test_circle_area_matches_analytic(self):
        c = geo.prepare(geo.circle_poly(667, 720))
        self.assertAlmostEqual(geo.shoelace_area(c) / (math.pi * 667 ** 2), 1.0, places=4)

    def test_overlap_two_circles_matches_analytic(self):
        r, d = 667.0, 500.0
        a = geo.prepare(geo.circle_poly(r, 360))
        b = geo.prepare([(x + d, y) for x, y in geo.circle_poly(r, 360)])
        lens = (2 * r * r * math.acos(d / (2 * r))
                - (d / 2) * math.sqrt(4 * r * r - d * d))
        self.assertAlmostEqual(geo.overlap_ratio(a, b), lens / (math.pi * r * r), places=2)

    def test_disjoint_overlap_is_zero(self):
        a = geo.prepare(geo.circle_poly(300))
        b = geo.prepare([(x + 5000, y) for x, y in geo.circle_poly(300)])
        self.assertEqual(geo.overlap_ratio(a, b), 0.0)

    def test_prepared_shortcut_matches_raw(self):
        """내접·외접 반지름 지름길이 원래 판정과 같은 답을 내야 한다."""
        poly = geo.circle_poly(400, 64)
        prep = geo.prepare(poly)
        for cx in range(-600, 601, 37):
            for cy in range(-600, 601, 53):
                self.assertAlmostEqual(geo.cell_coverage(cx, cy, 100, prep),
                                       geo.cell_coverage(cx, cy, 100, poly), places=9)

    def test_haversine_known_distance(self):
        d = geo.haversine(37.4979, 127.0276, 37.5006, 127.0364)
        self.assertTrue(830 < d < 950, d)


class TestM1(unittest.TestCase):
    def test_R_is_area_over_ideal(self):
        a = M1.resolve("x", 37.5, 127.0, {}, fallback_R=0.5)
        self.assertAlmostEqual(a["R"], a["P10_면적_m2"] / (math.pi * 667 ** 2), places=6)

    def test_fallback_is_flagged(self):
        a = M1.resolve("x", 37.5, 127.0, {}, fallback_R=0.5)
        self.assertEqual(a["출처"], "열화폴백")
        self.assertTrue(any("등시선 없음" in w for w in a["경고"]))

    def test_missing_R_warns_about_optimism(self):
        a = M1.resolve("x", 37.5, 127.0, {})
        self.assertTrue(any("1.0(이상 원형)" in w for w in a["경고"]))

    def test_low_R_warns(self):
        a = M1.resolve("x", 37.5, 127.0, {}, fallback_R=0.15)
        self.assertTrue(any("단절이 심한" in w for w in a["경고"]))

    def test_overlap_decreases_with_distance(self):
        base = M1.resolve("a", 37.5, 127.0, {}, 0.7)
        near = M1.overlap_with(base, "b", 37.5 + 200 / 110540, 127.0, {}, 0.7)
        far = M1.overlap_with(base, "c", 37.5 + 900 / 110540, 127.0, {}, 0.7)
        self.assertGreater(near, far)
        self.assertLessEqual(near, 1.0)


class TestM2(unittest.TestCase):
    def setUp(self):
        self.area = M1.resolve("x", 37.5, 127.0, {}, fallback_R=0.9)
        self.cells = [{"중심위도": 37.5 + j * 100 / 110540,
                       "중심경도": 127.0 + i * 100 / 88300,
                       "한변_m": 100, "세대수": 50, "직장인구": 100}
                      for i in range(-2, 3) for j in range(-2, 3)]

    def test_crossing_resistance_applied(self):
        pts = [{"위도": 37.5, "경도": 127.0, "도로변": "A", "시간대": "오전", "인원": 1000},
               {"위도": 37.5, "경도": 127.0, "도로변": "B", "시간대": "오전", "인원": 1000}]
        d = M2.demand(self.area, self.cells, pts, "A")
        self.assertEqual(d["D_am"], 2000)
        self.assertAlmostEqual(d["D_am_adj"], 1000 + 1000 * C.c("횡단저항"))

    def test_unknown_side_warns(self):
        pts = [{"위도": 37.5, "경도": 127.0, "도로변": "", "시간대": "오전", "인원": 500}]
        d = M2.demand(self.area, self.cells, pts, "A")
        self.assertTrue(any("도로변 미상" in w for w in d["경고"]))

    def test_missing_data_warns(self):
        d = M2.demand(self.area, [], [], "A")
        self.assertTrue(any("유동인구 데이터 없음" in w for w in d["경고"]))
        self.assertTrue(any("격자 인구 데이터 없음" in w for w in d["경고"]))

    def test_points_outside_p5_excluded(self):
        far = {"위도": 37.5 + 3000 / 110540, "경도": 127.0, "도로변": "A",
               "시간대": "오전", "인원": 9999}
        d = M2.demand(self.area, self.cells, [far], "A")
        self.assertEqual(d["D_am"], 0)


class TestM3(unittest.TestCase):
    def setUp(self):
        self.area = M1.resolve("x", 37.5, 127.0, {}, fallback_R=0.9)
        self.cells = [{"중심위도": 37.5 + j * 100 / 110540,
                       "중심경도": 127.0 + i * 100 / 88300,
                       "한변_m": 100, "세대수": 50, "직장인구": 100}
                      for i in range(-3, 4) for j in range(-3, 4)]

    def rival(self, dx, seats=24, tier="동일가격대"):
        return {"상호": f"r{dx}", "브랜드": "", "티어": tier,
                "위도": 37.5, "경도": 127.0 + dx / 88300,
                "좌석수": seats, "A": M3.attraction(seats, tier), "자사": False}

    def test_attraction_formula(self):
        self.assertAlmostEqual(M3.attraction(36, "동일가격대"), 6.0)
        self.assertAlmostEqual(M3.attraction(36, "저가형"), 6.0 * 0.6)

    def test_share_falls_with_more_rivals(self):
        a = M3.share(self.area, M3.attraction(30, "동일가격대"),
                     [self.rival(200)], self.cells)["S"]
        b = M3.share(self.area, M3.attraction(30, "동일가격대"),
                     [self.rival(200 + 30 * k) for k in range(8)], self.cells)["S"]
        self.assertGreater(a, b)

    def test_share_is_bounded(self):
        r = M3.share(self.area, M3.attraction(30, "동일가격대"), [], self.cells)
        self.assertLessEqual(r["S"], 1.0)
        self.assertGreater(r["S"], 0.99)     # 경쟁이 없으면 전부 가져간다
        self.assertTrue(any("경쟁점 데이터 없음" in w for w in r["경고"]))

    def test_lambda_increases_distance_penalty(self):
        """λ 가 커지면 먼 경쟁점의 영향이 줄어 후보지 점유율이 올라간다."""
        far = [self.rival(500)]
        base = C.COEFFICIENTS["거리마찰_람다"]
        try:
            C.COEFFICIENTS["거리마찰_람다"] = (1.2, base[1], base[2])
            lo = M3.share(self.area, M3.attraction(24, "동일가격대"), far, self.cells)["S"]
            C.COEFFICIENTS["거리마찰_람다"] = (3.2, base[1], base[2])
            hi = M3.share(self.area, M3.attraction(24, "동일가격대"), far, self.cells)["S"]
        finally:
            C.COEFFICIENTS["거리마찰_람다"] = base
        self.assertGreater(hi, lo)

    def test_network_distance_warning(self):
        r = M3.share(self.area, 5.0, [self.rival(300)], self.cells, network_ok=False)
        self.assertTrue(any("보행 네트워크 거리 미확보" in w for w in r["경고"]))
        r2 = M3.share(self.area, 5.0, [self.rival(300)], self.cells, network_ok=True)
        self.assertFalse(any("보행 네트워크" in w for w in r2["경고"]))


def make_rec(name, W, H, D, S, front=8.0, corner="Y", direction="Y", rent=400,
             seats=26, R=0.7, **site):
    """M4·M5 테스트용 최소 레코드. 파이프라인을 돌리지 않고 모듈만 검증한다."""
    base = {"후보지명": name, "점포명": name, "전면폭_m": front, "코너여부": corner,
            "방향적합": direction, "월임대료_만원": rent, "관리비_만원": 30,
            "층": 1, "주차가능대수": 2, "정차가능": "Y", "좌석수": seats,
            "계약조건점수": 3}
    base.update(site)
    return {
        "이름": name, "후보지": base, "기존점": False,
        "상권": {"R": R},
        "수요": {"H": H, "W": W, "D_am_adj": D, "D_am": D, "D_am_같은편": D * 0.7,
               "D_all": D * 5, "주말야간": D * 0.5},
        "경쟁": {"S": S, "동일가격대_수": 4, "저가형_수": 3, "반경내_경쟁": 12},
    }


class TestM4ModeB(unittest.TestCase):
    def test_scores_sum_to_axis_totals(self):
        recs = [make_rec(f"s{i}", 1000 * i, 300 * i, 500 * i, 0.05 * i) for i in range(1, 6)]
        M4.score_pool(recs)
        for r in recs:
            self.assertAlmostEqual(sum(r["S_축"].values()), r["S"], places=6)
            self.assertGreaterEqual(r["S"], 0)
            self.assertLessEqual(r["S"], 100)

    def test_best_on_everything_scores_100(self):
        lo = make_rec("lo", 100, 50, 100, 0.01, front=2, corner="N", direction="N",
                      rent=900, R=0.2, 주차가능대수=0, 정차가능="N", 계약조건점수=1, 층=2)
        hi = make_rec("hi", 9000, 4000, 9000, 0.30, front=12, corner="Y", direction="Y",
                      rent=100, R=0.95, 주차가능대수=10, 정차가능="Y", 계약조건점수=5, 층=1)
        hi["경쟁"]["동일가격대_수"] = 0
        hi["경쟁"]["저가형_수"] = 0
        lo["수요"]["D_am_같은편"] = lo["수요"]["D_am"] * 0.1
        hi["수요"]["D_am_같은편"] = hi["수요"]["D_am"]
        M4.score_pool([lo, hi])
        self.assertAlmostEqual(hi["S"], 100.0, places=6)
        self.assertAlmostEqual(lo["S"], 0.0, places=6)

    def test_zero_variance_indicator_gives_half_credit(self):
        """풀 안에서 값이 똑같은 지표는 변별력이 없어 배점의 절반만 준다.

        그 결과 '모든 면에서 최고'인 후보지도 지표가 하나라도 무분산이면 100 에
        닿지 못한다. S 를 절대 점수로 읽으면 안 되는 이유 중 하나다.
        """
        a = make_rec("a", 100, 50, 100, 0.01, 층=1)
        b = make_rec("b", 9000, 4000, 9000, 0.30, 층=1)     # 층은 둘 다 1 → 무분산
        M4.score_pool([a, b])
        w = C.MODE_B_WEIGHTS["접근성"]["1층접근성"]
        self.assertAlmostEqual(a["S_상세"]["1층접근성"]["점수"], w * 0.5, places=9)
        self.assertAlmostEqual(b["S_상세"]["1층접근성"]["점수"], w * 0.5, places=9)
        self.assertLess(b["S"], 100.0)

    def test_gate_degeneracy_detected(self):
        """모든 지표에서 1등이어야 100 이라, 보통은 아무도 70 을 못 넘는다."""
        recs = [make_rec(f"s{i}", 1000 + i * 10, 300, 500, 0.05) for i in range(6)]
        M4.score_pool(recs)
        self.assertTrue(recs[0]["S_게이트_축퇴"])
        self.assertLess(recs[0]["S_풀최대"], C.c("보류_점수"))

    def test_anchor_proportionality(self):
        cand = make_rec("cand", 2000, 800, 1500, 0.08)
        anchor = make_rec("anchor", 1000, 400, 800, 0.05, 월매출_만원=3000)
        anchor["후보지"]["월매출_만원"] = 3000
        M4.score_pool([cand, anchor])
        out = M4.predict_mode_b(cand, [anchor], 30)
        self.assertAlmostEqual(out["월매출_중앙"], 3000 * (cand["S"] / anchor["S"]), places=4)
        self.assertTrue(any("순환" in w or "참고자료" in w for w in out["경고"]))

    def test_no_anchor_fails_explicitly(self):
        cand = make_rec("cand", 2000, 800, 1500, 0.08)
        M4.score_pool([cand])
        out = M4.predict_mode_b(cand, [], 30)
        self.assertIn("실패", out)
        self.assertIn("기준점포", out["실패"])


class TestM4ModeA(unittest.TestCase):
    def _stores(self, n):
        """참 모델에서 만든 합성 기존점 — 회귀가 복원할 대상이 실제로 존재하게 한다."""
        import random
        rnd = random.Random(11)
        out = []
        for i in range(n):
            W = rnd.uniform(800, 9000)
            H = rnd.uniform(300, 3000)
            D = rnd.uniform(400, 6000)
            S = rnd.uniform(0.02, 0.2)
            front = rnd.uniform(3, 12)
            corner = "Y" if rnd.random() < 0.5 else "N"
            direction = "Y" if rnd.random() < 0.5 else "N"
            lg = (-2.6 + 0.34 * math.log(W) + 0.16 * math.log(H) + 0.31 * math.log(D)
                  + 1.15 * S + 0.09 * (corner == "Y") + 0.10 * (direction == "Y")
                  + 0.14 * math.log(front))
            daily = math.exp(lg + rnd.gauss(0, 0.12))
            r = make_rec(f"st{i}", W, H, D, S, front=front, corner=corner, direction=direction)
            r["후보지"]["일매출_만원"] = daily
            out.append(r)
        return out

    def test_below_threshold_returns_none(self):
        self.assertIsNone(M4.fit_mode_a(self._stores(14)))

    def test_at_threshold_fits(self):
        m = M4.fit_mode_a(self._stores(15))
        self.assertIsNotNone(m)
        self.assertIn("beta", m)
        self.assertEqual(m["표본수"], 15)

    def test_recovers_true_coefficients(self):
        m = M4.fit_mode_a(self._stores(90))
        names = ["const"] + m["특징"]
        b = dict(zip(names, m["beta"]))
        self.assertAlmostEqual(b["log(W)"], 0.34, delta=0.06)
        self.assertAlmostEqual(b["log(H)"], 0.16, delta=0.06)
        self.assertAlmostEqual(b["log(D_am_adj)"], 0.31, delta=0.06)
        self.assertGreater(m["R2"], 0.85)

    def test_prediction_interval_is_ordered(self):
        stores = self._stores(30)
        m = M4.fit_mode_a(stores)
        out = M4.predict_mode_a(stores[0], m, 30)
        self.assertLess(out["월매출_하한"], out["월매출_중앙"])
        self.assertLess(out["월매출_중앙"], out["월매출_상한"])
        self.assertAlmostEqual(out["월매출_중앙"], out["일매출_중앙"] * 30, places=4)

    def test_uses_loocv_below_40_and_kfold_above(self):
        self.assertEqual(M4.fit_mode_a(self._stores(20))["CV"]["방식"], "LOOCV")
        self.assertEqual(M4.fit_mode_a(self._stores(45))["CV"]["방식"], "5-fold")

    def test_zero_feature_excluded_from_samples(self):
        stores = self._stores(20)
        stores[0]["수요"]["W"] = 0            # 로그 불가
        X, y, used = M4.valid_samples(stores)
        self.assertEqual(len(used), 19)


class TestM5(unittest.TestCase):
    SITE = {"월임대료_만원": 400, "관리비_만원": 30,
            "근저당_과다": "N", "임대인_불일치": "N", "소송_계류": "N", "인허가_불가": "N"}

    def judge(self, med, low, S=90, overlaps=(), **site):
        s = dict(self.SITE, **site)
        return M5.judge(s, {"월매출_중앙": med, "월매출_하한": low}, SETTINGS, S, list(overlaps))

    def test_bep_formula(self):
        j = self.judge(4000, 3500)
        F = 400 + 30 + 620 + 170
        v = 0.35 + 0.03 + 0.01
        self.assertAlmostEqual(j["고정비"]["F"], F)
        self.assertAlmostEqual(j["변동비율"], v)
        self.assertAlmostEqual(j["BEP_만원"], F / (1 - v), places=6)

    def test_margin_formula(self):
        j = self.judge(4000, 3000)
        self.assertAlmostEqual(j["margin"], (4000 - j["BEP_만원"]) / 4000, places=9)
        self.assertAlmostEqual(j["margin_low"], (3000 - j["BEP_만원"]) / 3000, places=9)

    def test_pass(self):
        self.assertEqual(self.judge(4000, 3500)["판정"], "통과")

    def test_reject_on_low_margin(self):
        bep = self.judge(4000, 3500)["BEP_만원"]
        self.assertEqual(self.judge(bep / 0.86, bep / 0.86)["판정"], "부결")

    def test_hold_on_mid_margin(self):
        bep = self.judge(4000, 3500)["BEP_만원"]
        self.assertEqual(self.judge(bep / 0.80, bep / 0.80)["판정"], "보류")

    def test_hold_on_low_score(self):
        self.assertEqual(self.judge(4000, 3500, S=69.9)["판정"], "보류")
        self.assertEqual(self.judge(4000, 3500, S=70.0)["판정"], "통과")

    def test_hold_on_overlap(self):
        ov = [{"점포명": "A", "overlap": 0.31, "월매출_만원": 3000}]
        self.assertEqual(self.judge(4000, 3500, overlaps=ov)["판정"], "보류")
        ov2 = [{"점포명": "A", "overlap": 0.30, "월매출_만원": 3000}]
        self.assertEqual(self.judge(4000, 3500, overlaps=ov2)["판정"], "통과")

    def test_hold_on_negative_margin_low(self):
        bep = self.judge(4000, 3500)["BEP_만원"]
        j = self.judge(4000, bep * 0.9)
        self.assertEqual(j["판정"], "보류")
        self.assertTrue(any("하한 시나리오 적자" in x for x in j["사유"]))

    def test_fatal_flag_overrides_everything(self):
        for key, _ in C.FATAL_FLAGS:
            with self.subTest(flag=key):
                j = self.judge(99999, 99999, S=100, **{key: "Y"})
                self.assertEqual(j["판정"], "부결")

    def test_unchecked_flags_qualify_a_pass(self):
        j = M5.judge({"월임대료_만원": 400, "관리비_만원": 30},
                     {"월매출_중앙": 4000, "월매출_하한": 3500}, SETTINGS, 90, [])
        self.assertEqual(j["판정"], "통과")
        self.assertEqual(len(j["치명_미확인"]), 4)
        self.assertTrue(any("잠정" in x for x in j["비고"]))

    def test_cannibalization_uses_max_overlap_and_sum_amount(self):
        ov = [{"점포명": "A", "overlap": 0.2, "월매출_만원": 3000},
              {"점포명": "B", "overlap": 0.4, "월매출_만원": 2000}]
        j = self.judge(4000, 3500, overlaps=ov)
        k = C.c("잠식계수_카파")
        self.assertAlmostEqual(j["카니발"]["최대_overlap"], 0.4)
        self.assertAlmostEqual(j["카니발"]["잠식액_합_만원"],
                               0.2 * 3000 * k + 0.4 * 2000 * k, places=6)
        self.assertAlmostEqual(j["순증_월매출_만원"], 4000 - j["카니발"]["잠식액_합_만원"], places=6)

    def test_impossible_variable_rate(self):
        bad = {"운영": {"변동비": {"원재료율": 1.1}, "고정비": {}}}
        j = M5.judge(self.SITE, {"월매출_중앙": 9000, "월매출_하한": 8000}, bad, 90, [])
        self.assertEqual(j["판정"], "부결")
        self.assertIsNone(j["BEP_만원"])

    def test_s_gate_degeneracy_surfaces(self):
        j = M5.judge(self.SITE, {"월매출_중앙": 4000, "월매출_하한": 3500},
                     SETTINGS, 60, [], s_pool_max=63.0)
        self.assertTrue(any("S 게이트 축퇴" in x for x in j["비고"]))


class TestM6(unittest.TestCase):
    def rows(self, errors):
        return [{"점포명": f"S{i}", "개점일": f"2025-{i + 1:02d}-01",
                 "심의시_예측_중앙_만원": 3000 * (1 + e), "12개월_월매출_만원": 3000}
                for i, e in enumerate(errors)]

    def test_mape_and_bias(self):
        e = M6.error_log(self.rows([0.10, -0.10, 0.20, -0.20]))
        self.assertAlmostEqual(e["MAPE"], 0.15, places=9)
        self.assertAlmostEqual(e["편향"], 0.0, places=9)

    def test_refit_trigger_on_three_consecutive(self):
        self.assertFalse(M6.error_log(self.rows([0.30, 0.30, 0.05, 0.30]))["재적합_필요"])
        e = M6.error_log(self.rows([0.05, 0.30, 0.30, 0.30, 0.05]))
        self.assertTrue(e["재적합_필요"])
        self.assertEqual(e["연속초과_최대"], 3)

    def test_threshold_is_strict_greater(self):
        e = M6.error_log(self.rows([0.20, 0.20, 0.20]))
        self.assertEqual(e["연속초과_최대"], 0)

    def test_orders_by_open_date(self):
        rows = self.rows([0.30, 0.30, 0.30])
        rows[0]["개점일"] = "2025-12-01"      # 첫 건을 맨 뒤로 보낸다
        e = M6.error_log(rows)
        self.assertEqual([x["점포명"] for x in e["기록"]], ["S1", "S2", "S0"])

    def test_uses_12m_over_6m(self):
        r = [{"점포명": "a", "개점일": "2025-01-01", "심의시_예측_중앙_만원": 1000,
              "6개월_월매출_만원": 500, "12개월_월매출_만원": 1000}]
        self.assertAlmostEqual(M6.error_log(r)["MAPE"], 0.0, places=9)

    def test_kappa_recovers_planted_value(self):
        rows = [{"점포명": f"s{i}", "인접_overlap": 0.4,
                 "인접_개점전_월매출_만원": 3000,
                 "인접_개점후_월매출_만원": 3000 - 0.4 * 3000 * 0.55} for i in range(6)]
        out = M6.recalibrate_kappa(rows)
        self.assertAlmostEqual(out["제안_κ"], 0.55, places=6)
        self.assertEqual(out["표본수"], 6)

    def test_kappa_needs_data(self):
        out = M6.recalibrate_kappa([{"점포명": "a"}])
        self.assertIn("실패", out)
        self.assertIn("인접_overlap", out["필요항목"])

    def test_lambda_search_picks_minimum(self):
        out = M6.recalibrate_lambda(lambda lam: 0.10 + abs(lam - 2.0) * 0.03)
        self.assertAlmostEqual(out["제안_λ"], 2.0)
        self.assertGreater(out["개선"], 0)

    def test_mode_switch(self):
        self.assertFalse(M6.mode_switch(14)["ModeA_가능"])
        self.assertTrue(M6.mode_switch(15)["ModeA_가능"])
        self.assertEqual(M6.mode_switch(9)["남은표본"], 6)

    def test_crossing_resistance_reports_missing_inputs(self):
        out = M6.crossing_resistance_status([{"점포명": "a"}])
        self.assertTrue(out["교정불가"])
        self.assertIn("실측_같은편_오전", out["필요항목"])

    def test_proposal_never_includes_unimproved_lambda(self):
        err = M6.error_log(self.rows([0.10]))
        lam = {"제안_λ": 1.4, "개선": 0.001, "현재_MAPE": 0.2, "제안_MAPE": 0.199, "격자": []}
        prop = M6.proposal(err, lam, {"실패": "x", "필요항목": []},
                           M6.mode_switch(20), {"교정불가": True})
        self.assertNotIn("거리마찰_람다", prop["변경제안"])


class TestOLS(unittest.TestCase):
    def test_solves_known_system(self):
        self.assertEqual([round(v, 6) for v in ols.solve([[2, 1], [1, 3]], [5, 10])], [1.0, 3.0])

    def test_singular_raises(self):
        with self.assertRaises(ols.SingularMatrix):
            ols.solve([[1, 2], [2, 4]], [1, 2])

    def test_quantile_matches_linear_interpolation(self):
        v = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(ols.quantile(v, 0.0), 1.0)
        self.assertAlmostEqual(ols.quantile(v, 0.5), 2.5)
        self.assertAlmostEqual(ols.quantile(v, 0.25), 1.75)
        self.assertAlmostEqual(ols.quantile(v, 1.0), 4.0)
