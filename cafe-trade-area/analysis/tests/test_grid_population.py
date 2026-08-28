#!/usr/bin/env python3
"""
SGIS 격자 인구 수집 (전국)

H·W 는 M2 의 배후 수요다. 지금까지 격자인구.csv 를 사람이 준비해야 했고, 그래서
전국 어디든 후보지를 넣기 전에 손작업이 하나 있었다. 여기서 지키는 것:

  · 조회 영역이 P10(도보 10분)을 덮는가 — 좁으면 배후 수요가 잘린다
  · 겹친 격자를 두 번 더하지 않는가 — 더하면 H·W 가 부풀고 그 후보지만 좋아 보인다
  · 좌표·인구를 못 읽은 격자를 0 으로 만들지 않는가
  · dry-run 이 인구를 지어내지 않는가
"""
from __future__ import annotations

import io
import json
import math
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_grid_population as GP   # noqa: E402
import geo                             # noqa: E402
import m2_demand as M2                 # noqa: E402
from common import read_csv            # noqa: E402


class TestBBox(unittest.TestCase):
    def test_반경이_P10_을_덮는다(self):
        """P10 = 4km/h × 10분 ≈ 667m. 조회 영역이 그보다 좁으면 배후 수요가 잘린다."""
        self.assertGreaterEqual(GP.DEFAULT_RADIUS, 667.0)

    def test_사각형이_요청한_반경을_담는다(self):
        lat, lon, r = 37.5445, 127.0557, 800.0
        y1, x1, y2, x2 = GP.bbox(lat, lon, r)
        # 남북
        self.assertAlmostEqual((y2 - lat) * 111_000, r, delta=1.0)
        # 동서 — 위도가 올라가면 경도 1도가 짧아지므로 그만큼 넓게 잡아야 한다
        동서_m = (x2 - lon) * 111_000 * math.cos(math.radians(lat))
        self.assertAlmostEqual(동서_m, r, delta=1.0)

    def test_좌표가_없는_후보지는_건너뛴다(self):
        """주소만으로는 격자를 고를 수 없다. 추측한 좌표로 받은 인구는 근거가 아니다."""
        got = GP.sites_bboxes([
            {"후보지명": "있음", "위도": "37.5", "경도": "127.0"},
            {"후보지명": "없음", "위도": "", "경도": ""},
        ], 800.0)
        self.assertEqual([b["이름"] for b in got], ["있음"])


class TestSgisStatsShape(unittest.TestCase):
    """실제 SGIS 응답. 처음에 세웠던 bbox·격자 가정은 틀렸고, 받아 보니
    adm_cd 와 값만 온다 — 좌표도 면적도 없다."""

    실제 = {"result": [{"household_cnt": "4141659", "avg_family_member_cnt": "2.2",
                      "family_member_cnt": 8908911, "all_household_cnt": 4141659,
                      "adm_cd": "11", "adm_nm": "서울특별시"}],
           "errCd": 0, "errMsg": "Success", "id": "API_0305",
           "trId": "m8Uw_API_0305_1787896255885"}

    AREAS = {"11200": {"면적_m2": 16850000.0, "위도": 37.5634, "경도": 127.0371}}

    def test_세대수_필드를_읽는다(self):
        rows, 버림 = GP.sgis_to_cells(
            [dict(self.실제["result"][0], adm_cd="11200")],
            self.AREAS, "세대수", GP.SGIS_STATS["세대수"][1])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["세대수"], 4141659.0)
        self.assertEqual(rows[0]["직장인구"], 0)
        self.assertEqual(rows[0]["격자ID"], "SGIS:11200")

    def test_좌표와_면적은_areas_에서_온다(self):
        """SGIS 통계는 좌표도 면적도 주지 않는다. 지어내면 배후 수요가 그 값으로
        안분되고 아무도 추측이었다는 걸 모른다."""
        rows, 버림 = GP.sgis_to_cells(
            [dict(self.실제["result"][0], adm_cd="99999")],
            self.AREAS, "세대수", GP.SGIS_STATS["세대수"][1])
        self.assertEqual(rows, [])
        self.assertEqual(버림["면적없음"], 1)

    def test_면적에서_한변을_환산한다(self):
        rows, _ = GP.sgis_to_cells(
            [dict(self.실제["result"][0], adm_cd="11200")],
            self.AREAS, "세대수", GP.SGIS_STATS["세대수"][1])
        self.assertAlmostEqual(float(rows[0]["한변_m"]), 16850000 ** 0.5, delta=1.0)

    def test_두_통계의_경로가_정해져_있다(self):
        self.assertIn("household.json", GP.SGIS_STATS["세대수"][0])
        self.assertIn("company.json", GP.SGIS_STATS["직장인구"][0])
        self.assertIn("household_cnt", GP.SGIS_STATS["세대수"][1])

    def test_errCd_가_0이_아니면_자료로_받지_않는다(self):
        원래 = urllib.request.urlopen

        class R:
            def __init__(s, b):
                s._b = b.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        urllib.request.urlopen = lambda url, timeout=None, context=None: R(
            json.dumps({"errCd": "-401", "errMsg": "토큰 만료", "result": []},
                       ensure_ascii=False))
        try:
            rows, err = GP.fetch_sgis_stats("T", "https://x", "/p", "11", "2023")
        finally:
            urllib.request.urlopen = 원래
        self.assertEqual(rows, [])
        self.assertIn("토큰 만료", err)


class TestReachesM2(unittest.TestCase):
    """받은 격자가 실제로 H·W 로 도달하는가. 거기까지 봐야 '붙었다' 고 할 수 있다."""

    def test_H_와_W_가_나온다(self):
        tmp = Path(tempfile.mkdtemp(prefix="grid-"))
        rows = [
            {"격자ID": "G1", "중심위도": 37.5445, "중심경도": 127.0557,
             "한변_m": 100, "세대수": 8, "직장인구": 14},
            {"격자ID": "G2", "중심위도": 37.5450, "중심경도": 127.0562,
             "한변_m": 100, "세대수": 7, "직장인구": 19},
        ]
        out = GP.write_rows(rows, tmp / "격자인구.csv")
        cells = M2.load_cells(out)
        self.assertEqual(len(cells), 2)

        lat0, lon0 = 37.5445, 127.0557
        p10 = [geo.project(lat0, lon0, lat0 + dy, lon0 + dx)
               for dy, dx in [(0.006, -0.008), (0.006, 0.008),
                              (-0.006, 0.008), (-0.006, -0.008)]]
        got = M2.residents_workers({"위도": lat0, "경도": lon0, "P10": p10}, cells)
        self.assertGreater(got["H"], 0, "격자가 H 에 닿지 않았습니다")
        self.assertGreater(got["W"], 0, "격자가 W 에 닿지 않았습니다")


