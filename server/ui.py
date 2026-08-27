#!/usr/bin/env python3
"""
디자인 시스템 · 레이아웃 · 조각들

밝고 깔끔한 쪽으로 잡았다. 흰 바탕, 옅은 회색 경계, 넉넉한 여백, 한 가지 강조색.

강조색을 파랑(#2563eb)으로 둔 데는 기능적 이유가 있다. 이 화면의 주인공은
**판정**이고 판정은 통과(초록)·보류(주황)·부결(빨강) 세 색을 쓴다. 브랜드색이
붉은 계열이면 부결과 부딪혀 어느 쪽이 경고인지 흐려진다. 강조색은 판정 색과
겹치지 않는 자리에 있어야 한다.

웹폰트를 걸지 않는다. 시스템 글꼴이 한글을 이미 잘 그리고, 외부 요청이 하나
줄면 첫 화면이 그만큼 빨리 뜬다.
"""
from __future__ import annotations

import html

E = lambda s: html.escape(str(s if s is not None else ""))

CSS = """
:root{
  --bg:#ffffff; --soft:#f7f8fa; --sunken:#f1f3f6;
  --line:#e6e8ec; --line-2:#d9dde3;
  --ink:#16181d; --body:#3d4350; --mute:#7b8494;
  --pri:#2563eb; --pri-ink:#1d4ed8; --pri-soft:#eff5ff; --pri-line:#bfd6ff;
  --ok:#0f7b52; --ok-soft:#e7f6ef; --warn:#a76900; --warn-soft:#fdf3e2;
  --no:#c02626; --no-soft:#fdeeee;
  --r:10px; --r-sm:7px;
  --shadow:0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.04);
  --maxw:1120px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  /* 내용이 짧은 화면(로그인·빈 목록)에서 푸터가 중간에 떠 있지 않게 한다 */
  margin:0;min-height:100vh;display:flex;flex-direction:column;
  background:var(--soft);color:var(--ink);
  font:400 15px/1.6 -apple-system,BlinkMacSystemFont,'Pretendard','Apple SD Gothic Neo',
       'Malgun Gothic',Roboto,'Helvetica Neue',sans-serif;
  letter-spacing:-.011em;-webkit-font-smoothing:antialiased;
}
a{color:var(--pri);text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--pri);outline-offset:2px;border-radius:4px}
h1,h2,h3{margin:0;letter-spacing:-.022em;font-weight:650;color:var(--ink)}
h1{font-size:26px;line-height:1.3}
h2{font-size:17px}
h3{font-size:14px}
p{margin:0}
.mono{font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.num{font-variant-numeric:tabular-nums}

.skip{position:absolute;left:-9999px;top:0;z-index:99;padding:10px 16px;
  background:var(--pri);color:#fff;font-weight:600;border-radius:0 0 var(--r-sm) 0}
.skip:focus{left:0;top:0;text-decoration:none}
.vh{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;
  clip-path:inset(50%);white-space:nowrap;border:0}

/* ── 뼈대 ─────────────────────────── */
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
header.top{background:var(--bg);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:40}
.top-in{display:flex;align-items:center;gap:8px;height:58px}
.brand{display:flex;align-items:center;gap:9px;font-weight:650;color:var(--ink);font-size:15px}
.brand:hover{text-decoration:none}
.brand .mk{width:26px;height:26px;border-radius:8px;background:var(--pri);color:#fff;
  display:grid;place-items:center;font-size:13px;font-weight:700}
.nav{display:flex;gap:2px;margin-left:18px}
.nav a{padding:7px 12px;border-radius:var(--r-sm);color:var(--body);font-size:14px;font-weight:500}
.nav a:hover{background:var(--sunken);text-decoration:none}
.nav a.on{background:var(--pri-soft);color:var(--pri-ink)}
.top-end{margin-left:auto;display:flex;align-items:center;gap:10px}
.who{font-size:13px;color:var(--mute)}
.who b{color:var(--body);font-weight:600}
main{flex:1;padding:28px 0 72px}
.page-h{display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.page-h .sub{margin-top:5px;color:var(--mute);font-size:14px;max-width:70ch}
.page-h .acts{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}

/* ── 버튼 ─────────────────────────── */
button,.btn{
  font:inherit;font-size:14px;font-weight:550;line-height:1;border-radius:var(--r-sm);
  padding:9px 14px;cursor:pointer;border:1px solid var(--line-2);background:var(--bg);
  color:var(--ink);display:inline-flex;align-items:center;gap:6px;
  transition:background .13s,border-color .13s,box-shadow .13s;box-shadow:var(--shadow)
}
button:hover,.btn:hover{background:var(--sunken);text-decoration:none}
button:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}
.pri{background:var(--pri);border-color:var(--pri);color:#fff}
.pri:hover{background:var(--pri-ink);border-color:var(--pri-ink)}
.ghost{background:transparent;box-shadow:none;border-color:transparent;color:var(--body)}
.ghost:hover{background:var(--sunken)}
.danger{color:var(--no);border-color:#f0c9c9}
.sm{font-size:13px;padding:6px 11px}

/* ── 카드 · 표 ─────────────────────── */
.card{background:var(--bg);border:1px solid var(--line);border-radius:var(--r);
  box-shadow:var(--shadow);margin-bottom:18px}
.card > .hd{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;
  align-items:center;gap:12px;flex-wrap:wrap}
.card > .hd .acts{margin-left:auto;display:flex;gap:8px}
.card > .bd{padding:18px 20px}
/* 표는 자기 상자 안에서 가로로 넘긴다 — 페이지 본문이 옆으로 밀리지 않게 */
.card > .bd.tight{padding:0;overflow-x:auto}
.hint{color:var(--mute);font-size:13.5px;line-height:1.6;max-width:78ch}
.hint + .hint{margin-top:8px}

table{width:100%;border-collapse:collapse;font-size:14px}
td,th{white-space:nowrap}
td.wrap-cell{white-space:normal;min-width:22ch}
thead th{padding:9px 20px;text-align:left;font-size:11.5px;font-weight:600;color:var(--mute);
  letter-spacing:.05em;text-transform:uppercase;background:var(--soft);
  border-bottom:1px solid var(--line);white-space:nowrap}
tbody td{padding:12px 20px;border-bottom:1px solid var(--line);vertical-align:middle;color:var(--body)}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--soft)}
td.r,th.r{text-align:right}
td.strong{color:var(--ink);font-weight:550}
.empty{padding:40px 20px;text-align:center;color:var(--mute);font-size:14px}

/* ── 배지 · 상태 ───────────────────── */
.tag{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;
  font-size:12.5px;font-weight:600;white-space:nowrap}
.t-통과{background:var(--ok-soft);color:var(--ok)}
.t-보류{background:var(--warn-soft);color:var(--warn)}
.t-부결{background:var(--no-soft);color:var(--no)}
.t-대기,.t-실행중{background:var(--pri-soft);color:var(--pri-ink)}
.t-완료{background:var(--ok-soft);color:var(--ok)}
.t-실패{background:var(--no-soft);color:var(--no)}
.t-plain{background:var(--sunken);color:var(--body)}
.dot{width:6px;height:6px;border-radius:50%;background:currentColor}

/* ── 알림 ─────────────────────────── */
.note{border-radius:var(--r);padding:13px 16px;font-size:13.5px;line-height:1.65;
  display:flex;gap:11px;align-items:flex-start;margin-bottom:18px}
.note b{font-weight:650}
.n-info{background:var(--pri-soft);color:#1e3a8a;border:1px solid var(--pri-line)}
.n-warn{background:var(--warn-soft);color:#7c4a03;border:1px solid #f0dcb4}
.n-err{background:var(--no-soft);color:#8f1d1d;border:1px solid #f3cccc}
.note .ic{flex:none;font-weight:700}

/* ── 통계 타일 ─────────────────────── */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--bg);border:1px solid var(--line);border-radius:var(--r);padding:15px 17px;
  box-shadow:var(--shadow)}
.tile .k{font-size:12.5px;color:var(--mute);font-weight:500}
.tile .v{margin-top:5px;font-size:25px;font-weight:680;letter-spacing:-.03em;
  font-variant-numeric:tabular-nums;color:var(--ink)}
.tile .v small{font-size:14px;font-weight:500;color:var(--mute);margin-left:3px}
.tile.acc .v{color:var(--pri-ink)}
.bar{height:5px;border-radius:3px;background:var(--sunken);margin-top:10px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--pri);border-radius:3px}
.bar.hot i{background:var(--warn)}
.bar.full i{background:var(--no)}

/* ── 폼 ───────────────────────────── */
.field{margin-bottom:15px}
.field > .lb{display:flex;align-items:baseline;gap:7px;margin-bottom:6px;flex-wrap:wrap}
label{font-size:13.5px;font-weight:600;color:var(--body)}
.req{font-size:11.5px;color:var(--no);font-weight:600}
.opt{font-size:11.5px;color:var(--mute);font-weight:500}
input,select,textarea{
  font:inherit;font-size:14px;color:var(--ink);background:var(--bg);width:100%;
  border:1px solid var(--line-2);border-radius:var(--r-sm);padding:9px 11px;
  transition:border-color .13s,box-shadow .13s
}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--pri);
  box-shadow:0 0 0 3px var(--pri-soft)}
input[type=number]{font-variant-numeric:tabular-nums;text-align:right}
input[type=file]{padding:8px;background:var(--soft);cursor:pointer}
.help{margin-top:6px;font-size:12.5px;color:var(--mute);line-height:1.55}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:0 18px}
@media(max-width:720px){
  .grid2,.grid3{grid-template-columns:1fr}
  /* 좁은 화면에서 상단이 글자 단위로 접히던 것을 막는다.
     메뉴는 줄바꿈 대신 가로 스크롤로 넘긴다 */
  .top-in{height:auto;padding:10px 0;flex-wrap:wrap;row-gap:8px}
  .brand{white-space:nowrap}
  .nav{order:3;width:100%;margin-left:0;overflow-x:auto;scrollbar-width:none;
    -webkit-overflow-scrolling:touch}
  .nav::-webkit-scrollbar{display:none}
  .nav a{white-space:nowrap;flex:0 0 auto}
  .top-end{gap:8px}
  .who{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:44vw}
  .wrap{padding:0 16px}
  .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
}
.inline-form{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}
.inline-form .field{margin-bottom:0;flex:1 1 160px}

/* ── 진행 단계 ─────────────────────── */
.steps{display:flex;gap:0;flex-wrap:wrap;border:1px solid var(--line);border-radius:var(--r);
  overflow:hidden;background:var(--bg);box-shadow:var(--shadow);margin-bottom:18px}
.step{flex:1 1 180px;padding:14px 17px;border-left:1px solid var(--line);position:relative}
.step:first-child{border-left:0}
.step .n{font-size:11.5px;font-weight:700;color:var(--mute);letter-spacing:.06em}
.step .t{margin-top:3px;font-weight:600;font-size:14px;color:var(--ink)}
.step .d{margin-top:2px;font-size:12.5px;color:var(--mute)}
.step.done{background:var(--ok-soft)}
.step.done .n,.step.done .t{color:var(--ok)}
.step.todo{background:var(--warn-soft)}
.step.todo .n,.step.todo .t{color:var(--warn)}

/* 표 안에서 쓰는 버튼. .ghost 는 테두리가 없어 글자처럼 보인다 */
.row-act{font-size:13px;padding:6px 11px}

footer{border-top:1px solid var(--line);background:var(--bg);padding:20px 0;
  font-size:12.5px;color:var(--mute)}
"""


