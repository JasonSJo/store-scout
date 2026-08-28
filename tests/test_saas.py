#!/usr/bin/env python3
"""
스스닷컴 SaaS — 경계선 검사

기능 테스트가 아니라 **사고 방지선** 검사다. 이 제품에서 나면 안 되는 일 셋:

  1. A 프랜차이즈의 후보지가 B 프랜차이즈에게 보인다
  2. 한도를 넘겨 조용히 과금된다 / 실패한 실행이 청구된다
  3. 사내 한정 자료가 등급 표시 없이 조직 밖으로 나간다
"""
from __future__ import annotations

import json
import re
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
from server import (app as app_mod, auth, bootstrap, consults, db, jobs,   # noqa: E402
                    orgdata, plans, views)


def seed(onboard: bool = True):
    """두 조직을 만든다 — 격리 검사의 전제.

    onboard=True 면 온보딩까지 끝내 둔다(브랜드 + 실매출·좌표 있는 기존점 2곳 중
    1곳이 기준점포). 온보딩이 끝나지 않은 조직은 심의를 돌릴 수 없으므로,
    그 게이트를 검사하는 자리에서만 onboard=False 를 쓴다.
    """
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
            if onboard:
                orgdata.save_settings(con, org, orgdata.merge(
                    orgdata.기본설정, {"브랜드": f"브랜드{key}"}))
                for i, (점포, 기준) in enumerate([(f"{key}점1", "Y"), (f"{key}점2", "N")]):
                    con.execute(
                        "INSERT INTO stores (org_id,점포명,위도,경도,기준점포,월매출_만원,좌석수)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (org, 점포, 37.5 + i * 0.01, 127.0 + i * 0.01, 기준, 3000 + i * 200, 24))
    return ids


def client_for(email: str) -> TestClient:
    c = TestClient(app_mod.app)
    r = c.post("/login", data={"email": email, "password": "pw-1234"},
               follow_redirects=False)
    assert r.status_code == 303, r.status_code
    return c


# 예시 후보지 CSV 는 알고리즘 저장소에 있다. 없으면 그 테스트만 건너뛴다.
SITES = jobs.PIPELINE / "후보지.example.csv"


def csv_rows(text: str):
    import csv, io
    return csv.DictReader(io.StringIO(text.lstrip("\ufeff")))


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

    def test_숫자가_아닌_타일은_모노로_조판하지_않는다(self):
        """'B(앵커링)' 에 모노를 걸면 괄호만 모노가 되고 자간이 벌어져 흩어져 보인다.
        수치 타일(6/150건)은 자릿수가 맞아야 하므로 모노를 유지한다."""
        from server import ui
        self.assertIn('class="v txt"', ui.tile("매출 추정 모드", "B(앵커링)"))
        self.assertIn('class="v"', ui.tile("이번 달 분석", "6", "/150건"))
        self.assertNotIn("txt", ui.tile("이번 달 분석", "6", "/150건"))

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
        self.assertIn("한도", r.text)

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
        self.assertIn("후보지명이 있는 행이 없습니다", r.text)

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


class TestOnboarding(unittest.TestCase):
    """온보딩이 끝나지 않은 조직은 심의를 돌릴 수 없다.

    막지 않으면 파이프라인이 예시 기존점을 집어 **남의 브랜드 실적으로** 이 조직의
    매출을 추정한다. 화면만 격리되고 판정은 섞이는, 가장 알아채기 어려운 사고다.
    """

    def test_기존점이_없으면_실행을_막고_무엇이_없는지_말한다(self):
        ids = seed(onboard=False)
        r = client_for("운영@a.kr").post(
            "/runs", data={"name": "성급한것"},
            files={"sites": ("s.csv", "후보지명\n가\n", "text/csv")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("온보딩", r.text)
        with db.tx() as con:
            self.assertEqual(db.rows_for_org(con, "runs", ids["A"]["org"]), [])

    def test_readiness가_남은_일을_짚는다(self):
        ids = seed(onboard=False)
        with db.tx() as con:
            r = orgdata.readiness(con, ids["A"]["org"])
            self.assertFalse(r["준비됨"])
            self.assertEqual([w for w, _, _ in r["할일"]], ["설정", "기존점"])
            orgdata.save_settings(con, ids["A"]["org"], {"브랜드": "가맹A"})
            con.execute("INSERT INTO stores (org_id,점포명,위도,경도,기준점포,월매출_만원)"
                        " VALUES (?,?,?,?,?,?)",
                        (ids["A"]["org"], "1호점", 37.5, 127.0, "N", 3000))
            con.execute("INSERT INTO stores (org_id,점포명,위도,경도,기준점포,월매출_만원)"
                        " VALUES (?,?,?,?,?,?)",
                        (ids["A"]["org"], "2호점", 37.51, 127.01, "N", 3200))
            r = orgdata.readiness(con, ids["A"]["org"])
            # 좌표는 찼지만 기준점포가 없다 — Mode B 앵커링이 성립하지 않는다
            self.assertFalse(r["준비됨"])
            self.assertEqual(r["모드"], "—")
            con.execute("UPDATE stores SET 기준점포='Y' WHERE 점포명='1호점'")
            r = orgdata.readiness(con, ids["A"]["org"])
            self.assertTrue(r["준비됨"])
            self.assertEqual(r["모드"], "B(앵커링)")

    def test_실매출_없는_기존점은_준비된_것으로_세지_않는다(self):
        ids = seed(onboard=False)
        with db.tx() as con:
            for i in range(3):
                con.execute("INSERT INTO stores (org_id,점포명,위도,경도,기준점포) "
                            "VALUES (?,?,?,?,'Y')",
                            (ids["A"]["org"], f"{i}호점", 37.5, 127.0))
            r = orgdata.readiness(con, ids["A"]["org"])
        self.assertEqual(r["기존점"], 3)
        self.assertEqual(r["실매출"], 0)
        self.assertFalse(r["준비됨"])


class TestOrgData(unittest.TestCase):
    """조직 자신의 숫자가 파이프라인 입력으로 나가는가."""

    def setUp(self):
        self.ids = seed()

    def test_기존점CSV에_자기_조직만_들어간다(self):
        with db.tx() as con:
            a = orgdata.stores_csv(con, self.ids["A"]["org"])
        self.assertIn("A점1", a)
        self.assertNotIn("B점1", a)

    def test_일매출은_월매출에서_나온다(self):
        with db.tx() as con:
            rows = list(csv_rows(orgdata.stores_csv(con, self.ids["A"]["org"])))
        one = [r for r in rows if r["점포명"] == "A점1"][0]
        self.assertEqual(float(one["월매출_만원"]), 3000.0)
        self.assertEqual(float(one["일매출_만원"]), 100.0)

    def test_설정YAML에_등급과_고지가_실린다(self):
        with db.tx() as con:
            y = orgdata.settings_yaml(con, self.ids["A"]["org"])
        self.assertIn("사내 한정 · 대외 배포 금지", y)
        self.assertIn("예상매출액 산정서", y)

    def test_설정은_조직마다_따로다(self):
        with db.tx() as con:
            orgdata.save_settings(con, self.ids["A"]["org"], {"브랜드": "A만의브랜드"})
            self.assertEqual(orgdata.load_settings(con, self.ids["A"]["org"])["브랜드"],
                             "A만의브랜드")
            self.assertEqual(orgdata.load_settings(con, self.ids["B"]["org"])["브랜드"],
                             "브랜드B")


class TestStoresPage(unittest.TestCase):
    def setUp(self):
        self.ids = seed()

    def test_남의_기존점은_보이지도_지워지지도_않는다(self):
        with db.tx() as con:
            sid = con.execute("SELECT id FROM stores WHERE org_id=? AND 점포명='A점1'",
                              (self.ids["A"]["org"],)).fetchone()["id"]
        cb = client_for("운영@b.kr")
        self.assertNotIn("A점1", cb.get("/stores").text)
        self.assertEqual(cb.post(f"/stores/{sid}/delete").status_code, 404)
        with db.tx() as con:                      # 404 를 받았지 지워지지 않았다
            self.assertIsNotNone(
                con.execute("SELECT 1 FROM stores WHERE id=?", (sid,)).fetchone())

    def test_영업팀은_기존점을_고칠_수_없다(self):
        c = client_for("영업@a.kr")
        self.assertEqual(c.get("/stores").status_code, 200)      # 읽기는 된다
        r = c.post("/stores", data={"점포명": "몰래", "월매출_만원": "3000",
                                    "위도": "37.5", "경도": "127.0"})
        self.assertEqual(r.status_code, 403)

    def test_좌표나_실매출이_없으면_받지_않는다(self):
        c = client_for("운영@a.kr")
        없음 = c.post("/stores", data={"점포명": "좌표없음", "월매출_만원": "3000",
                                     "위도": "", "경도": ""})
        self.assertEqual(없음.status_code, 400)
        self.assertIn("좌표", 없음.text)
        매출없음 = c.post("/stores", data={"점포명": "매출없음", "월매출_만원": "",
                                       "위도": "37.5", "경도": "127.0"})
        self.assertEqual(매출없음.status_code, 400)
        with db.tx() as con:
            이름 = [r["점포명"] for r in db.rows_for_org(con, "stores", self.ids["A"]["org"])]
        self.assertNotIn("좌표없음", 이름)
        self.assertNotIn("매출없음", 이름)

    def test_퇴짜를_놓아도_입력을_돌려준다(self):
        """특히 기준점포. 비워 두면 '아니오' 로 돌아가는데, Mode B 는 기준점포를
        앵커로 매출을 추정한다 — 다시 저장하면 앵커가 아닌 점포로 조용히 들어간다."""
        c = client_for("운영@a.kr")
        낸것 = {"점포명": "성수점", "월매출_만원": "", "기준점포": "Y",
              "위도": "37.5445", "경도": "127.0557", "좌석수": "24",
              "월임대료_만원": "420", "전용면적_평": "18", "주소": "서울 성동구"}
        r = c.post("/stores", data=낸것, follow_redirects=False)
        self.assertEqual(r.status_code, 400)
        폼 = r.text[r.text.find('action="/stores"'):]
        for k in ("점포명", "위도", "경도", "좌석수", "월임대료_만원",
                  "전용면적_평", "주소"):
            m = re.search(r'name="%s"[^>]*value="([^"]*)"' % re.escape(k), 폼)
            self.assertEqual(m.group(1), 낸것[k], k)
        블록 = re.search(r'name="기준점포"[^>]*>(.*?)</select>', 폼, re.S)
        고름 = re.search(r'<option value="([^"]*)"\s+selected', 블록.group(1))
        self.assertEqual(고름.group(1), "Y", "기준점포가 '아니오' 로 돌아갔다")

    def test_추가와_삭제가_감사에_남는다(self):
        c = client_for("운영@a.kr")
        c.post("/stores", data={"점포명": "3호점", "월매출_만원": "2800",
                                "위도": "37.6", "경도": "127.1", "기준점포": "N"},
               follow_redirects=False)
        with db.tx() as con:
            acts = [r["action"] for r in db.rows_for_org(con, "audit", self.ids["A"]["org"])]
        self.assertIn("기존점 추가", acts)


class TestSettingsPage(unittest.TestCase):
    def setUp(self):
        self.ids = seed()

    def 폼(self, **over):
        base = {"브랜드": "가맹A", "자사브랜드티어": "동일가격대", "좌석수_기본": "24",
                "영업일수": "30", "원재료율": "0.35", "로열티율": "0.03",
                "광고분담금율": "0.01", "기타변동비율": "0.022",
                "고정인건비_월_만원": "620", "기타_월_만원": "170"}
        return base | over

    def test_변동비_합이_100퍼센트를_넘으면_저장하지_않는다(self):
        """BEP = F ÷ (1 − v). v ≥ 1 이면 0 으로 나누거나 음수 BEP 가 조용히 통과가 된다."""
        c = client_for("운영@a.kr")
        r = c.post("/settings", data=self.폼(원재료율="0.9", 로열티율="0.2"))
        self.assertEqual(r.status_code, 400)
        with db.tx() as con:
            st = orgdata.load_settings(con, self.ids["A"]["org"])
        self.assertEqual(st["운영"]["변동비"]["원재료율"], 0.35)

    def test_저장한_값이_다음_설정_화면과_YAML에_그대로_있다(self):
        c = client_for("운영@a.kr")
        r = c.post("/settings", data=self.폼(브랜드="새브랜드", 원재료율="0.31"))
        self.assertEqual(r.status_code, 200)
        with db.tx() as con:
            st = orgdata.load_settings(con, self.ids["A"]["org"])
            y = orgdata.settings_yaml(con, self.ids["A"]["org"])
        self.assertEqual(st["브랜드"], "새브랜드")
        self.assertEqual(st["운영"]["변동비"]["원재료율"], 0.31)
        self.assertIn("새브랜드", y)

    def test_영업팀은_설정을_바꿀_수_없다(self):
        c = client_for("영업@a.kr")
        self.assertEqual(c.get("/settings").status_code, 200)
        self.assertEqual(c.post("/settings", data=self.폼()).status_code, 403)


class TestTeamPage(unittest.TestCase):
    def setUp(self):
        self.ids = seed()

    def test_좌석_한도를_넘겨_추가할_수_없다(self):
        """starter 는 좌석 3개고 A 조직은 이미 3명이다."""
        r = client_for("관리자@a.kr").post(
            "/team", data={"email": "넷째@a.kr", "name": "넷", "role": "영업",
                           "password": "pw-12345"})
        self.assertEqual(r.status_code, 402)
        self.assertIn("좌석", r.text)

    def test_비활성화하면_세션이_끊긴다(self):
        """안 끊으면 쿠키를 가진 브라우저가 계속 들어온다."""
        영업 = client_for("영업@a.kr")
        self.assertEqual(영업.get("/dashboard").status_code, 200)
        client_for("관리자@a.kr").post(f"/team/{self.ids['A']['영업']}/toggle",
                                    follow_redirects=False)
        self.assertEqual(영업.get("/dashboard").status_code, 401)

    def test_퇴짜를_놓아도_입력을_돌려주되_비밀번호는_빼고(self):
        c = client_for("관리자@a.kr")
        r = c.post("/team", data={"email": "새사람@a.kr", "name": "새사람",
                                  "role": "영업", "password": "짧음"},
                   follow_redirects=False)
        self.assertEqual(r.status_code, 400)
        폼 = r.text[r.text.find('action="/team"'):]
        self.assertEqual(
            re.search(r'name="email"[^>]*value="([^"]*)"', 폼).group(1), "새사람@a.kr")
        self.assertEqual(
            re.search(r'name="name"[^>]*value="([^"]*)"', 폼).group(1), "새사람")
        # 비밀번호는 화면에 다시 실어 보내지 않는다
        m = re.search(r'name="password"[^>]*value="([^"]*)"', 폼)
        self.assertIn(m.group(1) if m else "", ("", None))

    def test_자기_계정은_비활성화하지_못한다(self):
        관리 = client_for("관리자@a.kr")
        r = 관리.post(f"/team/{self.ids['A']['관리자']}/toggle")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(관리.get("/dashboard").status_code, 200)

    def test_남의_조직_구성원은_404다(self):
        r = client_for("관리자@a.kr").post(f"/team/{self.ids['B']['영업']}/toggle")
        self.assertEqual(r.status_code, 404)
        with db.tx() as con:
            self.assertEqual(
                con.execute("SELECT active FROM users WHERE id=?",
                            (self.ids["B"]["영업"],)).fetchone()["active"], 1)

    def test_감사_로그로_갈_길이_있다(self):
        """화면마다 '열람·내보내기 기록이 남습니다' 라고 말한다. 그 기록을 볼 링크가
        없으면 그 말은 확인할 수 없는 약속이다."""
        import re as _re
        html = client_for("관리자@a.kr").get("/dashboard").text
        nav = _re.search(r"<nav[^>]*>(.*?)</nav>", html, _re.S).group(1)
        self.assertIn('href="/audit"', nav)
        self.assertEqual(client_for("관리자@a.kr").get("/audit").status_code, 200)

    def test_감사_로그는_관리자만_본다(self):
        import re as _re
        for who in ("운영@a.kr", "영업@a.kr"):
            html = client_for(who).get("/dashboard").text
            nav = _re.search(r"<nav[^>]*>(.*?)</nav>", html, _re.S).group(1)
            self.assertNotIn('href="/audit"', nav, who)
            self.assertEqual(client_for(who).get("/audit").status_code, 403, who)

    def test_관리자만_팀을_본다(self):
        self.assertEqual(client_for("운영@a.kr").get("/team").status_code, 403)
        self.assertEqual(client_for("관리자@a.kr").get("/team").status_code, 200)

    def test_팀_화면에_남의_조직_사람이_없다(self):
        body = client_for("관리자@a.kr").get("/team").text
        self.assertNotIn("영업@b.kr", body)


class TestPages(unittest.TestCase):
    """새 화면들이 열리고, 열람 자리마다 등급이 붙는가."""

    def setUp(self):
        self.ids = seed()

    def test_모든_화면이_열린다(self):
        c = client_for("관리자@a.kr")
        for path in ("/dashboard", "/runs", "/stores", "/settings", "/team", "/audit"):
            self.assertEqual(c.get(path).status_code, 200, path)

    def test_심의_목록에_등급이_붙는다(self):
        self.assertIn("사내 한정 · 대외 배포 금지", client_for("영업@a.kr").get("/runs").text)

    def test_후보지_상세는_org_밖이면_404다(self):
        result = {"후보지": [{"이름": "가", "S": 61.2,
                           "판정": {"판정": "보류", "사유": ["시세 대비 임대료 높음"],
                                  "margin": 0.28, "BEP_만원": 1800},
                           "매출": {"월매출_하한": 2600, "월매출_상한": 3400},
                           "입력": {"주소": "서울시 어딘가"}, "경고": []}]}
        with db.tx() as con:
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (self.ids["A"]["org"], "묶음", self.ids["A"]["운영"], "x", 1)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status,mode,result_json)"
                              " VALUES (?,?,'완료','B',?)",
                              (self.ids["A"]["org"], b,
                               __import__("json").dumps(result, ensure_ascii=False))).lastrowid
        ca, cb = client_for("영업@a.kr"), client_for("영업@b.kr")
        good = ca.get(f"/runs/{run}/sites/0")
        self.assertEqual(good.status_code, 200)
        self.assertIn("시세 대비 임대료 높음", good.text)
        self.assertEqual(ca.get(f"/runs/{run}/sites/9").status_code, 404)
        self.assertEqual(cb.get(f"/runs/{run}/sites/0").status_code, 404)

    def test_실행중인_심의는_스스로_새로_고친다(self):
        with db.tx() as con:
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (self.ids["A"]["org"], "묶음", self.ids["A"]["운영"], "x", 1)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status) VALUES (?,?,'실행중')",
                              (self.ids["A"]["org"], b)).lastrowid
        body = client_for("영업@a.kr").get(f"/runs/{run}").text
        self.assertIn('http-equiv="refresh"', body)


