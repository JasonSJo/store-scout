#!/usr/bin/env python3
"""
출점심의 SaaS — HTTP 계층

원칙 셋. 이 셋이 어긋나면 제품이 아니라 사고다.

  1. 모든 조회는 org_id 로 좁힌다. 로그인한 사용자의 org 밖 자원은 404 로 답한다
     (403 으로 답하면 '그 id 가 존재한다' 는 사실이 새어 나간다).
  2. 산출물에는 예외 없이 '사내 한정 · 대외 배포 금지' 등급이 붙는다.
  3. 열람·내보내기·실행은 감사 로그에 남는다.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
                     Request, UploadFile)
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from . import auth, db, jobs, plans
from .views import layout, login_page, dashboard_page, run_page, audit_page

COOKIE = "scout_session"
등급 = "사내 한정 · 대외 배포 금지"

app = FastAPI(title="출점심의", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    db.init()


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


def require_role(user: dict, allowed: tuple[str, ...]) -> None:
    if user["role"] not in allowed:
        raise HTTPException(status_code=403,
                            detail=f"이 작업은 {' 또는 '.join(allowed)} 권한이 필요합니다")


def org_of(con, user: dict) -> dict:
    row = con.execute("SELECT * FROM orgs WHERE id = ?", (user["org_id"],)).fetchone()
    return dict(row)


# ── 인증 ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(request: Request, con=Depends(_con)):
    u = auth.user_for_token(con, request.cookies.get(COOKIE, ""))
    if not u:
        return HTMLResponse(login_page())
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/login")
def do_login(request: Request, email: str = Form(...), password: str = Form(...),
             con=Depends(_con)):
    u = auth.login(con, email, password)
    if not u:
        # 어느 쪽이 틀렸는지 알려 주지 않는다 — 계정 존재 여부가 새어 나간다
        return HTMLResponse(login_page("이메일 또는 비밀번호가 맞지 않습니다."),
                            status_code=401)
    token = auth.start_session(con, u["id"])
    db.log(con, u["org_id"], u["id"], "로그인")
    r = RedirectResponse("/dashboard", status_code=303)
    r.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                 secure=bool(os.environ.get("STORE_SCOUT_HTTPS")))
    return r


@app.post("/logout")
def do_logout(request: Request, con=Depends(_con)):
    auth.end_session(con, request.cookies.get(COOKIE, ""))
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie(COOKIE)
    return r


# ── 대시보드 ──────────────────────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(current_user), con=Depends(_con)):
    org = org_of(con, user)
    runs = db.rows_for_org(con, "runs", user["org_id"])
    batches = {b["id"]: b for b in db.rows_for_org(con, "batches", user["org_id"])}
    return HTMLResponse(dashboard_page(
        user, org, runs, batches,
        used=plans.used_this_month(con, user["org_id"]),
        seats=plans.seats_used(con, user["org_id"])))


@app.post("/runs")
async def create_run(request: Request, background: BackgroundTasks,
                     name: str = Form(""), sites: UploadFile = File(...),
                     user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_RUN)
    org = org_of(con, user)
    raw = (await sites.read()).decode("utf-8-sig", "replace")
    units = jobs.count_sites(raw)
    if units == 0:
        raise HTTPException(400, "후보지명이 있는 행이 없습니다. CSV 를 확인하십시오.")

    ok, why = plans.run_check(org["plan"], plans.used_this_month(con, user["org_id"]), units)
    if not ok:
        raise HTTPException(402, why)

    cur = con.execute(
        "INSERT INTO batches (org_id, name, created_by, sites_csv, site_count) "
        "VALUES (?,?,?,?,?)",
        (user["org_id"], name.strip() or sites.filename or "이름 없는 묶음",
         user["id"], raw, units))
    batch_id = cur.lastrowid
    cur = con.execute(
        "INSERT INTO runs (org_id, batch_id, status, billed_units) VALUES (?,?,?,?)",
        (user["org_id"], batch_id, "실행중", units))
    run_id = cur.lastrowid
    db.log(con, user["org_id"], user["id"], "실행", f"run:{run_id}", f"{units}건")
    con.commit()

    # 파이프라인은 응답을 붙잡고 돌리지 않는다. 후보지가 몇 곳이면 몇 초지만
    # 수십 곳이면 분 단위가 되고, 그 사이 브라우저와 프록시가 먼저 끊는다.
    # 응답은 바로 주고 결과 화면이 상태를 따라간다.
    background.add_task(_execute, run_id, user["org_id"], raw)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


def _execute(run_id: int, org_id: int, sites_csv: str) -> None:
    """백그라운드 실행. 자기 연결을 새로 연다 — 요청 연결은 이미 닫혔다."""
    out = jobs.run(sites_csv)
    with db.tx() as con:
        if out["ok"]:
            con.execute(
                "UPDATE runs SET status='완료', mode=?, result_json=?, report_md=?, "
                "finished_at=datetime('now') WHERE id=? AND org_id=?",
                (out["mode"], json.dumps(out["result"], ensure_ascii=False),
                 out["report"], run_id, org_id))
        else:
            # 실패는 청구하지 않는다
            con.execute(
                "UPDATE runs SET status='실패', error=?, billed_units=0, "
                "finished_at=datetime('now') WHERE id=? AND org_id=?",
                (out["error"], run_id, org_id))


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def view_run(run_id: int, user=Depends(current_user), con=Depends(_con)):
    run = db.row_for_org(con, "runs", user["org_id"], run_id)
    if not run:
        raise HTTPException(404, "없는 분석입니다")   # 남의 org 자원도 404
    batch = db.row_for_org(con, "batches", user["org_id"], run["batch_id"])
    summary = jobs.summarize(json.loads(run["result_json"])) if run["result_json"] else None
    db.log(con, user["org_id"], user["id"], "열람", f"run:{run_id}")
    return HTMLResponse(run_page(user, run, batch, summary, 등급))


@app.get("/runs/{run_id}/report")
def download_report(run_id: int, user=Depends(current_user), con=Depends(_con)):
    run = db.row_for_org(con, "runs", user["org_id"], run_id)
    if not run or not run["report_md"]:
        raise HTTPException(404, "없는 분석입니다")
    db.log(con, user["org_id"], user["id"], "내보내기", f"run:{run_id}")
    # 파일명에 internal 을 박는다 — 파일이 조직 밖으로 나가도 등급이 함께 간다
    return Response(
        run["report_md"], media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="internal-review-{run_id}.md"'})


@app.get("/audit", response_class=HTMLResponse)
def view_audit(user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_MANAGE)
    rows = db.rows_for_org(con, "audit", user["org_id"])[:300]
    users = {u["id"]: u for u in db.rows_for_org(con, "users", user["org_id"])}
    return HTMLResponse(audit_page(user, rows, users))


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    ok, why = jobs.available()
    return f"ok pipeline={'yes' if ok else 'no'} {why}".strip()
