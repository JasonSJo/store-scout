#!/usr/bin/env python3
"""
위치 모듈 — 좌표 파서·이름 제안·외부 링크

입력 페이지는 주소를 골라 좌표를 채운다. 좌표가 어긋나면 상권이 통째로 다른 곳에
잡히므로, 파서가 한국 범위 밖 값이나 순서가 뒤바뀐 입력을 어떻게 다루는지 고정한다.
외부 링크는 네트워크를 타지 않고 형식만 본다(각 서비스가 URL 을 바꿀 수 있다).

node 가 없으면 건너뛴다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DUMP = Path(__file__).resolve().parent / "place_dump.js"
ADDR = "서울 성동구 연무장길 42"


class TestPlace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 위치 모듈 검사를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"place_dump.js 실패:\n{p.stderr}")
        cls.d = json.loads(p.stdout)
        cls.coords = {c["입력"]: c["결과"] for c in cls.d["coords"]}
        cls.검색 = {c["사례"]: c for c in cls.d["검색"]}

    def test_좌표를_읽는다(self):
        want = {"위도": 37.5445, "경도": 127.0557}
        for text in ("37.5445, 127.0557", "위도 37.5445 경도 127.0557", "37.5445\t127.0557"):
            with self.subTest(입력=text):
                self.assertEqual(self.coords[text], want)

    def test_순서가_뒤바뀌어도_받는다(self):
        """지도마다 경도를 먼저 주는 곳이 있다. 한국 범위로 판별해 바로잡는다."""
        self.assertEqual(self.coords["127.0557, 37.5445"],
                         {"위도": 37.5445, "경도": 127.0557})

    def test_좌표가_아니면_거절한다(self):
        """엉뚱한 값을 조용히 통과시키면 상권이 다른 곳에 잡힌다."""
        for text in ("서울시", "1, 2", "", "37.5445"):
            with self.subTest(입력=text):
                self.assertIsNone(self.coords[text])

    def test_이름을_제안한다(self):
        got = {json.dumps(n["입력"], ensure_ascii=False): n["결과"] for n in self.d["names"]}
        self.assertEqual(got[json.dumps({"이름": "스타벅스 성수점", "주소": ADDR}, ensure_ascii=False)],
                         "스타벅스 성수점")
        # 건물·상호가 없으면 주소 뒤쪽 세 토막으로 줄인다
        self.assertEqual(got[json.dumps({"이름": "", "주소": ADDR}, ensure_ascii=False)],
                         "성동구 연무장길 42")
        self.assertEqual(got[json.dumps({"이름": "", "주소": "서울 성동구"}, ensure_ascii=False)],
                         "서울 성동구")

    def test_네_곳_모두_링크한다(self):
        self.assertEqual(self.d["서비스"],
                         ["네이버지도", "네이버 부동산", "호갱노노", "일사편리"])
        self.assertEqual(len(self.d["링크"]), 4)

    def test_링크가_https_이고_주소를_인코딩한다(self):
        enc = quote(ADDR, safe="")
        for l in self.d["링크"]:
            with self.subTest(서비스=l["이름"]):
                u = urlparse(l["href"])
                self.assertEqual(u.scheme, "https", "외부 링크는 https 여야 합니다")
                self.assertTrue(u.netloc, l["href"])
                # 검색 URL 이면 주소가 인코딩되어 들어가야 한다(일사편리는 검색 파라미터가 없다)
                if l["이름"] != "일사편리":
                    self.assertIn(enc, l["href"].replace("%20", "%20"))

    def test_법정동코드에서_실거래가_지역코드를_뽑는다(self):
        """국토교통부 실거래가 API 는 법정동코드 앞 5자리를 지역코드(LAWD_CD)로 받는다.
        10자리를 그대로 넣으면 조회되지 않는다."""
        got = {x["입력"]: x["결과"] for x in self.d["lawd"]}
        self.assertEqual(got["1114010300"], "11140")
        self.assertEqual(got["11140"], "11140")
        for bad in ("", "abc", "111"):
            with self.subTest(입력=bad):
                self.assertEqual(got[bad], "")

    def test_주소가_없으면_링크를_만들지_않는다(self):
        """빈 주소로 검색 URL 을 열면 엉뚱한 페이지로 보낸다."""
        self.assertEqual(self.d["링크_주소없음"], [])


class TestSearchFailures(unittest.TestCase):
    """검색 실패를 '결과 없음' 과 구분하는가.

    카카오 JS 키는 **도메인을 등록해야** 동작한다. 등록하지 않으면 SDK 는 스크립트를
    잘 내려 주고 검색 콜백만 ERROR 로 돌아온다. 그것을 '결과가 없습니다' 로 보여 주면
    사람은 주소가 틀린 줄 알고 주소만 계속 고쳐 본다 — 설정 문제인데 데이터 문제로
    읽힌다. 이 검사가 그 구분을 고정한다.

    실제 카카오에 붙지 않는다(가짜 SDK). 보려는 것은 통신이 아니라 분기다.
    """

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 위치 모듈 검사를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"place_dump.js 실패:\n{p.stderr}")
        cls.검색 = {c["사례"]: c for c in json.loads(p.stdout)["검색"]}

    def test_주소_결과가_장소보다_앞이다(self):
        """후보지는 '그 자리'가 기준이지 상호가 기준이 아니다."""
        got = self.검색["둘 다 성공"]
        self.assertEqual(got["출처"], ["주소", "장소"])
        self.assertEqual(got["첫결과"]["법정동코드"], "1120011400")
        self.assertEqual(got["첫결과"]["위도"], 37.5445)

    def test_결과가_없으면_빈_목록이지_오류가_아니다(self):
        got = self.검색["둘 다 없음"]
        self.assertEqual(got["결과"], "ok")
        self.assertEqual(got["건수"], 0)

    def test_키나_도메인_문제는_결과_없음으로_숨기지_않는다(self):
        got = self.검색["키/도메인 오류"]
        self.assertEqual(got["결과"], "실패")
        # 무엇을 해야 하는지가 메시지에 있어야 한다
        self.assertIn("도메인", got["메시지"])
        self.assertIn("플랫폼", got["메시지"])

    def test_장소_검색만_실패하면_주소_결과는_살린다(self):
        """주소만으로도 후보지 등록은 된다. 한쪽 실패로 전부 버리지 않는다."""
        got = self.검색["장소만 오류 — 주소는 살린다"]
        self.assertEqual(got["결과"], "ok")
        self.assertEqual(got["출처"], ["주소"])

    def test_주소만_없을_때는_장소_결과로_잇는다(self):
        got = self.검색["주소만 없음"]
        self.assertEqual(got["결과"], "ok")
        self.assertEqual(got["출처"], ["장소"])
        # 장소 검색은 우편번호·법정동코드를 주지 않는다 — 지어내지 않고 비워 둔다
        self.assertEqual(got["첫결과"]["우편번호"], "")
        self.assertEqual(got["첫결과"]["법정동코드"], "")


class TestSearchTimeout(unittest.TestCase):
    """콜백이 끝내 오지 않으면 화면이 '찾는 중…' 에서 영원히 멈춘다."""

    def test_시한이_걸려_있다(self):
        src = (Path(__file__).resolve().parents[2] / "input" / "js" / "place.js") \
            .read_text(encoding="utf-8")
        self.assertIn("TIMEOUT_MS", src)
        self.assertIn("setTimeout", src)
        self.assertIn("clearTimeout", src)   # 성공했는데 뒤늦게 거절하지 않는다


class TestMapAndReverse(unittest.TestCase):
    """지도와 역지오코딩 — 좌표를 눈으로 확인하고 손으로 바로잡는 경로.

    좌표 두 줄만 봐서는 그 자리가 맞는지 사람이 판단할 수 없다. 검색이 엉뚱한 곳을
    짚어도 알아챌 방법이 없었다. 가짜 SDK 로 배선만 검사한다 — 실제 카카오에 붙지
    않는다.
    """

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node 가 없어 위치 모듈 검사를 건너뜁니다")
        p = subprocess.run(["node", str(DUMP)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise AssertionError(f"place_dump.js 실패:\n{p.stderr}")
        d = json.loads(p.stdout)
        cls.역 = {c["사례"]: c for c in d["역"]}
        cls.지도 = d["지도"]

    def test_카카오는_경도를_먼저_받는다(self):
        """순서를 바꿔 넣으면 오류도 없이 엉뚱한 곳이 나온다 — 가장 조용한 종류의 버그다."""
        호출 = self.역["둘 다 성공"]["호출"]
        for 이름, c in 호출.items():
            with self.subTest(호출=이름):
                self.assertEqual(c["x"], 127.0557, "x 는 경도여야 합니다")
                self.assertEqual(c["y"], 37.5445, "y 는 위도여야 합니다")

    def test_법정동코드를_고른다(self):
        """행정동(H)과 법정동(B)이 함께 온다. 실거래가 지역코드는 **법정동**에서 나온다."""
        got = self.역["둘 다 성공"]["결과"]
        self.assertEqual(got["법정동코드"], "1121510300")
        self.assertEqual(got["우편번호"], "04998")

    def test_한쪽이_실패해도_다른_쪽은_살린다(self):
        """주소와 법정동코드는 다른 호출이다. 한쪽 실패로 전부 버리지 않는다."""
        주소실패 = self.역["주소만 실패"]["결과"]
        self.assertEqual(주소실패["주소"], "")
        self.assertEqual(주소실패["법정동코드"], "1121510300")
        코드실패 = self.역["코드만 실패"]["결과"]
        self.assertTrue(코드실패["주소"])
        self.assertEqual(코드실패["법정동코드"], "")

    def test_마커를_끌_수_있고_옮긴_좌표를_알려_준다(self):
        self.assertTrue(self.지도["끌수있음"], "마커가 draggable 이 아닙니다")
        self.assertEqual(self.지도["마커끌기"], {"위도": 37.54, "경도": 127.09})

    def test_지도를_정리한다(self):
        """화면을 다시 그릴 때마다 지도 인스턴스가 쌓이면 안 된다."""
        self.assertTrue(self.지도["정리됨"])


class TestMapWiring(unittest.TestCase):
    """옮긴 좌표가 주소를 조용히 갈아 끼우지 않는가."""

    def test_주소는_사람이_누를_때만_바뀐다(self):
        """주소·우편번호·법정동코드는 그 자리의 신원이고 실거래가 지역코드까지 이어진다.
        마커를 끌었다고 자동으로 바꾸면, 사람이 모르는 사이에 다른 동의 시세와
        대조하게 된다."""
        src = (Path(__file__).resolve().parents[2] / "input" / "js" / "app.js") \
            .read_text(encoding="utf-8")
        # dragend 처리에서 바꾸는 것은 좌표뿐
        블록 = src.split("PLACE.showMap(", 1)[1].split("}).then(", 1)[0]
        self.assertIn("s3.위도", 블록)
        self.assertIn("s3.경도", 블록)
        for 신원 in ("s3.주소", "s3.우편번호", "s3.법정동코드"):
            self.assertNotIn(신원, 블록, f"{신원} 를 끌기만 해도 바꾸고 있습니다")
        # 대신 사람이 누르는 버튼이 있어야 한다
        self.assertIn("driftok", src)
        self.assertIn("주소도 이 자리로 바꾸기", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
