#!/usr/bin/env python3
"""
스스닷컴 SaaS — JSON API

콘솔 화면을 React 로 옮기는 중이다. 그 화면이 먹을 데이터를 여기서 낸다.
HTML 을 찍던 views.py 는 React 가 각 화면을 따라잡을 때까지 그대로 돈다.

**이 파일은 격리 규칙을 다시 쓰지 않는다.** app.py 의 current_user·org_of 와
db.rows_for_org 를 그대로 쓴다. 규칙이 두 벌이 되면 한쪽만 고치고 안심하게 되고,
그 순간 A 프랜차이즈의 후보지가 B 에게 보인다 — 이 제품에서 나면 안 되는 일 1번이다.

응답 규약
  · 로그인 안 됨            401 {"detail": ...}
  · 권한 없음               403
  · 내 org 밖의 자원        404  (403 으로 답하면 그 id 가 존재한다는 사실이 샌다)
  · 등급이 붙는 자료        본문에 "등급" 필드를 함께 낸다 — 화면이 빠뜨릴 수 없게
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response

from . import auth, db, orgdata, plans

router = APIRouter(prefix="/api")

COOKIE = "scout_session"
등급 = "사내 한정 · 대외 배포 금지"


def _con(request: Request):
    con = db.connect()
    try:
        request.state.con = con
        yield con
        con.commit()
    finally:
        con.close()


def current_user(request: Request, con=Depends(_con)) -> dict:
    u = auth.user_for_token(con, request.cookies.get(COOKIE, ""))
    if not u:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return u


def _org(con, user: dict) -> dict:
    return dict(con.execute("SELECT * FROM orgs WHERE id = ?",
                            (user["org_id"],)).fetchone())


def _사용자(u: dict) -> dict:
    """비밀번호 해시는 어떤 경로로도 나가지 않는다."""
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}


# ── 인증 ──────────────────────────────────────────────
@router.post("/login")
def login(response: Response, email: str = Form(...), password: str = Form(...),
          con=Depends(_con)):
    u = auth.login(con, email, password)
    if not u:
        # 어느 쪽이 틀렸는지 알려 주지 않는다 — 계정 존재 여부가 새어 나간다
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 맞지 않습니다.")
    token = auth.start_session(con, u["id"])
    db.log(con, u["org_id"], u["id"], "로그인")
    # 토큰은 httponly 쿠키로만 준다. 자바스크립트가 읽을 수 있게 하면
    # XSS 하나로 세션이 통째로 나간다.
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                        secure=bool(os.environ.get("STORE_SCOUT_HTTPS")))
    return {"사용자": _사용자(u)}


@router.post("/logout")
def logout(request: Request, response: Response, con=Depends(_con)):
    auth.end_session(con, request.cookies.get(COOKIE, ""))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/session")
def session(user=Depends(current_user), con=Depends(_con)):
    org = _org(con, user)
    spec = plans.spec(org["plan"])
    return {
        "사용자": _사용자(user),
        "조직": {"id": org["id"], "name": org["name"], "plan": org["plan"],
               "플랜이름": spec["이름"], "플랜설명": spec["설명"],
               "월_분석": spec["월_분석"], "좌석": spec["좌석"]},
        "등급": 등급,
    }


# ── 개요 ──────────────────────────────────────────────
@router.get("/dashboard")
def dashboard(user=Depends(current_user), con=Depends(_con)):
    org = _org(con, user)
    spec = plans.spec(org["plan"])
    runs = db.rows_for_org(con, "runs", user["org_id"])
    batches = {b["id"]: b for b in db.rows_for_org(con, "batches", user["org_id"])}
    ready = orgdata.readiness(con, user["org_id"])

    할일키 = {t[0] for t in ready["할일"]}
    단계 = [
        {"키": 키, "제목": 제목, "설명": 설명, "링크": 링크,
         "완료": 키 not in 할일키 and (키 != "심의" or bool(runs)),
         "해야함": 키 in 할일키}
        for 키, 제목, 설명, 링크 in (
            ("설정", "브랜드 설정", "변동비·고정비를 조직에 맞춥니다", "/settings"),
            ("기존점", "기존점 실매출", "매출 추정의 유일한 근거입니다", "/stores"),
            ("심의", "후보지 심의", "후보지 CSV 를 올려 판정을 받습니다", "/runs"),
        )
    ]
    return {
        "등급": 등급,
        "조직": {"name": org["name"], "플랜이름": spec["이름"], "플랜설명": spec["설명"]},
        "단계": 단계,
        "할일": [{"키": w, "말": m, "링크": h} for w, m, h in ready["할일"]],
        "지표": {
            "이번달분석": plans.used_this_month(con, user["org_id"]),
            "월_분석_한도": spec["월_분석"],
            "좌석": plans.seats_used(con, user["org_id"]),
            "좌석_한도": spec["좌석"],
            "기존점": ready["기존점"],
            "좌표있음": ready["좌표"],
            "매출추정모드": ready["모드"],
        },
        "최근심의": [
            {"id": r["id"], "묶음": batches.get(r["batch_id"], {}).get("name", ""),
             "상태": r["status"], "후보지수": r["billed_units"],
             "실행": (r["started_at"] or "")[:16]}
            for r in runs[:6]
        ],
    }


# ── 심의 ──────────────────────────────────────────────
@router.get("/runs")
def runs(user=Depends(current_user), con=Depends(_con)):
    runs = db.rows_for_org(con, "runs", user["org_id"])
    batches = {b["id"]: b for b in db.rows_for_org(con, "batches", user["org_id"])}
    상담 = db.rows_for_org(con, "consults", user["org_id"])
    ready = orgdata.readiness(con, user["org_id"])
    return {
        "등급": 등급,
        "돌릴수있나": not ready["할일"],
        "할일": [{"키": w, "말": m, "링크": h} for w, m, h in ready["할일"]],
        "심의": [
            {"id": r["id"], "묶음": batches.get(r["batch_id"], {}).get("name", ""),
             "상태": r["status"], "후보지수": r["billed_units"],
             "실행": (r["started_at"] or "")[:16], "오류": r["error"] or ""}
            for r in runs
        ],
        # 목록에서 연락처는 가려 둔다 — 전체 열람은 따로 감사 로그에 남는다
        # consults 의 개인정보 칸은 고객명·고객전화번호·거주지·근무지 넷이다.
        # 목록에는 이름만 낸다 — 나머지는 전체 열람 경로로만 나간다.
        "상담": [{"id": c["id"], "고객명": c["고객명"], "만든이": c["created_by"],
                "만든때": (c["created_at"] or "")[:16]} for c in 상담],
    }


@router.get("/runs/{run_id}")
def run(run_id: int, user=Depends(current_user), con=Depends(_con)):
    r = db.row_for_org(con, "runs", user["org_id"], run_id)
    if not r:
        raise HTTPException(status_code=404, detail="없는 심의입니다")
    b = db.row_for_org(con, "batches", user["org_id"], r["batch_id"])
    결과 = None
    if r["status"] == "완료" and r["result_json"]:
        import json as _json
        후보 = (_json.loads(r["result_json"]) or {}).get("후보지") or []
        결과 = [
            {"순": i, "이름": s.get("이름", ""), "S": s.get("S"),
             "판정": (s.get("판정") or {}).get("판정", ""),
             "사유": (s.get("판정") or {}).get("사유") or [],
             "월매출_하한": (s.get("매출") or {}).get("월매출_하한"),
             "월매출_상한": (s.get("매출") or {}).get("월매출_상한"),
             "경고": s.get("경고") or []}
            for i, s in enumerate(후보)
        ]
    return {
        "등급": 등급,
        "id": r["id"], "상태": r["status"], "모드": r["mode"],
        "오류": r["error"] or "",
        "묶음": {"name": b["name"] if b else "", "후보지수": b["site_count"] if b else 0},
        "후보지": 결과,
    }
