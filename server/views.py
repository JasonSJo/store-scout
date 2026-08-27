#!/usr/bin/env python3
"""
화면 — 서버가 그리는 HTML

상권분석 사이트와 같은 시각 언어(종이 도면·놋쇠 시그널)를 쓴다. 프레임워크를 얹지
않는다: 화면이 몇 개뿐이고, 빌드 단계가 없으면 배포가 그만큼 단순해진다.
"""
from __future__ import annotations

import html

from . import plans

CSS = """
:root{--bg:#efeae0;--bg-soft:#e6dfd1;--card:#f5f2ea;--border:#cabfad;--border-2:#ddd4c4;
 --fg:#17130f;--soft:#4b423a;--mute:#8a7f6e;--sig:#9a3b1b;--sig-ink:#6f2911;
 --sig-soft:#e8dbd1;--ok:#2f5d50;--warn:#b0822a;--no:#a8231c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);line-height:1.65;letter-spacing:-.01em;
 font-family:'IBM Plex Sans KR','Pretendard',-apple-system,'Malgun Gothic',sans-serif}
a{color:var(--sig);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.skip{position:absolute;left:-9999px;top:0;z-index:99;padding:10px 16px;
 background:var(--sig);color:#fff;font-weight:600}
.skip:focus{left:8px;top:8px}
h1,h2,h3{margin:0;font-family:'Hahmlet','Nanum Myeongjo',serif;letter-spacing:-.02em}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums}
header.top{background:var(--bg);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:30}
.top-in{display:flex;align-items:center;gap:14px;padding:13px 0;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;color:var(--fg)}
.brand .mk{width:26px;height:26px;border-radius:50%;background:var(--sig);color:#fff;
 display:grid;place-items:center;font-family:'IBM Plex Mono',monospace;font-size:13px}
.brand small{font-weight:400;color:var(--mute);font-size:12px}
.top-acts{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.who{font-size:12.5px;color:var(--mute)}
button,.btn{font:inherit;font-size:13.5px;font-weight:500;border-radius:2px;padding:8px 14px;
 cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--fg);
 display:inline-flex;align-items:center;gap:6px}
.primary{background:var(--sig);color:#fff;border-color:var(--sig)}
.sm{font-size:12.5px;padding:5px 10px}
input,select{font:inherit;font-size:13.5px;color:var(--fg);background:var(--card);
 border:1px solid var(--border);border-radius:2px;padding:8px 10px;width:100%}
.grade{background:#f7f2e6;border:1px solid var(--warn);border-left-width:3px;
 padding:11px 14px;margin:16px 0;font-size:13px;color:var(--soft)}
.grade b{color:var(--sig-ink)}
.card{border:1px solid var(--border);background:var(--card);padding:18px 20px;margin-top:16px}
.card h2{font-size:17px;margin-bottom:4px}
.meta{font-size:12.5px;color:var(--mute)}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}
th,td{padding:8px 10px;border-bottom:1px solid var(--border-2);text-align:left;vertical-align:top}
th{font-size:11px;font-family:'IBM Plex Mono',monospace;letter-spacing:.12em;
 text-transform:uppercase;color:var(--mute);font-weight:500}
td.num{text-align:right;font-family:'IBM Plex Mono',monospace;font-variant-numeric:tabular-nums}
.v{font-weight:600;white-space:nowrap}.v-통과{color:var(--ok)}.v-보류{color:var(--warn)}.v-부결{color:var(--no)}
.quota{display:flex;gap:22px;flex-wrap:wrap;margin-top:10px}
.quota div{font-size:13px}.quota b{font-family:'IBM Plex Mono',monospace;font-size:20px;color:var(--sig-ink)}
.note{font-size:12.5px;color:var(--mute);margin:8px 0 0;max-width:78ch}
.err{border-left:3px solid var(--no);background:#fbf0ee;padding:10px 13px;font-size:13px;margin-top:12px}
.f-h{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:5px}
label{font-size:12.5px;font-weight:500;color:var(--soft)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px 18px}
@media(max-width:680px){.row{grid-template-columns:1fr}}
footer{border-top:1px solid var(--border);margin-top:40px;padding:18px 0;font-size:12px;color:var(--mute)}
"""

E = lambda s: html.escape(str(s if s is not None else ""))


