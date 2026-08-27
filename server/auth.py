#!/usr/bin/env python3
"""
인증 — 비밀번호 해시와 세션

비밀번호는 PBKDF2-HMAC-SHA256 으로만 저장한다. 평문도, 되돌릴 수 있는 형태도 남기지
않는다. 표준 라이브러리만 쓴다(외부 의존성이 하나 줄면 배포가 그만큼 단순해진다).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

ITER = 240_000


def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER)
    return f"pbkdf2_sha256${ITER}${salt.hex()}${dk.hex()}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(iters))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)   # 타이밍 공격 방지


def new_token() -> str:
    return secrets.token_urlsafe(32)


def login(con, email: str, pw: str) -> dict | None:
    row = con.execute(
        "SELECT * FROM users WHERE email = ? AND active = 1", (email.strip().lower(),)
    ).fetchone()
    if not row or not verify_pw(pw, row["pw_hash"]):
        return None
    return dict(row)


def start_session(con, user_id: int) -> str:
    token = new_token()
    con.execute("INSERT INTO sessions (token, user_id) VALUES (?,?)", (token, user_id))
    return token


def user_for_token(con, token: str) -> dict | None:
    if not token:
        return None
    row = con.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND u.active = 1", (token,)).fetchone()
    return dict(row) if row else None


def end_session(con, token: str) -> None:
    con.execute("DELETE FROM sessions WHERE token = ?", (token,))
