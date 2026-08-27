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
  consult_id INTEGER REFERENCES consults(id) ON DELETE SET NULL,
  consult_md TEXT NOT NULL DEFAULT '',    -- 상담 조건이 무엇을 걸렀는지
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

-- 조직의 기존점 실매출. 이것이 없으면 M4 가 회귀도 앵커링도 못 한다 —
-- 서비스가 성립하지 않는 유일한 필수 데이터다(PRODUCT.md 온보딩).
CREATE TABLE IF NOT EXISTS stores (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  점포명 TEXT NOT NULL,
  주소 TEXT NOT NULL DEFAULT '',
  위도 REAL, 경도 REAL,
  개점일 TEXT NOT NULL DEFAULT '',
  기준점포 TEXT NOT NULL DEFAULT 'N',
  월매출_만원 REAL,
  좌석수 REAL, 층 REAL, 전면폭_m REAL, 주차가능대수 REAL,
  전용면적_평 REAL, 월임대료_만원 REAL, 관리비_만원 REAL,
  코너여부 TEXT NOT NULL DEFAULT 'N', 정차가능 TEXT NOT NULL DEFAULT 'N',
  도로변 TEXT NOT NULL DEFAULT 'A', 방향적합 TEXT NOT NULL DEFAULT 'N',
  계약조건점수 REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_stores_org ON stores(org_id);

-- 조직별 운영 설정(브랜드·변동비·고정비). 파이프라인의 설정.yaml 로 나간다.
CREATE TABLE IF NOT EXISTS org_settings (
  org_id INTEGER PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
  data TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 상담 기록. 개인정보(성명·연락처·거주지·근무지)가 들어가는 유일한 표다.
-- 그래서 다른 표와 다르게 셋을 더 짊어진다:
--   1. 동의 없이는 저장하지 않는다(app.py 가 막는다)
--   2. 보관기간이 지나면 파기 대상으로 표시한다(consults.만료됨)
--   3. 연락처 열람은 '개인정보 열람' 으로 감사 로그에 따로 남는다
-- 심의로는 조건만 넘어가고 개인정보는 넘어가지 않는다(analysis/consult.py 의 읽는키).
CREATE TABLE IF NOT EXISTS consults (
  id INTEGER PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  -- 개인정보
  고객명 TEXT NOT NULL,
  고객전화번호 TEXT NOT NULL DEFAULT '',
  거주지 TEXT NOT NULL DEFAULT '',
  근무지 TEXT NOT NULL DEFAULT '',
  동의 INTEGER NOT NULL DEFAULT 0,
  -- 조건 — 알고리즘(운영형태·투자금형태)과 필터(나머지)로 나뉜다
  희망지역 TEXT NOT NULL DEFAULT '',      -- 선호 순, 쉼표 구분
  희망평수 REAL,
  희망상권 TEXT NOT NULL DEFAULT '',      -- 쉼표 구분
  보증금_만원 REAL, 권리금_만원 REAL,
  투자금형태 TEXT NOT NULL DEFAULT '현금',
  운영형태 TEXT NOT NULL DEFAULT '점주+알바',
  메모 TEXT NOT NULL DEFAULT '',
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_consults_org ON consults(org_id);

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


# 이미 만들어진 DB 에 뒤늦게 붙는 열. CREATE TABLE IF NOT EXISTS 는 열을 더해 주지
# 않으므로 여기서 따로 채운다. (열 추가만 다룬다 — 형 변경·삭제는 손으로 옮긴다)
MIGRATIONS = [
    ("runs", "consult_id", "INTEGER REFERENCES consults(id) ON DELETE SET NULL"),
    ("runs", "consult_md", "TEXT NOT NULL DEFAULT ''"),
]


def init(path: Path | None = None) -> None:
    with connect(path) as con:
        con.executescript(SCHEMA)
        for table, col, decl in MIGRATIONS:
            have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


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
    if table not in ("batches", "runs", "users", "audit", "stores", "consults"):
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
