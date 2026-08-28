#!/usr/bin/env python3
"""화면. 디자인 토큰과 조각은 ui.py 에 있다."""
from __future__ import annotations

from . import plans
from . import consults as C
from .ui import (E, checkbox, checks, field, layout,
                 md_to_html, note, tag, tile)

등급배너 = note(
    "warn", "⚠",
    "<b>사내 한정 · 대외 배포 금지</b> — 내부 의사결정 자료입니다. 가맹희망자에게 제공하는 "
    "<b>예상매출액 산정서와 수치를 혼용하지 마십시오.</b> 열람·내보내기 기록이 남습니다.")


def _nf(v, d=0):
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return "—"


# ── 로그인 ───────────────────────────────────────────
def login_page(error: str = "") -> str:
    err = note("err", "✕", E(error)) if error else ""
    return layout("로그인", f"""
<div style="max-width:400px;margin:56px auto">
  <div class="page-h"><div><h1>스스닷컴</h1>
    <p class="sub">프랜차이즈 운영팀·영업팀을 위한 점포개발 상권분석</p></div></div>
  {err}
  <div class="card"><div class="bd">
    <form method="post" action="/login">
      {field("email", "이메일", kind="email", required=True,
             attrs=' autocomplete="username" placeholder="ops@brand.co.kr"')}
      {field("password", "비밀번호", kind="password", required=True,
             attrs=' autocomplete="current-password"')}
      <button class="pri" type="submit" style="width:100%;justify-content:center;margin-top:4px">
        들어가기</button>
    </form>
  </div></div>
  <p class="hint" style="text-align:center">계정은 조직 관리자가 만듭니다.</p>
</div>""")


# ── 개요 ────────────────────────────────────────────
def dashboard_page(user, org, runs, batches, used, seats, ready) -> str:
    spec = plans.spec(org["plan"])
    cap_run, cap_seat = spec["월_분석"], spec["좌석"]

    단계 = []
    할일키 = {t[0] for t in ready["할일"]}
    for key, 제목, 설명, 링크 in [
        ("설정", "브랜드 설정", "변동비·고정비를 조직에 맞춥니다", "/settings"),
        ("기존점", "기존점 실매출", "매출 추정의 유일한 근거입니다", "/stores"),
        ("심의", "후보지 심의", "후보지 CSV 를 올려 판정을 받습니다", "/runs"),
    ]:
        done = key not in 할일키 and (key != "심의" or bool(runs))
        cls = "done" if done else ("todo" if key in 할일키 else "")
        단계.append(f'<a class="step {cls}" href="{링크}" style="color:inherit">'
                    f'<div class="n">{"완료" if done else "해야 함"}</div>'
                    f'<div class="t">{E(제목)}</div><div class="d">{E(설명)}</div></a>')

    안내 = ""
    if ready["할일"]:
        목록 = "".join(f'<li><a href="{h}">{E(w)}</a> — {E(m)}</li>'
                     for w, m, h in ready["할일"])
        안내 = note("info", "→",
                  "<b>아직 심의를 돌릴 수 없습니다.</b> 매출 추정은 이 조직의 실적에서 나옵니다 — "
                  f"예시 데이터로 대신하지 않습니다.<ul style='margin:7px 0 0;padding-left:18px'>{목록}</ul>")

    최근 = "".join(f"""<tr>
      <td class="strong">{'<a href="/runs/%d">%s</a>' % (r["id"], E(batches.get(r["batch_id"], {}).get("name", "")))
                        if r["status"] == "완료" else E(batches.get(r["batch_id"], {}).get("name", ""))}</td>
      <td>{tag(r["status"], r["status"])}</td>
      <td class="r num">{r['billed_units']}</td>
      <td class="mono" style="font-size:12.5px;color:var(--mute)">{E(r['started_at'][:16])}</td>
    </tr>""" for r in runs[:6])

    return layout("개요", f"""
<div class="page-h"><div>
  <h1>{E(org['name'])}</h1>
  <p class="sub">{E(spec['이름'])} 플랜 · {E(spec['설명'])}</p></div>
  <div class="acts"><a class="btn pri" href="/runs">심의 실행</a></div>
</div>
{등급배너}{안내}
<div class="steps">{''.join(단계)}</div>
<div class="tiles" style="margin-bottom:18px">
  {tile("이번 달 분석", str(used), f"/{cap_run}건" if cap_run else " 건", accent=True,
        bar=(used, cap_run) if cap_run else None)}
  {tile("좌석", str(seats), f"/{cap_seat}" if cap_seat else "", bar=(seats, cap_seat) if cap_seat else None)}
  {tile("기존점", str(ready["좌표"]), f"/{ready['기존점']}곳 좌표 있음")}
  {tile("매출 추정 모드", ready["모드"])}
</div>
<div class="card"><div class="hd"><h2>최근 심의</h2>
  <div class="acts"><a class="btn sm" href="/runs">전체 보기</a></div></div>
  <div class="bd tight">
  {'<table><thead><tr><th>묶음</th><th>상태</th><th class="r">후보지</th><th>실행</th></tr></thead><tbody>'
   + 최근 + '</tbody></table>' if 최근 else '<div class="empty">아직 실행한 심의가 없습니다.</div>'}
  </div></div>""", user, active="/dashboard")