def tag(text: str, kind: str = "plain") -> str:
    return f'<span class="tag t-{E(kind)}">{E(text)}</span>'


def note(kind: str, icon: str, body: str) -> str:
    return f'<div class="note n-{kind}"><span class="ic">{E(icon)}</span><div>{body}</div></div>'


def tile(k: str, v: str, unit: str = "", accent: bool = False, bar: tuple | None = None) -> str:
    b = ""
    if bar:
        used, cap = bar
        pct = min(100, round(used / cap * 100)) if cap else 0
        cls = "full" if pct >= 100 else ("hot" if pct >= 80 else "")
        b = f'<div class="bar {cls}"><i style="width:{pct}%"></i></div>'
    u = f"<small>{E(unit)}</small>" if unit else ""
    return (f'<div class="tile{" acc" if accent else ""}"><div class="k">{E(k)}</div>'
            f'<div class="v">{E(v)}{u}</div>{b}</div>')


def field(name: str, label: str, value="", kind: str = "text", *,
          required: bool = False, help_text: str = "", attrs: str = "",
          options: list | None = None) -> str:
    fid = f"f-{name}"
    req = '<span class="req">필수</span>' if required else '<span class="opt">선택</span>'
    hid = f"{fid}-help"
    desc = f' aria-describedby="{hid}"' if help_text else ""
    if options is not None:
        opts = "".join(
            f'<option value="{E(v)}"{" selected" if str(value) == str(v) else ""}>{E(t)}</option>'
            for v, t in options)
        ctl = f'<select id="{fid}" name="{E(name)}"{desc}{attrs}>{opts}</select>'
    else:
        ctl = (f'<input id="{fid}" name="{E(name)}" type="{E(kind)}" value="{E(value)}"'
               f'{" required" if required else ""}{desc} autocomplete="off"{attrs}/>')
    h = f'<div class="help" id="{hid}">{E(help_text)}</div>' if help_text else ""
    return (f'<div class="field"><div class="lb"><label for="{fid}">{E(label)}</label>{req}</div>'
            f'{ctl}{h}</div>')


