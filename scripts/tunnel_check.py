#!/usr/bin/env python3
"""터널이 안 될 때 어디서 막혔는지 한 번에 본다.

  python3 scripts/tunnel_check.py

'터널이 안 된다' 는 증상 하나에 원인이 여러 갈래다. 이 구성에서는 특히
**앱이 건강하지 않으면 터널이 아예 시작하지 않는다** (depends_on: service_healthy).
그래서 터널 로그를 아무리 봐도 아무것도 없는 상태가 나온다 — 컨테이너가 없으니까.
그 갈래를 순서대로 짚는다.

읽기만 한다. 아무것도 고치지 않는다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
문제: list[str] = []
다음: list[str] = []


def 말(표시: str, 글: str) -> None:
    print(f"  {표시} {글}")


def 달리기(*args: str, 초: int = 25) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=초, cwd=ROOT)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, f"{args[0]} 를 찾지 못했습니다"
    except subprocess.TimeoutExpired:
        return 124, "시간 초과"


def compose(*args: str, 초: int = 25) -> tuple[int, str]:
    return 달리기("docker", "compose", *args, 초=초)


# ── 1. 도커부터 ────────────────────────────────────────
print("\n1. 도커")
if not shutil.which("docker"):
    문제.append("docker 명령이 없습니다")
    다음.append("Docker Desktop(또는 docker engine)을 설치하고 실행하십시오")
    말("✕", "docker 명령을 찾지 못했습니다")
else:
    코드, 글 = 달리기("docker", "info", 초=20)
    if 코드 != 0:
        문제.append("도커 데몬이 응답하지 않습니다")
        다음.append("Docker Desktop 을 켜십시오. 재부팅 뒤라면 자동 시작이 꺼져 "
                   "있을 수 있습니다 (DEPLOY.md 「늘 켜 두기」)")
        말("✕", "데몬이 응답하지 않습니다")
    else:
        말("✓", "데몬 정상")

# ── 2. .env ───────────────────────────────────────────
print("\n2. .env")
env파일 = ROOT / ".env"
값: dict[str, str] = {}
if not env파일.exists():
    문제.append(".env 가 없습니다")
    다음.append("cp .env.example .env 로 만들고 토큰을 채우십시오")
    말("✕", f"{env파일} 이 없습니다")
    # 윈도우에서 흔한 실수 — 확장자가 붙어 버린 경우
    비슷 = [p.name for p in ROOT.glob(".env*") if p.name != ".env.example"]
    if 비슷:
        말("!", f"비슷한 이름이 있습니다: {', '.join(비슷)} — 파일 이름이 정확히 "
               f"'.env' 여야 합니다 (윈도우는 확장자를 숨깁니다)")
else:
    for 줄 in env파일.read_text(encoding="utf-8", errors="replace").splitlines():
        줄 = 줄.strip()
        if 줄 and not 줄.startswith("#") and "=" in 줄:
            k, v = 줄.split("=", 1)
            값[k.strip()] = v.strip().strip('"').strip("'")

    토큰 = 값.get("CLOUDFLARE_TUNNEL_TOKEN", "")
    if not 토큰:
        문제.append("CLOUDFLARE_TUNNEL_TOKEN 이 비어 있습니다")
        다음.append("Cloudflare Zero Trust → Networks → Tunnels 에서 토큰을 받아 "
                   ".env 에 넣으십시오")
        말("✕", "CLOUDFLARE_TUNNEL_TOKEN 이 비어 있습니다")
    elif len(토큰) < 40:
        문제.append("토큰이 너무 짧습니다 — 잘려 붙었을 수 있습니다")
        다음.append("토큰을 다시 복사해 넣으십시오 (보통 100자가 넘습니다)")
        말("✕", f"토큰이 {len(토큰)}자입니다 — 잘린 것 같습니다")
    else:
        말("✓", f"토큰 있음 ({len(토큰)}자)")

    if 값.get("STORE_SCOUT_HTTPS") != "1":
        문제.append("STORE_SCOUT_HTTPS 가 1 이 아닙니다")
        다음.append(".env 에 STORE_SCOUT_HTTPS=1 을 넣으십시오 — 없으면 로그인 "
                   "쿠키에 Secure 가 붙지 않습니다")
        말("✕", "STORE_SCOUT_HTTPS 가 1 이 아닙니다 (쿠키에 Secure 가 안 붙습니다)")
    else:
        말("✓", "STORE_SCOUT_HTTPS=1")

# ── 3. 터널 서비스가 켜졌는가 ──────────────────────────
print("\n3. 컨테이너")
코드, 글 = compose("ps", "--format", "json")
줄들 = [l for l in 글.splitlines() if l.strip().startswith("{")]
상태: dict[str, dict] = {}
for l in 줄들:
    try:
        d = json.loads(l)
        상태[d.get("Service") or d.get("Name", "")] = d
    except ValueError:
        pass

if 코드 != 0 and not 상태:
    말("✕", "docker compose ps 가 실패했습니다")
    print("   " + 글.strip()[:300])
else:
    app = 상태.get("app")
    tun = 상태.get("tunnel")

    if not app:
        문제.append("app 컨테이너가 없습니다")
        다음.append("STORE_SCOUT_REV=$(git rev-parse HEAD) "
                   "docker compose --profile tunnel up -d --build")
        말("✕", "app 이 떠 있지 않습니다")
    else:
        건강 = (app.get("Health") or "").lower()
        말("✓" if app.get("State") == "running" else "✕",
           f"app — {app.get('State')} · health={건강 or '없음'}")
        if 건강 and 건강 != "healthy":
            문제.append(f"app 이 healthy 가 아닙니다 (health={건강})")
            다음.append("터널은 app 이 healthy 해야 시작합니다. 먼저 앱을 보십시오: "
                       "docker compose logs --tail 50 app")

    if not tun:
        문제.append("tunnel 컨테이너가 없습니다")
        if app and (app.get("Health") or "").lower() not in ("", "healthy"):
            말("✕", "tunnel 이 없습니다 — app 이 healthy 가 아니라 **시작 자체를 "
                   "안 했습니다** (depends_on: service_healthy)")
        else:
            말("✕", "tunnel 이 없습니다 — --profile tunnel 을 빠뜨렸을 수 있습니다")
            다음.append("docker compose --profile tunnel up -d  ← --profile tunnel 이 "
                       "없으면 터널은 뜨지 않습니다")
    else:
        말("✓" if tun.get("State") == "running" else "✕",
           f"tunnel — {tun.get('State')}")

# ── 4. 터널 로그에서 흔한 원인 ────────────────────────
if 상태.get("tunnel"):
    print("\n4. 터널 로그")
    코드, 로그 = compose("logs", "--tail", "80", "tunnel", 초=25)
    표 = [
        (r"Provided Tunnel token is not valid|invalid token|401",
         "토큰이 유효하지 않습니다 — Cloudflare 에서 다시 복사하십시오"),
        (r"Unauthorized|failed to authenticate",
         "인증에 실패했습니다 — 터널이 대시보드에서 지워졌을 수 있습니다"),
        (r"dial tcp .*: connect: connection refused",
         "터널이 대상에 닿지 못했습니다 — Public Hostname 의 Service 를 "
         "http://app:8000 으로 두었는지 보십시오 (localhost 가 아닙니다)"),
        (r"no such host",
         "대상 이름을 찾지 못했습니다 — Service 가 http://app:8000 인지 보십시오"),
        (r"Registered tunnel connection",
         None),   # 정상 신호
    ]
    붙음 = False
    for 무늬, 말씀 in 표:
        if re.search(무늬, 로그, re.I):
            if 말씀 is None:
                붙음 = True
                말("✓", "Cloudflare 에 연결됨 (Registered tunnel connection)")
            else:
                문제.append(말씀)
                말("✕", 말씀)
    if not 붙음 and not any("Registered" in l for l in 로그.splitlines()):
        말("!", "연결 성공 줄이 없습니다. 마지막 로그를 그대로 봅니다:")
        for l in 로그.strip().splitlines()[-12:]:
            print("     " + l[:160])

# ── 5. 앱이 안에서 응답하는가 ─────────────────────────
if 상태.get("app"):
    print("\n5. 앱 응답 (컨테이너 안에서)")
    코드, 글 = compose(
        "exec", "-T", "app", "python3", "-c",
        "import urllib.request;"
        "print(urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=5)"
        ".read().decode())", 초=20)
    if 코드 == 0 and "pipeline=" in 글:
        말("✓" if "pipeline=yes" in 글 else "✕", 글.strip()[:160])
        if "pipeline=no" in 글:
            문제.append("알고리즘이 이미지에 없습니다")
            다음.append("모든 심의가 실패합니다. 이미지를 다시 빌드하십시오: "
                       "docker compose --profile tunnel up -d --build")
    else:
        문제.append("앱이 컨테이너 안에서도 응답하지 않습니다")
        다음.append("docker compose logs --tail 50 app")
        말("✕", 글.strip()[:200] or "응답 없음")

# ── 맺음 ──────────────────────────────────────────────
print("\n" + "─" * 62)
if not 문제:
    print("여기서는 막힌 곳을 못 찾았습니다.")
    print("컨테이너와 앱은 정상입니다 — 남은 곳은 Cloudflare 쪽 설정입니다:")
    print("  · Public Hostname 의 Service 가 HTTP → app:8000 인가")
    print("  · 그 호스트명이 이 터널에 붙어 있는가")
    print("  · Access 정책을 켰다면 내 계정이 그 정책에 드는가")
    sys.exit(0)

print(f"막힌 곳 {len(문제)}건:")
for m in 문제:
    print(f"  ✕ {m}")
if 다음:
    print("\n할 일:")
    for m in dict.fromkeys(다음):
        print(f"  → {m}")
sys.exit(1)
