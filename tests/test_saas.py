#!/usr/bin/env python3
"""
출점심의 SaaS — 경계선 검사

기능 테스트가 아니라 **사고 방지선** 검사다. 이 제품에서 나면 안 되는 일 셋:

  1. A 프랜차이즈의 후보지가 B 프랜차이즈에게 보인다
  2. 한도를 넘겨 조용히 과금된다 / 실패한 실행이 청구된다
  3. 사내 한정 자료가 등급 표시 없이 조직 밖으로 나간다
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="scout-test-")
os.environ["STORE_SCOUT_DB"] = str(Path(_TMP) / "t.sqlite3")

from fastapi.testclient import TestClient       # noqa: E402
from server import app as app_mod, auth, db, jobs, plans, views   # noqa: E402


def seed():
    """두 조직을 만든다 — 격리 검사의 전제."""
    db.DB_PATH = Path(os.environ["STORE_SCOUT_DB"])
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    db.init()
    ids = {}
    with db.tx() as con:
        for key, (name, plan) in {
            "A": ("가맹A", "starter"), "B": ("가맹B", "team")}.items():
            org = con.execute("INSERT INTO orgs (name, plan) VALUES (?,?)",
                              (name, plan)).lastrowid
            ids[key] = {"org": org}
            for role in ("관리자", "운영", "영업"):
                uid = con.execute(
                    "INSERT INTO users (org_id,email,name,role,pw_hash) VALUES (?,?,?,?,?)",
                    (org, f"{role}@{key.lower()}.kr", role, role,
                     auth.hash_pw("pw-1234"))).lastrowid
                ids[key][role] = uid
    return ids


def client_for(email: str) -> TestClient:
    c = TestClient(app_mod.app)
    r = c.post("/login", data={"email": email, "password": "pw-1234"},
               follow_redirects=False)
    assert r.status_code == 303, r.status_code
    return c


SITES = (ROOT.parent / "cafe-trade-area" / "analysis" / "후보지.example.csv")


class TestTenancy(unittest.TestCase):
    """조직 경계 — 이게 깨지면 제품이 아니라 사고다."""

    def setUp(self):
        self.ids = seed()

    def test_남의_조직_분석은_404다(self):
        """403 으로 답하면 '그 id 가 존재한다' 는 사실이 새어 나간다."""
        with db.tx() as con:
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (self.ids["A"]["org"], "A의 묶음", self.ids["A"]["운영"], "x", 1)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status,result_json)"
                              " VALUES (?,?,'완료','{}')",
                              (self.ids["A"]["org"], b)).lastrowid
        cb = client_for("영업@b.kr")
        self.assertEqual(cb.get(f"/runs/{run}").status_code, 404)
        self.assertEqual(cb.get(f"/runs/{run}/report").status_code, 404)
        ca = client_for("영업@a.kr")
        self.assertEqual(ca.get(f"/runs/{run}").status_code, 200)

    def test_조회_헬퍼가_org_없이는_안_돈다(self):
        with db.tx() as con:
            with self.assertRaises(TypeError):
                db.rows_for_org(con, "runs")            # org_id 필수
            with self.assertRaises(ValueError):
                db.rows_for_org(con, "orgs", 1)         # 허용 테이블 밖

    def test_대시보드에_남의_묶음이_없다(self):
        with db.tx() as con:
            con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                        " VALUES (?,?,?,?,?)",
                        (self.ids["A"]["org"], "A만의비밀묶음", self.ids["A"]["운영"], "x", 1))
        body = client_for("관리자@b.kr").get("/dashboard").text
        self.assertNotIn("A만의비밀묶음", body)

    def test_로그인_실패는_어느_쪽이_틀렸는지_말하지_않는다(self):
        c = TestClient(app_mod.app)
        없는계정 = c.post("/login", data={"email": "nobody@x.kr", "password": "pw-1234"})
        틀린비번 = c.post("/login", data={"email": "영업@a.kr", "password": "wrong"})
        self.assertEqual(없는계정.status_code, 401)
        self.assertEqual(틀린비번.status_code, 401)
        self.assertIn("이메일 또는 비밀번호", 없는계정.text)
        self.assertIn("이메일 또는 비밀번호", 틀린비번.text)


class TestRoles(unittest.TestCase):
    def setUp(self):
        self.ids = seed()

    def test_영업팀은_분석을_실행할_수_없다(self):
        """분석 건수가 과금 단위다. 아무나 돌리면 월 한도가 조용히 소진된다."""
        c = client_for("영업@a.kr")
        r = c.post("/runs", data={"name": "x"},
                   files={"sites": ("s.csv", "후보지명\n가\n", "text/csv")})
        self.assertEqual(r.status_code, 403)

    def test_감사_로그는_관리자만_본다(self):
        self.assertEqual(client_for("운영@a.kr").get("/audit").status_code, 403)
        self.assertEqual(client_for("관리자@a.kr").get("/audit").status_code, 200)

    def test_로그인하지_않으면_401이다(self):
        self.assertEqual(TestClient(app_mod.app).get("/dashboard").status_code, 401)


class TestPlanGating(unittest.TestCase):
    def setUp(self):
        self.ids = seed()

    def test_한도를_넘으면_막고_이유를_말한다(self):
        """조용히 초과분을 청구하면 다음 달 청구서에서 신뢰를 잃는다."""
        org = self.ids["A"]["org"]                      # starter = 월 30건
        with db.tx() as con:
            con.execute("INSERT INTO batches (id,org_id,name,created_by,sites_csv,site_count)"
                        " VALUES (99,?,'과거',?, 'x', 28)", (org, self.ids["A"]["운영"]))
            con.execute("INSERT INTO runs (org_id,batch_id,status,billed_units)"
                        " VALUES (?,99,'완료',28)", (org,))
        csv = "후보지명\n" + "".join(f"후보{i}\n" for i in range(5))
        r = client_for("운영@a.kr").post(
            "/runs", data={"name": "초과"}, files={"sites": ("s.csv", csv, "text/csv")})
        self.assertEqual(r.status_code, 402)
        self.assertIn("한도", r.json()["detail"])

    def test_실패한_실행은_청구하지_않는다(self):
        os.environ["STORE_SCOUT_PIPELINE"] = "/없는/경로"
        try:
            import importlib
            importlib.reload(jobs)
            c = client_for("운영@a.kr")
            c.post("/runs", data={"name": "실패할것"},
                   files={"sites": ("s.csv", "후보지명\n가\n", "text/csv")},
                   follow_redirects=False)
            with db.tx() as con:
                row = con.execute("SELECT status, billed_units FROM runs "
                                  "ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row["status"], "실패")
            self.assertEqual(row["billed_units"], 0)
        finally:
            os.environ.pop("STORE_SCOUT_PIPELINE", None)
            import importlib
            importlib.reload(jobs)

    def test_빈_CSV_는_거절한다(self):
        r = client_for("운영@a.kr").post(
            "/runs", data={"name": "빈것"}, files={"sites": ("s.csv", "후보지명\n\n", "text/csv")})
        self.assertEqual(r.status_code, 400)

    def test_좌석_한도(self):
        self.assertTrue(plans.seat_check("team", 9)[0])
        self.assertFalse(plans.seat_check("starter", 3)[0])
        self.assertTrue(plans.seat_check("enterprise", 9999)[0])


class TestDisclosure(unittest.TestCase):
    """사내 한정 자료가 등급 없이 나가지 않는가."""

    def setUp(self):
        self.ids = seed()

    def test_대시보드에_등급과_가맹사업법_경고가_있다(self):
        body = client_for("영업@a.kr").get("/dashboard").text
        self.assertIn("사내 한정 · 대외 배포 금지", body)
        self.assertIn("예상매출액 산정서", body)

    def test_내려받는_파일명에_internal_이_박힌다(self):
        with db.tx() as con:
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (self.ids["A"]["org"], "묶음", self.ids["A"]["운영"], "x", 1)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status,report_md)"
                              " VALUES (?,?,'완료','# 심의표')",
                              (self.ids["A"]["org"], b)).lastrowid
        r = client_for("운영@a.kr").get(f"/runs/{run}/report")
        self.assertEqual(r.status_code, 200)
        self.assertIn("internal", r.headers["content-disposition"])

    def test_요약은_매출을_구간으로만_낸다(self):
        """단일 숫자를 보여 주면 그 숫자가 상담 자리에서 그대로 인용된다."""
        s = jobs.summarize({"후보지": [{
            "이름": "가",
            "판정": {"판정": "보류", "margin": 0.3, "BEP_만원": 1800, "사유": []},
            "매출": {"월매출_중앙": 3000, "월매출_하한": 2600, "월매출_상한": 3400}}]})
        one = s["후보지"][0]
        self.assertIn("월매출_하한", one)
        self.assertIn("월매출_상한", one)
        self.assertNotIn("월매출_중앙", one)
        self.assertEqual(s["보류"], 1)

    def test_산출물_모양이_어긋나도_화면이_죽지_않는다(self):
        """파이프라인이 바뀌면 여기부터 흔들린다. 500 대신 빈 요약을 낸다."""
        for junk in ({}, {"후보지": None}, {"후보지": ["문자열"]},
                     {"후보지": [{"판정": "문자열", "매출": 3}]}):
            got = jobs.summarize(junk)
            self.assertEqual(got["통과"] + got["보류"] + got["부결"], 0)

    def test_모든_화면이_noindex다(self):
        for path in ("/", "/dashboard"):
            c = client_for("관리자@a.kr")
            self.assertIn('name="robots" content="noindex"', c.get(path).text, path)


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.ids = seed()

    def test_열람과_내보내기가_기록된다(self):
        with db.tx() as con:
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (self.ids["A"]["org"], "묶음", self.ids["A"]["운영"], "x", 1)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status,result_json,report_md)"
                              " VALUES (?,?,'완료','{}','# r')",
                              (self.ids["A"]["org"], b)).lastrowid
        c = client_for("영업@a.kr")
        c.get(f"/runs/{run}")
        c.get(f"/runs/{run}/report")
        with db.tx() as con:
            acts = [r["action"] for r in db.rows_for_org(con, "audit", self.ids["A"]["org"])]
        for want in ("로그인", "열람", "내보내기"):
            self.assertIn(want, acts)

    def test_감사_로그도_조직_밖은_안_보인다(self):
        client_for("영업@a.kr")                    # A 조직에 로그인 기록 생성
        body = client_for("관리자@b.kr").get("/audit").text
        self.assertNotIn("영업@a.kr", body)


class TestPipelineIsolation(unittest.TestCase):
    def test_서브프로세스로_돈다(self):
        """import 로 끌어 쓰면 파이프라인의 전역 계수 레지스트리가 요청 사이에 공유되어,
        한 조직이 넣은 계수가 다른 조직의 판정에 새어 든다."""
        src = (ROOT / "server" / "jobs.py").read_text(encoding="utf-8")
        self.assertIn("subprocess.run", src)
        self.assertNotIn("import review_sites", src)

    def test_실행_뒤_임시_디렉터리를_지운다(self):
        src = (ROOT / "server" / "jobs.py").read_text(encoding="utf-8")
        self.assertIn("shutil.rmtree", src)

    @unittest.skipUnless(SITES.exists(), "파이프라인 예시 CSV 없음")
    def test_실제_파이프라인이_완주한다(self):
        out = jobs.run(SITES.read_text(encoding="utf-8-sig"))
        self.assertTrue(out["ok"], out.get("error", "")[:400])
        s = jobs.summarize(out["result"])
        self.assertEqual(s["통과"] + s["보류"] + s["부결"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
