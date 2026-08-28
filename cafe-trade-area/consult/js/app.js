/* 고객 상담 페이지.

   개인정보를 다루는 유일한 화면이다. 그래서 두 가지를 지킨다.
     1. 어디로도 전송하지 않는다. 서버가 없고, 저장은 이 브라우저의 localStorage 뿐이다.
     2. 수집·이용 동의를 받기 전에는 고객 정보를 저장하지도 내보내지도 않는다.

   내보내는 파일도 둘로 나눈다.
     상담카드.md    개인정보 포함 — 상담사가 보관한다
     조건.json      개인정보 제외 — 파이프라인에 넣는다 (consult.py 가 먹는다)
   심의 자료는 사내 회람 문서라 고객 연락처가 들어갈 자리가 아니다. */
(() => {
  'use strict';

  const KEY = 'cafe-trade-area/상담/v1';
  const AGREE = 'cafe-trade-area/상담동의/v1';
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nf = v => Math.round(Number(v) || 0).toLocaleString('ko-KR');

  const blank = () => ({ 희망지역: [], 희망상권: [], 희망평수: '', 보증금_만원: '',
                         권리금_만원: '', 투자금형태: '', 운영형태: '',
                         고객명: '', 고객전화번호: '', 거주지: '', 근무지: '' });

  let cond = load();
  let agreed = loadAgree();
  let 미리보기임대료 = '300';

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? Object.assign(blank(), JSON.parse(raw)) : blank();
    } catch (e) { return blank(); }
  }
  function loadAgree() {
    try { return localStorage.getItem(AGREE) === 'Y'; } catch (e) { return false; }
  }
  function save() {
    try {
      // 동의 전에는 개인정보를 저장하지 않는다 — 나머지 조건만 남긴다
      const out = Object.assign({}, cond);
      if (!agreed) CFIELDS.개인정보키().forEach(k => { out[k] = ''; });
      localStorage.setItem(KEY, JSON.stringify(out));
    } catch (e) {}
  }

  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('on');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove('on'), 2600);
  }

  /* ── 입력 컨트롤 ─────────────────────────────── */
  /* id·describedby 를 밖에서 받는다. 라벨은 컨트롤을 감싸지 않고 for 로 가리키므로
     (그래야 접근성 이름이 라벨 글자만 남는다) 연결에 쓸 id 가 필요하다.
     칩·지역처럼 컨트롤이 버튼 묶음인 경우는 for 로 가리킬 대상이 없어
     role="group" + aria-labelledby 로 묶는다. */
  function control(k, id, help) {
    const m = CFIELDS.meta(k);
    const v = cond[k];
    const off = (m.목적지 === '개인정보' && !agreed) ? ' disabled' : '';
    const grp = ` role="group" aria-labelledby="${id}-lb" aria-describedby="${help}"`;
    if (m.종류 === 'choice' || m.종류 === 'multi') {
      const multi = m.종류 === 'multi';
      const set = multi ? (Array.isArray(v) ? v : []) : null;
      return `<div class="chips${multi ? ' multi' : ''}" data-k="${k}"${grp}>${m.선택지.map(o => {
        const on = multi ? set.includes(o) : v === o;
        return `
        <button type="button" class="chip ${on ? 'on' : ''}" data-v="${esc(o)}"${off}
          aria-pressed="${on}">${esc(o)}</button>`;
      }).join('')}</div>`;
    }
    if (m.종류 === 'regions') {
      const list = Array.isArray(v) ? v : [];
      return `<div class="regions" data-k="${k}"${grp}>
        ${list.map((r, i) => `<span class="rg"><b>${i + 1}</b>${esc(r)}
          <button type="button" class="x" data-i="${i}"
            aria-label="${esc(r)} 빼기">×</button></span>`).join('')}
        <span class="rgadd">
          <label class="vh" for="rg-in">지역 추가</label>
          <input type="text" id="rg-in" name="지역추가" placeholder="예: 성수동…"
            autocomplete="off" enterkeyhint="done"/><button type="button" id="rg-go">추가</button></span>
      </div>`;
    }
    const type = m.종류 === 'num' ? 'number' : (m.종류 === 'tel' ? 'tel' : 'text');
    const attrs = m.종류 === 'num'
      ? ` min="${m.최소 ?? 0}" max="${m.최대 ?? 999999}" step="${m.증분 ?? 1}" inputmode="decimal"` : '';
    // autocomplete 는 끈다 — 고객 정보를 상담사 브라우저의 자동완성에 남기지 않는다
    return `<input type="${type}" id="${id}" name="${esc(k)}" data-k="${k}" value="${esc(v)}"${attrs}${off}
      autocomplete="off" spellcheck="false" aria-describedby="${help}"${m.종류 === 'tel' ? ' placeholder="010-0000-0000"' : ''}/>`;
  }

  const 뱃지 = d => `<span class="dest d-${d === '알고리즘' ? 'a' : d === '필터' ? 'f' : 'p'}">${d}</span>`;

  /* 라벨이 뱃지·설명까지 감싸면 접근성 이름이 통째로 뭉친다 —
     스크린리더가 '고객명필수개인정보 상담 기록에만 남습니다' 를 필드 이름으로 읽는다.
     라벨은 글자만, 나머지는 aria-describedby 로 붙인다. */
  function field(k) {
    const m = CFIELDS.meta(k);
    const wide = (m.종류 === 'regions' || m.종류 === 'multi' || m.종류 === 'choice');
    const id = 'f-' + k;
    const help = `${id}-help`;
    const 묶음 = (m.종류 === 'regions' || m.종류 === 'multi' || m.종류 === 'choice');
    const lb = 묶음
      ? `<span class="lb"><span id="${id}-lb">${esc(m.라벨)}</span>`
      : `<label class="lb" for="${id}">${esc(m.라벨)}</label>`;
    return `<div class="fld${wide ? ' wide' : ''}">
      <div class="f-h">${lb}${m.필수 ? '<em>필수</em>' : ''}${뱃지(m.목적지)}${묶음 ? '</span>' : ''}</div>
      ${control(k, id, help)}
      <small id="${help}">${esc(m.설명)}</small></div>`;
  }

  /* ── 개인정보 동의 ─────────────────────────────── */
  function consentBlock() {
    return `<fieldset class="consent ${agreed ? 'ok' : ''}">
      <legend>개인정보 수집·이용 동의</legend>
      <p class="note">고객의 성명·연락처·거주지·근무지를 <b>상담 진행과 후보지 추천</b>을 위해
        수집합니다. 이 페이지에는 서버가 없습니다 — 입력한 값은 <b>이 브라우저에만</b> 저장되고
        어디로도 전송되지 않습니다. 상담이 끝나면 <b>전체 비우기</b>로 지우십시오.</p>
      <ul class="cnote">
        <li>수집 항목 — 성명 · 연락처 · 거주지 · 근무지</li>
        <li>이용 목적 — 상담 기록, 통근 가능 범위 확인, 후보지 추천</li>
        <li>보관 — 이 브라우저 안에서만. 별도 서버 보관 없음</li>
        <li>파이프라인으로 내보내는 <code>조건.json</code> 에는 <b>개인정보가 들어가지 않습니다</b></li>
      </ul>
      <label class="agree"><input type="checkbox" id="agree" name="동의"${agreed ? ' checked' : ''}/>
        <span>고객에게 위 내용을 안내하고 동의를 받았습니다</span></label>
      ${agreed ? '' : '<p class="warn">동의 전에는 고객 정보를 입력·저장할 수 없습니다.</p>'}
    </fieldset>`;
  }

  /* ── 미리보기 ─────────────────────────────── */
  function preview() {
    const 금융 = CCALC.금융비용(cond), 노무 = CCALC.인건비(cond);
    const 준비 = 금융.적용 && 노무.적용;
    if (!준비) {
      return `<fieldset><legend>손익분기 미리보기</legend>
        <p class="note">투자금 형태와 운영 형태를 고르면 <b>월 손익분기 매출</b>이 나옵니다.
          상담에서 받는 값 중 판정을 실제로 움직이는 것은 이 둘뿐입니다.</p></fieldset>`;
    }
    const rent = 미리보기임대료;
    const b = CCALC.bep(cond, rent);
    const 비교 = CCALC.형태비교(cond, rent);
    return `<fieldset>
      <legend>손익분기 미리보기</legend>
      <p class="note">월임대료를 가정해 <b>월 얼마를 팔아야 본전인지</b>를 냅니다.
        고정인건비·기타는 설정 파일이 아니라 화면용 폴백이며, 파이프라인은 <code>설정.yaml</code> 을 씁니다.</p>
      <div class="fld inline"><div class="f-h"><label class="lb" for="pv-rent">가정 월임대료 (만원)</label></div>
        <input type="number" id="pv-rent" name="가정월임대료" value="${esc(rent)}"
          min="0" step="10" inputmode="decimal" autocomplete="off"/></div>
      <div class="bep">
        <div class="bep-n"><span>월 손익분기 매출</span><b>${nf(b.월BEP)}<small>만원</small></b></div>
        <div class="bep-n"><span>일 손익분기 매출</span><b>${nf(b.일BEP)}<small>만원</small></b></div>
        <p class="note">고정비 F ${nf(b.F)}만원 = 임대료 ${nf(rent)} + 관리비 ${nf(b.관리비)}(추정)
          + 고정인건비 ${nf(노무.고정인건비_월_만원)} + 기타 ${nf(b.기타)}
          (금융비용 ${nf(금융.월_금융비용_만원)} 포함) · 변동비율 ${(b.변동비율 * 100).toFixed(1)}%</p>
      </div>
      <div class="cmp">
        <div class="cmp-h">운영 형태를 바꾸면</div>
        <table><thead><tr><th>형태</th><th>고정인건비</th><th>월 BEP</th><th>차이</th></tr></thead><tbody>
        ${비교.map(r => `<tr class="${r.형태 === cond.운영형태 ? 'on' : ''}">
          <td>${esc(r.형태)}</td><td class="mono">${nf(r.인건비)}</td>
          <td class="mono">${nf(r.월BEP)}</td>
          <td class="mono ${r.월BEP > b.월BEP ? 'up' : r.월BEP < b.월BEP ? 'dn' : ''}">
            ${r.월BEP === b.월BEP ? '—' : (r.월BEP > b.월BEP ? '+' : '') + nf(r.월BEP - b.월BEP)}</td></tr>`).join('')}
        </tbody></table>
      </div>
      ${금융.차입_추정_만원 > 0 ? `<p class="note warnline">⚠ 차입 원금을 (보증금+권리금) ×
        대출비율 = ${nf(금융.차입_추정_만원)}만원 으로 잡았습니다. 인테리어·집기 같은 시설자금과
        운전자금이 빠진 <b>과소 추정</b>입니다 — 실제 월 상환액이 나오면 설정을 고쳐야 합니다.</p>` : ''}
    </fieldset>`;
  }

  /* ── 준비 상태 ─────────────────────────────── */
  function ready() {
    const 빠짐 = CFIELDS.required().filter(k => {
      if (CFIELDS.meta(k).목적지 === '개인정보' && !agreed) return false;
      return String(cond[k] ?? '').trim() === '';
    });
    const 조건없음 = CFIELDS.알고리즘키().filter(k => !String(cond[k] ?? '').trim());
    const ok = !빠짐.length && !조건없음.length;
    const L = [];
    if (!agreed) L.push('개인정보 수집·이용 동의를 받아야 고객 정보를 입력할 수 있습니다');
    if (빠짐.length) L.push(`필수 항목 미입력 — ${빠짐.map(k => CFIELDS.meta(k).라벨).join(', ')}`);
    if (조건없음.length) L.push(`판정에 필요한 항목 미선택 — ${조건없음.map(k => CFIELDS.meta(k).라벨).join(', ')}`);
    $('#ready').innerHTML = `<div class="ready ${ok ? 'go' : 'hold'}">
      <b>${ok ? '내보낼 수 있습니다' : '아직 내보낼 수 없습니다'}</b>
      ${L.length ? `<ul>${L.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`
        : '<p>조건.json 을 파이프라인에 넣으면 고정비가 반영된 심의가 돌아갑니다.</p>'}</div>`;
    $$('.needcond').forEach(b => { b.disabled = !ok; });
  }

  /* ── 내보내기 ─────────────────────────────── */
  function 조건JSON() {
    // 개인정보를 뺀 사본. consult.py 가 읽는 키만 남긴다.
    const out = {};
    CFIELDS.keys().forEach(k => {
      if (CFIELDS.meta(k).목적지 === '개인정보') return;
      out[k] = cond[k];
    });
    return JSON.stringify({ 생성: 'consult 페이지', 조건: out }, null, 2);
  }

  function 상담카드MD() {
    const 금융 = CCALC.금융비용(cond), 노무 = CCALC.인건비(cond);
    const b = CCALC.bep(cond, 미리보기임대료);
    const L = ['# 상담 카드', '',
      '> ⚠ 이 파일에는 **고객 개인정보가 들어 있습니다.** 사내 상담 기록으로만 보관하고,',
      '> 심의 자료(심의표·리포트)와 섞지 마십시오.', '',
      '## 고객', '', '| 항목 | 값 |', '|---|---|'];
    CFIELDS.개인정보키().forEach(k =>
      L.push(`| ${CFIELDS.meta(k).라벨} | ${cond[k] || '—'} |`));
    L.push('', '## 희망 조건', '', '| 항목 | 값 |', '|---|---|',
      `| 창업 희망 지역 | ${(cond.희망지역 || []).map((r, i) => `${i + 1}. ${r}`).join(' · ') || '—'} |`,
      `| 희망 평수 | ${cond.희망평수 || '—'}평 |`,
      `| 희망 상권 | ${(cond.희망상권 || []).join(' · ') || '—'} |`,
      `| 보증금 | ${nf(cond.보증금_만원)}만원 |`,
      `| 권리금 | ${nf(cond.권리금_만원)}만원 |`,
      `| 투자 합계 | ${nf(CCALC.투자합계(cond))}만원 |`,
      `| 투자금 형태 | ${cond.투자금형태 || '—'} |`,
      `| 운영 형태 | ${cond.운영형태 || '—'} |`);
    if (노무.적용 && 금융.적용) {
      L.push('', '## 손익분기 (가정)', '',
        `월임대료 ${nf(미리보기임대료)}만원 가정 시 **월 ${nf(b.월BEP)}만원 / 일 ${nf(b.일BEP)}만원**`, '',
        `- 고정비 F ${nf(b.F)}만원 (고정인건비 ${nf(노무.고정인건비_월_만원)} · 금융비용 ${nf(금융.월_금융비용_만원)} 포함)`,
        `- 변동비율 ${(b.변동비율 * 100).toFixed(1)}%`, '',
        '> 임대료를 가정한 값이고, 고정인건비·기타는 화면용 폴백입니다.',
        '> 실제 판정은 후보지를 넣고 파이프라인을 돌려야 나옵니다.');
    }
    L.push('', '---', '', '개인정보 수집·이용 동의: ' + (agreed ? '받음' : '미수령'));
    return L.join('\n') + '\n';
  }

  function download(name, text, mime) {
    const blob = new Blob([text], { type: (mime || 'text/plain') + ';charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  /* ── 렌더 ─────────────────────────────── */
  function render() {
    $('#pane').innerHTML = consentBlock() + CFIELDS.GROUPS.map(g => `
      <fieldset${g.개인정보 ? ' class="pii"' : ''}>
        <legend>${esc(g.이름)}${g.개인정보 ? '<span class="pii-tag">개인정보</span>' : ''}</legend>
        ${g.설명 ? `<p class="note">${esc(g.설명)}</p>` : ''}
        <div class="grid">${g.항목.map(([k]) => field(k)).join('')}</div>
      </fieldset>`).join('') + preview();
    wire();
    ready();
  }

  function set(k, v) { cond[k] = v; save(); render(); }

  function wire() {
    const ag = $('#agree');
    if (ag) ag.onchange = () => {
      agreed = ag.checked;
      try { localStorage.setItem(AGREE, agreed ? 'Y' : 'N'); } catch (e) {}
      if (!agreed) CFIELDS.개인정보키().forEach(k => { cond[k] = ''; });
      save(); render();
      toast(agreed ? '동의를 기록했습니다' : '동의를 해제하고 고객 정보를 지웠습니다');
    };

    $$('#pane input[data-k]').forEach(el => {
      el.onchange = () => set(el.dataset.k, el.value);
    });
    $$('#pane .chips').forEach(box => {
      const k = box.dataset.k, multi = box.classList.contains('multi');
      $$('.chip', box).forEach(b => {
        b.onclick = () => {
          if (multi) {
            const cur = Array.isArray(cond[k]) ? cond[k].slice() : [];
            const i = cur.indexOf(b.dataset.v);
            if (i >= 0) cur.splice(i, 1); else cur.push(b.dataset.v);
            set(k, cur);
          } else {
            set(k, cond[k] === b.dataset.v ? '' : b.dataset.v);
          }
        };
      });
    });
    const rgIn = $('#rg-in'), rgGo = $('#rg-go');
    const addRegion = () => {
      const v = (rgIn.value || '').trim();
      if (!v) return;
      const cur = Array.isArray(cond.희망지역) ? cond.희망지역.slice() : [];
      if (cur.includes(v)) { toast('이미 넣은 지역입니다'); return; }
      cur.push(v); set('희망지역', cur);
    };
    if (rgGo) rgGo.onclick = addRegion;
    if (rgIn) rgIn.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); addRegion(); } };
    $$('#pane .regions .x').forEach(b => {
      b.onclick = () => {
        const cur = cond.희망지역.slice();
        cur.splice(Number(b.dataset.i), 1);
        set('희망지역', cur);
      };
    });
    const pv = $('#pv-rent');
    if (pv) {
      pv.oninput = () => { 미리보기임대료 = pv.value; };
      pv.onchange = () => { 미리보기임대료 = pv.value; render(); };
    }
  }

  function init() {
    $('#ex-json').onclick = () => {
      download('consult.json', 조건JSON(), 'application/json');
      toast('조건.json 을 내려받았습니다 — 개인정보는 들어 있지 않습니다');
    };
    $('#ex-card').onclick = () => {
      if (!agreed) { toast('동의를 받아야 상담 카드를 만들 수 있습니다'); return; }
      download('consult-card.md', 상담카드MD(), 'text/markdown');
      toast('상담 카드를 내려받았습니다 — 개인정보가 들어 있습니다');
    };
    $('#clear').onclick = () => {
      if (!confirm('이 브라우저에 저장된 상담 내용을 모두 지웁니다. 계속할까요?')) return;
      cond = blank(); agreed = false;
      try { localStorage.removeItem(KEY); localStorage.removeItem(AGREE); } catch (e) {}
      render();
      toast('전부 지웠습니다');
    };
    render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
