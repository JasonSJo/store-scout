#!/usr/bin/env python3
"""
스키마 · 연결

멀티테넌시의 축은 **조직(org)** 이다. 후보지·분석·산출물 모든 행이 org_id 를 갖고,
조회는 예외 없이 org_id 로 좁힌다. 이 규칙이 깨지면 A 프랜차이즈의 출점 후보지가
B 프랜차이즈에게 보인다 — 이 제품에서 가장 큰 사고다.

그래서 쿼리를 손으로 쓰지 않고 org 를 강제로 받는 헬퍼만 노출한다
(tests/test_tenancy.py 가 org 인자 없는 조회 경로가 없는지 검사한다).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("STORE_SCOUT_DB", "store-scout.sqlite3"))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS orgs (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  brand TEXT NOT NULL DEFAULT '',
  plan TEXT NOT NULL DEFAULT 'starter',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT '영업',      -- 관리자 · 운영 · 영업
  pw_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_users_org ON users(org_id);

-- 후보지 묶음 하나 = 한 번의 심의 대상
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_by INTEGER NOT NULL REFERENCES users(id),
  sites_csv TEXT NOT NULL,                -- 업로드 원본
  site_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_batches_org ON batches(org_id);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT '대기',    -- 대기 · 실행중 · 완료 · 실패
  billed_units INTEGER NOT NULL DEFAULT 0,
  mode TEXT NOT NULL DEFAULT '',
  result_json TEXT NOT NULL DEFAULT '',
  report_md TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_runs_org ON runs(org_id);

-- 사내 한정 자료를 다루므로 열람 기록은 기능이 아니라 의무다
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,                   -- 열람 · 내보내기 · 실행 · 로그인
  target TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_audit_org ON audit(org_id, at);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    # check_same_thread=False 인 이유: FastAPI 는 동기 엔드포인트를 스레드풀에서,
    # async 엔드포인트를 이벤트 루프에서 돌린다. 의존성이 만든 연결이 다른 스레드에서
    # 쓰일 수 있다. 연결은 **요청당 하나**이고 요청 사이에 공유되지 않으므로 안전하다
    # (공유 풀로 바꾸는 순간 이 가정이 깨지니 그때는 이 줄부터 다시 보십시오).
    con = sqlite3.connect(str(path or DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init(path: Path | None = None) -> None:
    with connect(path) as con:
        con.executescript(SCHEMA)


@contextmanager
def tx(path: Path | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ── 조직 경계를 강제하는 조회 ────────────────────────────────
# org_id 를 빼먹을 수 없게 인자로 받는다. 아래를 거치지 않는 SELECT 는 두지 않는다.

def rows_for_org(con, table: str, org_id: int, where: str = "", args=()) -> list[dict]:
    if table not in ("batches", "runs", "users", "audit"):
        raise ValueError(f"허용되지 않은 테이블: {table}")
    sql = f"SELECT * FROM {table} WHERE org_id = ?"
    if where:
        sql += f" AND ({where})"
    sql += " ORDER BY id DESC"
    return [dict(r) for r in con.execute(sql, (org_id, *args))]


def row_for_org(con, table: str, org_id: int, row_id: int) -> dict | None:
    got = rows_for_org(con, table, org_id, "id = ?", (row_id,))
    return got[0] if got else None


def log(con, org_id: int, user_id: int | None, action: str,
        target: str = "", detail: str = "") -> None:
    con.execute(
        "INSERT INTO audit (org_id, user_id, action, target, detail) VALUES (?,?,?,?,?)",
        (org_id, user_id, action, target, detail))
