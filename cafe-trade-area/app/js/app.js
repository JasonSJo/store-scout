/* 콘솔 — 파이프라인 산출(심의결과.json)을 읽어 심의 자료로 보여주고,
   M5 판정 산술만 브라우저에서 다시 계산한다.

   여기서 하지 않는 것: M1 등시선·M2 격자교차·M3 Huff·M4 회귀.
   그 넷은 OSM 보행 네트워크·통계청 격자·기존점 실적이 있어야 하며,
   브라우저에서 흉내내면 CLI 와 다른 숫자를 내는 것이 유일한 결과다. */
const App = (() => {
  const TABS = ['status', 'sites', 'sim', 'coef', 'data'];
  let tab = 'status';
  let picked = null;
  let knobs = null;

  const V = { 통과: 'ok', 보류: 'hold', 부결: 'no' };
  const MARK = { 통과: '○', 보류: '△', 부결: '✕' };

  const settings = () => S.settings();
  const gov = () => (settings().거버넌스 || {});
  const ops = () => CFG.ops((settings().운영) || {});

  /* 입력한 계수와 고친 후보지 입력값으로 M5 를 다시 계산한다.
     둘 다 손대지 않았으면 파이프라인이 낸 판정을 그대로 쓴다 — 화면과 CLI 가 갈리지 않는다. */
  const recalc = () => CFG.liveDirty() || INP.liveDirty();

  function verdictOf(r) {
    if (!recalc()) return r.판정;
    const rev = { 월매출_중앙: (r.매출 || {}).월매출_중앙, 월매출_하한: (r.매출 || {}).월매출_하한 };
    return M5.judge(INP.merged(r), rev, { 운영: ops() }, r.S,
                    (r.판정.카니발.상세 || []).map(x => ({ ...x })),
                    CFG.c('잠식계수_카파'), r.S_풀최대);
  }
  const flipped = r => recalc() && verdictOf(r).판정 !== r.판정.판정;

  /* 계수를 손댔다는 사실은 어느 화면에서도 보여야 한다 — 심의 자리에서 제일 중요한 정보다. */
  function cfgBar() {
    if (!CFG.anyDirty() && !INP.anyDirty()) return '';
    const live = CFG.liveDirty() || INP.liveDirty();
    const pipe = CFG.pipelineDirty() || INP.pipelineDirty();
    const what = [
      CFG.anyDirty() ? `계수 ${CFG.dirtyCount()}건` : '',
      INP.anyDirty() ? `후보지 입력값 ${INP.dirtyCount()}건` : '',
    ].filter(Boolean).join(' · ');
    const msg = [
      live ? '<b>판정 다시 계산됨</b> 이 화면의 판정은 손으로 넣은 값으로 계산한 결과입니다.' : '',
      pipe ? '<b>파이프라인 값 변경</b> M1~M4·M6 로 들어가는 값은 브라우저에서 다시 계산할 수 없습니다 — 파일로 내보내 파이프라인을 다시 돌려야 반영됩니다.' : '',
    ].filter(Boolean).join(' ');
    return `<div class="cfgbar"><b>${what} 입력</b><span>${msg}</span>
      <div class="acts">
        ${CFG.anyDirty() ? '<button class="sm" data-go="coef">계수 보기</button>' : ''}
        ${INP.anyDirty() ? '<button class="sm" data-go="sites">입력값 보기</button>' : ''}
        <button class="sm ghost danger" id="cfg-reset-all">원래 값으로</button></div></div>`;
  }

  // ── 심의 현황 ─────────────────────────────
  function renderStatus() {
    const el = document.getElementById('p-status');
    if (!S.has()) { el.innerHTML = empty(); wireEmpty(); return; }
    const d = S.get(), rows = S.sites();
    const cnt = { 통과: 0, 보류: 0, 부결: 0 };
    rows.forEach(r => cnt[verdictOf(r).판정]++);
    const m = d.모델 || {};
    const modeA = d.모드 === 'A' && m.표본수;

    el.innerHTML = `
      ${banner()}
      ${cfgBar()}
      <div class="grid g4">
        <div class="kpi"><div class="k">후보지</div><div class="v">${rows.length}<small>곳</small></div>
          <div class="d">심의 대상</div></div>
        <div class="kpi"><div class="k">통과 / 보류 / 부결</div>
          <div class="v">${cnt.통과} <small>/</small> ${cnt.보류} <small>/</small> ${cnt.부결}</div>
          <div class="d">M5 3단 판정</div></div>
        <div class="kpi"><div class="k">추정 모드</div><div class="v">${d.모드}</div>
          <div class="d">${modeA ? `회귀 · 표본 ${m.표본수}` : '앵커링 · 표본 15개 미만'}</div></div>
        <div class="kpi"><div class="k">${modeA ? '모델 MAPE' : '예측구간'}</div>
          <div class="v">${modeA ? U.pct((m.CV || {}).MAPE || 0, 1) : '±' + U.pct(0.25, 0)}</div>
          <div class="d">${modeA ? `${(m.CV || {}).방식 || ''} · R² ${U.num(m.R2, 3)}` : '미검증 가정값'}</div></div>
      </div>

      <div class="card" style="margin-top:14px">
        <h3>판정</h3>
        <div class="tablewrap"><table>
          <thead><tr><th>판정</th><th>후보지</th><th class="num">S</th><th class="num">월매출(중앙)</th>
            <th class="num">BEP</th><th class="num">margin</th><th class="num">중첩</th><th>사유</th></tr></thead>
          <tbody>${rows.map(rowHtml).join('')}</tbody>
        </table></div>
      </div>

      ${warnCard()}`;
    wireOpen();
  }

  const banner = () => `<div class="gov">
      <b>${U.esc(gov().문서등급 || '사내 한정 · 대외 배포 금지')}</b>
      <span>${U.esc((gov().고지 || '').trim())}</span></div>`;

  function rowHtml(r) {
    const j = verdictOf(r), p = r.매출 || {};
    const flip = flipped(r) ? `<div class="flip">파이프라인 ${r.판정.판정} → ${j.판정}</div>` : '';
    return `<tr data-open="${U.esc(r.이름)}">
      <td><span class="vd ${V[j.판정]}">${MARK[j.판정]} ${j.판정}</span>${flip}</td>
      <td><b>${U.esc(r.이름)}</b><div class="why">${U.esc(r.입력.주소 || '')}</div>
        ${INP.siteDirty(r) ? `<div class="flip">입력값 ${INP.siteDirty(r)}건 수정</div>` : ''}</td>
      <td class="num">${U.num(r.S, 1)}</td>
      <td class="num">${U.num(p.월매출_중앙, 0)}</td>
      <td class="num">${U.num(j.BEP_만원, 0)}</td>
      <td class="num ${(j.margin ?? 0) < CFG.c('부결_마진') ? 'neg' : ''}">${U.pct(j.margin || 0, 1)}</td>
      <td class="num">${U.pct(j.카니발.최대_overlap, 0)}</td>
      <td class="why">${U.esc(j.사유.join('; ') || '—')}</td>
    </tr>`;
  }

  function warnCard() {
    const w = S.warnings();
    if (!w.length) return '';
    return `<div class="card" style="margin-top:14px"><h3>데이터 경고 ${w.length}건</h3>
      <p class="hint" style="margin-top:0">어떤 입력이 비어 있는지가 판정의 신뢰도를 정합니다.</p>
      <div class="risks">${w.map(x => `<div class="risk ${x.경고.startsWith('⛔') ? 'high' : 'warn'}">
        ${U.esc(x.경고)}<span class="who">${U.esc(x.대상.join(' · '))}</span></div>`).join('')}</div></div>`;
  }

  // ── 후보지 상세 ───────────────────────────
  function renderSites() {
    const el = document.getElementById('p-sites');
    if (!S.has()) { el.innerHTML = empty(); wireEmpty(); return; }
    const r = S.find(picked);
    const j = verdictOf(r), p = r.매출 || {}, a = r.상권, d = r.수요, c = r.경쟁;

    el.innerHTML = `
      ${banner()}
      ${cfgBar()}
      <div class="panel-head">
        <div><h3>${U.esc(r.이름)}</h3><p>${U.esc(r.입력.주소 || '')}</p></div>
        <div class="acts"><label class="field" style="margin:0;min-width:230px"><span>후보지</span>
          <select id="pick">${S.sites().map(x =>
            `<option ${x.이름 === r.이름 ? 'selected' : ''}>${U.esc(x.이름)}</option>`).join('')}</select>
        </label></div>
      </div>

      <div class="verdictbox ${V[j.판정]}">
        <b>${MARK[j.판정]} ${j.판정}</b>
        ${flipped(r) ? `<div class="flip">손으로 넣은 값으로 다시 계산 — 파이프라인 판정은 ${r.판정.판정}</div>` : ''}
        <div>${j.사유.length ? j.사유.map(U.esc).join(' · ') : '부결·보류 조건에 해당하지 않습니다'}</div>
      </div>

      <div class="grid g2" style="margin-top:14px">
        <div class="card"><h3>M1 상권 · M2 수요</h3>
          ${kv([
            ['P10 면적', `${U.num(a.P10_면적_m2 / 10000, 1)}ha`],
            ['잔존율 R', U.num(a.R, 2)],
            ['등시선 출처', a.출처],
            ['H (배후 세대)', U.num(d.H, 0)],
            ['W (직장인구)', U.num(d.W, 0)],
            ['D_am', U.num(d.D_am, 0)],
            ['D_am_adj', `<b>${U.num(d.D_am_adj, 0)}</b> (같은편 ${U.num(d.D_am_같은편, 0)} + 반대편 ${U.num(d.D_am_반대편, 0)} × ${d.횡단저항})`],
            ['D_all', U.num(d.D_all, 0)],
          ])}</div>
        <div class="card"><h3>M3 경쟁 · M4 매출</h3>
          ${kv([
            ['Huff 점유율 S', `<b>${U.pct(c.S, 2)}</b>`],
            ['λ (거리 마찰)', `${c.λ} <span class="tagx">미검증</span>` +
              (CFG.changed('거리마찰_람다')
                ? `<div class="flip">입력값 ${CFG.c('거리마찰_람다')} — 파이프라인 재실행 전까지 위 점유율에 반영되지 않습니다</div>` : '')],
            ['반경 내 경쟁', `${c.반경내_경쟁}곳 (동일가격대 ${c.동일가격대_수} · 저가형 ${c.저가형_수})`],
            ['추정 모드', p.모드 || '—'],
            ['월매출 하한', U.num(p.월매출_하한, 0)],
            ['월매출 중앙', `<b>${U.num(p.월매출_중앙, 0)}만원</b> — 심의 기준값`],
            ['월매출 상한', U.num(p.월매출_상한, 0)],
          ])}</div>
      </div>

      <div class="grid g2" style="margin-top:14px">
        <div class="card"><h3>M5 판정</h3>
          ${kv([
            ['고정비 F', `${U.num(j.고정비.F, 0)}만원`],
            ['변동비율 v', U.pct(j.변동비율, 1)],
            ['BEP', `${U.num(j.BEP_만원, 0)}만원`],
            ['margin', U.pct(j.margin || 0, 1)],
            ['margin_low', U.pct(j.margin_low || 0, 1)],
            ['S', `${U.num(j.S, 1)} / 100`],
            ['최대 중첩', U.pct(j.카니발.최대_overlap, 0)],
            ['잠식 추정', `${U.num(j.카니발.잠식액_합_만원, 0)}만원/월 (κ=${j.카니발['κ']})`],
            ['순증 월매출', `${U.num(j.순증_월매출_만원, 0)}만원`],
          ])}</div>
        <div class="card"><h3>치명 플래그 · 비고</h3>
          <div class="risks">
            ${j.치명플래그.length
              ? j.치명플래그.map(x => `<div class="risk high">⛔ ${U.esc(x)}</div>`).join('')
              : '<div class="risk">치명 플래그 해당 없음</div>'}
            ${j.치명_미확인.map(x => `<div class="risk warn">미확인 — ${U.esc(x)}</div>`).join('')}
            ${j.비고.map(x => `<div class="risk ${x.startsWith('⛔') ? 'high' : ''}">${U.esc(x)}</div>`).join('')}
            ${(r.경고 || []).map(x => `<div class="risk ${x.startsWith('⛔') ? 'high' : 'warn'}">${U.esc(x)}</div>`).join('')}
          </div>
          <h3 style="margin-top:16px">S 배점</h3>
          ${kv(Object.entries(r.S_축 || {}).map(([k, v]) => [k, U.num(v, 1)]))}
          <p class="hint">실증 회귀가 아닌 임의 배점입니다. 후보지 간 상대 비교로만 쓰십시오.</p>
        </div>
      </div>

      ${inputCard(r)}`;

    document.getElementById('pick').onchange = e => { picked = e.target.value; render(); };
    wireInputs(r);
  }

  /* ── 후보지 입력값 수정 ─────────────────────
     후보지 CSV 행을 화면에서 고친다. 임대료·관리비·치명 플래그는 M5 로 바로 들어가
     판정이 즉시 다시 계산되고, 나머지는 M1~M4 로 들어가므로 CSV 로 내보내
     파이프라인을 다시 돌려야 반영된다. */
  const INP_SCOPE = {
    [INP.콘솔]: '<span class="scope live">즉시 반영</span>',
    [INP.파이프라인]: '<span class="scope pipe">재실행 필요</span>',
    [INP.미사용]: '<span class="scope none">미사용</span>',
  };
  const FLAG_OPTS = [['Y', '해당'], ['N', '해당 없음'], ['', '미확인']];

  function inputRow(r, k) {
    const m = INP.meta(k), v = INP.value(r, k) ?? '', ch = INP.changed(r, k);
    const orig = INP.origin(r, k);
    const control = m.종류 === 'flag'
      ? `<select data-inp="${k}">${FLAG_OPTS.map(([val, lb]) =>
          `<option value="${val}" ${String(v) === val ? 'selected' : ''}>${lb}</option>`).join('')}</select>`
      : m.종류 === 'num'
        ? `<input type="number" data-inp="${k}" value="${U.esc(v)}"
             min="${m.최소}" max="${m.최대}" step="${m.증분}"/>`
        : `<input type="text" data-inp="${k}" value="${U.esc(v)}"/>`;
    return `<tr class="${ch ? 'edited' : ''}">
      <td><span class="lbl">${U.esc(m.라벨)}</span>
        ${ch ? ` <span class="flip">원본 ${U.esc(String(orig ?? '') || '(빈칸)')}</span>` : ''}
        <div class="why">${U.esc(m.설명)}</div></td>
      <td class="num">${control}</td>
      <td><code>${m.모듈}</code></td>
      <td>${INP_SCOPE[m.반영]}</td>
      <td>${ch ? `<button class="sm ghost" data-ri="${k}">되돌리기</button>` : ''}</td>
    </tr>`;
  }

  function inputCard(r) {
    const group = scope => INP.keys().filter(k => INP.meta(k).반영 === scope
                                                 && k in (r.입력 || {}));
    const table = (title, note, ks) => ks.length ? `<h3 style="margin-top:16px">${title}</h3>
      <p class="hint" style="margin-top:0">${note}</p>
      <div class="tablewrap cfg"><table>
        <thead><tr><th>항목</th><th class="num">값</th><th>모듈</th><th>반영</th><th></th></tr></thead>
        <tbody>${ks.map(k => inputRow(r, k)).join('')}</tbody></table></div>` : '';

    const n = INP.siteDirty(r);
    return `<div class="card" style="margin-top:14px">
      <div class="inp-head">
        <h3>입력값 수정 — ${U.esc(r.이름)}</h3>
        <div class="acts">
          <button class="sm primary" id="inp-export">후보지 CSV 내보내기</button>
          ${n ? `<button class="sm ghost" id="inp-reset-site">이 후보지 되돌리기</button>` : ''}
          ${INP.anyDirty() ? `<button class="sm ghost danger" id="inp-reset-all">전체 되돌리기</button>` : ''}
        </div>
      </div>
      <p class="hint" style="margin-top:2px">실사로 확인한 값을 넣어 보십시오. 원본
        심의결과는 그대로 두고 고친 값만 따로 얹습니다${n ? ` — 이 후보지 <b>${n}건 수정됨</b>` : ''}.</p>

      ${table('M5 로 들어가는 값', '고치면 이 화면의 판정이 즉시 다시 계산됩니다. 치명 플래그는 하나만 해당해도 점수·매출과 무관하게 단독 부결입니다.', group(INP.콘솔))}
      ${table('M1~M4 로 들어가는 값', '브라우저가 다시 계산할 수 없습니다(등시선·격자인구·회귀표본 필요). CSV 로 내보내 <code>python3 review_sites.py --sites 후보지.csv</code> 로 다시 돌리십시오.', group(INP.파이프라인))}
      ${table('알고리즘에 들어가지 않는 값', '심의 참고용으로만 싣는 항목입니다. 고쳐도 어떤 모듈도 이 값을 읽지 않습니다.', group(INP.미사용))}
    </div>`;
  }

  function wireInputs(r) {
    const el = document.getElementById('p-sites');
    el.querySelectorAll('[data-inp]').forEach(c => {
      c.onchange = () => { INP.set(r, c.dataset.inp, c.value); afterCoef(); };
    });
    el.querySelectorAll('[data-ri]').forEach(b => b.onclick = () => {
      INP.reset(r, b.dataset.ri); afterCoef();
    });
    const b = (id, fn) => { const x = document.getElementById(id); if (x) x.onclick = fn; };
    b('inp-reset-site', () => { INP.reset(r); U.toast(`${r.이름} 입력값을 되돌렸습니다`); afterCoef(); });
    b('inp-reset-all', () => {
      if (!confirm('모든 후보지의 수정한 입력값을 지웁니다. 계속할까요?')) return;
      INP.reset(); U.toast('입력값을 전부 되돌렸습니다'); afterCoef();
    });
    b('inp-export', () => {
      U.download('sites.csv', INP.toCSV(S.sites()), 'text/csv');
      U.toast('sites.csv 저장 — python3 review_sites.py --sites sites.csv 로 다시 돌리세요');
    });
  }

  const kv = pairs => `<div class="kv">${pairs.map(([k, v]) =>
    `<div><span>${U.esc(k)}</span><b>${v}</b></div>`).join('')}</div>`;

  // ── 손익 시뮬 (M5 재계산) ──────────────────
  const KNOBS = [
    ['rent', '월임대료', 0, 1500, 10, v => `${U.num(v, 0)}만원`],
    ['sales', '월매출(중앙)', 500, 12000, 50, v => `${U.num(v, 0)}만원`],
    ['lowRatio', '하한/중앙 비율', 0.5, 1.0, 0.01, v => v.toFixed(2)],
    ['cogs', '원재료율', 0.2, 0.55, 0.005, v => U.pct(v, 1)],
    ['labor', '고정인건비', 0, 1500, 10, v => `${U.num(v, 0)}만원`],
  ];

  function baseKnobs(r) {
    const o = ops(), fx = o.고정비, vb = o.변동비;
    const p = r.매출 || {};
    return {
      rent: M5.f(INP.merged(r).월임대료_만원),
      sales: p.월매출_중앙 || 0,
      lowRatio: p.월매출_중앙 ? (p.월매출_하한 / p.월매출_중앙) : 0.8,
      cogs: M5.f(vb.원재료율, 0.35),
      labor: M5.f(fx.고정인건비_월_만원, 620),
    };
  }

  function simJudge(r, k) {
    const o = ops();
    const site = { ...INP.merged(r), 월임대료_만원: k.rent };
    const cfg = {
      운영: {
        변동비: { ...o.변동비, 원재료율: k.cogs },
        고정비: { ...o.고정비, 고정인건비_월_만원: k.labor },
      },
    };
    const rev = { 월매출_중앙: k.sales, 월매출_하한: k.sales * k.lowRatio };
    const ov = (r.판정.카니발.상세 || []).map(x => ({ ...x }));
    return M5.judge(site, rev, cfg, r.S, ov, CFG.c('잠식계수_카파'), r.S_풀최대);
  }

  function renderSim() {
    const el = document.getElementById('p-sim');
    if (!S.has()) { el.innerHTML = empty(); wireEmpty(); return; }
    const r = S.find(picked);
    if (!knobs || knobs._for !== r.이름) knobs = { ...baseKnobs(r), _for: r.이름 };
    const j = simJudge(r, knobs);
    const base = verdictOf(r);

    el.innerHTML = `
      ${banner()}
      ${cfgBar()}
      <div class="panel-head">
        <div><h3>손익 시뮬레이션 — ${U.esc(r.이름)}</h3>
          <p>M5 판정 산술만 다시 계산합니다. 상권·수요·경쟁(M1~M3)은 파이프라인 값을 그대로 씁니다.</p></div>
        <div class="acts"><button class="sm ghost" id="sim-reset">기준값으로</button></div>
      </div>
      <div class="grid g2">
        <div class="card"><h3>협상 가정</h3>
          <div class="sliders">${KNOBS.map(([k, lb, mn, mx, st, fmt]) => `
            <div class="slider"><span class="lb">${lb}</span>
              <span class="out" id="o-${k}">${fmt(knobs[k])}</span>
              <input type="range" id="k-${k}" min="${mn}" max="${mx}" step="${st}" value="${knobs[k]}"/>
            </div>`).join('')}</div>
          <p class="hint">가정만 바꿉니다. 저장된 심의결과는 그대로입니다.</p>
        </div>
        <div class="card"><h3>재판정</h3>
          <div class="verdictbox ${V[j.판정]}" style="margin:0 0 12px">
            <b>${MARK[j.판정]} ${j.판정}</b>
            <div>${j.사유.length ? j.사유.map(U.esc).join(' · ') : '조건 충족'}</div>
          </div>
          ${kv([
            ['고정비 F', `${U.num(j.고정비.F, 0)}만원`],
            ['변동비율 v', U.pct(j.변동비율, 1)],
            ['BEP', `${U.num(j.BEP_만원, 0)}만원`],
            ['margin', `${U.pct(j.margin || 0, 1)} <span class="delta">(기준 ${U.pct(base.margin || 0, 1)})</span>`],
            ['margin_low', U.pct(j.margin_low || 0, 1)],
          ])}
          <p class="hint">임대료가 얼마까지 버티는지 확인한 뒤 협상 카드로 쓰십시오.
            치명 플래그는 슬라이더로 사라지지 않습니다.</p>
        </div>
      </div>`;

    KNOBS.forEach(([k, , , , , fmt]) => {
      const inp = document.getElementById(`k-${k}`);
      inp.oninput = () => { knobs[k] = parseFloat(inp.value);
                            document.getElementById(`o-${k}`).textContent = fmt(knobs[k]); };
      inp.onchange = renderSim;
    });
    document.getElementById('sim-reset').onclick = () => { knobs = null; renderSim(); };
  }

  // ── 계수 입력 ─────────────────────────────
  /* 알고리즘의 모든 수치를 여기서 직접 넣는다.
     M5 계수는 넣는 즉시 화면의 판정이 다시 계산되고,
     M1~M4·M6 계수는 브라우저가 다시 계산할 수 없으므로 계수.json 으로 내보내 파이프라인에 넣는다. */
  const SCOPE_TAG = m => m.반영 === CFG.콘솔
    ? '<span class="scope live">즉시 반영</span>'
    : '<span class="scope pipe">재실행 필요</span>';

  function coefRow(n) {
    const m = CFG.meta(n), v = CFG.c(n), ch = CFG.changed(n);
    return `<tr class="${ch ? 'edited' : ''}">
      <td><code>${n}</code>${ch ? ` <span class="flip">명세 ${m.값}</span>` : ''}
        <div class="why">${U.esc(m.설명)}</div></td>
      <td class="num"><input type="number" data-coef="${n}" value="${v}"
        min="${m.최소}" max="${m.최대}" step="${m.증분}"/></td>
      <td><span class="st ${m.상태}">${m.상태}</span></td>
      <td>${SCOPE_TAG(m)}</td>
      <td>${ch ? `<button class="sm ghost" data-rc="${n}">되돌리기</button>` : ''}</td>
    </tr>`;
  }

  const coefTable = names => `<div class="tablewrap cfg"><table>
      <thead><tr><th>계수</th><th class="num">입력값</th><th>검증</th><th>반영</th><th></th></tr></thead>
      <tbody>${names.map(coefRow).join('')}</tbody></table></div>`;

  const byModule = mod => CFG.names().filter(n => CFG.meta(n).모듈 === mod);

  function opsRow(group, k, v) {
    const m = CFG.opsMeta(k), ch = CFG.opsChanged(group, k);
    const base = CFG.opsBase(settings().운영 || {})[group][k];
    return `<tr class="${ch ? 'edited' : ''}">
      <td><code>${k}</code>${ch ? ` <span class="flip">설정 ${base}</span>` : ''}
        <div class="why">${U.esc(m.설명)}</div></td>
      <td class="num"><input type="number" data-ops="${group}.${k}" value="${v}"
        min="${m.최소}" max="${m.최대}" step="${m.증분}"/></td>
      <td><span class="st">설정.yaml</span></td>
      <td><span class="scope live">즉시 반영</span></td>
      <td>${ch ? `<button class="sm ghost" data-ro="${group}.${k}">되돌리기</button>` : ''}</td>
    </tr>`;
  }

  function opsCard() {
    const o = ops();
    const v = M5.variableRate({ 운영: o });
    return `<div class="card"><h3>운영 계수 — 손익 (설정.yaml)</h3>
      <p class="hint" style="margin-top:0">BEP 와 margin 을 직접 만드는 값입니다.
        입력하면 판정이 즉시 다시 계산됩니다.</p>
      <div class="tablewrap cfg"><table>
        <thead><tr><th>항목</th><th class="num">입력값</th><th>출처</th><th>반영</th><th></th></tr></thead>
        <tbody>
          ${Object.keys(o.변동비).map(k => opsRow('변동비', k, o.변동비[k])).join('')}
          ${Object.keys(o.고정비).map(k => opsRow('고정비', k, o.고정비[k])).join('')}
        </tbody></table></div>
      <div class="sumline ${v >= 1 ? 'bad' : ''}"><span>변동비율 v (합)</span>
        <b>${U.pct(v, 1)}${v >= 1 ? ' — 100% 이상이면 어떤 매출에서도 흑자 불가' : ''}</b></div>
    </div>`;
  }

  function tierCard() {
    return `<div class="card"><h3>M3 브랜드 티어 가중</h3>
      <p class="hint" style="margin-top:0">교차탄력 가중입니다. 실증 근거가 아닌 실무 판단값이며,
        Huff 점유율에 직접 들어가므로 파이프라인을 다시 돌려야 반영됩니다.</p>
      <div class="tablewrap cfg"><table>
        <thead><tr><th>티어</th><th class="num">가중</th><th>반영</th><th></th></tr></thead>
        <tbody>${CFG.tierKeys().map(k => {
          const ch = CFG.tier(k) !== CFG.TIER_SPEC[k];
          return `<tr class="${ch ? 'edited' : ''}">
            <td><code>${k}</code>${ch ? ` <span class="flip">명세 ${CFG.TIER_SPEC[k]}</span>` : ''}</td>
            <td class="num"><input type="number" data-tier="${k}" value="${CFG.tier(k)}"
              min="0" max="3" step="0.05"/></td>
            <td><span class="scope pipe">재실행 필요</span></td>
            <td>${ch ? `<button class="sm ghost" data-rt="${k}">되돌리기</button>` : ''}</td>
          </tr>`;
        }).join('')}</tbody></table></div></div>`;
  }

  function modeBCard() {
    const total = CFG.weightTotal();
    return `<div class="card"><h3>M4 Mode B 배점</h3>
      <p class="hint" style="margin-top:0">실증 회귀가 아닌 임의 배점입니다. 후보지 간 상대 비교에만
        유효하며, S 점수를 만드는 값이라 파이프라인을 다시 돌려야 반영됩니다.</p>
      <div class="tablewrap cfg"><table>
        <thead><tr><th>축 · 항목</th><th class="num">배점</th><th>명세</th><th></th></tr></thead>
        <tbody>${CFG.axes().map(a => CFG.items(a).map(k => {
          const w = CFG.weight(a, k), sp = CFG.MODEB_SPEC[a][k], ch = w !== sp;
          return `<tr class="${ch ? 'edited' : ''}">
            <td><span class="tag">${a}</span> <code>${k}</code></td>
            <td class="num"><input type="number" data-mb="${a}.${k}" value="${w}"
              min="0" max="100" step="1"/></td>
            <td class="num">${sp}</td>
            <td>${ch ? `<button class="sm ghost" data-rm="${a}.${k}">되돌리기</button>` : ''}</td>
          </tr>`;
        }).join('')).join('')}</tbody></table></div>
      ${CFG.axes().map(a => `<div class="sumline"><span>${a} 소계</span>
        <b>${CFG.axisTotal(a)}</b></div>`).join('')}
      <div class="sumline ${total !== 100 ? 'bad' : ''}"><span>합계</span>
        <b>${total}${total !== 100 ? ' — 100 이 아니면 S 가 100점 척도가 아닙니다' : ' / 100'}</b></div>
    </div>`;
  }

  function renderCoef() {
    const el = document.getElementById('p-coef');
    const M5N = byModule('M5');
    const pipeMods = ['M1', 'M2', 'M3', 'M4', 'M6'].filter(m => byModule(m).length);

    el.innerHTML = `
      ${banner()}
      ${cfgBar()}
      <div class="panel-head">
        <div><h3>계수 입력</h3>
          <p>알고리즘의 수치를 직접 넣습니다. <b class="scope live">즉시 반영</b> 은 M5 판정 산술에
            들어가 이 콘솔이 바로 다시 계산하는 값이고, <b class="scope pipe">재실행 필요</b> 는
            등시선·격자인구·회귀표본이 있어야 하는 M1~M4·M6 값이라
            <code>coefficients.json</code> 으로 내보내 파이프라인을 다시 돌려야 반영됩니다.</p></div>
        <div class="acts">
          <button class="sm primary" id="cfg-export">계수 파일 내보내기</button>
          <button class="sm" id="cfg-import">계수 파일 불러오기</button>
          <button class="sm ghost danger" id="cfg-reset">전체 명세값으로</button>
        </div>
      </div>

      <div class="card"><h3>M5 판정 임계값 · 잠식</h3>
        <p class="hint" style="margin-top:0">3단 판정의 경계선입니다. 여기를 건드리면
          <b>어떤 후보지가 통과하는지가 바로 바뀝니다</b> — 심의 기준을 바꾸는 행위이므로
          바꾼 값은 리포트에 그대로 남습니다.</p>
        ${coefTable(M5N)}</div>

      <div style="margin-top:14px">${opsCard()}</div>

      ${pipeMods.map(m => `<div class="card" style="margin-top:14px">
        <h3>${m} 계수</h3>${coefTable(byModule(m))}</div>`).join('')}

      <div style="margin-top:14px">${tierCard()}</div>
      <div style="margin-top:14px">${modeBCard()}</div>

      <div class="card" style="margin-top:14px"><h3>파이프라인에 넣기</h3>
        <p class="hint" style="margin-top:0">내보낸 파일을 <code>analysis/</code> 에 두고 파이프라인을
          다시 돌리면 입력값이 M1~M6 전체에 적용됩니다. 어떤 계수가 명세값이 아니라 사람이 넣은
          값인지는 심의표 <b>“콘솔에서 입력한 계수”</b> 절에 그대로 실립니다.</p>
        <pre class="mdout">cd cafe-trade-area/analysis
# 내려받은 coefficients.json (또는 계수.json) 을 이 폴더에 두고
python3 review_sites.py
# 다른 경로에 두었다면
python3 review_sites.py --계수 /경로/coefficients.json</pre></div>`;

    wireCoef();
  }

  function wireCoef() {
    const el = document.getElementById('p-coef');
    const base = () => settings().운영 || {};

    el.querySelectorAll('input[data-coef]').forEach(inp => {
      inp.onchange = () => { CFG.set(inp.dataset.coef, inp.value); afterCoef(); };
    });
    el.querySelectorAll('input[data-ops]').forEach(inp => {
      inp.onchange = () => {
        const [g, k] = inp.dataset.ops.split('.');
        CFG.setOps(g, k, inp.value, base());
        afterCoef();
      };
    });
    el.querySelectorAll('input[data-tier]').forEach(inp => {
      inp.onchange = () => { CFG.setTier(inp.dataset.tier, inp.value); afterCoef(); };
    });
    el.querySelectorAll('input[data-mb]').forEach(inp => {
      inp.onchange = () => {
        const [a, k] = inp.dataset.mb.split('.');
        CFG.setWeight(a, k, inp.value);
        afterCoef();
      };
    });

    el.querySelectorAll('[data-rc]').forEach(b => b.onclick = () => {
      CFG.set(b.dataset.rc, CFG.spec(b.dataset.rc)); afterCoef();
    });
    el.querySelectorAll('[data-ro]').forEach(b => b.onclick = () => {
      const [g, k] = b.dataset.ro.split('.');
      CFG.setOps(g, k, CFG.opsBase(base())[g][k], base()); afterCoef();
    });
    el.querySelectorAll('[data-rt]').forEach(b => b.onclick = () => {
      CFG.setTier(b.dataset.rt, CFG.TIER_SPEC[b.dataset.rt]); afterCoef();
    });
    el.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => {
      const [a, k] = b.dataset.rm.split('.');
      CFG.setWeight(a, k, CFG.MODEB_SPEC[a][k]); afterCoef();
    });

    const b = (id, fn) => { const x = document.getElementById(id); if (x) x.onclick = fn; };
    b('cfg-export', () => {
      const obj = CFG.exportObject(base());
      if (!CFG.anyDirty()) { U.toast('명세값 그대로입니다 — 내보낼 입력값이 없습니다'); return; }
      U.download('coefficients.json', JSON.stringify(obj, null, 2), 'application/json');
      U.toast('coefficients.json 저장 — analysis/ 에 두고 파이프라인을 다시 돌리세요');
    });
    b('cfg-import', () => U.pickFile('.json,application/json', text => {
      try { CFG.importObject(JSON.parse(text), base()); U.toast('계수를 불러왔습니다'); afterCoef(); }
      catch (e) { U.toast(`불러오기 실패: ${e.message}`); }
    }));
    b('cfg-reset', () => {
      if (!CFG.anyDirty()) { U.toast('이미 명세값입니다'); return; }
      if (!confirm('입력한 계수를 모두 지우고 명세 기본값으로 되돌립니다. 계속할까요?')) return;
      CFG.reset(); U.toast('명세값으로 되돌렸습니다'); afterCoef();
    });
  }

  // 계수가 바뀌면 판정이 바뀐다 — 화면 전체를 다시 그린다.
  function afterCoef() { knobs = null; render(); }

  // ── 데이터 ────────────────────────────────
  function renderData() {
    const d = S.get();
    document.getElementById('p-data').innerHTML = `
      ${banner()}
      <div class="card"><h3>불러오기</h3>
        <p class="hint" style="margin-top:0">이 콘솔은 파이프라인이 만든
          <code>analysis/output/심의결과.json</code> 을 읽습니다.
          모델을 다시 계산하지 않으므로 CLI 와 숫자가 어긋나지 않습니다.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="primary" id="btn-file">심의결과.json 열기</button>
          <button id="btn-fetch">output/ 에서 불러오기</button>
          <button class="ghost" id="btn-demo2">예시 결과</button>
          <button class="ghost danger" id="btn-clear">비우기</button>
        </div>
        ${d ? `<p class="hint">현재: 후보지 ${d.후보지.length}곳 · 모드 ${d.모드} · 생성 ${U.esc(d.생성 || '')}</p>` : ''}
      </div>

      <div class="card"><h3>미검증 계수</h3>
        <p class="hint" style="margin-top:0">실증 근거가 아닌 실무 판단 초기값이
          ${CFG.names().filter(n => CFG.meta(n).상태 === CFG.ESTIMATED).length}건 있습니다.
          M6 사후 보정 루프(<code>calibrate.py</code>)로 순차 교정해야 하며,
          그 전까지는 <b>계수 입력</b> 탭에서 직접 값을 넣어 결과가 어떻게 움직이는지 확인하십시오.</p>
        <button class="sm" data-go="coef">계수 입력 열기</button>
      </div>

      <div class="card"><h3>콘솔이 계산하지 않는 것</h3>
        <p class="hint" style="margin-top:0">M1 등시선 · M2 격자 교차 · M3 Huff · M4 회귀는
          OSM 보행 네트워크, 통계청 격자 인구, 기존점 실적이 있어야 합니다. 브라우저에서
          흉내내면 CLI 와 다른 숫자를 내는 것이 유일한 결과이므로 재현하지 않습니다.
          콘솔이 다시 계산하는 것은 <b>M5 판정 산술</b>뿐이며,
          <code>analysis/tests/test_m5_parity.py</code> 가 두 구현을 대조합니다.</p>
      </div>`;
    wireLoaders();
  }

  // ── 공통 ─────────────────────────────────
  const empty = () => `${banner()}<div class="empty"><b>심의결과가 없습니다</b>
    <code>cd analysis && python3 review_sites.py</code> 로 만든
    <code>output/심의결과.json</code> 을 불러오세요.
    <div style="margin-top:16px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
      <button class="primary" id="e-file">파일 열기</button>
      <button id="e-fetch">output/ 에서 불러오기</button>
      <button class="ghost" id="e-demo">예시 결과 보기</button>
    </div></div>`;

  function loadFile() {
    U.pickFile('.json,application/json', text => {
      try { S.set(JSON.parse(text)); U.toast('심의결과를 불러왔습니다'); render(); }
      catch (e) { U.toast(`불러오기 실패: ${e.message}`); }
    });
  }

  async function loadFetch() {
    try {
      const res = await fetch('../analysis/output/심의결과.json');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      S.set(await res.json());
      U.toast('output/ 에서 불러왔습니다');
      render();
    } catch (e) {
      U.toast('불러오지 못했습니다. file:// 로 열었다면 "파일 열기"를 쓰세요.');
    }
  }

  function wireEmpty() {
    const b = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
    b('e-file', loadFile); b('e-fetch', loadFetch);
    b('e-demo', () => { S.demo(); U.toast('예시 결과를 넣었습니다'); render(); });
  }

  function wireLoaders() {
    const b = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
    b('btn-file', loadFile); b('btn-fetch', loadFetch);
    b('btn-demo2', () => { S.demo(); U.toast('예시 결과를 넣었습니다'); render(); });
    b('btn-clear', () => {
      if (!confirm('불러온 심의결과를 비웁니다. 계속할까요?')) return;
      S.clear(); knobs = null; U.toast('비웠습니다'); render();
    });
  }

  function wireOpen() {
    document.querySelectorAll('[data-open]').forEach(tr => tr.onclick = () => {
      picked = tr.dataset.open; go('sites');
    });
  }

  function go(next) {
    if (!TABS.includes(next)) return;
    tab = next;
    document.querySelectorAll('.tab').forEach(b =>
      b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    TABS.forEach(t => document.getElementById(`p-${t}`).classList.toggle('hide', t !== tab));
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function render() {
    document.getElementById('pill-sites').textContent = S.sites().length;
    const pc = document.getElementById('pill-coef');
    pc.textContent = CFG.dirtyCount();
    pc.classList.toggle('hide', !CFG.dirtyCount());
    const pi = document.getElementById('pill-inputs');
    pi.textContent = INP.dirtyCount();
    pi.classList.toggle('hide', !INP.dirtyCount());

    if (tab === 'status') renderStatus();
    else if (tab === 'sites') renderSites();
    else if (tab === 'sim') renderSim();
    else if (tab === 'coef') renderCoef();
    else renderData();

    const rb = document.getElementById('cfg-reset-all');
    if (rb) rb.onclick = () => {
      if (!confirm('손으로 넣은 계수와 후보지 입력값을 모두 지우고 원래 값으로 되돌립니다. 계속할까요?')) return;
      CFG.reset(); INP.reset(); U.toast('원래 값으로 되돌렸습니다'); afterCoef();
    };
  }

  function init() {
    document.querySelectorAll('.tab').forEach(b => b.onclick = () => go(b.dataset.tab));
    document.addEventListener('click', e => {
      const t = e.target.closest && e.target.closest('[data-go]');
      if (t) go(t.dataset.go);
    });
    document.getElementById('btn-demo').onclick = () => {
      S.demo(); knobs = null; U.toast('예시 결과를 넣었습니다'); go('status');
    };
    go('status');
  }

  return { init, go, render };
})();

document.addEventListener('DOMContentLoaded', App.init);