# ── 상담 ────────────────────────────────────────────
개인정보고지 = note(
    "info", "!",
    "<b>이 화면에만 개인정보가 들어옵니다.</b> 고객의 성명·연락처·거주지·근무지는 "
    "상담 기록에만 남고 <b>심의로 넘어가지 않습니다</b> — 심의표는 사내 회람 문서라 "
    "고객 연락처가 들어갈 자리가 아닙니다. 목록에서 연락처는 가려 두고, 전체 열람은 "
    "감사 로그에 따로 남습니다.")


def _조건표(row, settings) -> str:
    """이 상담이 판정에 어떻게 닿는지. 알고리즘과 필터를 갈라서 보여 준다 —
    흐려지면 '상담에 원하는 대로 적으면 판정이 좋아진다' 는 오해가 생긴다."""
    예고 = "".join(f"<tr><td class='strong'>{E(k)}</td><td>{E(v)}</td></tr>"
                 for k, v in C.반영예고(row, settings))
    지역 = C.split_list(row["희망지역"])
    상권 = C.split_list(row["희망상권"])
    투자 = (row["보증금_만원"] or 0) + (row["권리금_만원"] or 0)
    필터 = "".join(f"<tr><td class='strong'>{E(k)}</td><td>{E(v)}</td></tr>" for k, v in [
        ("희망 지역", "·".join(지역) or "—"),
        ("희망 평수", f"{row['희망평수']:g}평 (±30% 밖은 목록에서 뺍니다)"
                   if row["희망평수"] else "—"),
        ("희망 상권", "·".join(상권) or "— (고르지 않으면 상권 유형으로 거르지 않습니다)"),
        ("보증금 + 권리금", f"{투자:,.0f}만원 (한도 초과 물건 제외)" if 투자 else "—"),
    ])
    return f"""
<div class="card"><div class="hd"><h2>판정에 닿는 것</h2>
  <span class="tag t-통과">알고리즘</span></div><div class="bd tight">
  <p class="hint" style="padding:14px 20px 0;margin:0">상담에서 받은 값 중 판정에 실제로
    닿는 것은 <b>운영 형태와 투자금 형태</b> 둘뿐입니다. 둘 다 고정비 F 를 바꾸고,
    F 가 바뀌면 BEP → margin → 판정이 바뀝니다.</p>
  <table><tbody>{예고 or '<tr><td class="empty" colspan=2>반영될 항목이 없습니다.</td></tr>'}</tbody></table>
</div></div>
<div class="card"><div class="hd"><h2>판정에 닿지 않는 것</h2>
  <span class="tag t-plain">필터</span></div><div class="bd tight">
  <p class="hint" style="padding:14px 20px 0;margin:0">후보지를 <b>목록에서 빼는</b>
    기준입니다. 점수를 깎지 않습니다. 무엇이 왜 빠졌는지는 심의 결과에 남습니다.</p>
  <table><tbody>{필터}</tbody></table>
</div></div>"""


