#!/usr/bin/env python3
"""
첫 조직과 첫 관리자 만들기

배포한 직후의 DB 는 비어 있다. 조직도 계정도 없으니 아무도 로그인할 수 없고,
화면에는 가입 경로가 없다 — 이 제품은 **누구나 가입하는 서비스가 아니라**
조직 단위로 계약하고 관리자가 구성원을 넣는 도구이기 때문이다(PRODUCT.md).

그래서 첫 계정은 배포한 사람이 서버에서 한 번 만든다. seed_demo.py 는 꾸며 낸
기존점 매출을 넣으므로 운영에 쓰면 안 된다 — 이 스크립트는 아무 데이터도 지어내지
않고 조직과 관리자만 만든다.

    python3 -m server.bootstrap --org "카페하다 본부" --plan team \\
        --email ops@brand.co.kr --name "김운영"

비밀번호는 인자로 받지 않는다. 명령행 인자는 셸 히스토리와 프로세스 목록에 남는다.
표준입력으로 받거나(파이프), 주지 않으면 무작위로 만들어 화면에 한 번만 보여 준다.
"""
from __future__ import annotations

import argparse
import secrets
import sqlite3
import string
import sys

from . import auth, db, plans


def 무작위_비밀번호(n: int = 20) -> str:
    글자 = string.ascii_letters + string.digits
    return "".join(secrets.choice(글자) for _ in range(n))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="첫 조직과 관리자 계정을 만든다")
    ap.add_argument("--org", required=True, help="조직 이름")
    ap.add_argument("--email", required=True, help="관리자 이메일")
    ap.add_argument("--name", default="", help="관리자 이름")
    ap.add_argument("--plan", default=plans.DEFAULT, choices=sorted(plans.PLANS),
                    help=f"요금제 (기본 {plans.DEFAULT})")
    ap.add_argument("--brand", default="", help="브랜드 이름 (설정 화면에서 나중에 넣어도 된다)")
    ap.add_argument("--password-stdin", action="store_true",
                    help="비밀번호를 표준입력에서 읽는다. 주지 않으면 무작위로 만든다")
    args = ap.parse_args(argv)

    email = args.email.strip().lower()
    if "@" not in email:
        print(f"이메일 형식이 아닙니다: {email}", file=sys.stderr)
        return 2

    if args.password_stdin:
        pw = sys.stdin.readline().rstrip("\n")
        if len(pw) < 8:
            print("비밀번호는 8자 이상이어야 합니다.", file=sys.stderr)
            return 2
        보여줄까 = False
    else:
        pw = 무작위_비밀번호()
        보여줄까 = True

    db.init()
    with db.tx() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            print(f"이미 있는 이메일입니다: {email}", file=sys.stderr)
            return 1
        org = con.execute("INSERT INTO orgs (name, brand, plan) VALUES (?,?,?)",
                          (args.org.strip(), args.brand.strip(), args.plan)).lastrowid
        try:
            con.execute(
                "INSERT INTO users (org_id, email, name, role, pw_hash) VALUES (?,?,?,?,?)",
                (org, email, args.name.strip(), "관리자", auth.hash_pw(pw)))
        except sqlite3.IntegrityError as e:
            print(f"계정을 만들지 못했습니다: {e}", file=sys.stderr)
            return 1
        db.log(con, org, None, "조직 생성", f"org:{org}", f"{args.org} · {args.plan}")

    print(f"조직 {org} ({args.org} · {plans.spec(args.plan)['이름']}) · 관리자 {email}")
    if 보여줄까:
        print(f"임시 비밀번호: {pw}")
        print("이 줄은 다시 볼 수 없습니다. 지금 옮겨 적고, 로그에 남았다면 지우십시오.")
    print("다음: 로그인 → 설정에서 브랜드, 기존점에서 실매출을 넣어야 심의를 돌릴 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