def layout(title: str, body: str, user: dict | None = None, head: str = "") -> str:
    acts = ""
    if user:
        links = ['<a class="btn sm" href="/dashboard">분석</a>']
        if user["role"] in plans.CAN_MANAGE:
            links.append('<a class="btn sm" href="/audit">감사 로그</a>')
        acts = (f'<div class="top-acts"><span class="who">{E(user["name"] or user["email"])}'
                f' · {E(user["role"])}</span>{"".join(links)}'
                '<form method="post" action="/logout" style="margin:0">'
                '<button class="sm" type="submit">로그아웃</button></form></div>')
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="robots" content="noindex"/>
<title>{E(title)} · 출점심의</title>
{head}
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@500;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>{CSS}</style></head><body>
<a class="skip" href="#main">본문 바로가기</a>
<header class="top"><div class="wrap top-in">
  <a class="brand" href="/"><span class="mk">◎</span>출점심의<small>상권분석 구독</small></a>
  {acts}</div></header>
<main id="main" class="wrap">{body}</main>
<footer><div class="wrap">출점심의 · 사내 한정 자료를 다룹니다 · 열람 기록이 남습니다</div></footer>
</body></html>"""


def login_page(error: str = "") -> str:
    err = f'<div class="err">{E(error)}</div>' if error else ""
    return layout("로그인", f"""
<div class="card" style="max-width:420px;margin-top:48px">
  <h2>로그인</h2>
  <p class="note">조직 관리자가 만든 계정으로 들어갑니다.</p>
  {err}
  <form method="post" action="/login" style="margin-top:14px">
    <div class="f-h"><label for="email">이메일</label></div>
    <input id="email" name="email" type="email" autocomplete="username" required
      placeholder="예: ops@brand.co.kr…"/>
    <div class="f-h" style="margin-top:12px"><label for="password">비밀번호</label></div>
    <input id="password" name="password" type="password" autocomplete="current-password" required/>
    <button class="primary" type="submit" style="margin-top:16px;width:100%;justify-content:center">
      들어가기</button>
  </form>
</div>""")


def dashboard_page(user, org, runs, batches, used: int, seats: int) -> str:
    spec = plans.spec(org["plan"])
    cap_run = spec["월_분석"] if spec["월_분석"] is not None else "무제한"
    cap_seat = spec["좌석"] if spec["좌석"] is not None else "무제한"

    rows = []
    for r in runs[:60]:
        b = batches.get(r["batch_id"], {})
        st = r["status"]
        link = (f'<a href="/runs/{r["id"]}">{E(b.get("name", ""))}</a>'
                if st == "완료" else E(b.get("name", "")))
        rows.append(f"""<tr><td>{link}</td><td>{E(st)}</td>
          <td class="num">{r['billed_units']}</td><td>{E(r['mode'] or '—')}</td>
          <td class="mono" style="font-size:12px">{E(r['started_at'])}</td></tr>""")
    table = ("".join(rows) if rows else
             '<tr><td colspan="5" class="meta">아직 실행한 분석이 없습니다.</td></tr>')

    upload = ""
    if user["role"] in plans.CAN_RUN:
        upload = f"""
<div class="card">
  <h2>새 분석</h2>
  <p class="note">입력 화면에서 내보낸 <code>sites.csv</code> 를 올립니다.
    청구 단위는 <b>후보지 수</b>입니다 — 실패한 실행은 청구하지 않습니다.</p>
  <form method="post" action="/runs" enctype="multipart/form-data" style="margin-top:12px">
    <div class="row">
      <div><div class="f-h"><label for="name">묶음 이름</label></div>
        <input id="name" name="name" placeholder="예: 2026 3분기 수도권…"/></div>
      <div><div class="f-h"><label for="sites">후보지 CSV</label></div>
        <input id="sites" name="sites" type="file" accept=".csv" required/></div>
    </div>
    <button class="primary" type="submit" style="margin-top:14px">심의 실행</button>
  </form>
</div>"""
    else:
        upload = ('<div class="card"><h2>새 분석</h2><p class="note">'
                  '분석 실행은 운영팀 이상 권한이 필요합니다. 분석 건수가 과금 단위라 '
                  '누구나 돌리면 조직의 월 한도가 조용히 소진됩니다.</p></div>')

    return layout("분석", f"""
<div class="grade"><b>사내 한정 · 대외 배포 금지</b> — 이 화면의 산출물은 내부 의사결정
자료입니다. 가맹희망자에게 제공하는 <b>예상매출액 산정서와 수치를 혼용하지 마십시오.</b>
열람·내보내기 기록이 남습니다.</div>