def consults_page(user, rows, settings, msg: str = "", err: str = "",
                  낸값: dict | None = None) -> str:
    """낸값 은 방금 보냈다가 퇴짜맞은 입력이다.

    이걸 되돌려 주지 않으면 상담자가 고객 앞에서 열세 칸을 다시 묻는다. 그보다 나쁜
    것은 select 다 — 비워 두면 화면은 **기본값**으로 돌아가는데, 그건 빈 칸이 아니라
    '현금 · 점주+알바' 라는 값이다. 동의만 체크하고 저장하면 고객이 말한 '점주' 대신
    '점주+알바' 가 들어가고, 고정비가 달라지니 BEP 와 판정이 함께 바뀐다.
    """
    낸 = 낸값 or {}

    def 온것(key, 기본=""):
        v = 낸.get(key)
        return 기본 if v in (None, "") else str(v)

    행 = "".join(f"""<tr>
      <td class="strong"><a href="/consults/{r['id']}">{E(r['고객명'])}</a></td>
      <td class="mono" style="font-size:13px;color:var(--mute)">{E(C.마스킹(r['고객전화번호']))}</td>
      <td style="color:var(--body);font-size:13.5px">{E(C.요약(r))}</td>
      <td>{tag(r['투자금형태'] or '—', 'plain')}</td>
      <td class="mono" style="font-size:12.5px;color:var(--mute)">{E(r['created_at'][:10])}</td>
      <td>{tag('파기 대상', '부결') if C.보관상태(r, settings)['만료됨'] else ''}</td>
    </tr>""" for r in rows)

    쓰기 = user["role"] in plans.CAN_RUN or user["role"] == "영업"   # 상담은 영업팀의 일이다
    폼 = f"""<div class="bd">
  <form method="post" action="/consults">
    <h3 class="sec">고객 정보</h3>
    <div class="grid2">
      {field("고객명", "고객명", 온것("고객명"), required=True)}
      {field("고객전화번호", "연락처", 온것("고객전화번호"), kind="tel", required=True,
             attrs=' placeholder="010-0000-0000"')}
    </div>
    <div class="grid2">
      {field("거주지", "거주지", 온것("거주지"), help_text="통근 가능 범위를 가늠할 때만 봅니다")}
      {field("근무지", "근무지", 온것("근무지"), help_text="통근 가능 범위를 가늠할 때만 봅니다")}
    </div>
    {checkbox("동의", "개인정보 수집·이용에 동의를 받았습니다", bool(낸.get("동의")),
              required=True,
              help_text=f"보관기간 {C.보관개월(settings)}개월. 동의 없이는 저장하지 않습니다.")}

    <h3 class="sec">창업 희망 조건</h3>
    <div class="grid2">
      {field("희망지역", "창업 희망 지역", 온것("희망지역"), help_text="선호 순으로, 쉼표로 나눠 적습니다 (예: 강남, 성수, 홍대). 후보지 주소·이름에 이 말이 들어가야 목록에 남습니다")}
      {field("희망평수", "희망 평수", 온것("희망평수"), kind="number", attrs=' step="1" min="1" max="300"',
             help_text="±30% 밖의 물건은 목록에서 뺍니다")}
    </div>
    {checks("희망상권", "희망 상권", C.상권유형, 낸.get("희망상권") or (),
            help_text="고르지 않으면 상권 유형으로 거르지 않습니다")}

    <h3 class="sec">투자 계획</h3>
    <div class="grid3">
      {field("보증금_만원", "보증금 (만원)", 온것("보증금_만원"), kind="number", attrs=' step="100" min="0"',
             help_text="알고리즘 미사용 — 투자 한도 필터로만")}
      {field("권리금_만원", "권리금 (만원)", 온것("권리금_만원"), kind="number", attrs=' step="100" min="0"',
             help_text="알고리즘 미사용 — 투자 한도 필터로만")}
      {field("투자금형태", "투자금 형태", 온것("투자금형태", "현금"),
             options=[(k, f"{k} — {v.get('설명','')}")
                      for k, v in (settings.get("투자금형태") or {}).items()],
             help_text="월 금융비용이 고정비에 더해집니다 — BEP 가 바뀝니다")}
    </div>

    <h3 class="sec">운영 계획</h3>
    <div class="grid2">
      {field("운영형태", "운영 형태", 온것("운영형태", "점주+알바"),
             options=[(k, f"{k} — 고정인건비 {v.get('고정인건비_월_만원', 0):,.0f}만원")
                      for k, v in (settings.get("운영형태") or {}).items()],
             help_text="상담에서 받는 값 중 판정을 가장 크게 움직입니다")}
      {field("메모", "메모", 온것("메모"), help_text="상담 기록용. 알고리즘에 들어가지 않습니다")}
    </div>
    <button class="pri" type="submit">상담 저장</button>
  </form></div>""" if 쓰기 else '<div class="bd"><p class="hint">상담 작성 권한이 없습니다.</p></div>'

    return layout("상담", f"""
<div class="page-h"><div><h1>상담</h1>
  <p class="sub">고객의 희망 조건을 받아 둡니다. 조건은 심의를 돌릴 때 후보지 필터와
    고정비에 얹힙니다.</p></div></div>
{개인정보고지}
{note("info", "✓", E(msg)) if msg else ""}{note("err", "✕", E(err)) if err else ""}
<div class="card"><div class="hd"><h2>새 상담</h2></div>{폼}</div>
<div class="card"><div class="hd"><h2>상담 기록 <span class="tag t-plain">{len(rows)}</span></h2></div>
  <div class="bd tight">
  {'<table><thead><tr><th>고객</th><th>연락처</th><th>조건</th><th>투자금 형태</th><th>상담일</th><th></th></tr></thead><tbody>'
   + 행 + '</tbody></table>' if 행 else '<div class="empty">상담 기록이 없습니다.</div>'}
  </div></div>""", user, active="/consults")