class TestDryRun(unittest.TestCase):
    def test_인구를_지어내지_않는다(self):
        """지어낸 배후 수요가 심의표에 실리면 실측으로 오인된다."""
        tmp = Path(tempfile.mkdtemp(prefix="grid-dry-"))
        out = tmp / "out.csv"
        rc = GP.main(["--out", str(out)])
        self.assertEqual(rc, 0)
        self.assertEqual(read_csv(out), [])

    def test_키가_없으면_라이브를_거절한다(self):
        tmp = Path(tempfile.mkdtemp(prefix="grid-live-"))
        import os
        saved = {k: os.environ.pop(k, None) for k in ("SGIS_KEY", "SGIS_SECRET")}
        try:
            rc = GP.main(["--live", "--out", str(tmp / "o.csv")])
            self.assertEqual(rc, 2)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class TestProbe(unittest.TestCase):
    """SGIS 문서를 이 환경에서 열 수 없어 자료 엔드포인트를 확정하지 못했다.
    추측으로 코드를 쌓는 대신, 키가 있는 곳에서 한 번 돌리면 진실이 나오게 한다."""

    def setUp(self):
        self.원래 = urllib.request.urlopen
        self.응답 = {
            GP.AUTH_URL: {"result": {"accessToken": "TOKEN-abc"}},
            "https://sgisapi.kostat.go.kr/OpenAPI3/stats/household.json":
                {"errCd": 0, "result": [{"adm_cd": "11", "adm_nm": "서울특별시",
                                         "household_cnt": "4227000"}]},
        }

        class FakeResp:
            def __init__(s, body):
                s._b = body.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        def fake(url, timeout=None, context=None):
            base = url.split("?")[0]
            if base in self.응답:
                return FakeResp(json.dumps(self.응답[base], ensure_ascii=False))
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

        urllib.request.urlopen = fake

    def tearDown(self):
        urllib.request.urlopen = self.원래

    def 실행(self):
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.probe("KEY", "SECRET", GP.AUTH_URL, "11", "2023", None)
        finally:
            sys.stdout = old
        return rc, buf.getvalue()

    def test_한쪽_호스트가_죽어_있으면_다른_쪽으로_넘어간다(self):
        """개편으로 옛 주소가 404 여도 새 주소로 붙으면 진행돼야 한다."""
        self.응답 = {
            "https://sgisapi.mods.go.kr/OpenAPI3/auth/authentication.json":
                {"result": {"accessToken": "TOK"}},
            "https://sgisapi.mods.go.kr/OpenAPI3/stats/household.json":
                {"errCd": 0, "result": [{"adm_cd": "11", "household_cnt": "1"}]},
        }
        rc, 말 = self.실행()
        self.assertEqual(rc, 0)
        self.assertIn("sgisapi.mods.go.kr", 말)
        # 자료 주소도 인증이 통한 호스트를 따라가야 한다
        self.assertIn("sgisapi.mods.go.kr/OpenAPI3/stats/household.json", 말)

    def test_응답한_것과_아닌_것을_갈라_보여_준다(self):
        rc, 말 = self.실행()
        self.assertEqual(rc, 0)
        self.assertIn("토큰 발급됨", 말)
        self.assertIn("household.json", 말)
        self.assertIn("household_cnt", 말, "응답 필드를 보여 주지 않습니다")
        self.assertIn("HTTP 404", 말, "실패한 후보도 보여 줘야 합니다")

    def test_인증이_실패하면_거기서_멈춘다(self):
        """두 호스트 다 눌러 보고, 그래도 안 되면 조회로 넘어가지 않는다."""
        self.응답 = {GP.AUTH_URL: {"result": {}}}
        rc, 말 = self.실행()
        self.assertEqual(rc, 1)
        self.assertIn("토큰을 받지 못했습니다", 말)
        # 두 호스트를 모두 시도했는지
        for h in GP.SGIS_HOSTS:
            self.assertIn(h, 말, h)
        # 인증이 안 됐는데 자료를 부르지 않는다
        self.assertNotIn("household.json", 말)

    def test_하나도_답하지_않으면_0_이_아닌_코드(self):
        self.응답 = {GP.AUTH_URL: {"result": {"accessToken": "T"}}}
        rc, 말 = self.실행()
        self.assertEqual(rc, 1)
        self.assertIn("응답한 엔드포인트가 없습니다", 말)

    def test_키가_없으면_발급_방법을_알려_준다(self):
        buf, old = io.StringIO(), sys.stderr
        sys.stderr = buf
        try:
            rc = GP.probe("", "", GP.AUTH_URL, "11", "2023", None)
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)
        self.assertIn("개발지원센터", buf.getvalue())


class TestRealAuthResponse(unittest.TestCase):
    """실제 SGIS 인증 응답. 짐작이 아니라 받아 본 것이다.

    문서를 이 환경에서 열 수 없어 형태를 확정하지 못하고 있었는데, 키를 발급받아
    호출한 응답이 들어왔다. 그 모양을 그대로 박아 둔다 — 나중에 파서를 손댈 때
    이것과 어긋나면 바로 알 수 있다.
    """

    실제 = {"result": {"accessToken": "f31ad90a-e9c4-431f-acd4-b1a8cca50963",
                      "accessTimeout": "1787910189924"},
           "errCd": 0, "errMsg": "Success", "id": "API_0101",
           "trId": "sp*S_API_0101_1787895789922"}

    def _가짜(self, doc):
        원래 = urllib.request.urlopen

        class R:
            def __init__(s, b):
                s._b = b.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        urllib.request.urlopen = lambda url, timeout=None, context=None: R(
            json.dumps(doc, ensure_ascii=False))
        return 원래

    def test_실제_응답에서_토큰을_읽는다(self):
        원래 = self._가짜(self.실제)
        try:
            tok, err = GP.get_token("K", "S")
        finally:
            urllib.request.urlopen = 원래
        self.assertEqual(err, "")
        self.assertEqual(tok, "f31ad90a-e9c4-431f-acd4-b1a8cca50963")

    def test_토큰_수명은_4시간이다(self):
        """한 번 실행이 그보다 길 일은 없지만, 오래 걸리는 배치는 재발급이 필요하다."""
        발급 = int(self.실제["trId"].rsplit("_", 1)[1])
        만료 = int(self.실제["result"]["accessTimeout"])
        self.assertAlmostEqual((만료 - 발급) / 1000 / 3600, 4.0, places=2)

    def test_errCd_가_0이_아니면_그_말을_전한다(self):
        """오류도 HTTP 200 으로 온다. errMsg 를 그대로 전해야 원인을 빨리 짚는다."""
        원래 = self._가짜({"errCd": "-401", "errMsg": "인증키가 유효하지 않습니다",
                        "result": {}})
        try:
            tok, err = GP.get_token("K", "S")
        finally:
            urllib.request.urlopen = 원래
        self.assertEqual(tok, "")
        self.assertIn("인증키가 유효하지 않습니다", err)


class TestConfirmedEndpoints(unittest.TestCase):
    def test_인증_주소는_문서로_확인한_것이다(self):
        self.assertEqual(
            GP.AUTH_URL,
            "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json")

    def test_개편된_호스트도_후보에_있다(self):
        """통계청 → 국가데이터처 개편으로 개발지원센터가 sgis.mods.go.kr 로 옮겼다.
        API 호스트도 함께 바뀌었을 수 있는데, 한쪽만 박아 두면 '키가 잘못됐나' 하고
        엉뚱한 데를 찾게 된다."""
        self.assertIn("https://sgisapi.mods.go.kr", GP.SGIS_HOSTS)
        self.assertIn("https://sgisapi.kostat.go.kr", GP.SGIS_HOSTS)

    def test_후보에_가구와_사업체가_들어_있다(self):
        """H 는 세대수, W 는 종사자수에서 온다. 둘 다 눌러 봐야 한다."""
        urls = " ".join(u for _, u, _, _ in GP.CANDIDATES)
        self.assertIn("household", urls)
        self.assertIn("company", urls)

    def test_경계도_눌러_본다(self):
        """경계가 응답하면 --areas 표(면적·중심점)를 손으로 채우지 않아도 된다.
        지금은 그 표를 사람이 만들어야 하는 것이 가장 큰 손작업이다."""
        kinds = {k for _, _, k, _ in GP.CANDIDATES}
        self.assertIn("boundary", kinds)
        urls = " ".join(u for _, u, _, _ in GP.CANDIDATES)
        self.assertIn("boundary", urls)