# 인라인 파비콘. 파일 하나를 더 두지 않으려고 data URI 로 박는다
FAVICON = ("%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2032%2032'%3E"
           "%3Crect%20width='32'%20height='32'%20rx='8'%20fill='%232563eb'/%3E"
           "%3Ccircle%20cx='16'%20cy='16'%20r='8'%20fill='none'%20stroke='%23fff'%20"
           "stroke-width='2.5'/%3E%3Ccircle%20cx='16'%20cy='16'%20r='2.5'%20fill='%23fff'/%3E"
           "%3C/svg%3E")

NAV = [("/dashboard", "개요"), ("/runs", "심의"), ("/stores", "기존점"),
       ("/settings", "설정"), ("/team", "팀")]


def layout(title: str, body: str, user: dict | None = None, *,
           active: str = "", head: str = "") -> str:
    top = ""
    if user:
        links = "".join(
            f'<a href="{h}"{" class=on" if h == active else ""}>{E(t)}</a>'
            for h, t in NAV
            if h != "/team" or user.get("role") == "관리자")
        top = f"""<nav class="nav">{links}</nav>
      <div class="top-end">
        <span class="who"><b>{E(user['name'] or user['email'])}</b> · {E(user['role'])}</span>
        <form method="post" action="/logout" style="margin:0">
          <button class="ghost sm" type="submit">로그아웃</button></form>
      </div>"""
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="robots" content="noindex"/><meta name="color-scheme" content="light"/>
<meta name="theme-color" content="#ffffff"/>
<link rel="icon" href="data:image/svg+xml,{FAVICON}"/>
<title>{E(title)} · 출점심의</title>{head}
<style>{CSS}</style></head><body>
<a class="skip" href="#main">본문 바로가기</a>
<header class="top"><div class="wrap top-in">
  <a class="brand" href="/"><span class="mk">◎</span>출점심의</a>{top}
</div></header>
<main id="main"><div class="wrap">{body}</div></main>
<footer><div class="wrap">사내 한정 자료를 다룹니다 · 열람·내보내기 기록이 남습니다</div></footer>
</body></html>"""