def consult_page(user, row, settings, runs, batches) -> str:
    보관 = C.보관상태(row, settings)
    만료배너 = ""
    if 보관["만료됨"]:
        만료배너 = note("err", "✕",
                     f"<b>보관기간이 지났습니다</b> — {E(보관['만료일'])} 까지였습니다. "
                     "파기하십시오. 자동으로 지우지 않는 것은, 조용히 사라지면 "
                     "무엇이 없어졌는지 알 수 없기 때문입니다.")
    elif 보관["남은일"] is not None and 보관["남은일"] < 30:
        만료배너 = note("warn", "!", f"보관기간이 {보관['남은일']}일 남았습니다 "
                                 f"({E(보관['만료일'])} 만료).")

    심의행 = "".join(f"""<tr>
      <td class="strong"><a href="/runs/{r['id']}">{E(batches.get(r['batch_id'], {}).get('name', ''))}</a></td>
      <td>{tag(r['status'], r['status'])}</td>
      <td class="r num">{r['billed_units']}</td>
      <td class="mono" style="font-size:12.5px;color:var(--mute)">{E(r['started_at'][:16])}</td>
    </tr>""" for r in runs)

    return layout(row["고객명"], f"""
<div class="page-h"><div><h1>{E(row['고객명'])}</h1>
  <p class="sub">{E(row['created_at'][:16])} 상담 · 보관 {보관['보관개월']}개월
    (~{E(보관['만료일'] or '—')})</p></div>
  <div class="acts">
    <a class="btn" href="/consults">목록</a>
    {'<a class="btn pri" href="/runs?consult=%d">이 조건으로 심의</a>' % row['id']
     if user["role"] in plans.CAN_RUN else ''}
  </div></div>
{만료배너}
<div class="card"><div class="hd"><h2>고객 정보</h2>
  <span class="tag t-부결">개인정보</span></div><div class="bd tight">
  <table><tbody>
    <tr><td class="strong">연락처</td><td class="mono">{E(row['고객전화번호'] or '—')}</td></tr>
    <tr><td class="strong">거주지</td><td>{E(row['거주지'] or '—')}</td></tr>
    <tr><td class="strong">근무지</td><td>{E(row['근무지'] or '—')}</td></tr>
    <tr><td class="strong">메모</td><td>{E(row['메모'] or '—')}</td></tr>
  </tbody></table>
  <p class="hint" style="padding:12px 20px">이 칸의 값은 심의로 넘어가지 않습니다.
    지금 이 열람은 감사 로그에 <b>개인정보 열람</b> 으로 남았습니다.</p>
</div></div>
{_조건표(row, settings)}
<div class="card"><div class="hd"><h2>이 상담으로 돌린 심의</h2></div><div class="bd tight">
  {'<table><thead><tr><th>묶음</th><th>상태</th><th class="r">후보지</th><th>실행</th></tr></thead><tbody>'
   + 심의행 + '</tbody></table>' if 심의행 else '<div class="empty">아직 없습니다.</div>'}
</div></div>
<form method="post" action="/consults/{row['id']}/delete"
      onsubmit="return confirm('상담 기록을 파기합니다. 되돌릴 수 없습니다.')">
  <button class="danger" type="submit">상담 기록 파기</button>
</form>""", user, active="/consults")


# ── 심의 목록 ────────────────────────────────────────
def runs_page(user, runs, batches, ready, quota_msg: str = "",
              상담=(), 고른상담=None) -> str:
    상담이름 = {c["id"]: c["고객명"] for c in 상담}
    행 = "".join(f"""<tr>
      <td class="strong">{'<a href="/runs/%d">%s</a>' % (r["id"], E(batches.get(r["batch_id"], {}).get("name", "")))
                        if r["status"] == "완료" else E(batches.get(r["batch_id"], {}).get("name", ""))}</td>
      <td>{tag(r["status"], r["status"])}</td>
      <td class="r num">{r['billed_units']}</td>
      <td>{'<a href="/consults/%d">%s</a>' % (r["consult_id"], E(상담이름.get(r["consult_id"], "상담")))
           if r["consult_id"] and r["consult_id"] in 상담이름 else
           ('<span style="color:var(--mute)">기록 파기됨</span>' if r["consult_id"] else '—')}</td>
      <td>{E(r['mode'] or '—')}</td>
      <td class="mono" style="font-size:12.5px;color:var(--mute)">{E(r['started_at'][:16])}</td>
    </tr>""" for r in runs)

    if user["role"] not in plans.CAN_RUN:
        폼 = ('<div class="bd"><p class="hint">심의 실행은 <b>운영팀 이상</b> 권한이 필요합니다. '
              '분석 건수가 과금 단위라, 누구나 돌리면 조직의 월 한도가 조용히 소진됩니다.</p></div>')
    elif not ready["준비됨"]:
        목록 = "".join(f'<li><a href="{h}">{E(w)}</a> — {E(m)}</li>' for w, m, h in ready["할일"])
        폼 = ('<div class="bd"><p class="hint">온보딩이 끝나야 심의를 돌릴 수 있습니다.'
              f'<ul style="margin:7px 0 0;padding-left:18px">{목록}</ul></p></div>')
    else:
        폼 = f"""<div class="bd">
      <form method="post" action="/runs" enctype="multipart/form-data">
        <div class="grid2">
          {field("name", "묶음 이름", help_text="예: 2026 3분기 수도권")}
          {field("sites", "후보지 CSV", kind="file", required=True,
                 help_text="입력 화면에서 내보낸 sites.csv. 청구는 실제로 심의한 후보지 수로 하며, 실패한 실행과 상담 조건으로 걸러진 후보지는 청구하지 않습니다.",
                 attrs=' accept=".csv"')}
        </div>
        {field("consult_id", "상담 조건", 고른상담 or "",
               options=[("", "붙이지 않음 — 조직 설정 그대로")]
                       + [(str(c["id"]), f"{c['고객명']} — {C.요약(c)}") for c in 상담],
               help_text="상담을 붙이면 희망 조건으로 후보지를 거르고, 운영·투자금 형태가 고정비를 바꿉니다. 고객 개인정보는 넘어가지 않습니다.")}
        <button class="pri" type="submit">심의 실행</button>
      </form></div>"""

    경고 = note("err", "✕", E(quota_msg)) if quota_msg else ""
    return layout("심의", f"""
<div class="page-h"><div><h1>심의</h1>
  <p class="sub">후보지 묶음을 올리면 M1~M6 파이프라인이 판정을 냅니다.</p></div></div>
{등급배너}{경고}
<div class="card"><div class="hd"><h2>새 심의</h2></div>{폼}</div>
<div class="card"><div class="hd"><h2>실행 기록</h2></div><div class="bd tight">
{'<table><thead><tr><th>묶음</th><th>상태</th><th class="r">후보지</th><th>상담</th><th>모드</th><th>실행</th></tr></thead><tbody>'
 + 행 + '</tbody></table>' if 행 else '<div class="empty">아직 실행한 심의가 없습니다.</div>'}
</div></div>""", user, active="/runs")


