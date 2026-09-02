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
import re

E = lambda s: html.escape(str(s if s is not None else ""))

CSS = """
:root{
  /* 스스닷컴 측량 도면 — 공개 페이지(shared/base.css)와 같은 값이다.
     제품이 하나면 화면도 하나여야 한다. 전에는 여기만 파란 SaaS 였고,
     로그인하면 딴 사이트에 온 것 같았다.
     ⚠ 같은 값이 두 벌 있다. 한쪽만 고치면 조용히 어긋난다 — 바꿀 일이 있으면
       cafe-trade-area/shared/base.css 도 함께. (저장소가 하나가 됐으니 언젠가
       한 파일로 합칠 수 있다.) */
  --bg:#f5f2ea; --soft:#efeae0; --sunken:#e6dfd1;
  --line:#cabfad; --line-2:#ddd4c4;
  --ink:#17130f; --body:#4b423a; --mute:#8a7f6e;
  /* 시그널은 로스트 시에나 하나다. 파랑을 쓰지 않는다 — 도면에 파랑은 없다. */
  --pri:#9a3b1b; --pri-ink:#6f2911; --pri-soft:#e8dbd1; --pri-line:#c9a992;
  --ok:#2f5d50; --ok-soft:#dde8e3; --warn:#b0822a; --warn-soft:#f0e6d0;
  --no:#a8231c; --no-soft:#f2ddda;
  /* 도면은 각지고 그림자가 없다. 종이 위에 인쇄된 것이지 떠 있는 것이 아니다. */
  --r:2px; --r-sm:2px;
  --shadow:none;
  --maxw:1120px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  /* 내용이 짧은 화면(로그인·빈 목록)에서 푸터가 중간에 떠 있지 않게 한다 */
  margin:0;min-height:100vh;display:flex;flex-direction:column;
  background:var(--soft);color:var(--ink);
  font:400 15px/1.65 'IBM Plex Sans KR','Pretendard',-apple-system,'Apple SD Gothic Neo',
       'Malgun Gothic',sans-serif;
  letter-spacing:-.01em;-webkit-font-smoothing:antialiased;
  /* 한글은 낱자 사이 어디서나 끊긴다 — keep-all 로 띄어쓰기에서만 끊고,
     break-word 로 긴 라틴 토막이 칸을 넘치지 않게 막는다. */
  word-break:keep-all;overflow-wrap:break-word;
  /* 종이 그레인 — 평면 색이 인쇄물처럼 앉는다. 공개 페이지와 같은 것. */
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.82' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='220' height='220' filter='url(%23n)' opacity='.16'/%3E%3C/svg%3E");
}
a{color:var(--pri);text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--pri);outline-offset:2px;border-radius:4px}
h1,h2,h3{margin:0;font-family:'Hahmlet','Nanum Myeongjo',serif;letter-spacing:-.02em;font-weight:700;color:var(--ink)}
h1{font-size:26px;line-height:1.3}
h2{font-size:17px}
h3{font-size:14px}
p{margin:0}
.mono{font-family:'IBM Plex Mono',ui-monospace,'SF Mono',Menlo,monospace;font-variant-numeric:tabular-nums}
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
.brand .mk{width:26px;height:26px;border-radius:50%;background:var(--pri);color:#fff;
  display:grid;place-items:center;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px}
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
/* 도면에 알약은 없다 — 각진 라벨에 테두리를 준다. 배경만으로 가르면
   종이 바탕에서 통과와 보류가 비슷해 보인다. */
.tag{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:2px;
  border:1px solid currentColor;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12px;font-weight:500;letter-spacing:.02em;white-space:nowrap}
.t-통과{background:var(--ok-soft);color:var(--ok)}
.t-보류{background:var(--warn-soft);color:var(--warn)}
/* 부결은 이 화면에서 가장 강한 신호다 — 유일하게 채워 넣는다 */
.t-부결{background:var(--no);color:#fff;border-color:var(--no)}
.t-대기,.t-실행중{background:var(--pri-soft);color:var(--pri-ink)}
.t-완료{background:var(--ok-soft);color:var(--ok)}
.t-실패{background:var(--no);color:#fff;border-color:var(--no)}
.t-plain{background:transparent;color:var(--mute)}
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
.tile .k{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--mute);font-weight:500}
.tile .v{margin-top:5px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:25px;font-weight:500;letter-spacing:-.02em;
  font-variant-numeric:tabular-nums;color:var(--ink)}
.tile .v.txt{font-family:inherit;font-size:22px;font-weight:600;letter-spacing:-.03em}
.tile .v small{font-size:14px;font-weight:500;color:var(--mute);margin-left:3px}
.tile.acc .v{color:var(--pri-ink)}
.bar{height:5px;background:var(--sunken);margin-top:10px;overflow:hidden;border:1px solid var(--line-2)}
.bar i{display:block;height:100%;background:var(--pri)}
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

/* ── 체크박스 · 칩 ─────────────────── */
/* 파일 선택은 브라우저 기본 모양이라 혼자 튄다. 버튼 부분만 우리 버튼처럼 만든다 */
input[type=file]{padding:8px 10px;background:var(--bg);cursor:pointer}
input[type=file]::file-selector-button{font:inherit;font-size:13px;font-weight:550;
  margin-right:11px;padding:6px 12px;border-radius:var(--r-sm);cursor:pointer;
  border:1px solid var(--line-2);background:var(--soft);color:var(--ink)}
input[type=file]::file-selector-button:hover{background:var(--sunken)}

.check{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--body);
  cursor:pointer;line-height:1.4}
.check input{width:16px;height:16px;accent-color:var(--pri);margin:0;flex:0 0 auto}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.check.chip{border:1px solid var(--line-2);border-radius:2px;padding:7px 13px 7px 11px;
  background:var(--bg);transition:border-color .13s,background .13s}
.check.chip:hover{background:var(--sunken)}
.check.chip:has(input:checked){border-color:var(--pri);background:var(--pri-soft);
  color:var(--pri-ink);font-weight:550}
.lb-t{font-weight:600;font-size:13.5px;color:var(--ink)}
/* 긴 폼을 덩어리로 끊는 소제목 */
h3.sec{margin:22px 0 12px;font-size:12px;font-weight:700;letter-spacing:.07em;
  color:var(--mute);text-transform:none;padding-bottom:8px;
  border-bottom:1px solid var(--line)}
form > h3.sec:first-child{margin-top:0}

/* ── 파이프라인 산출물(마크다운) ────── */
.md{font-size:14px;color:var(--body);line-height:1.7}
.md > :first-child{margin-top:0}
.md h2,.md h3,.md h4,.md h5{margin:20px 0 8px;color:var(--ink);line-height:1.35}
.md h2{font-size:17px}.md h3{font-size:15px}.md h4,.md h5{font-size:14px}
.md p{margin:8px 0}
.md ul{margin:8px 0;padding-left:19px}
.md li{margin:3px 0}
.md blockquote{margin:12px 0;padding:11px 15px;border-left:3px solid var(--line-2);
  background:var(--soft);border-radius:0 var(--r-sm) var(--r-sm) 0;color:var(--mute);
  font-size:13.5px}
.md code{font-family:var(--mono);font-size:12.5px;background:var(--sunken);
  padding:1px 5px;border-radius:4px}
.md-table{overflow-x:auto;margin:12px 0;border:1px solid var(--line);
  border-radius:var(--r-sm)}
.md-table table{font-size:13.5px}
.md-table thead th{padding:8px 13px}
.md-table td{padding:9px 13px}

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
    # 수치는 모노로 조판한다(자릿수가 맞아야 표가 읽힌다). 값이 숫자로 시작하지
    # 않으면 — '매출 추정 모드 = B(앵커링)' 같은 것 — 본문 서체로 둔다. 한글에
    # 모노를 걸면 괄호만 모노가 되고 자간이 벌어져 글자가 흩어져 보인다.
    글자값 = not str(v).strip()[:1].isdigit()
    return (f'<div class="tile{" acc" if accent else ""}"><div class="k">{E(k)}</div>'
            f'<div class="v{" txt" if 글자값 else ""}">{E(v)}{u}</div>{b}</div>')


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
# 공개 페이지(스스닷컴 소개·입력·상담)와 같은 마크 — 종이 바탕에 점선 등시선.
FAVICON = ("%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2032%2032'%3E"
           "%3Crect%20width='32'%20height='32'%20fill='%23efeae0'/%3E"
           "%3Ccircle%20cx='16'%20cy='16'%20r='11'%20fill='none'%20stroke='%239a3b1b'%20"
           "stroke-width='1.4'%20stroke-dasharray='3%203'/%3E"
           "%3Ccircle%20cx='16'%20cy='16'%20r='3.6'%20fill='%239a3b1b'/%3E%3C/svg%3E")

def checkbox(name: str, label: str, checked: bool = False, *,
             help_text: str = "", required: bool = False, value: str = "1") -> str:
    fid = f"f-{name}"
    hid = f"{fid}-help"
    desc = f' aria-describedby="{hid}"' if help_text else ""
    h = f'<div class="help" id="{hid}" style="margin-left:26px">{E(help_text)}</div>' if help_text else ""
    return (f'<div class="field"><label class="check" for="{fid}">'
            f'<input id="{fid}" name="{E(name)}" type="checkbox" value="{E(value)}"'
            f'{" checked" if checked else ""}{" required" if required else ""}{desc}/>'
            f'<span>{E(label)}</span></label>{h}</div>')


def checks(name: str, label: str, options, chosen=(), *, help_text: str = "") -> str:
    """같은 이름을 여럿 보내는 다중 선택. 고르지 않으면 그 조건으로 거르지 않는다."""
    골라진 = {str(x) for x in (chosen or [])}
    상자 = "".join(
        f'<label class="check chip" for="f-{name}-{i}">'
        f'<input id="f-{name}-{i}" name="{E(name)}" type="checkbox" value="{E(o)}"'
        f'{" checked" if str(o) in 골라진 else ""}/><span>{E(o)}</span></label>'
        for i, o in enumerate(options))
    h = f'<div class="help">{E(help_text)}</div>' if help_text else ""
    return (f'<div class="field"><div class="lb"><span class="lb-t">{E(label)}</span>'
            f'<span class="opt">선택</span></div>'
            f'<div class="chips">{상자}</div>{h}</div>')


def md_to_html(md: str) -> str:
    """파이프라인이 낸 마크다운을 화면에 싣는다.

    범용 파서가 아니다 — 우리 파이프라인이 쓰는 문법(제목·인용·표·목록·강조)만
    다룬다. 그 밖의 것은 문단으로 떨어진다. 어떤 경우에도 원문을 이스케이프한 뒤
    태그를 만들므로, 산출물에 든 문자가 화면의 태그가 되지는 않는다.
    """
    def inline(t: str) -> str:
        t = E(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)

    out, 표, 목록 = [], [], []

    def flush():
        if 목록:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in 목록) + "</ul>")
            목록.clear()
        if 표:
            머리, 몸 = 표[0], [r for r in 표[1:] if not set("-: |").issuperset(set("".join(r)))]
            out.append('<div class="md-table"><table><thead><tr>'
                       + "".join(f"<th>{c}</th>" for c in 머리) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                                 for r in 몸) + "</tbody></table></div>")
            표.clear()

    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            표.append([inline(c.strip()) for c in line.strip("|").split("|")])
            continue
        if 표:
            flush()
        if not line.strip():
            flush()
            continue
        if line.startswith("#"):
            flush()
            n = len(line) - len(line.lstrip("#"))
            out.append(f"<h{min(n + 1, 5)}>{inline(line.lstrip('#').strip())}</h{min(n + 1, 5)}>")
        elif line.startswith(">"):
            flush()
            out.append(f'<blockquote>{inline(line.lstrip("> ").strip())}</blockquote>')
        elif line.lstrip().startswith(("- ", "* ")):
            목록.append(inline(line.lstrip()[2:]))
        else:
            flush()
            out.append(f"<p>{inline(line.strip())}</p>")
    flush()
    return f'<div class="md">{"".join(out)}</div>'


# 관리자만 보는 것은 여기 적어 둔다. 링크를 빼먹으면 화면은 있는데 갈 데가 없다 —
# 감사 로그가 그랬다. 화면마다 '열람·내보내기 기록이 남습니다' 라고 말해 놓고
# 그 기록을 볼 자리가 어디에도 없었다.
관리자메뉴 = {"/team", "/audit"}
NAV = [("/dashboard", "개요"), ("/consults", "상담"), ("/runs", "심의"),
       ("/stores", "기존점"), ("/settings", "설정"), ("/team", "팀"),
       ("/audit", "감사 로그")]


def layout(title: str, body: str, user: dict | None = None, *,
           active: str = "", head: str = "") -> str:
    top = ""
    if user:
        links = "".join(
            f'<a href="{h}"{" class=on" if h == active else ""}>{E(t)}</a>'
            for h, t in NAV
            if h not in 관리자메뉴 or user.get("role") == "관리자")
        top = f"""<nav class="nav">{links}</nav>
      <div class="top-end">
        <span class="who"><b>{E(user['name'] or user['email'])}</b> · {E(user['role'])}</span>
        <form method="post" action="/logout" style="margin:0">
          <button class="ghost sm" type="submit">로그아웃</button></form>
      </div>"""
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="robots" content="noindex"/><meta name="color-scheme" content="light"/>
<meta name="theme-color" content="#efeae0"/>
<link rel="icon" href="data:image/svg+xml,{FAVICON}"/>
<!-- 공개 페이지와 같은 서체. 못 받아 와도 display=swap 이라 본문은 바로 뜨고
     폴백 스택으로 읽힌다 — 사내망에서 외부가 막혀도 화면이 비지 않는다. -->
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@500;700&amp;family=IBM+Plex+Mono:wght@400;500&amp;family=IBM+Plex+Sans+KR:wght@400;500;600&amp;display=swap" rel="stylesheet"/>
<title>{E(title)} · 스스닷컴</title>{head}
<style>{CSS}</style></head><body>
<a class="skip" href="#main">본문 바로가기</a>
<header class="top"><div class="wrap top-in">
  <a class="brand" href="/"><span class="mk">◎</span>스스닷컴</a>{top}
</div></header>
<main id="main"><div class="wrap">{body}</div></main>
<footer><div class="wrap">사내 한정 자료를 다룹니다 · 열람·내보내기 기록이 남습니다</div></footer>
</body></html>"""