class TestCoarseCellWarning(unittest.TestCase):
    """무료로 열린 전국 인구 자료(SGIS 통계·KOSIS)는 대부분 행정구역 단위다.
    그걸 격자인구.csv 에 그대로 넣으면 M2 가 균등분포로 안분하는데, 유동인구 쪽은
    같은 안분을 할 때 크게 경고하면서 여기는 조용했다."""

    def 상권(self, 반경_deg=0.003):
        lat0, lon0 = 37.5445, 127.0557
        p10 = [geo.project(lat0, lon0, lat0 + dy, lon0 + dx)
               for dy, dx in [(반경_deg, -반경_deg), (반경_deg, 반경_deg),
                              (-반경_deg, 반경_deg), (-반경_deg, -반경_deg)]]
        return {"위도": lat0, "경도": lon0, "P10": p10, "P5": p10}

    def test_100m_격자는_조용하다(self):
        cells = [{"격자ID": "G1", "중심위도": 37.5445, "중심경도": 127.0557,
                  "한변_m": "100", "세대수": "8", "직장인구": "14"}]
        got = M2.residents_workers(self.상권(), cells)
        self.assertEqual(got["굵은칸"], 0)
        self.assertEqual(got["경고"], [])

    def test_행정구역_단위는_경고한다(self):
        cells = [{"격자ID": "A1", "중심위도": 37.5445, "중심경도": 127.0557,
                  "한변_m": "1225", "세대수": "22000", "직장인구": "31000"}]
        got = M2.residents_workers(self.상권(), cells)
        self.assertEqual(got["굵은칸"], 1)
        말 = " ".join(got["경고"])
        self.assertIn("격자가 아닙니다", 말)
        self.assertIn("고르게 산다고 가정", 말)

    def test_큰_구역은_면적비로_깎인다(self):
        """P10 보다 큰 구역을 통째로 더하면 배후 수요가 몇 배로 부푼다."""
        작은상권 = self.상권(0.001)      # P10 을 좁게
        cells = [{"격자ID": "A1", "중심위도": 37.5445, "중심경도": 127.0557,
                  "한변_m": "1225", "세대수": "22000", "직장인구": "0"}]
        got = M2.residents_workers(작은상권, cells)
        self.assertLess(got["H"], 22000 * 0.5,
                        "행정동 인구가 거의 그대로 들어왔습니다 — 면적 가중이 안 먹었습니다")
        self.assertGreater(got["H"], 0)

    def test_배후_경고가_유동_경고에_먹히지_않는다(self):
        """demand() 가 dict 를 그냥 펼치면 뒤엣것이 앞엣것의 '경고' 를 덮어쓴다.
        경고가 사라지는 버그는 값이 틀리는 버그보다 알아채기 어렵다."""
        cells = [{"격자ID": "A1", "중심위도": 37.5445, "중심경도": 127.0557,
                  "한변_m": "1225", "세대수": "22000", "직장인구": "31000"}]
        points = [{"지점ID": "p", "위도": "37.5445", "경도": "127.0557",
                   "도로변": "A", "시간대": M2.AM, "인원": "300", "출처": "실측"}]
        got = M2.demand(self.상권(), cells, points, "A")
        말 = " ".join(got["경고"])
        self.assertIn("격자가 아닙니다", 말, "배후 인구 경고가 사라졌습니다")

    def test_칸이_하나도_없으면_말해_준다(self):
        got = M2.residents_workers(self.상권(), [])
        self.assertEqual(got["H"], 0)
        self.assertIn("하나도 없습니다", " ".join(got["경고"]))


class TestKosis(unittest.TestCase):
    """KOSIS 는 호출이 아니라 **어느 통계표를 쓸지** 고르는 데서 막힌다."""

    def test_키가_없으면_발급처를_알려_준다(self):
        buf, old = io.StringIO(), sys.stderr
        sys.stderr = buf
        try:
            rc = GP.kosis_probe("")
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)
        self.assertIn("kosis.kr/openapi", buf.getvalue())

    def test_목록을_받으면_통계표를_보여_준다(self):
        원래 = urllib.request.urlopen

        class FakeResp:
            def __init__(s, body):
                s._b = body.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        목록 = [{"ORG_ID": "101", "TBL_ID": "DT_1B040A3",
                "TBL_NM": "주민등록인구현황", "LIST_ID": "A_1"}]

        def fake(url, timeout=None, context=None):
            if url.split("?")[0] == GP.KOSIS_LIST_URL:
                return FakeResp(json.dumps(목록, ensure_ascii=False))
            raise urllib.error.HTTPError(url, 404, "nf", None, None)

        urllib.request.urlopen = fake
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.kosis_probe("KEY")
        finally:
            sys.stdout = old
            urllib.request.urlopen = 원래
        말 = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("DT_1B040A3", 말)
        self.assertIn("주민등록인구현황", 말)
        self.assertIn("ORG_ID", 말)

    def test_오류_응답을_목록으로_착각하지_않는다(self):
        """KOSIS 는 오류도 HTTP 200 + JSON 으로 보낸다."""
        원래 = urllib.request.urlopen

        class FakeResp:
            def __init__(s, body):
                s._b = body.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        def fake(url, timeout=None, context=None):
            return FakeResp(json.dumps({"err": "20", "errMsg": "인증키가 유효하지 않습니다"},
                                       ensure_ascii=False))

        urllib.request.urlopen = fake
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.kosis_probe("BAD")
        finally:
            sys.stdout = old
            urllib.request.urlopen = 원래
        self.assertEqual(rc, 1)
        self.assertIn("인증키가 유효하지 않습니다", buf.getvalue())