# ── 심의 결과 ────────────────────────────────────────
def run_page(user, run, batch, summary, 상담=None) -> str:
    if run["status"] != "완료":
        도는중 = run["status"] in ("대기", "실행중")
        본문 = ('<p class="hint">파이프라인이 도는 중입니다. 후보지 수에 따라 수 초에서 수 분이 '
              '걸립니다. 이 화면은 3초마다 스스로 새로 고칩니다.</p>' if 도는중 else "")
        오류 = note("err", "✕", f"<b>실행 실패</b><br/><span class='mono' style='font-size:12.5px'>"
                             f"{E(run['error'][:600])}</span>") if run["error"] else ""
        return layout("심의", f"""
<div class="page-h"><div><h1>{E(batch.get('name',''))}</h1>
  <p class="sub">{tag(run['status'], run['status'])}</p></div>
  <div class="acts"><a class="btn" href="/runs">목록</a></div></div>
{오류}<div class="card"><div class="bd">{본문 or '<p class="hint">결과가 없습니다.</p>'}</div></div>""",
            user, active="/runs",
            head='<meta http-equiv="refresh" content="3"/>' if 도는중 else "")

    def rng(lo, hi):
        return "—" if lo is None or hi is None else f"{lo:,.0f}~{hi:,.0f}"

    상담블록 = ""
    if run["consult_md"]:
        머리 = (f'<a class="btn sm" href="/consults/{상담["id"]}">{E(상담["고객명"])} 상담</a>'
              if 상담 else '<span class="tag t-plain">상담 기록 파기됨</span>')
        상담블록 = f"""<div class="card"><div class="hd"><h2>상담 조건 반영</h2>
          <div class="acts">{머리}</div></div>
          <div class="bd">{md_to_html(run["consult_md"])}</div></div>"""

    행 = "".join(f"""<tr>
      <td class="strong"><a href="/runs/{run['id']}/sites/{i}">{E(s['이름'])}</a></td>
      <td>{tag(s['판정'], s['판정'])}</td>
      <td class="r num">{_nf(s['S'], 1)}</td>
      <td class="r num">{rng(s['월매출_하한'], s['월매출_상한'])}</td>
      <td class="r num">{_nf(s['BEP_만원'])}</td>
      <td class="r num">{_nf((s['margin'] or 0)*100, 1)}%</td>
      <td class="wrap-cell" style="color:var(--mute);font-size:13px">{E('; '.join(s['사유']) or '—')}</td>
    </tr>""" for i, s in enumerate(summary["후보지"]))

    return layout("심의 결과", f"""
<div class="page-h"><div><h1>{E(batch.get('name',''))}</h1>
  <p class="sub">Mode {E(run['mode'])} · 후보지 {run['billed_units']}곳 · {E(run['started_at'][:16])}</p></div>
  <div class="acts">
    <a class="btn" href="/runs">목록</a>
    <a class="btn pri" href="/runs/{run['id']}/report">심의표 내려받기</a></div></div>
{note("warn", "⚠",
      "<b>사내 한정 · 대외 배포 금지</b> — 매출은 <b>구간으로만</b> 표시합니다. 단일 숫자는 "
      "상담 자리에서 그대로 인용됩니다. 내려받는 파일명에는 <code>internal</code> 이 붙습니다.")}
<div class="tiles" style="margin-bottom:18px">
  {tile("통과", str(summary['통과']))}{tile("보류", str(summary['보류']))}
  {tile("부결", str(summary['부결']))}{tile("후보지", str(run['billed_units']), "곳")}
</div>
<div class="card"><div class="bd tight"><table><thead><tr>
  <th>후보지</th><th>판정</th><th class="r">S</th><th class="r">월매출 구간(만원)</th>
  <th class="r">BEP</th><th class="r">margin</th><th>사유</th>
</tr></thead><tbody>{행}</tbody></table></div></div>
{상담블록}""", user, active="/runs")


