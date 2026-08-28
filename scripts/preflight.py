#!/usr/bin/env python3
"""
배포 전 점검

Fly 에 붙지 않고도 확인할 수 있는 것만 본다. 첫 배포에서 흔히 깨지는 자리들이고,
대부분 배포가 '성공' 한 뒤에야 드러나는 종류다 — 볼륨 밖에 DB 를 두면 배포는
멀쩡히 되고 다음 재배포에서 조직 데이터가 사라진다.

    python3 scripts/preflight.py

돌아가지 않는 것(계정·볼륨 존재 여부·요금제)은 여기서 알 수 없다. 그건 DEPLOY.md 의
절차가 다룬다.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
문제: list[str] = []
경고: list[str] = []


def 확인(조건, 말):
    if not 조건:
        문제.append(말)
    return bool(조건)


def main() -> int:
    fly = tomllib.loads((ROOT / "fly.toml").read_bytes().decode())
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    # 1. DB 가 볼륨 안에 있는가 — 밖이면 재배포 때 조직 데이터가 통째로 사라진다
    mount = (fly.get("mounts") or {}).get("destination", "")
    dbpath = (fly.get("env") or {}).get("STORE_SCOUT_DB", "")
    확인(mount and dbpath.startswith(mount.rstrip("/") + "/"),
       f"STORE_SCOUT_DB({dbpath!r}) 가 볼륨({mount!r}) 안이 아닙니다 — "
       "재배포하면 조직 데이터가 사라집니다")

    # 2. 기계가 하나로 묶여 있는가 — 둘이면 데이터가 조용히 갈라진다
    svc = fly.get("http_service") or {}
    확인(svc.get("min_machines_running") == 1,
       "http_service.min_machines_running 이 1 이 아닙니다")
    확인(str(svc.get("auto_stop_machines")).lower() in ("off", "false"),
       "auto_stop_machines 를 꺼야 합니다 — 심의가 도는 중에 기계가 멈추면 그 실행이 날아갑니다")
    확인(svc.get("force_https") is True,
       "force_https 가 켜져 있지 않습니다 — 로그인 쿠키와 고객 연락처가 평문으로 흐릅니다")

    # 3. HTTPS 쿠키 플래그
    확인((fly.get("env") or {}).get("STORE_SCOUT_HTTPS"),
       "STORE_SCOUT_HTTPS 가 비어 있습니다 — 세션 쿠키에 Secure 가 붙지 않습니다")

    # 4. 알고리즘이 커밋으로 고정돼 있는가
    revs = re.findall(r"^ARG PIPELINE_REV=(\S+)", df, re.M)
    if 확인(revs, "Dockerfile 에 ARG PIPELINE_REV 가 없습니다"):
        확인(len(set(revs)) == 1, f"단계별 PIPELINE_REV 가 다릅니다: {sorted(set(revs))}")
        for rev in set(revs):
            확인(re.fullmatch(r"[0-9a-f]{40}", rev),
               f"PIPELINE_REV 가 커밋 SHA 가 아닙니다: {rev!r} — "
               "브랜치를 따라가면 판정이 말 없이 바뀝니다")

    # 5. 헬스체크 경로가 앱에 실제로 있는가
    checks = svc.get("checks") or []
    경로 = {c.get("path") for c in checks}
    확인("/healthz" in 경로, "http_service.checks 에 /healthz 가 없습니다")
    확인("/healthz" in (ROOT / "server" / "app.py").read_text(encoding="utf-8"),
       "앱에 /healthz 라우트가 없습니다")

    # 6. 배포 이미지가 데모·테스트를 담지 않는가
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for 빼야할것 in ("seed_demo.py", "tests/"):
        확인(빼야할것 in ignore,
           f".dockerignore 에 {빼야할것} 이 없습니다 — 배포 이미지에 들어갑니다")

    # 7. 메모리 — 후보지가 많은 묶음은 256MB 에서 OOM 으로 죽는다
    vms = fly.get("vm") or []
    if vms and str(vms[0].get("memory", "")).lower() in ("256mb", "256"):
        경고.append("vm.memory 가 256MB 입니다 — 큰 묶음에서 파이프라인이 죽을 수 있습니다")

    # 8. 앱 이름은 Fly 전체에서 유일해야 한다. 여기서 확인할 수는 없다.
    앱 = fly.get("app", "")
    경고.append(f"앱 이름 {앱!r} 은 Fly 전체에서 유일해야 합니다 — "
              "이미 있으면 fly.toml 의 app 을 바꾸십시오")
    경고.append("auto_stop_machines 는 최근 flyctl 이 \"off\" 문자열을 씁니다. "
              "구버전이 거부하면 false 로 바꾸십시오")

    for w in 경고:
        print(f"  참고: {w}")
    if 문제:
        print()
        for p in 문제:
            print(f"  ✕ {p}", file=sys.stderr)
        print(f"\n{len(문제)}건을 고치고 다시 돌리십시오.", file=sys.stderr)
        return 1
    print(f"\n점검 통과 — {앱} 배포 준비됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
