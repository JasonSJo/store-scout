/* 후보지 입력값 — 심의결과에 담긴 후보지 CSV 행을 화면에서 직접 고친다.

   계수(config.js)와 같은 2단 구조다.
   '콘솔'      M5 판정 산술에 들어가는 값 — 고치면 판정이 즉시 다시 계산된다.
               (임대료·관리비 → F·BEP·margin, 치명 플래그 → 단독 부결)
   '파이프라인' M1~M4 로 들어가는 값 — 등시선·격자인구·회귀가 필요해 브라우저에서
               다시 계산할 수 없다. 후보지 CSV 로 내보내 파이프라인을 다시 돌린다.

   원본(파이프라인이 낸 심의결과)은 건드리지 않고, 고친 값만 따로 얹는다. */
const INP = (() => {
  const KEY = 'cafe-trade-area/후보지입력/v1';
  const 콘솔 = '콘솔', 파이프라인 = '파이프라인', 미사용 = '미사용';

  // 치명 플래그는 3상태다 — 빈칸(미확인)은 '해당 없음'과 다르며 통과 판정을 잠정으로 만든다.
  const FATAL = ['근저당_과다', '임대인_불일치', '소송_계류', '인허가_불가'];

  // [라벨, 종류, 반영, 모듈, 설명, 최소, 최대, 증분]
  const FIELDS = {
    월임대료_만원: ['월임대료', 'num', 콘솔, 'M5 · M4', '고정비 F 에 직접 들어간다. M4 Mode B 배점에도 쓰이지만 그쪽은 재실행 필요', 0, 20000, 1],
    관리비_만원:   ['관리비', 'num', 콘솔, 'M5', '고정비 F 구성 항목', 0, 5000, 1],
    근저당_과다:   ['근저당 과다', 'flag', 콘솔, 'M5', '등기부상 근저당 과다 또는 선순위 권리로 보증금 회수 불확실'],
    임대인_불일치: ['임대인 불일치', 'flag', 콘솔, 'M5', '임대인이 실소유자와 불일치 (전대차 구조·자기거래 정황)'],
    소송_계류:     ['소송 계류', 'flag', 콘솔, 'M5', '소송·명도 분쟁 계류 중인 물건'],
    인허가_불가:   ['인허가 불가', 'flag', 콘솔, 'M5', '용도지역·정화조 용량 등으로 휴게음식점 인허가 불가'],

    위도:          ['위도', 'num', 파이프라인, 'M1~M3', '등시선·격자 교차·경쟁 거리의 기준점', 33, 39, 0.0001],
    경도:          ['경도', 'num', 파이프라인, 'M1~M3', '등시선·격자 교차·경쟁 거리의 기준점', 124, 132, 0.0001],
    잔존율_R:      ['잔존율 R', 'num', 파이프라인, 'M1', '비우면 등시선 면적에서 계산한다', 0, 1, 0.01],
    도로변:        ['도로변', 'text', 파이프라인, 'M2', '같은편/반대편 유동인구 구분 (A·B)'],
    좌석수:        ['좌석수', 'num', 파이프라인, 'M3', '흡인력 A = 좌석수^0.5 × 브랜드가중', 0, 300, 1],
    층:            ['층', 'num', 파이프라인, 'M4', 'Mode B 1층접근성 배점', -3, 30, 1],
    코너여부:      ['코너 여부', 'flag', 파이프라인, 'M4', 'Mode B 코너전면가시성 배점'],
    전면폭_m:      ['전면폭(m)', 'num', 파이프라인, 'M4', 'Mode B 코너전면가시성 배점', 0, 60, 0.1],
    주차가능대수:  ['주차 가능 대수', 'num', 파이프라인, 'M4', 'Mode B 주차정차 배점', 0, 200, 1],
    정차가능:      ['정차 가능', 'flag', 파이프라인, 'M4', 'Mode B 주차정차 배점'],
    방향적합:      ['출근동선 방향적합', 'flag', 파이프라인, 'M4', 'Mode B 출근동선방향 배점'],
    계약조건점수:  ['계약조건 점수', 'num', 파이프라인, 'M4', 'Mode B 계약조건 배점 (0~5)', 0, 5, 1],

    전용면적_평:   ['전용면적(평)', 'num', 콘솔, 'M5', '지역 실거래가와 대조할 때 건물가치를 환산하는 면적. 비우면 시세 대조를 건너뛴다', 0, 500, 0.1],

    보증금_만원:   ['보증금', 'num', 미사용, '—', '알고리즘에 들어가지 않습니다 — 심의 참고값', 0, 200000, 10],
    권리금_만원:   ['권리금', 'num', 미사용, '—', '알고리즘에 들어가지 않습니다 — 심의 참고값', 0, 200000, 10],
  };

  const store = (() => {
    try { return (typeof localStorage !== 'undefined') ? localStorage : null; }
    catch (e) { return null; }
  })();

  let ov = load();

  function load() {
    if (!store) return {};
    try { return JSON.parse(store.getItem(KEY) || '{}'); } catch (e) { return {}; }
  }
  function save() {
    if (!store) return;
    try { store.setItem(KEY, JSON.stringify(ov)); } catch (e) { /* 시크릿 모드 등 */ }
  }

  const keys = () => Object.keys(FIELDS);
  const meta = k => {
    const f = FIELDS[k];
    if (!f) return null;
    return { 라벨: f[0], 종류: f[1], 반영: f[2], 모듈: f[3], 설명: f[4],
             최소: f[5], 최대: f[6], 증분: f[7] };
  };
  const editable = k => !!FIELDS[k];
  const 콘솔반영 = k => (FIELDS[k] || [])[2] === 콘솔;

  /* ── 값 ─────────────────────────────── */
  const origin = (r, k) => (r.입력 || {})[k];
  const value = (r, k) => {
    const o = ov[r.이름] || {};
    return (k in o) ? o[k] : origin(r, k);
  };
  const changed = (r, k) => {
    const o = ov[r.이름] || {};
    return (k in o) && String(o[k]) !== String(origin(r, k) ?? '');
  };

  // 판정에 넘길 입력 행 — 원본 위에 고친 값만 얹는다.
  const merged = r => ({ ...(r.입력 || {}), ...(ov[r.이름] || {}) });

  function set(r, k, raw) {
    const m = meta(k);
    if (!m) return value(r, k);
    let v = raw;
    if (m.종류 === 'num') {
      const n = Number(String(raw).replace(/,/g, '').trim());
      v = (String(raw).trim() === '') ? '' :
          (Number.isFinite(n) ? String(Math.min(m.최대, Math.max(m.최소, n))) : String(origin(r, k) ?? ''));
    } else {
      v = String(raw);
    }
    const o = ov[r.이름] || (ov[r.이름] = {});
    if (String(v) === String(origin(r, k) ?? '')) {
      delete o[k];
      if (!Object.keys(o).length) delete ov[r.이름];
    } else {
      o[k] = v;
    }
    save();
    return value(r, k);
  }

  function reset(r, k) {
    if (!r) { ov = {}; save(); return; }
    if (!k) { delete ov[r.이름]; save(); return; }
    const o = ov[r.이름];
    if (o) { delete o[k]; if (!Object.keys(o).length) delete ov[r.이름]; }
    save();
  }

  /* ── 변경 상태 ────────────────────────── */
  const siteDirty = r => Object.keys(ov[r.이름] || {}).length;
  const dirtyCount = () => Object.values(ov).reduce((n, o) => n + Object.keys(o).length, 0);
  // 판정을 다시 계산해야 하는 변경이 있는가
  const liveDirty = () => Object.values(ov).some(o => Object.keys(o).some(콘솔반영));
  const pipelineDirty = () => Object.values(ov).some(o =>
    Object.keys(o).some(k => (FIELDS[k] || [])[2] === 파이프라인));
  const anyDirty = () => dirtyCount() > 0;

  /* ── 후보지 CSV 내보내기 ──────────────── */
  // 파이프라인의 --sites 입력 형식 그대로. 열 순서는 원본 행의 순서를 따른다.
  function toCSV(sites) {
    if (!sites.length) return '';
    const cols = [];
    sites.forEach(r => Object.keys(r.입력 || {}).forEach(k => {
      if (!cols.includes(k)) cols.push(k);
    }));
    const cell = v => {
      const s = String(v ?? '');
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [cols.map(cell).join(',')];
    sites.forEach(r => {
      const row = merged(r);
      lines.push(cols.map(k => cell(row[k])).join(','));
    });
    return lines.join('\n') + '\n';
  }

  return {
    콘솔, 파이프라인, 미사용, FATAL,
    keys, meta, editable, 콘솔반영,
    origin, value, changed, merged, set, reset,
    siteDirty, dirtyCount, liveDirty, pipelineDirty, anyDirty, toCSV,
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = INP;