def site_page(user, run, batch, site, idx) -> str:
    j = site.get("판정") or {}
    m = site.get("매출") or {}
    사유 = "".join(f"<li>{E(x)}</li>" for x in j.get("사유", [])) or "<li>—</li>"
    비고 = "".join(f"<li>{E(x)}</li>" for x in j.get("비고", []))
    경고 = "".join(f"<li>{E(x)}</li>" for x in site.get("경고", []))
    # 파이프라인이 판정 밖(레코드 옆)에 싣는다 — 판정에 들어가지 않는 참고 자료다
    시세 = site.get("시세대조")
    시세블록 = ""
    if 시세:
        시세블록 = f"""<div class="card"><div class="hd"><h2>지역 시세 대조</h2>
        <span class="tag t-plain">참고 · 판정 미반영</span></div><div class="bd">
        <div class="tiles">
          {tile("실거래", str(시세['건수']), "건")}
          {tile("중앙 단가", _nf(시세['만원_per_m2_중앙'], 1), "만원/㎡")}
          {tile("기대 월임대료", _nf(시세['기대_월임대료_만원']), "만원")}
          {tile("제시 대비", _nf(시세['배수'], 2), "배", accent=True)}
        </div>
        <p class="hint" style="margin-top:12px">매매가를 임대료로 환산한 참고선이며
        <b>판정에는 들어가지 않습니다.</b> 매매가는 임대 조건이 아니고, 상업용은 층·용도·
        전면에 따라 편차가 크며, 환산에 쓰는 연임대수익률이 미검증 계수입니다.
        제시 임대료가 지역 수준을 크게 벗어나면 실사에서 확인하십시오.</p></div></div>"""
    return layout(site.get("이름", "후보지"), f"""
<div class="page-h"><div><h1>{E(site.get('이름',''))}</h1>
  <p class="sub">{E(batch.get('name',''))} · {E((site.get('입력') or {}).get('주소',''))}</p></div>
  <div class="acts"><a class="btn" href="/runs/{run['id']}">결과로</a></div></div>
<div class="tiles" style="margin-bottom:18px">
  {tile("판정", j.get("판정","—"), accent=True)}
  {tile("S 점수", _nf(site.get("S"), 1))}
  {tile("월매출 구간(만원)", f"{_nf(m.get('월매출_하한'))}~{_nf(m.get('월매출_상한'))}")}
  {tile("BEP", _nf(j.get("BEP_만원")), "만원")}
  {tile("margin", _nf((j.get("margin") or 0)*100, 1), "%")}
</div>
<div class="card"><div class="hd"><h2>판정 사유</h2></div><div class="bd">
  <ul style="margin:0;padding-left:18px;color:var(--body);font-size:14px">{사유}</ul></div></div>
{f'<div class="card"><div class="hd"><h2>비고</h2></div><div class="bd"><ul style="margin:0;padding-left:18px;color:var(--body);font-size:13.5px;line-height:1.7">{비고}</ul></div></div>' if 비고 else ''}
{시세블록}
{f'<div class="card"><div class="hd"><h2>경고</h2></div><div class="bd"><ul style="margin:0;padding-left:18px;color:var(--warn);font-size:13.5px;line-height:1.7">{경고}</ul></div></div>' if 경고 else ''}
""", user, active="/runs")