class TestConsultPrivacy(unittest.TestCase):
    """상담은 이 제품에서 개인정보가 들어오는 유일한 자리다.

    여기서 지키지 못하면 나머지 경계선은 의미가 없다.
    """

    def setUp(self):
        self.ids = seed()
        self.폼 = {"고객명": "홍길동", "고객전화번호": "010-1234-5678", "동의": "1",
                  "거주지": "서울 강남구", "근무지": "서울 중구",
                  "희망지역": "강남, 성수", "희망평수": "20",
                  "희망상권": ["오피스", "메인"], "보증금_만원": "9000",
                  "권리금_만원": "9000", "투자금형태": "현금+대출", "운영형태": "오토",
                  "메모": "2월 개점 희망"}

    def 등록(self, c=None, **over):
        c = c or client_for("영업@a.kr")
        r = c.post("/consults", data={**self.폼, **over}, follow_redirects=False)
        return r

    def test_동의_없이는_저장하지_않는다(self):
        """브라우저의 required 는 우회할 수 있다. 서버에서도 막아야 한다."""
        r = self.등록(동의="")
        self.assertEqual(r.status_code, 400)
        self.assertIn("동의", r.text)
        with db.tx() as con:
            self.assertEqual(db.rows_for_org(con, "consults", self.ids["A"]["org"]), [])

    def test_퇴짜를_놓아도_입력을_돌려준다(self):
        """상담자는 고객 앞에 앉아 있다. 열세 칸을 다시 묻게 하면 안 된다."""
        r = self.등록(동의="")
        self.assertEqual(r.status_code, 400)
        폼 = r.text[r.text.find('action="/consults"'):]
        for k in ("고객명", "고객전화번호", "거주지", "근무지", "희망지역",
                  "희망평수", "보증금_만원", "권리금_만원", "메모"):
            m = re.search(r'name="%s"[^>]*value="([^"]*)"' % re.escape(k), 폼)
            self.assertIsNotNone(m, k)
            self.assertEqual(m.group(1), self.폼[k], k)
        고른것 = re.findall(r'name="희망상권"[^>]*?value="([^"]*)"[^>]*checked', 폼)
        self.assertEqual(sorted(고른것), sorted(self.폼["희망상권"]))

    def test_퇴짜_뒤_select_가_기본값으로_돌아가지_않는다(self):
        """비워 두면 화면은 기본값('현금'·'점주+알바')으로 돌아간다. 그건 빈 칸이 아니라
        **다른 값**이다. 동의만 체크하고 저장하면 고객이 말한 '오토' 대신 '점주+알바'
        가 저장되고, 고정인건비가 달라지니 BEP 와 판정이 함께 바뀐다."""
        r = self.등록(동의="")
        폼 = r.text[r.text.find('action="/consults"'):]
        for 이름, 낸것, 기본 in (("투자금형태", "현금+대출", "현금"),
                            ("운영형태", "오토", "점주+알바")):
            블록 = re.search(r'name="%s"[^>]*>(.*?)</select>' % re.escape(이름), 폼, re.S)
            고름 = re.search(r'<option value="([^"]*)"\s+selected', 블록.group(1))
            self.assertEqual(고름.group(1), 낸것, 이름)
            self.assertNotEqual(고름.group(1), 기본, f"{이름} 가 기본값으로 돌아갔다")

    def test_동의만은_되돌리지_않는다(self):
        """나머지는 편의지만 동의는 사실 확인이다. 사람이 다시 눌러야 한다."""
        r = self.등록(동의="")
        폼 = r.text[r.text.find('action="/consults"'):]
        상자 = re.search(r'name="동의"[^>]*type="checkbox"([^>]*)', 폼)
        self.assertNotIn("checked", 상자.group(1))

    def test_설정에_없는_값으로_퇴짜를_놓아도_돌려준다(self):
        r = self.등록(운영형태="무인로봇")
        self.assertEqual(r.status_code, 400)
        폼 = r.text[r.text.find('action="/consults"'):]
        m = re.search(r'name="고객명"[^>]*value="([^"]*)"', 폼)
        self.assertEqual(m.group(1), "홍길동")

    def test_목록에는_연락처가_가려진다(self):
        self.등록()
        body = client_for("영업@a.kr").get("/consults").text
        self.assertNotIn("010-1234-5678", body)
        self.assertIn("5678", body)          # 뒤 네 자리로 사람을 알아본다

    def test_개인정보_열람은_따로_기록된다(self):
        self.등록()
        with db.tx() as con:
            cid = db.rows_for_org(con, "consults", self.ids["A"]["org"])[0]["id"]
        detail = client_for("영업@a.kr").get(f"/consults/{cid}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("010-1234-5678", detail.text)      # 상세에서는 전체를 본다
        with db.tx() as con:
            acts = [r["action"] for r in db.rows_for_org(con, "audit", self.ids["A"]["org"])]
        self.assertIn("개인정보 열람", acts)

    def test_감사_로그에_고객명을_남기지_않는다(self):
        """감사 로그는 관리자 전원이 본다. 여기에까지 이름을 퍼뜨리지 않는다."""
        self.등록()
        body = client_for("관리자@a.kr").get("/audit").text
        self.assertNotIn("홍길동", body)

    def test_심의로는_조건만_간다(self):
        """조건_json 에 개인정보 키가 하나라도 들어가면 파이프라인과 심의표로 샌다."""
        self.등록()
        with db.tx() as con:
            row = db.rows_for_org(con, "consults", self.ids["A"]["org"])[0]
        payload = consults.조건_json(row)
        for k in consults.개인정보키:
            self.assertNotIn(k, payload, k)
        for v in ("홍길동", "010-1234-5678", "서울 강남구", "서울 중구", "2월 개점 희망"):
            self.assertNotIn(v, payload, v)
        cond = json.loads(payload)["조건"]
        self.assertEqual(set(cond), set(consults.조건키))

    def test_남의_조직_상담은_보이지도_지워지지도_않는다(self):
        self.등록()
        with db.tx() as con:
            cid = db.rows_for_org(con, "consults", self.ids["A"]["org"])[0]["id"]
        cb = client_for("영업@b.kr")
        self.assertNotIn("홍길동", cb.get("/consults").text)
        self.assertEqual(cb.get(f"/consults/{cid}").status_code, 404)
        self.assertEqual(cb.post(f"/consults/{cid}/delete").status_code, 404)
        with db.tx() as con:
            self.assertIsNotNone(
                con.execute("SELECT 1 FROM consults WHERE id=?", (cid,)).fetchone())

    def test_보관기간이_지나면_파기_대상으로_표시한다(self):
        self.등록()
        with db.tx() as con:
            row = dict(db.rows_for_org(con, "consults", self.ids["A"]["org"])[0])
            st = orgdata.load_settings(con, self.ids["A"]["org"])
        row["created_at"] = "2020-01-01 00:00:00"
        상태 = consults.보관상태(row, st)
        self.assertTrue(상태["만료됨"])
        self.assertEqual(상태["보관개월"], 12)

    def test_설정에_없는_형태는_저장하지_않는다(self):
        """파이프라인이 조용히 무시하고 넘어가는 값이다. 저장 전에 막는다."""
        r = self.등록(운영형태="점주+로봇")
        self.assertEqual(r.status_code, 400)
        self.assertIn("운영 형태", r.text)

    def test_상담을_파기해도_심의는_남는다(self):
        self.등록()
        with db.tx() as con:
            cid = db.rows_for_org(con, "consults", self.ids["A"]["org"])[0]["id"]
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (self.ids["A"]["org"], "묶음", self.ids["A"]["운영"], "x", 1)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status,consult_id)"
                              " VALUES (?,?,'완료',?)",
                              (self.ids["A"]["org"], b, cid)).lastrowid
        client_for("영업@a.kr").post(f"/consults/{cid}/delete", follow_redirects=False)
        with db.tx() as con:
            got = db.row_for_org(con, "runs", self.ids["A"]["org"], run)
        self.assertIsNotNone(got)                 # 심의는 남고
        self.assertIsNone(got["consult_id"])      # 연결만 끊긴다


