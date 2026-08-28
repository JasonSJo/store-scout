#!/usr/bin/env python3
"""
공통 유틸 — 숫자 읽기·반올림·표기·파일 입출력

모델 로직은 여기 없다. M1~M6 각 모듈과 config.py 가 갖고 있다.
이 파일은 그 모듈들이 공유하는 잡일만 맡는다.

반올림 규칙을 이 파일에 모아 둔 이유가 있다. 파이썬 기본 round() 는 은행가
반올림(0.45 → 0.4)이라 자바스크립트 Math.round(→ 0.5)와 어긋난다. 콘솔이 M5
판정 산술을 다시 계산하므로, 두 구현이 같은 규칙을 써야 심의표와 화면의 숫자가
갈리지 않는다. app/js/m5.js 의 r2·nf 가 같은 구현이다.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path


# ── 반올림 · 표기 ────────────────────────────────────────────────
def r2(v: float, n: int = 1) -> float:
    """0.5 는 항상 절대값이 커지는 쪽으로. app/js/m5.js 의 r2 와 연산 순서까지 같다."""
    p = 10 ** n
    x = v * p
    r = math.floor(abs(x) + 0.5 + 1e-9)
    return (-r if x < 0 else r) / p


def ri(v: float) -> int:
    """정수 반올림(표시용). r2 와 같은 규칙."""
    return int(r2(v, 0))


def nf(v, d: int = 0) -> str:
    """천단위 콤마 + 소수 d 자리. 먼저 r2 로 굳혀 JS toLocaleString 과 맞춘다."""
    if v is None:
        return "—"
    return f"{r2(v, d):,.{d}f}"


def n1(v) -> str:
    """소수 한 자리를 JS Number 표기처럼 — 30.0 → '30', 19.6 → '19.6'."""
    if v is None:
        return "—"
    return (f"{v:.1f}".rstrip("0").rstrip(".")) or "0"


# ── 지저분한 입력 읽기 ───────────────────────────────────────────
def to_f(v, default=0.0) -> float:
    """'1,234' · '22평' · None 처럼 손으로 적은 CSV 값도 숫자로 읽는다."""
    if v is None:
        return default
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", ".", "-."):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def to_i(v, default=0) -> int:
    return int(to_f(v, default))


def is_yes(v) -> bool:
    return str(v).strip().upper() in ("Y", "YES", "예", "O", "TRUE", "1", "있음", "해당")


# ── 파일 ────────────────────────────────────────────────────────
def read_csv(path) -> list[dict]:
    p = Path(path)
    with p.open(encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def write_text(path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def write_json(path, obj) -> Path:
    return write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))