# ── 기존점 ───────────────────────────────────────────
def stores_page(user, stores, ready, msg: str = "", err: str = "",
                낸값: dict | None = None) -> str:
    """낸값 은 방금 보냈다가 퇴짜맞은 입력이다 (consults_page 와 같은 이유).

    여기서 특히 위험한 것은 기준점포다. 비워 두면 화면이 '아니오' 로 돌아가는데,
    Mode B 는 기준점포를 앵커로 매출을 추정한다 — 다시 저장하면 앵커가 아닌 점포로
    조용히 들어간다.
    """
    낸 = 낸값 or {}

    def 온것(key, 기본=""):
        x = 낸.get(key)
        return 기본 if x in (None, "") else str(x)

    행 = "".join(f"""<tr>
      <td class="strong">{E(s['점포명'])}</td>
      <td>{tag('기준점포','통과') if str(s['기준점포']).upper().startswith(('Y','예','O')) else ''}</td>
      <td class="r num">{_nf(s['월매출_만원'])}</td>
      <td class="r num">{_nf(s['좌석수'])}</td>
      <td class="mono" style="font-size:12.5px;color:var(--mute)">
        {(_nf(s['위도'],4) + ', ' + _nf(s['경도'],4)) if s['위도'] and s['경도'] else '<span style="color:var(--no)">좌표 없음</span>'}</td>
      <td class="r"><form method="post" action="/stores/{s['id']}/delete" style="margin:0">
        <button class="row-act danger" type="submit">삭제</button></form></td>
    </tr>""" for s in stores)

    알림 = (note("info", "✓", E(msg)) if msg else "") + (note("err", "✕", E(err)) if err else "")
    준비 = "" if ready["준비됨"] else note(
        "warn", "!",
        f"실매출과 좌표가 있는 기존점이 <b>{ready['좌표']}곳</b>입니다. 최소 2곳이 필요하고, "
        "그중 1곳 이상을 <b>기준점포</b>로 지정해야 Mode B 앵커링이 성립합니다. "
        "15곳을 넘으면 Mode A(회귀)로 올라갑니다.")

    return layout("기존점", f"""
<div class="page-h"><div><h1>기존점</h1>
  <p class="sub">매출 추정의 유일한 근거입니다. 이 데이터는 조직 밖으로 나가지 않고,
    쌓일수록 추정이 정확해집니다.</p></div></div>
{알림}{준비}
<div class="card"><div class="hd"><h2>기존점 추가</h2></div><div class="bd">
  <form method="post" action="/stores">
    <div class="grid3">
      {field("점포명", "점포명", 온것("점포명"), required=True)}
      {field("월매출_만원", "월매출 (만원)", 온것("월매출_만원"), kind="number", required=True, attrs=' step="1" min="0"')}
      {field("기준점포", "기준점포", 온것("기준점포", "N"), options=[("N","아니오"),("Y","예 — Mode B 앵커")])}
    </div>
    <div class="grid3">
      {field("위도", "위도", 온것("위도"), kind="number", required=True, attrs=' step="0.000001" min="33" max="39"')}
      {field("경도", "경도", 온것("경도"), kind="number", required=True, attrs=' step="0.000001" min="124" max="132"')}
      {field("좌석수", "좌석수", 온것("좌석수"), kind="number", attrs=' step="1" min="0"')}
    </div>
    <div class="grid3">
      {field("월임대료_만원", "월임대료 (만원)", 온것("월임대료_만원"), kind="number", attrs=' step="1" min="0"')}
      {field("전용면적_평", "전용면적 (평)", 온것("전용면적_평"), kind="number", attrs=' step="0.1" min="0"')}
      {field("주소", "주소", 온것("주소"))}
    </div>
    <button class="pri" type="submit">추가</button>
  </form></div></div>
<div class="card"><div class="hd"><h2>등록된 기존점 <span class="tag t-plain">{len(stores)}</span></h2></div>
  <div class="bd tight">
  {'<table><thead><tr><th>점포명</th><th></th><th class="r">월매출(만원)</th><th class="r">좌석</th><th>좌표</th><th></th></tr></thead><tbody>'
   + 행 + '</tbody></table>' if 행 else '<div class="empty">등록된 기존점이 없습니다. 위에서 추가하십시오.</div>'}
  </div></div>""", user, active="/stores")


# ── 설정 ────────────────────────────────────────────
def settings_page(user, st, msg: str = "", err: str = "") -> str:
    v = st["운영"]["변동비"]
    f = st["운영"]["고정비"]
    합 = sum(v.values())
    return layout("설정", f"""
<div class="page-h"><div><h1>설정</h1>
  <p class="sub">브랜드와 운영 계수. 여기 값이 고정비 F 와 변동비율 v 로 들어가
    BEP·margin·판정을 바꿉니다.</p></div></div>
{note("info", "✓", E(msg)) if msg else ""}{note("err", "✕", E(err)) if err else ""}
<form method="post" action="/settings">
<div class="card"><div class="hd"><h2>브랜드</h2></div><div class="bd">
  <div class="grid2">
    {field("브랜드", "브랜드 이름", st.get("브랜드",""), required=True,
           help_text="심의표 머리말과 경쟁점 자사 판별에 쓰입니다")}
    {field("자사브랜드티어", "브랜드 티어", st.get("자사브랜드티어",""),
           options=[(x,x) for x in ("동일가격대","저가형","스페셜티","비커피")],
           help_text="M3 흡인력의 브랜드 가중")}
  </div>
  <div class="grid2">
    {field("좌석수_기본", "기본 좌석수", st.get("좌석수_기본",24), kind="number", attrs=' step="1"')}
    {field("영업일수", "월 영업일수", st.get("영업일수",30), kind="number", attrs=' step="1"')}
  </div>
</div></div>
<div class="card"><div class="hd"><h2>변동비</h2>
  <span class="tag t-plain">합 {합*100:.1f}%</span></div><div class="bd">
  <p class="hint" style="margin-bottom:14px">v = 원재료율 + 로열티율 + 광고분담금율 + 기타.
    BEP = F ÷ (1 − v) 입니다.</p>
  <div class="grid2">
    {field("원재료율", "원재료율", v["원재료율"], kind="number", attrs=' step="0.001" min="0" max="1"')}
    {field("로열티율", "로열티율", v["로열티율"], kind="number", attrs=' step="0.001" min="0" max="1"')}
  </div>
  <div class="grid2">
    {field("광고분담금율", "광고분담금율", v["광고분담금율"], kind="number", attrs=' step="0.001" min="0" max="1"')}
    {field("기타변동비율", "기타 변동비율", v["기타변동비율"], kind="number",
           attrs=' step="0.001" min="0" max="1"', help_text="카드수수료 등")}
  </div>
</div></div>
<div class="card"><div class="hd"><h2>고정비</h2></div><div class="bd">
  <p class="hint" style="margin-bottom:14px">F = 임대료 + 관리비 + 고정인건비 + 기타.
    임대료·관리비는 후보지마다 다르므로 후보지 CSV 에서 옵니다.</p>
  <div class="grid2">
    {field("고정인건비_월_만원", "고정인건비 (월·만원)", f["고정인건비_월_만원"], kind="number", attrs=' step="1" min="0"')}
    {field("기타_월_만원", "기타 (월·만원)", f["기타_월_만원"], kind="number",
           attrs=' step="1" min="0"', help_text="수도광열·소모품 등")}
  </div>
</div></div>
<button class="pri" type="submit">저장</button>
</form>""", user, active="/settings")