class TestKosisFetch(unittest.TestCase):
    """표를 고른 뒤의 경로. probe 출력만 있으면 **코드를 고치지 않고** 플래그로 돈다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kosis-"))
        import csv
        with (self.tmp / "areas.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["구역코드", "면적_m2", "위도", "경도"])
            w.writeheader()
            w.writerow({"구역코드": "11200", "면적_m2": "16850000",
                        "위도": "37.5634", "경도": "127.0371"})
        self.원래 = urllib.request.urlopen

        class R:
            def __init__(s, b):
                s._b = b.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        def fake(url, timeout=None, context=None):
            if "DT_HOUSE" in url:
                return R(json.dumps([{"C1": "11200", "DT": "140000"}]))
            if "DT_WORK" in url:
                return R(json.dumps([{"C1": "11200", "DT": "210000"}]))
            if "DT_ERR" in url:
                return R(json.dumps({"err": "20", "errMsg": "인증키 오류"},
                                    ensure_ascii=False))
            raise urllib.error.HTTPError(url, 404, "nf", None, None)

        urllib.request.urlopen = fake
        import os
        self.키원래 = os.environ.get("KOSIS_API_KEY")
        os.environ["KOSIS_API_KEY"] = "KEY"

    def tearDown(self):
        import os
        urllib.request.urlopen = self.원래
        if self.키원래 is None:
            os.environ.pop("KOSIS_API_KEY", None)
        else:
            os.environ["KOSIS_API_KEY"] = self.키원래

    def 실행(self, extra):
        out = self.tmp / "out.csv"
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.main(["--source", "kosis", "--live",
                          "--areas", str(self.tmp / "areas.csv"),
                          "--out", str(out)] + extra)
        finally:
            sys.stdout = old
        return rc, out, buf.getvalue()

    def test_두_표를_한_행으로_합친다(self):
        """세대수 표와 종사자수 표는 따로 온다. 구역이 같으면 한 칸이어야 한다."""
        rc, out, _ = self.실행(["--tbl-id-household", "DT_HOUSE",
                              "--tbl-id-worker", "DT_WORK"])
        self.assertEqual(rc, 0)
        rows = read_csv(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["세대수"]), 140000.0)
        self.assertEqual(float(rows[0]["직장인구"]), 210000.0)

    def test_구역_면적에서_한변을_환산한다(self):
        """M2 는 정사각형 한 변으로 겹친 면적을 잰다. 성동구 16.85km² → 약 4.1km."""
        rc, out, _ = self.실행(["--tbl-id-household", "DT_HOUSE"])
        한변 = float(read_csv(out)[0]["한변_m"])
        self.assertAlmostEqual(한변, 16850000 ** 0.5, delta=1.0)
        self.assertGreater(한변, M2.굵은격자_m, "M2 가 경고할 만큼 큰 구역이어야 합니다")

    def test_M2_까지_도달하고_안분_경고가_난다(self):
        rc, out, _ = self.실행(["--tbl-id-household", "DT_HOUSE",
                              "--tbl-id-worker", "DT_WORK"])
        cells = read_csv(out)
        lat0, lon0 = 37.5634, 127.0371
        p10 = [geo.project(lat0, lon0, lat0 + dy, lon0 + dx)
               for dy, dx in [(0.006, -0.008), (0.006, 0.008),
                              (-0.006, 0.008), (-0.006, -0.008)]]
        got = M2.demand({"위도": lat0, "경도": lon0, "P10": p10, "P5": p10},
                        cells, [], "A")
        self.assertGreater(got["H"], 0)
        self.assertGreater(got["W"], 0)
        self.assertLess(got["H"], 140000 * 0.5, "구역 인구가 거의 그대로 들어왔습니다")
        self.assertIn("격자가 아닙니다", " ".join(got["경고"]))

    def test_면적표가_없으면_거절한다(self):
        """KOSIS 는 좌표도 면적도 주지 않는다. 추측해 나눈 값은 근거가 아니다."""
        out = self.tmp / "o2.csv"
        buf, old = io.StringIO(), sys.stderr
        sys.stderr = buf
        try:
            rc = GP.main(["--source", "kosis", "--live",
                          "--tbl-id-household", "DT_HOUSE", "--out", str(out)])
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)
        self.assertIn("--areas", buf.getvalue())

    def test_표를_안_고르면_probe_로_보낸다(self):
        out = self.tmp / "o3.csv"
        buf, old = io.StringIO(), sys.stderr
        sys.stderr = buf
        try:
            rc = GP.main(["--source", "kosis", "--live",
                          "--areas", str(self.tmp / "areas.csv"), "--out", str(out)])
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)
        self.assertIn("--probe", buf.getvalue())

    def test_오류_응답을_자료로_착각하지_않는다(self):
        rc, out, 말 = self.실행(["--tbl-id-household", "DT_ERR"])
        self.assertEqual(rc, 1)


class TestMakeAreas(unittest.TestCase):
    """--areas 표는 전국 229개를 다 만들 필요가 없다. 이번 후보지가 속한 구역만
    채우면 되고, 어느 코드가 필요한지 도구가 짚어 준다."""

    def setUp(self):
        import csv
        self.tmp = Path(tempfile.mkdtemp(prefix="mkareas-"))
        self.sites = self.tmp / "sites.csv"
        with self.sites.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["후보지명", "주소", "법정동코드"])
            w.writeheader()
            w.writerows([
                {"후보지명": "성수", "주소": "서울 성동구", "법정동코드": "1120011400"},
                {"후보지명": "강남", "주소": "서울 강남구", "법정동코드": "1168010100"},
                {"후보지명": "성수2", "주소": "서울 성동구", "법정동코드": "1120010300"},
                {"후보지명": "코드없음", "주소": "어딘가", "법정동코드": ""},
            ])

    def 실행(self):
        out = self.tmp / "areas.csv"
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.main(["--make-areas", "--sites", str(self.sites),
                          "--areas", str(out)])
        finally:
            sys.stdout = old
        return rc, out, buf.getvalue()

    def test_법정동코드_앞_다섯_자리로_묶는다(self):
        """같은 시군구의 후보지 둘이 줄 두 개가 되면 사람이 같은 값을 두 번 채운다."""
        rc, out, _ = self.실행()
        self.assertEqual(rc, 0)
        rows = read_csv(out)
        self.assertEqual(sorted(r["구역코드"] for r in rows), ["11200", "11680"])

    def test_면적과_좌표를_비워_둔다(self):
        """지어내면 그 값으로 배후 수요가 안분되고 아무도 추측이었다는 걸 모른다."""
        rc, out, _ = self.실행()
        for r in read_csv(out):
            self.assertEqual(r["면적_m2"], "")
            self.assertEqual(r["위도"], "")
            self.assertEqual(r["경도"], "")

    def test_어느_후보지_때문에_필요한지_적는다(self):
        rc, out, 말 = self.실행()
        비고 = " ".join(r["비고"] for r in read_csv(out))
        self.assertIn("성수", 비고)
        self.assertIn("강남", 비고)

    def test_법정동코드가_없는_후보지를_짚어_준다(self):
        rc, out, 말 = self.실행()
        self.assertIn("코드없음", 말)
        self.assertIn("주소를 검색", 말)

    def test_만든_표를_load_areas_가_읽는다(self):
        """유동인구 쪽과 같은 형식이어야 표 하나를 양쪽에 쓴다."""
        rc, out, _ = self.실행()
        got = GP.load_areas(out)
        self.assertEqual(sorted(got), ["11200", "11680"])


class TestPlaceholderGuard(unittest.TestCase):
    def test_자리표시자_통계표_ID_를_잡는다(self):
        """문서의 DT_xxxx 를 그대로 넣으면, 그냥 부르면 무슨 일인지 알기 어려운
        API 오류가 난다. 부르기 전에 말해 준다."""
        import os
        tmp = Path(tempfile.mkdtemp(prefix="ph-"))
        import csv
        areas = tmp / "a.csv"
        with areas.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["구역코드", "면적_m2", "위도", "경도"])
            w.writeheader()
            w.writerow({"구역코드": "11200", "면적_m2": "1", "위도": "37.5", "경도": "127.0"})
        saved = os.environ.get("KOSIS_API_KEY")
        os.environ["KOSIS_API_KEY"] = "K"
        buf, old = io.StringIO(), sys.stderr
        sys.stderr = buf
        try:
            rc = GP.main(["--source", "kosis", "--live", "--areas", str(areas),
                          "--tbl-id-household", "DT_xxxx",
                          "--out", str(tmp / "o.csv")])
        finally:
            sys.stderr = old
            if saved is None:
                os.environ.pop("KOSIS_API_KEY", None)
            else:
                os.environ["KOSIS_API_KEY"] = saved
        self.assertEqual(rc, 2)
        self.assertIn("자리표시자", buf.getvalue())


class TestKosisFind(unittest.TestCase):
    """분류 코드를 외워 박지 않기 위한 것.

    실제 응답을 받아 보니 A_1 은 '인구·가구' 가 아니라 **인구이동** 이었다. 그런
    추측은 맞는지 확인할 방법이 없고, 틀려도 조용히 빈 결과만 돌아온다. 폴더를 따라
    내려가며 표 이름을 보는 편이 확실하다.
    """

    def setUp(self):
        self.원래 = urllib.request.urlopen
        # 사용자가 실제로 받은 응답 모양 그대로 — 표 행과 폴더 행이 섞여 온다
        self.트리 = {
            "": [{"LIST_NM": "인구", "LIST_ID": "A"},
                 {"LIST_NM": "사업·기업", "LIST_ID": "F"}],
            "A": [{"LIST_NM": "인구이동", "LIST_ID": "A_1"},
                  {"LIST_NM": "인구총조사", "LIST_ID": "A_2"}],
            "A_1": [{"STAT_ID": "1976003", "TBL_ID": "DT_1B26001_A01", "ORG_ID": "101",
                     "TBL_NM": "시군구별 이동자수", "VW_CD": "MT_ZTITLE"},
                    {"LIST_NM": "전입사유별이동", "LIST_ID": "A_1_004",
                     "VW_CD": "MT_ZTITLE"}],
            "A_2": [{"TBL_ID": "DT_1JC1501", "ORG_ID": "101",
                     "TBL_NM": "행정구역별 가구원수별 가구(일반가구)"}],
            "F": [{"LIST_NM": "전국사업체조사", "LIST_ID": "F_29"}],
            "F_29": [{"TBL_ID": "DT_1K52C01", "ORG_ID": "101",
                      "TBL_NM": "행정구역별 사업체수 및 종사자수"}],
        }

        class R:
            def __init__(s, b):
                s._b = b.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        self.호출 = []

        def fake(url, timeout=None, context=None):
            import urllib.parse as up
            q = up.parse_qs(up.urlparse(url).query)
            pid = q.get("parentListId", [""])[0]
            self.호출.append(pid)
            return R(json.dumps(self.트리.get(pid, []), ensure_ascii=False))

        urllib.request.urlopen = fake

    def tearDown(self):
        urllib.request.urlopen = self.원래

    def 실행(self, 낱말, **kw):
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.kosis_find("KEY", 낱말, **kw)
        finally:
            sys.stdout = old
        return rc, buf.getvalue()

    def test_표와_폴더를_구분한다(self):
        """TBL_ID 가 있으면 조회할 수 있는 표, LIST_ID 만 있으면 더 내려갈 폴더."""
        표 = {"TBL_ID": "DT_1", "TBL_NM": "x"}
        폴더 = {"LIST_ID": "A_1", "LIST_NM": "y"}
        self.assertTrue(GP.is_table(표))
        self.assertFalse(GP.is_folder(표))
        self.assertTrue(GP.is_folder(폴더))
        self.assertFalse(GP.is_table(폴더))

    def test_트리를_내려가며_찾는다(self):
        rc, 말 = self.실행(["가구", "종사자"])
        self.assertEqual(rc, 0)
        self.assertIn("DT_1JC1501", 말)
        self.assertIn("DT_1K52C01", 말)
        self.assertIn("ORG_ID=101", 말)

    def test_어느_경로에서_나왔는지_적는다(self):
        """같은 이름의 표가 여러 곳에 있어 경로가 없으면 고를 수 없다."""
        rc, 말 = self.실행(["종사자"])
        self.assertIn("사업·기업 > 전국사업체조사", 말)

    def test_상관없는_표는_넣지_않는다(self):
        rc, 말 = self.실행(["가구"])
        self.assertNotIn("시군구별 이동자수", 말)

    def test_호출_수에_상한이_있다(self):
        """남의 API 를 넓이 우선으로 훑는 일이라 예의가 필요하다."""
        rc, 말 = self.실행(["가구"], 최대호출=2)
        self.assertLessEqual(len(self.호출), 2)

    def test_못_찾으면_넓히라고_말한다(self):
        rc, 말 = self.실행(["존재하지않는낱말"])
        self.assertEqual(rc, 1)
        self.assertIn("낱말을 넓혀", 말)

    def test_낱말이_없으면_거절한다(self):
        buf, old = io.StringIO(), sys.stderr
        sys.stderr = buf
        try:
            rc = GP.kosis_find("KEY", [])
        finally:
            sys.stderr = old
        self.assertEqual(rc, 2)
        self.assertIn("--find", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAdmCodeResolution(unittest.TestCase):
    """법정동코드 앞자리를 SGIS 행정구역코드로 쓰면 **조용히 다른 구를 받는다.**

    실제 응답에서 확인한 값:
        성동구  법정동 11200 · SGIS 11040
        동작구  법정동 11590 · SGIS 11200
    즉 성동구 후보지의 법정동코드를 잘라 쓰면 동작구 인구가 들어온다. 오류는 나지
    않는다 — 숫자가 멀쩡히 채워지고 그 후보지의 배후 수요만 남의 것이 된다.
    여기서 지키는 것: 코드는 반드시 SGIS 가 준 목록에서 이름으로 찾는다.
    """

    # 서울 아래 일부. adm_cd 는 실제 SGIS 응답 값이다.
    서울 = [
        {"adm_cd": "11010", "adm_nm": "종로구", "household_cnt": "72000",
         "tot_worker": "269222"},
        {"adm_cd": "11040", "adm_nm": "성동구", "household_cnt": "134000",
         "tot_worker": "198800"},
        {"adm_cd": "11200", "adm_nm": "동작구", "household_cnt": "176000",
         "tot_worker": "110000"},
    ]

    def setUp(self):
        self.원래 = urllib.request.urlopen
        self.부른곳 = []

        class R:
            def __init__(s, b):
                s._b = b.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        def fake(url, timeout=None, context=None):
            self.부른곳.append(url)
            q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")
                     if "=" in p)
            if "auth" in url:
                return R(json.dumps({"errCd": 0,
                                     "result": {"accessToken": "T"}}))
            adm, low = q.get("adm_cd", ""), q.get("low_search", "0")
            if adm == "11" and low == "0":
                return R(json.dumps({"errCd": 0, "result": [
                    {"adm_cd": "11", "adm_nm": "서울특별시",
                     "household_cnt": "4141659", "tot_worker": "5699761"}]},
                    ensure_ascii=False))
            if adm == "11" and low == "1":
                return R(json.dumps({"errCd": 0, "result": self.서울},
                                    ensure_ascii=False))
            for r in self.서울:
                if r["adm_cd"] == adm:
                    return R(json.dumps({"errCd": 0, "result": [r]},
                                        ensure_ascii=False))
            return R(json.dumps({"errCd": "-100", "errMsg": "없는 코드"},
                                ensure_ascii=False))

        urllib.request.urlopen = fake

    def tearDown(self):
        urllib.request.urlopen = self.원래

    def 옮기기(self, sites):
        return GP.resolve_regions("T", GP.SGIS_HOSTS[0], "2023", sites)

    def test_성동구가_동작구가_되지_않는다(self):
        지역, 문제 = self.옮기기([{"후보지명": "왕십리", "주소": "서울 성동구 왕십리로 222",
                              "법정동코드": "1120000000"}])
        self.assertEqual([z["adm_cd"] for z in 지역], ["11040"])
        self.assertNotIn("11200", [z["adm_cd"] for z in 지역],
                         "법정동 11200 을 그대로 쓰면 동작구를 받는다")
        self.assertEqual(문제, [])

    def test_이름으로_찾지_코드를_자르지_않는다(self):
        """법정동코드가 아예 없어도 주소만으로 옮겨져야 한다."""
        지역, 문제 = self.옮기기([{"후보지명": "성수", "주소": "서울특별시 성동구 아차산로",
                              "법정동코드": ""}])
        self.assertEqual([z["adm_cd"] for z in 지역], ["11040"])
        self.assertEqual(문제, [])

    def test_못_찾으면_버리고_말한다(self):
        """맞는 구역이 없으면 아무 코드나 고르지 않는다 — 없는 채로 말한다."""
        지역, 문제 = self.옮기기([{"후보지명": "어딘가", "주소": "서울 없는구 어딘가로 1",
                              "법정동코드": "1199900000"}])
        self.assertEqual(지역, [])
        self.assertTrue(any("없는구" in m for m in 문제), 문제)

    def test_주소가_없으면_짚어_준다(self):
        지역, 문제 = self.옮기기([{"후보지명": "무주소", "주소": ""}])
        self.assertEqual(지역, [])
        self.assertTrue(any("무주소" in m for m in 문제), 문제)

    def test_시도_이름이_다르면_그_코드를_쓰지_않는다(self):
        """강원은 42→51 로 바뀌었다. 어느 쪽인지는 받아 본 이름으로 정한다."""
        지역, 문제 = self.옮기기([{"후보지명": "강원", "주소": "강원 춘천시 중앙로",
                              "법정동코드": "4211000000"}])
        # 가짜 서버는 42 를 모른다 → 코드를 확인하지 못했다고 말하고 버린다
        self.assertEqual(지역, [])
        self.assertTrue(any("강원" in m for m in 문제), 문제)

    def test_한_구역에_후보지_둘이면_한_번만_부른다(self):
        지역, _ = self.옮기기([
            {"후보지명": "A", "주소": "서울 성동구 1", "법정동코드": "1120000000"},
            {"후보지명": "B", "주소": "서울 성동구 2", "법정동코드": "1120000000"},
        ])
        self.assertEqual([z["adm_cd"] for z in 지역], ["11040"])
        self.assertEqual(sorted(지역[0]["후보지"]), ["A", "B"])


class TestBoundaryToAreas(unittest.TestCase):
    """경계 API 는 좌표를 **위경도로 주지 않는다.** UTM-K(EPSG:5179) 미터 좌표다.

    그대로 위도·경도 칸에 넣으면 M2 가 그 구역을 지구 밖으로 보고 P10 과 절대
    겹치지 않는다 → H·W 가 0 이 되고, 그것이 '배후가 없는 자리' 라는 판단으로 읽힌다.
    """

    def test_원점이_38N_127_5E_로_돌아온다(self):
        lat, lon = GP.tm5179_to_wgs84(1_000_000, 2_000_000)
        self.assertAlmostEqual(lat, 38.0, places=6)
        self.assertAlmostEqual(lon, 127.5, places=6)

    def test_실제_응답의_종로구_대표점이_종로구가_된다(self):
        """properties {"x":"953858","y":"1955185"} — 실제로 받은 값."""
        lat, lon = GP.tm5179_to_wgs84(953858, 1955185)
        self.assertAlmostEqual(lat, 37.595, places=2)
        self.assertAlmostEqual(lon, 126.977, places=2)

    def test_사각형_넓이가_미터제곱이다(self):
        """EPSG:5179 는 미터 좌표계라 구두끈 넓이가 그대로 m² 다."""
        사각 = {"type": "Polygon", "coordinates": [[
            [0, 0], [1000, 0], [1000, 2000], [0, 2000], [0, 0]]]}
        self.assertAlmostEqual(GP.geom_area_m2(사각), 2_000_000.0)

    def test_구멍은_뺀다(self):
        구멍 = {"type": "Polygon", "coordinates": [
            [[0, 0], [1000, 0], [1000, 1000], [0, 1000], [0, 0]],
            [[100, 100], [200, 100], [200, 200], [100, 200], [100, 100]]]}
        self.assertAlmostEqual(GP.geom_area_m2(구멍), 1_000_000.0 - 10_000.0)

    def test_감는_방향이_반대여도_같은_넓이다(self):
        시계 = {"type": "Polygon", "coordinates": [[
            [0, 0], [0, 1000], [1000, 1000], [1000, 0], [0, 0]]]}
        self.assertAlmostEqual(GP.geom_area_m2(시계), 1_000_000.0)

    def test_경계에서_면적과_중심점이_나온다(self):
        feats = [{"type": "Feature",
                  "geometry": {"type": "Polygon", "coordinates": [[
                      [953000, 1954000], [954000, 1954000],
                      [954000, 1956000], [953000, 1956000], [953000, 1954000]]]},
                  "properties": {"x": "953858", "y": "1955185",
                                 "adm_cd": "11010", "adm_nm": "서울특별시 종로구"}}]
        areas, 문제 = GP.areas_from_boundary(feats)
        self.assertEqual(문제, [])
        a = areas["11010"]
        self.assertAlmostEqual(a["면적_m2"], 2_000_000.0)
        self.assertAlmostEqual(a["위도"], 37.595, places=2)
        self.assertAlmostEqual(a["경도"], 126.977, places=2)
        self.assertLess(abs(a["위도"]), 90, "미터 좌표가 위도 칸에 그대로 들어갔다")

    def test_중심점이_없으면_도형에서_구한다(self):
        feats = [{"geometry": {"type": "Polygon", "coordinates": [[
            [953000, 1954000], [954000, 1954000],
            [954000, 1956000], [953000, 1956000], [953000, 1954000]]]},
            "properties": {"adm_cd": "11010"}}]
        areas, 문제 = GP.areas_from_boundary(feats)
        self.assertEqual(문제, [])
        self.assertAlmostEqual(areas["11010"]["위도"], 37.6, places=1)

    def test_면적이_없으면_지어내지_않는다(self):
        feats = [{"geometry": {"type": "Point", "coordinates": [953858, 1955185]},
                  "properties": {"adm_cd": "11010", "adm_nm": "종로구",
                                 "x": "953858", "y": "1955185"}}]
        areas, 문제 = GP.areas_from_boundary(feats)
        self.assertEqual(areas, {})
        self.assertTrue(문제)


class TestSgisLiveRun(unittest.TestCase):
    """--areas 를 손으로 채우지 않아도 도는가, 그리고 그 값이 M2 까지 맞게 가는가."""

    def setUp(self):
        import os
        self.tmp = Path(tempfile.mkdtemp(prefix="sgis-"))
        self.원래 = urllib.request.urlopen
        self.키 = {k: os.environ.get(k) for k in ("SGIS_KEY", "SGIS_SECRET")}
        os.environ["SGIS_KEY"] = "K"
        os.environ["SGIS_SECRET"] = "S"

        구 = {"adm_cd": "11040", "adm_nm": "성동구",
             "household_cnt": "134000", "tot_worker": "198800"}

        class R:
            def __init__(s, b):
                s._b = b.encode()
                s.status = 200
            def read(s):
                return s._b
            def __enter__(s):
                return s
            def __exit__(s, *a):
                return False

        def fake(url, timeout=None, context=None):
            q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")
                     if "=" in p)
            if "auth" in url:
                return R(json.dumps({"errCd": 0, "result": {"accessToken": "T"}}))
            adm, low = q.get("adm_cd", ""), q.get("low_search", "0")
            if "boundary" in url:
                return R(json.dumps({"type": "FeatureCollection", "errCd": 0,
                    "features": [{"geometry": {"type": "Polygon", "coordinates": [[
                        [957000, 1951000], [961000, 1951000],
                        [961000, 1955000], [957000, 1955000], [957000, 1951000]]]},
                        "properties": {"x": "959000", "y": "1953000",
                                       "adm_cd": "11040", "adm_nm": "성동구"}}]},
                    ensure_ascii=False))
            if adm == "11" and low == "0":
                return R(json.dumps({"errCd": 0, "result": [
                    {"adm_cd": "11", "adm_nm": "서울특별시"}]}, ensure_ascii=False))
            if adm == "11":
                return R(json.dumps({"errCd": 0, "result": [구]},
                                    ensure_ascii=False))
            if adm == "11040":
                return R(json.dumps({"errCd": 0, "result": [구]},
                                    ensure_ascii=False))
            return R(json.dumps({"errCd": "-100", "errMsg": "없는 코드"},
                                ensure_ascii=False))

        urllib.request.urlopen = fake

        import csv
        self.sites = self.tmp / "sites.csv"
        with self.sites.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["후보지명", "주소", "법정동코드",
                                              "위도", "경도"])
            w.writeheader()
            w.writerow({"후보지명": "왕십리", "주소": "서울 성동구 왕십리로 222",
                        "법정동코드": "1120010800",
                        "위도": "37.561", "경도": "127.037"})

    def tearDown(self):
        import os
        urllib.request.urlopen = self.원래
        for k, v in self.키.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def 실행(self, extra=()):
        out = self.tmp / "격자인구.csv"
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.main(["--live", "--sites", str(self.sites),
                          "--out", str(out)] + list(extra))
        finally:
            sys.stdout = old
        return rc, out, buf.getvalue()

    def test_areas_없이도_돈다(self):
        """경계 API 가 면적·중심점을 주므로 손작업이 없다."""
        rc, out, 말 = self.실행()
        self.assertEqual(rc, 0, 말)
        rows = read_csv(out)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["격자ID"], "SGIS:11040")
        self.assertAlmostEqual(float(rows[0]["세대수"]), 134000.0)
        self.assertAlmostEqual(float(rows[0]["직장인구"]), 198800.0)

    def test_중심점이_한반도_안에_있다(self):
        rc, out, 말 = self.실행()
        r = read_csv(out)[0]
        self.assertTrue(33 < float(r["중심위도"]) < 39, r["중심위도"])
        self.assertTrue(124 < float(r["중심경도"]) < 132, r["중심경도"])

    def test_만든_면적표를_파일로_남긴다(self):
        """다음 실행과 통신사 유동인구 쪽에서 같이 쓴다."""
        rc, out, 말 = self.실행()
        표 = out.parent / "행정구역.csv"
        self.assertTrue(표.exists(), 말)
        self.assertEqual(read_csv(표)[0]["구역코드"], "11040")

    def test_법정동코드를_그대로_부르지_않는다(self):
        """11200 을 불렀다면 그건 동작구다."""
        rc, out, 말 = self.실행()
        self.assertIn("11040", 말)
        self.assertNotIn("SGIS:11200", (out.read_text(encoding="utf-8-sig")))

    def test_dry_run_은_인구를_지어내지_않는다(self):
        out = self.tmp / "dry.csv"
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.main(["--sites", str(self.sites), "--out", str(out)])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        self.assertEqual(read_csv(out), [])


class TestRealSeoulResponse(unittest.TestCase):
    """실제 SGIS 응답(2026-08, 서울 25개 구)으로 전 구간을 돌린다.

    fixtures/sgis_seoul.json 은 받은 값을 손대지 않고 옮긴 것이다. 여기서 지키는 것:

      · 25개 구 중심점이 실제 서울 위치로 돌아오는가 (UTM-K → 위경도)
      · 후보지가 자기 구의 인구를 받는가 (법정동코드 앞자리를 쓰면 남의 구가 온다)
      · 도형이 MultiPolygon 이어도 면적이 나오는가 — 양천구·구로구가 그렇다
      · 경계와 통계의 이름 표기가 달라도('서울특별시 종로구' vs '종로구') 이어지는가

    ⚠ 다각형 좌표까지는 옮기지 않았다(응답 하나가 수십만 자다). 도형은 실제 응답과
      같은 **종류**로 두고 넓이 계산 자체는 위의 단위 테스트가 지킨다.
    """

    실제 = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "sgis_seoul.json")
        .read_text(encoding="utf-8"))

    # 실제로 아는 위치. 변환이 틀어지면 여기서 걸린다.
    아는곳 = {"종로구": (37.595, 126.977), "강남구": (37.497, 127.063),
            "도봉구": (37.669, 127.032), "금천구": (37.461, 126.901)}

    def 구들(self):
        return self.실제["구"]

    def test_25개_구_중심점이_서울_안에_있다(self):
        for g in self.구들():
            lat, lon = GP.tm5179_to_wgs84(float(g["x"]), float(g["y"]))
            with self.subTest(구=g["adm_nm"]):
                self.assertTrue(37.42 < lat < 37.72, f"{g['adm_nm']} 위도 {lat}")
                self.assertTrue(126.76 < lon < 127.20, f"{g['adm_nm']} 경도 {lon}")

    def test_아는_구가_아는_자리에_온다(self):
        by = {g["adm_nm"]: g for g in self.구들()}
        for 이름, (알lat, 알lon) in self.아는곳.items():
            lat, lon = GP.tm5179_to_wgs84(float(by[이름]["x"]), float(by[이름]["y"]))
            with self.subTest(구=이름):
                self.assertAlmostEqual(lat, 알lat, places=2)
                self.assertAlmostEqual(lon, 알lon, places=2)

    def test_서울의_모양이_보존된다(self):
        """도봉이 북쪽, 금천이 남쪽, 강동이 동쪽, 강서가 서쪽. 축이 뒤집히면 걸린다."""
        pt = {g["adm_nm"]: GP.tm5179_to_wgs84(float(g["x"]), float(g["y"]))
              for g in self.구들()}
        self.assertEqual(max(pt, key=lambda k: pt[k][0]), "도봉구")
        self.assertEqual(min(pt, key=lambda k: pt[k][0]), "금천구")
        self.assertEqual(max(pt, key=lambda k: pt[k][1]), "강동구")
        self.assertEqual(min(pt, key=lambda k: pt[k][1]), "강서구")

    def test_이름이_25개_구_안에서_하나로_갈린다(self):
        """'중구' 가 '중랑구'·'동대문구' 를 함께 물면 엉뚱한 구를 받는다."""
        for g in self.구들():
            맞은 = [h for h in self.구들()
                  if GP.이름맞나(h["adm_nm"], g["adm_nm"])]
            with self.subTest(구=g["adm_nm"]):
                self.assertEqual([h["adm_cd"] for h in 맞은], [g["adm_cd"]])

    def test_경계_표기가_달라도_같은_구로_읽힌다(self):
        """경계는 '서울특별시 종로구', 통계는 '종로구' 로 온다."""
        self.assertTrue(GP.이름맞나("서울특별시 종로구", "종로구"))
        self.assertFalse(GP.이름맞나("서울특별시 종로구", "중구"))

    def test_MultiPolygon_면적이_합쳐진다(self):
        """양천구·구로구가 실제로 MultiPolygon 으로 온다."""
        self.assertEqual(self.실제["_도형종류"]["11150"], "MultiPolygon")
        멀티 = {"type": "MultiPolygon", "coordinates": [
            [[[0, 0], [1000, 0], [1000, 1000], [0, 1000], [0, 0]]],
            [[[2000, 0], [2500, 0], [2500, 1000], [2000, 1000], [2000, 0]]]]}
        self.assertAlmostEqual(GP.geom_area_m2(멀티), 1_000_000.0 + 500_000.0)

    def test_되짚어_나온_목이_면적을_깎지_않는다(self):
        """구로구 경계에는 같은 점을 두 번 지나는 좁은 목이 있다. 왕복하는 변은
        서로 지워져 0 이어야지, 음수가 되어 본체 면적을 깎으면 안 된다."""
        목있음 = {"type": "Polygon", "coordinates": [[
            [0, 0], [1000, 0], [1000, 1000],
            [500, 1000], [500, 1500], [500, 1000],   # 왕복하는 목
            [0, 1000], [0, 0]]]}
        self.assertAlmostEqual(GP.geom_area_m2(목있음), 1_000_000.0)

    def test_후보지가_자기_구의_인구를_받는다(self):
        """전 구간. 성동구 후보지에 성동구 값(세대 123124 · 종사자 198800)이 와야 한다.
        법정동코드 앞자리(11200)를 쓰면 동작구 값(173897 · 104719)이 온다."""
        import csv, os, tempfile
        구 = {g["adm_cd"]: g for g in self.구들()}

        class R:
            def __init__(s, b):
                s._b = b.encode(); s.status = 200
            def read(s): return s._b
            def __enter__(s): return s
            def __exit__(s, *a): return False

        def fake(url, timeout=None, context=None):
            q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")
                     if "=" in p)
            if "auth" in url:
                return R(json.dumps({"errCd": 0, "result": {"accessToken": "T"}}))
            adm, low = q.get("adm_cd", ""), q.get("low_search", "0")
            뽑기 = ([구[adm]] if adm in 구
                  else list(구.values()) if adm == "11" and low == "1" else [])
            if "boundary" in url:
                # 실제 응답과 같은 자리에 중심점을 두고, 도형은 그 둘레의 사각형
                feats = []
                for g in 뽑기:
                    x, y = float(g["x"]), float(g["y"])
                    feats.append({"type": "Feature", "geometry": {
                        "type": "Polygon", "coordinates": [[
                            [x - 2000, y - 2000], [x + 2000, y - 2000],
                            [x + 2000, y + 2000], [x - 2000, y + 2000],
                            [x - 2000, y - 2000]]]},
                        "properties": {"x": g["x"], "y": g["y"],
                                       "adm_cd": g["adm_cd"],
                                       "adm_nm": "서울특별시 " + g["adm_nm"]}})
                return R(json.dumps({"type": "FeatureCollection", "errCd": 0,
                                     "features": feats}, ensure_ascii=False))
            if adm == "11" and low == "0":
                return R(json.dumps({"errCd": 0, "result": [
                    {"adm_cd": "11", "adm_nm": "서울특별시"}]}, ensure_ascii=False))
            if 뽑기:
                return R(json.dumps({"errCd": 0, "result": 뽑기},
                                    ensure_ascii=False))
            return R(json.dumps({"errCd": "-100", "errMsg": "없는 코드"},
                                ensure_ascii=False))

        tmp = Path(tempfile.mkdtemp(prefix="seoul-"))
        sites = tmp / "sites.csv"
        with sites.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["후보지명", "주소", "법정동코드"])
            w.writeheader()
            w.writerow({"후보지명": "왕십리", "주소": "서울 성동구 왕십리로 222",
                        "법정동코드": "1120010800"})
            w.writerow({"후보지명": "역삼", "주소": "서울 강남구 테헤란로 152",
                        "법정동코드": "1168010100"})

        원래, 키 = urllib.request.urlopen, dict(os.environ)
        urllib.request.urlopen = fake
        os.environ["SGIS_KEY"], os.environ["SGIS_SECRET"] = "K", "S"
        out = tmp / "격자인구.csv"
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.main(["--live", "--sites", str(sites), "--out", str(out)])
        finally:
            sys.stdout, urllib.request.urlopen = old, 원래
            os.environ.clear(); os.environ.update(키)
        말 = buf.getvalue()
        self.assertEqual(rc, 0, 말)

        rows = {r["격자ID"]: r for r in read_csv(out)}
        self.assertEqual(sorted(rows), ["SGIS:11040", "SGIS:11230"], 말)
        성동 = rows["SGIS:11040"]
        self.assertAlmostEqual(float(성동["세대수"]), 123124.0)
        self.assertAlmostEqual(float(성동["직장인구"]), 198800.0)
        # 동작구(SGIS 11200) 값이 들어왔다면 법정동코드를 그대로 쓴 것이다
        self.assertNotAlmostEqual(float(성동["세대수"]), 173897.0)
        강남 = rows["SGIS:11230"]
        self.assertAlmostEqual(float(강남["세대수"]), 218895.0)
        self.assertAlmostEqual(float(강남["직장인구"]), 769609.0)
        self.assertAlmostEqual(float(성동["중심위도"]), 37.551, places=2)
        self.assertAlmostEqual(float(강남["중심경도"]), 127.063, places=2)


class TestAddressSplit(unittest.TestCase):
    """주소에서 시도·시군구를 읽는다. 여기서 헛이름을 만들면 헛호출이 늘고,
    무엇을 찾다 실패했는지도 흐려진다."""

    def test_한_토막_시군구(self):
        self.assertEqual(GP.주소쪼개기("서울 성동구 왕십리로 222"),
                         ("서울", ["성동구"]))

    def test_도로명을_시군구에_붙이지_않는다(self):
        """'강남구강남대로' 같은 이름은 어디에도 없다."""
        시도, 후보 = GP.주소쪼개기("서울 강남구 강남대로 152")
        self.assertEqual(후보, ["강남구"])

    def test_두_토막_시군구는_붙인다(self):
        """SGIS 는 '성남시분당구' 로 쓴다."""
        self.assertEqual(GP.주소쪼개기("경기 성남시 분당구 판교로 1"),
                         ("경기", ["성남시분당구", "성남시"]))

    def test_군도_붙인다(self):
        self.assertEqual(GP.주소쪼개기("경북 포항시 남구 대이로")[1],
                         ["포항시남구", "포항시"])

    def test_정식_시도명을_줄인다(self):
        self.assertEqual(GP.주소쪼개기("서울특별시 종로구 세종대로")[0], "서울")
        self.assertEqual(GP.주소쪼개기("강원특별자치도 춘천시 중앙로")[0], "강원")
        self.assertEqual(GP.주소쪼개기("전북특별자치도 전주시 완산구 팔달로")[0], "전북")

    def test_빈_주소는_빈_손으로_돌아온다(self):
        self.assertEqual(GP.주소쪼개기(""), ("", []))
        self.assertEqual(GP.주소쪼개기("서울"), ("서울", []))


class TestMakeAreasLive(unittest.TestCase):
    """--areas 표를 SGIS 경계에서 채워 낸다.

    이 표는 격자인구(H·W)와 통신사 유동인구(D_am)가 **같이** 쓴다. 지금까지 유동인구
    쪽은 이 표를 사람이 채워야 했고, 그게 전국으로 갈 때 남은 마지막 손작업이었다.
    """

    def setUp(self):
        import csv, os, tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="areas-"))
        self.원래 = urllib.request.urlopen
        self.키 = dict(os.environ)
        os.environ["SGIS_KEY"], os.environ["SGIS_SECRET"] = "K", "S"
        self.부른것 = []

        class R:
            def __init__(s, b):
                s._b = b.encode(); s.status = 200
            def read(s): return s._b
            def __enter__(s): return s
            def __exit__(s, *a): return False

        def 사각(x, y, 반, code, nm):
            return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[
                [x - 반, y - 반], [x + 반, y - 반], [x + 반, y + 반],
                [x - 반, y + 반], [x - 반, y - 반]]]},
                "properties": {"x": str(x), "y": str(y),
                               "adm_cd": code, "adm_nm": nm}}

        def fake(url, timeout=None, context=None):
            self.부른것.append(url)
            q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")
                     if "=" in p)
            if "auth" in url:
                return R(json.dumps({"errCd": 0, "result": {"accessToken": "T"}}))
            adm = q.get("adm_cd", "")
            if "jagurodarea" in url:
                # 집계구 — 훨씬 잘다
                feats = [사각(959458 + i * 400, 1950284, 150,
                            f"1104053{i:02d}", f"성동구 집계구{i}") for i in range(4)]
                return R(json.dumps({"type": "FeatureCollection", "errCd": 0,
                                     "features": feats}, ensure_ascii=False))
            if "hadmarea" in url:
                return R(json.dumps({"type": "FeatureCollection", "errCd": 0,
                                     "features": [사각(959458, 1950284, 2000,
                                                     "11040", "서울특별시 성동구")]},
                                    ensure_ascii=False))
            if adm == "11" and q.get("low_search") == "0":
                return R(json.dumps({"errCd": 0, "result": [
                    {"adm_cd": "11", "adm_nm": "서울특별시"}]}, ensure_ascii=False))
            if adm == "11":
                return R(json.dumps({"errCd": 0, "result": [
                    {"adm_cd": "11040", "adm_nm": "성동구",
                     "household_cnt": "123124"}]}, ensure_ascii=False))
            return R(json.dumps({"errCd": "-100", "errMsg": "없는 코드"},
                                ensure_ascii=False))

        urllib.request.urlopen = fake
        self.sites = self.tmp / "sites.csv"
        with self.sites.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["후보지명", "주소", "법정동코드"])
            w.writeheader()
            w.writerow({"후보지명": "왕십리", "주소": "서울 성동구 왕십리로 222",
                        "법정동코드": "1120010800"})

    def tearDown(self):
        import os
        urllib.request.urlopen = self.원래
        os.environ.clear(); os.environ.update(self.키)

    def 실행(self, extra=()):
        out = self.tmp / "행정구역.csv"
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc = GP.main(["--make-areas", "--sites", str(self.sites),
                          "--areas", str(out)] + list(extra))
        finally:
            sys.stdout = old
        return rc, out, buf.getvalue()

    def test_라이브면_면적과_좌표까지_채운다(self):
        rc, out, 말 = self.실행(["--live"])
        self.assertEqual(rc, 0, 말)
        r = read_csv(out)[0]
        self.assertEqual(r["구역코드"], "11040")
        self.assertAlmostEqual(float(r["면적_m2"]), 4000.0 ** 2, delta=1)
        self.assertAlmostEqual(float(r["위도"]), 37.551, places=2)
        self.assertAlmostEqual(float(r["경도"]), 127.041, places=2)

    def test_라이브가_아니면_비워_둔다(self):
        """키 없이 부르면 지어내지 않는다. 뼈대만 낸다."""
        rc, out, 말 = self.실행()
        self.assertEqual(rc, 0, 말)
        r = read_csv(out)[0]
        self.assertEqual(r["면적_m2"], "")
        self.assertEqual(r["위도"], "")

    def test_만든_표를_두_도구가_같이_읽는다(self):
        """유동인구(collect_carrier_flow)와 격자인구가 같은 load_areas 를 쓴다."""
        import collect_carrier_flow as CF
        rc, out, 말 = self.실행(["--live"])
        areas = CF.load_areas(out)
        self.assertIn("11040", areas)
        self.assertGreater(areas["11040"]["면적_m2"], 0)
        self.assertGreater(areas["11040"]["위도"], 37)

    def test_집계구는_행정동보다_잘게_온다(self):
        """유동인구에 쓸 표. P5(도보 5분)는 0.35km² 안팎이라 행정동은 대부분 버려진다."""
        rc, 잔것, 말 = self.실행(["--live", "--level", "집계구"])
        self.assertEqual(rc, 0, 말)
        self.assertTrue(any("jagurodarea" in u for u in self.부른것), self.부른것)
        rows = read_csv(잔것)
        self.assertEqual(len(rows), 4)
        for r in rows:
            self.assertLess(float(r["면적_m2"]), 350_000)

    def test_행정동_표에는_집계구를_권한다(self):
        """유동인구에 그대로 쓰면 대부분 버려지는데, 그걸 말해 주지 않으면
        '유동이 없는 자리' 로 읽힌다."""
        rc, out, 말 = self.실행(["--live"])
        self.assertIn("집계구", 말)
        self.assertIn("P5", 말)

    def test_확인되지_않은_단계는_그렇다고_말한다(self):
        """집계구 경계 주소는 실제 호출로 확인하지 못했다. 되는 척하지 않는다."""
        self.assertEqual(GP.BOUNDARY["집계구"][1], "미확인")
        self.assertEqual(GP.BOUNDARY["행정동"][1].split()[0], "확인됨")
