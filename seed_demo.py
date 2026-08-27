#!/usr/bin/env python3
"""
데모 조직·계정 생성. 개발용이며 운영에서는 관리자가 계정을 만든다.

기존점도 함께 넣는다 — 넣지 않으면 온보딩이 끝나지 않아 심의를 돌릴 수 없고,
화면을 열어 볼 수는 있어도 제품이 실제로 도는 모습은 못 본다.

여기 매출은 **꾸며 낸 숫자**다. 점포명에 '데모' 를 박아 두는 이유가 그것이다.
실제 조직에 이 파일을 돌리지 마십시오 — 남의 브랜드 실적으로 판정이 나간다.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import auth, consults, db, orgdata

db.DB_PATH = Path(os.environ.get("STORE_SCOUT_DB", "store-scout.sqlite3"))
db.DB_PATH.unlink(missing_ok=True)
db.init()

# 점포명 · 위도 · 경도 · 기준점포 · 월매출(만원) · 좌석수 · 전용면적(평) · 월임대료(만원)
데모기존점 = [
    ("데모 1호점", 37.5045, 127.0490, "Y", 3450, 28, 22.0, 320),
    ("데모 2호점", 37.4979, 127.0276, "N", 2980, 24, 19.5, 290),
    ("데모 3호점", 37.5172, 127.0473, "N", 4120, 34, 27.0, 410),
    ("데모 4호점", 37.4835, 126.9895, "N", 2540, 20, 17.0, 240),
]

with db.tx() as con:
    org = con.execute("INSERT INTO orgs (name, brand, plan) VALUES (?,?,?)",
                      ("카페하다 본부(데모)", "카페하다", "team")).lastrowid
    for email, name, role in [("ops@cafehada.kr", "김운영", "운영"),
                              ("sales@cafehada.kr", "박영업", "영업"),
                              ("admin@cafehada.kr", "이관리", "관리자")]:
        con.execute("INSERT INTO users (org_id,email,name,role,pw_hash) VALUES (?,?,?,?,?)",
                    (org, email, name, role, auth.hash_pw("demo-1234")))

    orgdata.save_settings(con, org, orgdata.merge(
        orgdata.기본설정, {"브랜드": "카페하다", "자사브랜드티어": "동일가격대"}))

    for 점포, lat, lon, 기준, 매출, 좌석, 면적, 임대 in 데모기존점:
        con.execute(
            "INSERT INTO stores (org_id,점포명,위도,경도,기준점포,월매출_만원,좌석수,"
            "전용면적_평,월임대료_만원) VALUES (?,?,?,?,?,?,?,?,?)",
            (org, 점포, lat, lon, 기준, 매출, 좌석, 면적, 임대))

    # 데모 상담 하나. 이름·번호 모두 실재하지 않는 값이다(번호는 0000-0000).
    con.execute(
        "INSERT INTO consults (org_id,고객명,고객전화번호,거주지,근무지,동의,희망지역,"
        "희망평수,희망상권,보증금_만원,권리금_만원,투자금형태,운영형태,메모,created_by)"
        " VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,?,?)",
        (org, "데모 고객", "010-0000-0000", "서울 강남구", "서울 중구",
         "강남, 성수, 홍대", 20, "오피스, 메인", 9000, 9000,
         "현금+대출", "오토", "데모 상담 기록 — 실재하지 않는 사람입니다", 1))

    준비 = orgdata.readiness(con, org)

print(f"조직 {org} · 계정 3개 (비밀번호 demo-1234) → {db.DB_PATH}")
print(f"기존점 {준비['기존점']}곳 · 매출 추정 모드 {준비['모드']} · "
      f"심의 실행 {'가능' if 준비['준비됨'] else '불가'}")
print("상담 1건(데모 고객 — 실재하지 않는 사람)")
print("※ 기존점 매출은 꾸며 낸 데모 값입니다. 실제 판단에 쓰지 마십시오.")
