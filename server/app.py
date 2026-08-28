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

import json
import os
import sqlite3

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
                     Request, UploadFile)
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

from . import auth, consults, db, jobs, orgdata, plans, views

COOKIE = "scout_session"
등급 = "사내 한정 · 대외 배포 금지"

app = FastAPI(title="출점심의", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    _recover_interrupted_runs()


def _recover_interrupted_runs() -> None:
    """재시작 전에 돌던 심의를 실패로 정리한다.

    파이프라인은 이 프로세스 안의 백그라운드 작업으로 돈다. 배포·재시작·크래시로
    프로세스가 죽으면 그 작업도 함께 죽지만 DB 의 상태는 '실행중' 인 채로 남는다.
    결과 화면은 3초마다 새로 고치며 영원히 기다리고, 그 건은 사용량에도 계속 잡힌다.
    시작 시점에 '실행중' 인 행은 예외 없이 죽은 프로세스의 것이므로(단일 인스턴스가
    전제다 — DEPLOY.md) 여기서 끊어 준다. 실패는 청구하지 않는다.
    """
    with db.tx() as con:
        n = con.execute(
            "UPDATE runs SET status='실패', billed_units=0, "
            "error='서버가 다시 시작되어 실행이 중단되었습니다. 다시 실행하십시오.', "
            "finished_at=datetime('now') WHERE status='실행중'").rowcount
    if n:
        print(f"[startup] 중단된 심의 {n}건을 실패로 정리했습니다", flush=True)


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


def _num(v, default=None):
    """폼에서 온 빈 문자열은 0 이 아니라 '모름'이다. 0 으로 바꾸면 좌표 없는 점포가
    적도 한가운데에 찍히고, 매출 0 원인 기존점이 회귀 표본에 들어간다."""
    s = str(v or "").strip()
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


# ── 인증 ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(request: Request, con=Depends(_con)):
    u = auth.user_for_token(con, request.cookies.get(COOKIE, ""))
    if not u:
        return HTMLResponse(views.login_page())
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/login")
def do_login(request: Request, email: str = Form(...), password: str = Form(...),
             con=Depends(_con)):
    u = auth.login(con, email, password)
    if not u:
        # 어느 쪽이 틀렸는지 알려 주지 않는다 — 계정 존재 여부가 새어 나간다
        return HTMLResponse(views.login_page("이메일 또는 비밀번호가 맞지 않습니다."),
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


# ── 개요 ──────────────────────────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(current_user), con=Depends(_con)):
    org = org_of(con, user)
    runs = db.rows_for_org(con, "runs", user["org_id"])
    batches = {b["id"]: b for b in db.rows_for_org(con, "batches", user["org_id"])}
    return HTMLResponse(views.dashboard_page(
        user, org, runs, batches,
        used=plans.used_this_month(con, user["org_id"]),
        seats=plans.seats_used(con, user["org_id"]),
        ready=orgdata.readiness(con, user["org_id"])))


# ── 심의 ──────────────────────────────────────────────
def _runs_html(con, user, msg: str = "", status: int = 200,
               고른상담=None) -> HTMLResponse:
    runs = db.rows_for_org(con, "runs", user["org_id"])
    batches = {b["id"]: b for b in db.rows_for_org(con, "batches", user["org_id"])}
    상담 = db.rows_for_org(con, "consults", user["org_id"])
    return HTMLResponse(
        views.runs_page(user, runs, batches, orgdata.readiness(con, user["org_id"]),
                        msg, 상담, 고른상담),
        status_code=status)


@app.get("/runs", response_class=HTMLResponse)
def list_runs(consult: str = "", user=Depends(current_user), con=Depends(_con)):
    return _runs_html(con, user, 고른상담=consult)


@app.post("/runs")
async def create_run(request: Request, background: BackgroundTasks,
                     name: str = Form(""), consult_id: str = Form(""),
                     sites: UploadFile = File(...),
                     user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_RUN)
    org = org_of(con, user)
    raw = (await sites.read()).decode("utf-8-sig", "replace")
    units = jobs.count_sites(raw)
    if units == 0:
        return _runs_html(con, user, "후보지명이 있는 행이 없습니다. CSV 를 확인하십시오.", 400)

    # 온보딩이 끝나지 않았으면 돌리지 않는다. 여기서 막지 않으면 파이프라인이
    # 예시 기존점을 집어 남의 브랜드 실적으로 이 조직의 매출을 추정한다.
    ready = orgdata.readiness(con, user["org_id"])
    if not ready["준비됨"]:
        return _runs_html(con, user, "온보딩이 끝나야 심의를 돌릴 수 있습니다: "
                          + " / ".join(f"{w} — {m}" for w, m, _ in ready["할일"]), 400)

    ok, why = plans.run_check(org["plan"], plans.used_this_month(con, user["org_id"]), units)
    if not ok:
        return _runs_html(con, user, why, 402)

    # 상담을 붙이면 조건이 후보지를 거르고 고정비를 바꾼다. 개인정보는 넘기지 않는다 —
    # consults.조건_json 이 조건키만 골라 담는다.
    상담 = None
    if consult_id.strip():
        상담 = db.row_for_org(con, "consults", user["org_id"], int(consult_id))
        if not 상담:
            raise HTTPException(404, "없는 상담입니다")

    cur = con.execute(
        "INSERT INTO batches (org_id, name, created_by, sites_csv, site_count) "
        "VALUES (?,?,?,?,?)",
        (user["org_id"], name.strip() or sites.filename or "이름 없는 묶음",
         user["id"], raw, units))
    batch_id = cur.lastrowid
    cur = con.execute(
        "INSERT INTO runs (org_id, batch_id, status, billed_units, consult_id) "
        "VALUES (?,?,?,?,?)",
        (user["org_id"], batch_id, "실행중", units, 상담["id"] if 상담 else None))
    run_id = cur.lastrowid
    db.log(con, user["org_id"], user["id"], "실행", f"run:{run_id}",
           f"{units}건" + (f" · 상담 {상담['id']}" if 상담 else ""))
    con.commit()

    # 파이프라인은 응답을 붙잡고 돌리지 않는다. 후보지가 몇 곳이면 몇 초지만
    # 수십 곳이면 분 단위가 되고, 그 사이 브라우저와 프록시가 먼저 끊는다.
    # 응답은 바로 주고 결과 화면이 상태를 따라간다.
    background.add_task(_execute, run_id, user["org_id"], raw,
                        orgdata.settings_yaml(con, user["org_id"]),
                        orgdata.stores_csv(con, user["org_id"]),
                        consults.조건_json(상담) if 상담 else "")
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


def _execute(run_id: int, org_id: int, sites_csv: str,
             settings_yaml: str, stores_csv: str, consult_json: str = "") -> None:
    """백그라운드 실행. 자기 연결을 새로 연다 — 요청 연결은 이미 닫혔다."""
    out = jobs.run(sites_csv, settings_yaml=settings_yaml, stores_csv=stores_csv,
                   consult_json=consult_json)
    with db.tx() as con:
        if out["ok"]:
            # 청구는 **실제로 심의한 후보지 수**로 바로잡는다. 상담 조건으로 걸러진
            # 물건은 심의에 올라오지 않았으니 청구하지 않는다.
            심의한 = len((out["result"] or {}).get("후보지") or [])
            con.execute(
                "UPDATE runs SET status='완료', mode=?, result_json=?, report_md=?, "
                "consult_md=?, billed_units=?, finished_at=datetime('now') "
                "WHERE id=? AND org_id=?",
                (out["mode"], json.dumps(out["result"], ensure_ascii=False),
                 out["report"], out.get("상담반영", ""), 심의한, run_id, org_id))
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
    batch = db.row_for_org(con, "batches", user["org_id"], run["batch_id"]) or {}
    summary = jobs.summarize(json.loads(run["result_json"])) if run["result_json"] else None
    상담 = (db.row_for_org(con, "consults", user["org_id"], run["consult_id"])
          if run["consult_id"] else None)
    db.log(con, user["org_id"], user["id"], "열람", f"run:{run_id}")
    return HTMLResponse(views.run_page(user, run, batch, summary, 상담))


@app.get("/runs/{run_id}/sites/{idx}", response_class=HTMLResponse)
def view_site(run_id: int, idx: int, user=Depends(current_user), con=Depends(_con)):
    run = db.row_for_org(con, "runs", user["org_id"], run_id)
    if not run or not run["result_json"]:
        raise HTTPException(404, "없는 분석입니다")
    사이트 = (json.loads(run["result_json"]) or {}).get("후보지") or []
    if not 0 <= idx < len(사이트):
        raise HTTPException(404, "없는 후보지입니다")
    batch = db.row_for_org(con, "batches", user["org_id"], run["batch_id"]) or {}
    db.log(con, user["org_id"], user["id"], "열람", f"run:{run_id}/site:{idx}")
    return HTMLResponse(views.site_page(user, run, batch, 사이트[idx], idx))


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


# ── 상담 ──────────────────────────────────────────────
# 개인정보가 들어오는 유일한 자리다. 동의 없이 저장하지 않고, 연락처 전체 열람은
# 감사 로그에 '개인정보 열람' 으로 따로 남기며, 심의로는 조건만 넘긴다.
def _consults_html(con, user, msg: str = "", err: str = "",
                   status: int = 200) -> HTMLResponse:
    rows = db.rows_for_org(con, "consults", user["org_id"])
    return HTMLResponse(
        views.consults_page(user, rows, orgdata.load_settings(con, user["org_id"]), msg, err),
        status_code=status)


@app.get("/consults", response_class=HTMLResponse)
def list_consults(user=Depends(current_user), con=Depends(_con)):
    return _consults_html(con, user)


@app.post("/consults", response_class=HTMLResponse)
def add_consult(고객명: str = Form(...), 고객전화번호: str = Form(""),
                거주지: str = Form(""), 근무지: str = Form(""), 동의: str = Form(""),
                희망지역: str = Form(""), 희망평수: str = Form(""),
                희망상권: list[str] = Form(default=[]),
                보증금_만원: str = Form(""), 권리금_만원: str = Form(""),
                투자금형태: str = Form(""), 운영형태: str = Form(""),
                메모: str = Form(""),
                user=Depends(current_user), con=Depends(_con)):
    이름 = 고객명.strip()
    if not 이름:
        return _consults_html(con, user, err="고객명을 넣으십시오.", status=400)
    if not 동의.strip():
        # 브라우저의 required 는 우회할 수 있다. 개인정보는 서버에서도 막는다.
        return _consults_html(con, user, err="개인정보 수집·이용 동의를 받아야 저장할 수 "
                              "있습니다. 동의 없이 연락처를 남기지 마십시오.", status=400)
    if not 고객전화번호.strip():
        return _consults_html(con, user, err="연락처를 넣으십시오.", status=400)

    st = orgdata.load_settings(con, user["org_id"])
    for 이름표, 값, 표 in [("투자금 형태", 투자금형태, st.get("투자금형태") or {}),
                       ("운영 형태", 운영형태, st.get("운영형태") or {})]:
        if 값.strip() and 값.strip() not in 표:
            # 표에 없는 값은 파이프라인이 조용히 무시한다. 저장 전에 막는 게 낫다.
            return _consults_html(con, user, err=f"설정에 {이름표} '{값}' 가 없습니다.",
                                  status=400)

    고른상권 = [x for x in 희망상권 if x in consults.상권유형]
    cur = con.execute(
        "INSERT INTO consults (org_id, 고객명, 고객전화번호, 거주지, 근무지, 동의, "
        "희망지역, 희망평수, 희망상권, 보증금_만원, 권리금_만원, 투자금형태, 운영형태, "
        "메모, created_by) VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,?,?)",
        (user["org_id"], 이름, 고객전화번호.strip(), 거주지.strip(), 근무지.strip(),
         ", ".join(consults.split_list(희망지역)), _num(희망평수),
         ", ".join(고른상권), _num(보증금_만원), _num(권리금_만원),
         투자금형태.strip(), 운영형태.strip(), 메모.strip(), user["id"]))
    # 감사 로그에 고객명을 남기지 않는다 — 로그는 관리자 전원이 본다
    db.log(con, user["org_id"], user["id"], "상담 등록", f"consult:{cur.lastrowid}")
    con.commit()
    return RedirectResponse("/consults", status_code=303)


@app.get("/consults/{consult_id}", response_class=HTMLResponse)
def view_consult(consult_id: int, user=Depends(current_user), con=Depends(_con)):
    row = db.row_for_org(con, "consults", user["org_id"], consult_id)
    if not row:
        raise HTTPException(404, "없는 상담입니다")
    runs = db.rows_for_org(con, "runs", user["org_id"], "consult_id = ?", (consult_id,))
    batches = {b["id"]: b for b in db.rows_for_org(con, "batches", user["org_id"])}
    # 이 화면은 연락처 전체를 보여 준다. 목록의 '열람' 과 구분해서 남긴다.
    db.log(con, user["org_id"], user["id"], "개인정보 열람", f"consult:{consult_id}")
    return HTMLResponse(views.consult_page(
        user, row, orgdata.load_settings(con, user["org_id"]), runs, batches))


@app.post("/consults/{consult_id}/delete")
def delete_consult(consult_id: int, user=Depends(current_user), con=Depends(_con)):
    row = db.row_for_org(con, "consults", user["org_id"], consult_id)
    if not row:
        raise HTTPException(404, "없는 상담입니다")
    con.execute("DELETE FROM consults WHERE id = ? AND org_id = ?",
                (consult_id, user["org_id"]))
    # 상담이 파기돼도 심의는 남는다(runs.consult_id 는 NULL 이 된다).
    # 심의 결과에 개인정보가 없으므로 함께 지울 이유가 없다.
    db.log(con, user["org_id"], user["id"], "상담 파기", f"consult:{consult_id}")
    con.commit()
    return RedirectResponse("/consults", status_code=303)


# ── 기존점 ────────────────────────────────────────────
def _stores_html(con, user, msg: str = "", err: str = "", status: int = 200) -> HTMLResponse:
    stores = db.rows_for_org(con, "stores", user["org_id"])
    return HTMLResponse(
        views.stores_page(user, stores, orgdata.readiness(con, user["org_id"]), msg, err),
        status_code=status)


@app.get("/stores", response_class=HTMLResponse)
def list_stores(user=Depends(current_user), con=Depends(_con)):
    return _stores_html(con, user)


@app.post("/stores")
def add_store(점포명: str = Form(...), 월매출_만원: str = Form(""),
              기준점포: str = Form("N"), 위도: str = Form(""), 경도: str = Form(""),
              좌석수: str = Form(""), 월임대료_만원: str = Form(""),
              전용면적_평: str = Form(""), 주소: str = Form(""),
              user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_RUN)
    이름 = 점포명.strip()
    if not 이름:
        return _stores_html(con, user, err="점포명을 넣으십시오.", status=400)
    매출, lat, lon = _num(월매출_만원), _num(위도), _num(경도)
    if 매출 is None or 매출 <= 0:
        return _stores_html(con, user, err=f"{이름}: 월매출이 없으면 추정에 쓰이지 "
                            "않습니다. 실매출을 넣으십시오.", status=400)
    if lat is None or lon is None:
        return _stores_html(con, user, err=f"{이름}: 좌표가 없으면 M1 등시선을 그릴 수 "
                            "없어 회귀 표본에서 빠집니다. 위도·경도를 넣으십시오.",
                            status=400)
    con.execute(
        "INSERT INTO stores (org_id, 점포명, 주소, 위도, 경도, 기준점포, 월매출_만원, "
        "좌석수, 월임대료_만원, 전용면적_평) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user["org_id"], 이름, 주소.strip(), lat, lon,
         "Y" if str(기준점포).upper().startswith(("Y", "예")) else "N",
         매출, _num(좌석수), _num(월임대료_만원), _num(전용면적_평)))
    db.log(con, user["org_id"], user["id"], "기존점 추가", 이름)
    con.commit()
    return RedirectResponse("/stores", status_code=303)


@app.post("/stores/{store_id}/delete")
def delete_store(store_id: int, user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_RUN)
    row = db.row_for_org(con, "stores", user["org_id"], store_id)
    if not row:
        raise HTTPException(404, "없는 기존점입니다")
    con.execute("DELETE FROM stores WHERE id = ? AND org_id = ?",
                (store_id, user["org_id"]))
    db.log(con, user["org_id"], user["id"], "기존점 삭제", row["점포명"])
    con.commit()
    return RedirectResponse("/stores", status_code=303)


# ── 설정 ──────────────────────────────────────────────
@app.get("/settings", response_class=HTMLResponse)
def view_settings(user=Depends(current_user), con=Depends(_con)):
    return HTMLResponse(views.settings_page(user, orgdata.load_settings(con, user["org_id"])))


@app.post("/settings", response_class=HTMLResponse)
def save_settings(브랜드: str = Form(""), 자사브랜드티어: str = Form("동일가격대"),
                  좌석수_기본: str = Form(""), 영업일수: str = Form(""),
                  원재료율: str = Form(""), 로열티율: str = Form(""),
                  광고분담금율: str = Form(""), 기타변동비율: str = Form(""),
                  고정인건비_월_만원: str = Form(""), 기타_월_만원: str = Form(""),
                  user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_RUN)
    cur = orgdata.load_settings(con, user["org_id"])
    v = dict(cur["운영"]["변동비"])
    for k, raw in (("원재료율", 원재료율), ("로열티율", 로열티율),
                   ("광고분담금율", 광고분담금율), ("기타변동비율", 기타변동비율)):
        n = _num(raw, v[k])
        v[k] = min(1.0, max(0.0, n))

    # BEP = F ÷ (1 − v). v 가 1 이면 0 으로 나누고, 1 을 넘으면 팔수록 손해라는
    # 뜻인데 판정은 음수 BEP 로 조용히 통과가 된다. 여기서 막는다.
    if sum(v.values()) >= 1:
        return HTMLResponse(
            views.settings_page(user, cur, err=
                                f"변동비 합이 {sum(v.values()) * 100:.1f}% 입니다 — "
                                "100% 미만이어야 BEP 를 계산할 수 있습니다. 저장하지 않았습니다."),
            status_code=400)

    새 = orgdata.merge(cur, {
        "브랜드": 브랜드.strip(),
        "자사브랜드티어": 자사브랜드티어.strip() or cur.get("자사브랜드티어", ""),
        "좌석수_기본": _num(좌석수_기본, cur.get("좌석수_기본")),
        "영업일수": _num(영업일수, cur.get("영업일수")),
        "운영": {"변동비": v, "고정비": {
            "고정인건비_월_만원": _num(고정인건비_월_만원,
                                cur["운영"]["고정비"]["고정인건비_월_만원"]),
            "기타_월_만원": _num(기타_월_만원, cur["운영"]["고정비"]["기타_월_만원"]),
        }},
    })
    orgdata.save_settings(con, user["org_id"], 새)
    db.log(con, user["org_id"], user["id"], "설정 변경", "", f"변동비 합 {sum(v.values())*100:.1f}%")
    con.commit()
    return HTMLResponse(views.settings_page(user, 새, "저장했습니다. 다음 심의부터 적용됩니다."))


# ── 팀 ────────────────────────────────────────────────
def _team_html(con, user, msg: str = "", err: str = "", status: int = 200) -> HTMLResponse:
    users = db.rows_for_org(con, "users", user["org_id"])
    return HTMLResponse(
        views.team_page(user, users, org_of(con, user),
                        plans.seats_used(con, user["org_id"]), msg, err),
        status_code=status)


@app.get("/team", response_class=HTMLResponse)
def view_team(user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_MANAGE)
    return _team_html(con, user)


@app.post("/team", response_class=HTMLResponse)
def add_member(email: str = Form(...), name: str = Form(""),
               role: str = Form("영업"), password: str = Form(...),
               user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_MANAGE)
    org = org_of(con, user)
    if role not in plans.ROLES:
        return _team_html(con, user, err=f"역할은 {', '.join(plans.ROLES)} 중 하나여야 합니다.",
                          status=400)
    if len(password) < 8:
        return _team_html(con, user, err="임시 비밀번호는 8자 이상으로 하십시오.", status=400)
    ok, why = plans.seat_check(org["plan"], plans.seats_used(con, user["org_id"]))
    if not ok:
        return _team_html(con, user, err=why, status=402)
    try:
        con.execute(
            "INSERT INTO users (org_id, email, name, role, pw_hash) VALUES (?,?,?,?,?)",
            (user["org_id"], email.strip().lower(), name.strip(), role,
             auth.hash_pw(password)))
    except sqlite3.IntegrityError:
        # email 은 전 조직에서 UNIQUE 다. 다른 조직에 있는 계정인지까지는 말하지 않는다.
        return _team_html(con, user, err="이미 쓰이고 있는 이메일입니다.", status=409)
    db.log(con, user["org_id"], user["id"], "구성원 추가", email.strip().lower(), role)
    con.commit()
    return RedirectResponse("/team", status_code=303)


@app.post("/team/{user_id}/toggle", response_class=HTMLResponse)
def toggle_member(user_id: int, user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_MANAGE)
    target = db.row_for_org(con, "users", user["org_id"], user_id)
    if not target:
        raise HTTPException(404, "없는 구성원입니다")
    if target["id"] == user["id"]:
        # 자기를 비활성화하면 조직에 관리자가 없는 상태로 잠길 수 있다
        return _team_html(con, user, err="자기 계정은 바꿀 수 없습니다.", status=400)
    새 = 0 if target["active"] else 1
    if 새:
        ok, why = plans.seat_check(org_of(con, user)["plan"],
                                   plans.seats_used(con, user["org_id"]))
        if not ok:
            return _team_html(con, user, err=why, status=402)
    con.execute("UPDATE users SET active = ? WHERE id = ? AND org_id = ?",
                (새, user_id, user["org_id"]))
    if not 새:
        # 비활성화는 세션까지 끊는다 — 안 끊으면 쿠키를 가진 브라우저가 계속 들어온다
        con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.log(con, user["org_id"], user["id"],
           "구성원 활성화" if 새 else "구성원 비활성화", target["email"])
    con.commit()
    return RedirectResponse("/team", status_code=303)


@app.get("/audit", response_class=HTMLResponse)
def view_audit(user=Depends(current_user), con=Depends(_con)):
    require_role(user, plans.CAN_MANAGE)
    rows = db.rows_for_org(con, "audit", user["org_id"])[:300]
    users = {u["id"]: u for u in db.rows_for_org(con, "users", user["org_id"])}
    return HTMLResponse(views.audit_page(user, rows, users))


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    ok, why = jobs.available()
    # 파이프라인 리비전을 함께 낸다. 판정이 알고리즘 판에 따라 달라지므로,
    # 어떤 판이 그 판정을 냈는지 나중에 확인할 수 있어야 한다(이미지 빌드 시 주입).
    rev = os.environ.get("STORE_SCOUT_PIPELINE_REV", "unknown")
    return f"ok pipeline={'yes' if ok else 'no'} rev={rev} {why}".strip()
