#!/usr/bin/env python3
"""데모 조직·계정 생성. 개발용이며 운영에서는 관리자가 계정을 만든다."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import auth, db

db.DB_PATH = Path(os.environ.get("STORE_SCOUT_DB", "store-scout.sqlite3"))
db.DB_PATH.unlink(missing_ok=True)
db.init()
with db.tx() as con:
    org = con.execute("INSERT INTO orgs (name, brand, plan) VALUES (?,?,?)",
                      ("카페하다 본부", "카페하다", "team")).lastrowid
    for email, name, role in [("ops@cafehada.kr", "김운영", "운영"),
                              ("sales@cafehada.kr", "박영업", "영업"),
                              ("admin@cafehada.kr", "이관리", "관리자")]:
        con.execute("INSERT INTO users (org_id,email,name,role,pw_hash) VALUES (?,?,?,?,?)",
                    (org, email, name, role, auth.hash_pw("demo-1234")))
print(f"조직 {org} · 계정 3개 (비밀번호 demo-1234) → {db.DB_PATH}")
