/* 공용 유틸 — CSV/파일 입출력·포맷. 의존성 없음. */
const U = (() => {

  /* 따옴표·줄바꿈이 든 셀까지 처리하는 CSV 파서.
     엑셀에서 저장한 한글 CSV 의 BOM 도 제거한다. */
  function parseCSV(text) {
    const src = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n');
    const rows = [];
    let row = [], cell = '', q = false;
    for (let i = 0; i < src.length; i++) {
      const ch = src[i];
      if (q) {
        if (ch === '"') { if (src[i + 1] === '"') { cell += '"'; i++; } else q = false; }
        else cell += ch;
      } else if (ch === '"') q = true;
      else if (ch === ',') { row.push(cell); cell = ''; }
      else if (ch === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
      else cell += ch;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    if (!rows.length) return [];
    const head = rows[0].map(h => h.trim());
    return rows.slice(1)
      .filter(r => r.some(c => String(c).trim() !== ''))
      .map(r => Object.fromEntries(head.map((h, i) => [h, (r[i] ?? '').trim()])));
  }

  function toCSV(rows, headers) {
    if (!rows.length && !headers) return '';
    const head = headers || Object.keys(rows[0]);
    const esc = v => {
      const s = v === null || v === undefined ? '' : String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    return [head.join(','), ...rows.map(r => head.map(h => esc(r[h])).join(','))].join('\n');
  }

  /* 브라우저에서 파일로 내려주기. BOM 을 붙여야 엑셀이 한글을 깨뜨리지 않는다. */
  function download(name, text, mime = 'text/plain') {
    const bom = mime.includes('csv') ? '﻿' : '';
    const url = URL.createObjectURL(new Blob([bom + text], { type: `${mime};charset=utf-8` }));
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function pickFile(accept, cb) {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = accept;
    inp.onchange = () => {
      const file = inp.files && inp.files[0];
      if (!file) return;
      const fr = new FileReader();
      fr.onload = () => cb(String(fr.result), file.name);
      fr.readAsText(file, 'utf-8');
    };
    inp.click();
  }

  const num = (v, d = 1) => Number(v || 0).toLocaleString('ko-KR', { maximumFractionDigits: d });
  const won = v => `${num(Math.round(v || 0), 0)}만원`;
  const pct = (v, d = 1) => `${((v || 0) * 100).toFixed(d)}%`;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const uid = () => 's' + Math.random().toString(36).slice(2, 9);
  const today = () => new Date().toISOString().slice(0, 10);

  function toast(msg) {
    let el = document.getElementById('toast');
    if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.add('on');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove('on'), 2200);
  }

  return { parseCSV, toCSV, download, pickFile, num, won, pct, esc, uid, today, toast };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = U;
