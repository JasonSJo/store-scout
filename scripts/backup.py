#!/usr/bin/env python3
"""
DB 백업

SQLite 파일을 그냥 복사하면 안 된다. 쓰기가 진행 중이면 반쯤 쓰인 페이지가 복사되고,
WAL 모드에서는 최근 트랜잭션이 별도 -wal 파일에 있어 본체만 복사하면 통째로 빠진다.
sqlite3 의 온라인 백업 API 는 열려 있는 DB 를 일관된 상태로 떠 준다.

    python3 scripts/backup.py /backup            # 타임스탬프 이름으로 저장
    python3 scripts/backup.py /backup --keep 14  # 최근 14개만 남기고 정리

⚠ 이 백업 파일에는 **조직의 기존점 실매출과 상담 개인정보가 그대로 들어 있다.**
   저장소 암호화와 접근 통제는 이 스크립트가 해 주지 않는다 — 옮겨 두는 곳이
   서버만큼 통제되는 자리인지 확인하십시오.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def backup(src: Path, dest: Path) -> int:
    """열려 있는 DB 를 일관된 상태로 dest 에 뜬다. 바이트 크기를 돌려준다."""
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        out = sqlite3.connect(str(dest))
        try:
            con.backup(out)          # 온라인 백업 — 쓰기 중이어도 일관된 스냅숏
        finally:
            out.close()
    finally:
        con.close()
    return dest.stat().st_size


def prune(folder: Path, keep: int) -> list[Path]:
    파일 = sorted(folder.glob("store-scout-*.sqlite3"))
    지울것 = 파일[:-keep] if keep > 0 and len(파일) > keep else []
    for p in 지울것:
        p.unlink()
    return 지울것


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SQLite DB 를 일관된 상태로 백업한다")
    ap.add_argument("dest", help="백업을 둘 디렉터리")
    ap.add_argument("--db", default=os.environ.get("STORE_SCOUT_DB", "store-scout.sqlite3"))
    ap.add_argument("--keep", type=int, default=0,
                    help="최근 N개만 남기고 지운다 (0 = 지우지 않음)")
    args = ap.parse_args(argv)

    src = Path(args.db)
    if not src.exists():
        print(f"DB 가 없습니다: {src}", file=sys.stderr)
        return 1
    folder = Path(args.dest)
    folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = folder / f"store-scout-{stamp}.sqlite3"
    # 같은 초에 두 번 돌면 앞의 백업을 덮어쓴다. 지우는 건 --keep 이 할 일이다.
    n = 1
    while dest.exists():
        n += 1
        dest = folder / f"store-scout-{stamp}-{n}.sqlite3"
    크기 = backup(src, dest)
    print(f"{dest} ({크기:,} bytes)")
    for p in prune(folder, args.keep):
        print(f"  지움 {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