# ── 팀 ─────────────────────────────────────────────
def team_page(user, users, org, seats, msg: str = "", err: str = "",
              낸값: dict | None = None) -> str:
    낸 = 낸값 or {}

    def 온것(key, 기본=""):
        x = 낸.get(key)
        return 기본 if x in (None, "") else str(x)

    행 = "".join(f"""<tr>
      <td class="strong">{E(u['name'] or '—')}</td>
      <td class="mono" style="font-size:13px">{E(u['email'])}</td>
      <td>{tag(u['role'], '통과' if u['role']=='관리자' else 'plain')}</td>
      <td>{tag('활성' if u['active'] else '비활성', '완료' if u['active'] else 'plain')}</td>
      <td class="r">{'' if u['id']==user['id'] else
        f'''<form method="post" action="/team/{u['id']}/toggle" style="margin:0">
          <button class="row-act" type="submit">{'비활성화' if u['active'] else '활성화'}</button></form>'''}</td>
    </tr>""" for u in users)
    spec = plans.spec(org["plan"])
    cap = spec["좌석"]
    return layout("팀", f"""
<div class="page-h"><div><h1>팀</h1>
  <p class="sub">좌석 {seats}{f' / {cap}' if cap else ''} 사용 중. 비활성 사용자는 좌석을 쓰지 않습니다.</p></div>
  <div class="acts"><a class="btn" href="/audit">감사 로그</a></div></div>
{note("info","✓",E(msg)) if msg else ""}{note("err","✕",E(err)) if err else ""}
{note("info","→",
  "<b>역할</b> — 영업팀은 읽기와 상담만 합니다. 심의 실행은 운영팀 이상입니다. "
  "분석 건수가 과금 단위라, 누구나 돌리면 조직의 월 한도가 조용히 소진됩니다.")}
<div class="card"><div class="hd"><h2>구성원 추가</h2></div><div class="bd">
  <form method="post" action="/team">
    <div class="grid3">
      {field("email", "이메일", 온것("email"), kind="email", required=True)}
      {field("name", "이름", 온것("name"))}
      {field("role", "역할", 온것("role", "영업"), options=[(r,r) for r in plans.ROLES])}
    </div>
    {field("password", "임시 비밀번호", kind="password", required=True,
           help_text="본인에게 전달하고 바꾸게 하십시오. 비밀번호 변경 화면은 아직 없습니다.")}
    <button class="pri" type="submit">추가</button>
  </form></div></div>
<div class="card"><div class="hd"><h2>구성원</h2></div><div class="bd tight">
  <table><thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>상태</th><th></th></tr></thead>
  <tbody>{행}</tbody></table></div></div>""", user, active="/team")


# ── 감사 로그 ────────────────────────────────────────
def audit_page(user, rows, users) -> str:
    행 = "".join(f"""<tr>
      <td class="mono" style="font-size:12.5px;color:var(--mute)">{E(r['at'])}</td>
      <td>{E((users.get(r['user_id']) or {}).get('email','—'))}</td>
      <td>{tag(r['action'], 'plain')}</td>
      <td class="mono" style="font-size:12.5px">{E(r['target'] or '—')}</td>
      <td class="wrap-cell" style="color:var(--mute);font-size:13px">{E(r['detail'])}</td>
    </tr>""" for r in rows)
    return layout("감사 로그", f"""
<div class="page-h"><div><h1>감사 로그</h1>
  <p class="sub">사내 한정 자료를 다루므로 열람 기록은 기능이 아니라 의무입니다. 최근 300건.</p></div>
  <div class="acts"><a class="btn" href="/team">팀</a></div></div>
<div class="card"><div class="bd tight">
  <table><thead><tr><th>시각</th><th>사용자</th><th>행위</th><th>대상</th><th>비고</th></tr></thead>
  <tbody>{행 or '<tr><td colspan=5 class="empty">기록이 없습니다.</td></tr>'}</tbody></table>
</div></div>""", user, active="/audit")