class TestConsultToJudgment(unittest.TestCase):
    """상담 조건이 판정에 닿는 경로. 알고리즘과 필터를 갈라 둔 것이 지켜지는가."""

    def setUp(self):
        self.ids = seed()

    def 상담넣기(self, **over):
        base = {"고객명": "김상담", "고객전화번호": "010-0000-0000", "동의": 1,
                "희망지역": "", "희망평수": None, "희망상권": "",
                "보증금_만원": 9000, "권리금_만원": 9000,
                "투자금형태": "현금+대출", "운영형태": "오토"}
        v = {**base, **over}
        with db.tx() as con:
            return con.execute(
                "INSERT INTO consults (org_id,고객명,고객전화번호,동의,희망지역,희망평수,"
                "희망상권,보증금_만원,권리금_만원,투자금형태,운영형태,created_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.ids["A"]["org"], v["고객명"], v["고객전화번호"], v["동의"],
                 v["희망지역"], v["희망평수"], v["희망상권"], v["보증금_만원"],
                 v["권리금_만원"], v["투자금형태"], v["운영형태"],
                 self.ids["A"]["운영"])).lastrowid

    def test_반영예고가_고정비_변화를_말한다(self):
        cid = self.상담넣기()
        with db.tx() as con:
            row = db.row_for_org(con, "consults", self.ids["A"]["org"], cid)
            st = orgdata.load_settings(con, self.ids["A"]["org"])
        예고 = dict(consults.반영예고(row, st))
        self.assertIn("620", 예고["고정인건비"])      # 기본값에서
        self.assertIn("980", 예고["고정인건비"])      # 오토로
        self.assertIn("금융비용", " ".join(예고))

    def test_남의_조직_상담을_붙여_돌릴_수_없다(self):
        cid = self.상담넣기()
        r = client_for("운영@b.kr").post(
            "/runs", data={"name": "남의상담", "consult_id": str(cid)},
            files={"sites": ("s.csv", "후보지명\n가\n", "text/csv")})
        self.assertEqual(r.status_code, 404)

    @unittest.skipUnless(SITES.exists(), "파이프라인 예시 CSV 없음")
    def test_상담_조건이_후보지를_거르고_고정비를_바꾼다(self):
        with db.tx() as con:
            row = db.row_for_org(con, "consults", self.ids["A"]["org"],
                                 self.상담넣기(희망지역="강남, 홍대, 성수", 희망평수=20,
                                           희망상권="오피스, 메인"))
            sy = orgdata.settings_yaml(con, self.ids["A"]["org"])
        sites = SITES.read_text(encoding="utf-8-sig")

        민 = jobs.run(sites, settings_yaml=sy)
        걸린 = jobs.run(sites, settings_yaml=sy, consult_json=consults.조건_json(row))
        self.assertTrue(민["ok"], 민.get("error", "")[:300])
        self.assertTrue(걸린["ok"], 걸린.get("error", "")[:300])

        # 필터는 목록에서 뺀다 — 점수를 깎는 게 아니다
        self.assertLess(len(걸린["result"]["후보지"]), len(민["result"]["후보지"]))
        self.assertIn("제외", 걸린["상담반영"])

        # 알고리즘은 고정비로 닿는다 — 같은 후보지의 BEP 가 올라가야 한다
        민BEP = {s["이름"]: s["판정"]["BEP_만원"] for s in 민["result"]["후보지"]}
        for s in 걸린["result"]["후보지"]:
            self.assertGreater(s["판정"]["BEP_만원"], 민BEP[s["이름"]], s["이름"])

    @unittest.skipUnless(SITES.exists(), "파이프라인 예시 CSV 없음")
    def test_조건이_너무_좁으면_판정_기준을_낮추는_대신_멈춘다(self):
        with db.tx() as con:
            row = db.row_for_org(con, "consults", self.ids["A"]["org"],
                                 self.상담넣기(희망지역="울릉도"))
            sy = orgdata.settings_yaml(con, self.ids["A"]["org"])
        out = jobs.run(SITES.read_text(encoding="utf-8-sig"),
                       settings_yaml=sy, consult_json=consults.조건_json(row))
        self.assertFalse(out["ok"])
        self.assertIn("남은 후보지가 없습니다", out["error"])

    @unittest.skipUnless(SITES.exists(), "파이프라인 예시 CSV 없음")
    def test_걸러진_후보지는_청구하지_않는다(self):
        cid = self.상담넣기(희망지역="강남, 홍대, 성수", 희망평수=20)
        r = client_for("운영@a.kr").post(
            "/runs", data={"name": "상담심의", "consult_id": str(cid)},
            files={"sites": ("s.csv", SITES.read_text(encoding="utf-8-sig"), "text/csv")},
            follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        with db.tx() as con:
            run = db.rows_for_org(con, "runs", self.ids["A"]["org"])[0]
        self.assertEqual(run["status"], "완료", run["error"][:300])
        올린수 = jobs.count_sites(SITES.read_text(encoding="utf-8-sig"))
        self.assertLess(run["billed_units"], 올린수)
        self.assertEqual(run["billed_units"], len(json.loads(run["result_json"])["후보지"]))
        self.assertTrue(run["consult_md"])


class TestDeployment(unittest.TestCase):
    """배포한 인스턴스에서만 드러나는 것들."""

    def test_첫_계정을_서버에서_만들_수_있다(self):
        """배포 직후 DB 는 비어 있고 화면에 가입 경로가 없다. 이게 없으면
        아무도 들어갈 수 없다."""
        db.DB_PATH = Path(os.environ["STORE_SCOUT_DB"])
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        rc = bootstrap.main(["--org", "새 본부", "--plan", "team",
                             "--email", "Boss@Brand.co.kr", "--name", "대표"])
        self.assertEqual(rc, 0)
        with db.tx() as con:
            u = con.execute("SELECT * FROM users").fetchone()
            o = con.execute("SELECT * FROM orgs").fetchone()
        self.assertEqual(u["email"], "boss@brand.co.kr")   # 소문자로 정규화
        self.assertEqual(u["role"], "관리자")
        self.assertEqual(o["plan"], "team")
        # 데이터를 지어내지 않는다 — 온보딩은 사람이 채운다
        with db.tx() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) c FROM stores").fetchone()["c"], 0)

    def test_같은_이메일로_두_번_만들지_않는다(self):
        db.DB_PATH = Path(os.environ["STORE_SCOUT_DB"])
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()
        self.assertEqual(bootstrap.main(["--org", "A", "--email", "x@a.kr"]), 0)
        self.assertEqual(bootstrap.main(["--org", "B", "--email", "x@a.kr"]), 1)
        with db.tx() as con:
            # 조직만 덩그러니 남지 않는다
            self.assertEqual(con.execute("SELECT COUNT(*) c FROM orgs").fetchone()["c"], 1)

    def test_재시작하면_중단된_심의를_실패로_정리한다(self):
        """파이프라인은 이 프로세스의 백그라운드 작업이다. 배포·크래시로 프로세스가
        죽으면 작업도 죽지만 상태는 '실행중' 으로 남아, 화면이 영원히 기다리고
        사용량에도 계속 잡힌다."""
        ids = seed()
        with db.tx() as con:
            b = con.execute("INSERT INTO batches (org_id,name,created_by,sites_csv,site_count)"
                            " VALUES (?,?,?,?,?)",
                            (ids["A"]["org"], "묶음", ids["A"]["운영"], "x", 6)).lastrowid
            run = con.execute("INSERT INTO runs (org_id,batch_id,status,billed_units)"
                              " VALUES (?,?,'실행중',6)", (ids["A"]["org"], b)).lastrowid
        app_mod._recover_interrupted_runs()
        with db.tx() as con:
            got = db.row_for_org(con, "runs", ids["A"]["org"], run)
        self.assertEqual(got["status"], "실패")
        self.assertEqual(got["billed_units"], 0)      # 실패는 청구하지 않는다
        self.assertIn("다시 시작", got["error"])

    def test_배포_설정이_전부_같은_볼륨을_가리킨다(self):
        """DB 경로가 볼륨 밖이면 재배포 때 조직 데이터가 통째로 사라진다."""
        import tomllib
        import yaml as _yaml
        fly = tomllib.loads((ROOT / "fly.toml").read_bytes().decode())
        self.assertTrue(fly["env"]["STORE_SCOUT_DB"].startswith(
            fly["mounts"]["destination"] + "/"))
        # 인스턴스는 하나여야 한다 — SQLite 와 백그라운드 작업이 한 프로세스에 묶여 있다
        self.assertEqual(fly["http_service"]["min_machines_running"], 1)
        self.assertEqual(fly["http_service"]["auto_stop_machines"], "off")

        r = _yaml.safe_load((ROOT / "render.yaml").read_bytes())["services"][0]
        env = {e["key"]: e["value"] for e in r["envVars"]}
        self.assertEqual(r["numInstances"], 1)
        self.assertTrue(env["STORE_SCOUT_DB"].startswith(r["disk"]["mountPath"] + "/"))

    def test_이미지가_이_저장소의_알고리즘을_담는다(self):
        """판정은 알고리즘 판에 따라 달라진다. 어제 통과한 후보지가 오늘 부결이 되면
        왜 바뀌었는지 짚을 수 있어야 한다.

        전에는 알고리즘이 다른 저장소에 있어 PIPELINE_REV 로 커밋을 박았다. 이관한
        뒤로는 이 저장소의 커밋이 곧 알고리즘 판이므로, 지켜야 할 것이 바뀌었다 —
        **빌드가 밖에서 알고리즘을 받아 오지 않을 것.** 받아 오면 이미지와 커밋이
        갈라져 그 보장이 사라진다."""
        df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for 금지 in ("git fetch", "git clone", "PIPELINE_REPO"):
            self.assertNotIn(금지, df, f"빌드가 밖에서 알고리즘을 받아 옵니다: {금지}")
        self.assertIn("COPY cafe-trade-area/analysis", df,
                      "이미지가 이 저장소의 알고리즘을 담지 않습니다")
        # 심의 콘솔은 사내 한정이고 서버가 쓰지도 않는다 — 이미지에 들어가면 안 된다
        self.assertNotIn("COPY cafe-trade-area/app", df)
        self.assertNotIn("COPY cafe-trade-area ", df)

    def test_healthz_가_알고리즘_판을_밝힌다(self):
        """어떤 판이 그 판정을 냈는지 나중에 확인할 수 있어야 한다."""
        df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG STORE_SCOUT_REV", df)
        self.assertIn("STORE_SCOUT_REV=${STORE_SCOUT_REV}", df)
        self.assertIn("STORE_SCOUT_REV", (ROOT / "server" / "app.py").read_text(encoding="utf-8"))

    def test_알고리즘이_이_저장소_안에_있다(self):
        """이관이 끝났는지 파일로 확인한다. 없으면 심의가 아예 돌지 않는다."""
        분석 = ROOT / "cafe-trade-area" / "analysis"
        self.assertTrue((분석 / "review_sites.py").exists(), 분석)
        self.assertTrue((분석 / "requirements.txt").exists())

    def test_배포_설정이_앱에_없는_환경변수를_적지_않는다(self):
        """배포 설정에 없는 변수를 적어도 **아무 일도 일어나지 않는다.** 아무도
        읽지 않으니 오류가 없고, 그걸 준비 절차에 적어 두면 사람이 매번 하나마나
        한 일을 한다. 실제로 그렇게 STORE_SCOUT_SECRET 을 적어 넣은 적이 있다 —
        이 앱의 세션은 DB 에 넣는 무작위 토큰이라 서명 시크릿이 아예 없다."""
        import re as _re, tomllib
        읽는것 = set()
        for f in (ROOT / "server").glob("*.py"):
            읽는것 |= set(_re.findall(r"os\.environ(?:\.get)?[\(\[][\"']([A-Z_]+)",
                                    f.read_text(encoding="utf-8")))
        적는것 = set()
        fly = tomllib.load((ROOT / "fly.toml").open("rb"))
        적는것 |= set(fly.get("env") or {})
        적는것 |= set(_re.findall(r"^\s+STORE_SCOUT_[A-Z_]+",
                                (ROOT / "docker-compose.yml").read_text(encoding="utf-8"),
                                _re.M))
        적는것 = {x.strip().rstrip(":") for x in 적는것}
        for 문서 in (".github/workflows/deploy-fly.yml", "DEPLOY.md"):
            적는것 |= set(_re.findall(r"(STORE_SCOUT_[A-Z_]+)=",
                                    (ROOT / 문서).read_text(encoding="utf-8")))
        모르는것 = {v for v in 적는것 if v.startswith("STORE_SCOUT_")} - 읽는것
        self.assertEqual(모르는것, set(),
                         f"앱이 읽지 않는 환경변수를 배포 설정이 적습니다: {sorted(모르는것)}")

    def test_볼륨을_두_번_만들지_않는다(self):
        """볼륨이 둘이 되면 기계가 어느 쪽을 붙일지 알 수 없다. 붙지 않은 쪽의
        조직 데이터는 사라진 것처럼 보이고, 화면은 멀쩡하며 DB 만 비어 있다."""
        wf = (ROOT / ".github" / "workflows" / "deploy-fly.yml").read_text(encoding="utf-8")
        # 안내문(echo)과 주석에 적힌 명령은 세지 않는다 — 실제로 도는 줄만 본다.
        # 처음엔 문자열 위치로 봤다가, 오류 안내에 적어 둔 'volumes create' 때문에
        # 순서가 뒤집힌 것으로 읽혔다.
        도는줄 = [l.strip() for l in wf.splitlines()
                if "flyctl volumes" in l
                and not l.strip().startswith(("#", "echo"))
                and "echo " not in l]
        확인 = [i for i, l in enumerate(도는줄) if l.startswith("if flyctl volumes list")
              or l.startswith("flyctl volumes list")]
        생성 = [i for i, l in enumerate(도는줄) if "flyctl volumes create" in l]
        self.assertTrue(확인, f"볼륨을 만들기 전에 있는지 보지 않습니다: {도는줄}")
        self.assertTrue(생성, f"볼륨을 만드는 줄이 없습니다: {도는줄}")
        self.assertLess(min(확인), min(생성), f"확인이 생성보다 뒤에 있습니다: {도는줄}")

    def test_배포_워크플로가_Dockerfile_과_같은_빌드인자를_쓴다(self):
        """워크플로가 없는 ARG 를 넘기면 **오류 없이 무시된다.** 배포는 성공하고
        /healthz 만 rev=unknown 을 내며, 어떤 판이 그 판정을 냈는지 잃는다.
        실제로 알고리즘을 이관하면서 PIPELINE_REV 가 그렇게 죽은 인자가 됐다."""
        import re as _re
        wf = (ROOT / ".github" / "workflows" / "deploy-fly.yml").read_text(encoding="utf-8")
        df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        선언 = set(_re.findall(r"^ARG\s+([A-Z_][A-Z0-9_]*)", df, _re.M))
        넘김 = set(_re.findall(r"--build-arg\s+([A-Z_][A-Z0-9_]*)=", wf))
        self.assertTrue(넘김, "워크플로가 빌드 인자를 하나도 넘기지 않습니다")
        self.assertLessEqual(넘김, 선언,
                             f"Dockerfile 에 없는 인자를 넘깁니다: {sorted(넘김 - 선언)}")

    def test_배포_확인이_올라간_판을_대조한다(self):
        """pipeline=yes 만 보면 '알고리즘이 있다' 는 것만 확인한다. 옛 이미지가
        그대로 떠 있어도 통과한다 — 커밋까지 맞는지 봐야 배포가 됐다고 할 수 있다."""
        wf = (ROOT / ".github" / "workflows" / "deploy-fly.yml").read_text(encoding="utf-8")
        self.assertIn("pipeline=yes", wf)
        self.assertIn("rev=$GITHUB_SHA", wf)

    def test_배포_이미지가_데모_시드를_담지_않는다(self):
        """seed_demo.py 는 꾸며 낸 매출을 넣는다. 운영 이미지에 있으면 안 된다."""
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
        self.assertIn("seed_demo.py", ignore)
        self.assertIn("tests/", ignore)


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