<div class="card">
  <h2>{E(org['name'])}</h2>
  <div class="meta">{E(spec['이름'])} 플랜 · {E(spec['설명'])}</div>
  <div class="quota">
    <div>이번 달 분석<br/><b>{used}</b> / {cap_run}건</div>
    <div>좌석<br/><b>{seats}</b> / {cap_seat}</div>
  </div>
</div>
{upload}
<div class="card">
  <h2>실행 기록</h2>
  <table><thead><tr><th>묶음</th><th>상태</th><th>청구</th><th>모드</th><th>시작</th></tr></thead>
  <tbody>{table}</tbody></table>
</div>""", user)


def run_page(user, run, batch, summary, 등급: str) -> str:
    if run["status"] != "완료":
        detail = f'<div class="err">{E(run["error"])}</div>' if run["error"] else ""
        # 실행 중이면 화면이 상태를 따라간다. 자바스크립트 없이 meta refresh 로 —
        # 화면 몇 개짜리 제품에 폴링 스크립트를 얹을 이유가 없다.
        refresh = ('<meta http-equiv="refresh" content="3"/>'
                   if run["status"] in ("대기", "실행중") else "")
        도는중 = ('<p class="note">파이프라인이 도는 중입니다. 후보지 수에 따라 수 초에서 '
                '수 분이 걸립니다. 이 화면은 3초마다 스스로 새로 고칩니다.</p>'
                if refresh else "")
        return layout("분석", f"""
<div class="card"><h2>{E(batch.get('name',''))}</h2>
<div class="meta">상태 {E(run['status'])}</div>{도는중}{detail}</div>""", user, head=refresh)

    def rng(lo, hi):
        if lo is None or hi is None:
            return "—"
        return f"{lo:,.0f}~{hi:,.0f}"

    rows = "".join(f"""<tr>
      <td>{E(s['이름'])}</td>
      <td class="v v-{E(s['판정'])}">{E(s['판정'])}</td>
      <td class="num">{(s['S'] or 0):.1f}</td>
      <td class="num">{rng(s['월매출_하한'], s['월매출_상한'])}</td>
      <td class="num">{(s['BEP_만원'] or 0):,.0f}</td>
      <td class="num">{((s['margin'] or 0)*100):.1f}%</td>
      <td class="meta">{E('; '.join(s['사유']) or '—')}</td></tr>""" for s in summary["후보지"])

    return layout("분석 결과", f"""
<div class="grade"><b>{E(등급)}</b> — 매출은 <b>구간으로만</b> 표시합니다.
단일 숫자는 상담 자리에서 그대로 인용되기 때문입니다.
내려받는 파일명에는 <code>internal</code> 이 붙습니다.</div>

<div class="card">
  <h2>{E(batch.get('name',''))}</h2>
  <div class="meta">Mode {E(run['mode'])} · 후보지 {run['billed_units']}곳 ·
    통과 {summary['통과']} · 보류 {summary['보류']} · 부결 {summary['부결']}</div>
  <table><thead><tr><th>후보지</th><th>판정</th><th>S</th><th>월매출 구간(만원)</th>
    <th>BEP</th><th>margin</th><th>사유</th></tr></thead><tbody>{rows}</tbody></table>
  <p style="margin-top:16px"><a class="btn" href="/runs/{run['id']}/report">심의표 내려받기</a></p>
</div>""", user)


def audit_page(user, rows, users) -> str:
    tr = "".join(f"""<tr><td class="mono" style="font-size:12px">{E(r['at'])}</td>
      <td>{E((users.get(r['user_id']) or {}).get('email','—'))}</td>
      <td>{E(r['action'])}</td><td class="mono" style="font-size:12px">{E(r['target'])}</td>
      <td class="meta">{E(r['detail'])}</td></tr>""" for r in rows)
    return layout("감사 로그", f"""
<div class="card">
  <h2>감사 로그</h2>
  <p class="note">사내 한정 자료를 다루므로 열람 기록은 기능이 아니라 의무입니다.
    최근 300건을 보여 줍니다.</p>
  <table><thead><tr><th>시각</th><th>사용자</th><th>행위</th><th>대상</th><th>비고</th></tr></thead>
  <tbody>{tr or '<tr><td colspan="5" class="meta">기록이 없습니다.</td></tr>'}</tbody></table>
</div>""", user)
