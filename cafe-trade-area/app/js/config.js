/* 계수 레지스트리 — analysis/config.py 의 웹앱 대응물.
   명세 기본값(SPEC)은 config.py 와 같아야 하며 tests/test_config_parity.py 가 대조한다.
   사용자가 입력한 값은 override 로 얹히고 이 브라우저에만 남는다.

   ── 반영 범위 ──
   '콘솔'      M5 판정 산술에 들어가는 값. 입력하면 화면의 판정이 즉시 다시 계산된다.
   '파이프라인' M1~M4·M6 계수. 등시선·격자인구·회귀표본이 있어야 하므로 브라우저에서는
                다시 계산할 수 없다. 입력값은 계수.json 으로 내보내 파이프라인에 넣는다.
   '참고'      판정에 들어가지 않는 값. 심의표의 참고 표시(지역 실거래가 환산)에만 쓴다.
                바꿔도 판정은 그대로다 — 그 사실을 화면에 적어 두어야, 돌리면 뭔가
                바뀔 것 같은 노브로 읽히지 않는다. */
const CFG = (() => {
  const KEY = 'cafe-trade-area/계수/v1';
  const MEASURED = 'MEASURED', ESTIMATED = 'ESTIMATED', DERIVED = 'DERIVED';
  const 콘솔 = '콘솔', 파이프라인 = '파이프라인', 참고 = '참고';

  // [값, 검증상태, 반영범위, 모듈, 설명, 최소, 최대, 증분]
  const SPEC = {
    보행속도_kmh:        [4.0,  DERIVED,   파이프라인, 'M1', '명세 고정값 — 등시선 기준 보행속도', 1, 8, 0.1],
    P10_이상반경_m:      [667.0, DERIVED,  파이프라인, 'M1', '4km/h × 10분. 잔존율 R 의 분모', 100, 2000, 1],
    경사_배제_퍼센트:    [10.0, ESTIMATED, 파이프라인, 'M1', '이 경사를 넘는 링크는 barrier 처리', 0, 30, 0.5],

    횡단저항:            [0.3,  ESTIMATED, 파이프라인, 'M2', '반대편 유동인구의 유효 반영률 — 실측 캘리브레이션 필요', 0, 1, 0.01],

    유동_안분_집중계수:  [1.0,  ESTIMATED, 파이프라인, 'M2', '행정동·상권 단위 유동인구를 P5 면적비로 안분할 때 곱하는 보정. 1.0 은 균등분포 가정이고, 실제 통행량은 간선도로변에 몰린다. M6 가 실측 카운트(실적.csv 의 실측_같은편_오전)를 확보하면 교정한다', 0.2, 5, 0.05],

    거리마찰_람다:       [2.2,  ESTIMATED, 파이프라인, 'M3', 'Huff 거리 마찰계수 — 실적으로 반드시 캘리브레이션', 0.5, 5, 0.1],
    흡인력_좌석지수:     [0.5,  ESTIMATED, 파이프라인, 'M3', 'A = 좌석수^0.5 × 브랜드가중', 0.1, 1.5, 0.05],
    보행우회계수:        [1.3,  ESTIMATED, 파이프라인, 'M3', '보행 네트워크 거리 미확보 시 직선거리에 곱하는 우회율', 1, 2, 0.05],

    ModeA_최소표본:      [15,   DERIVED,   파이프라인, 'M4', '유효 표본이 이 수 이상이면 회귀(Mode A)', 5, 60, 1],
    ModeA_GBM검토_표본:  [40,   DERIVED,   파이프라인, 'M4', '이 수 이상이면 Gradient Boosting 과 성능 비교', 10, 200, 1],
    예측구간_하한분위:   [0.25, DERIVED,   파이프라인, 'M4', '명세 고정', 0.01, 0.49, 0.01],
    예측구간_중앙분위:   [0.50, DERIVED,   파이프라인, 'M4', '심의 기준값', 0.1, 0.9, 0.01],
    예측구간_상한분위:   [0.75, DERIVED,   파이프라인, 'M4', '명세 고정', 0.51, 0.99, 0.01],
    ModeB_예측구간_폭:   [0.25, ESTIMATED, 파이프라인, 'M4', 'Mode B 는 잔차 표본이 없어 구간을 만들 수 없다. M6 가 실적 MAPE 를 확보하면 그 값으로 대체된다', 0.05, 0.6, 0.01],

    잠식계수_카파:       [0.5,  ESTIMATED, 콘솔, 'M5', '중첩 상권 내 자사 점포 간 수요 분할률', 0, 1, 0.05],
    부결_마진:           [0.15, DERIVED,   콘솔, 'M5', 'margin 이 이 값 미만이면 부결 (명세 고정)', 0, 0.6, 0.01],
    보류_마진:           [0.30, DERIVED,   콘솔, 'M5', 'margin 이 이 값 미만이면 보류 (명세 고정)', 0, 0.8, 0.01],
    보류_점수:           [70.0, DERIVED,   콘솔, 'M5', 'S 가 이 값 미만이면 보류 (명세 고정)', 0, 100, 1],
    보류_중첩:           [0.30, DERIVED,   콘솔, 'M5', 'overlap 이 이 값 초과면 보류 (명세 고정)', 0, 1, 0.01],

    상업용_연임대수익률: [0.045, ESTIMATED, 참고, '참고', '지역 매매 시세를 기대 임대료로 환산할 때 쓰는 연 수익률. 판정에는 쓰이지 않고 참고 표시에만 쓴다', 0.01, 0.15, 0.001],
    시세대조_최소건수:   [5,    ESTIMATED, 참고, '참고', '지역 실거래가 이 건수 미만이면 대조하지 않는다. 표본이 적으면 중앙값이 한두 건에 끌려다닌다. 판정 미사용', 1, 50, 1],

    재적합_MAPE:         [0.20, DERIVED,   파이프라인, 'M6', 'MAPE 가 이 값을 넘는 건이 3연속이면 재적합', 0.05, 0.6, 0.01],
    재적합_연속건수:     [3,    DERIVED,   파이프라인, 'M6', '명세 고정', 1, 10, 1],
  };

  // M3 브랜드 티어 가중 (교차탄력) — 실증 근거가 아닌 실무 판단값
  const TIER_SPEC = { 동일가격대: 1.0, 저가형: 0.6, 스페셜티: 0.4, 비커피: 0.3 };

  // M4 Mode B 배점 (수요 40 · 접근성 30 · 경쟁 20 · 비용계약 10)
  const MODEB_SPEC = {
    수요:     { 배후주거세대: 10, 직장인구: 10, 오전유동: 15, 주말야간유입: 5 },
    접근성:   { 출근동선방향: 10, 코너전면가시성: 8, '1층접근성': 7, 주차정차: 5 },
    경쟁:     { 동일티어밀도: 8, 저가브랜드밀집: 7, 유효상권잔존율: 5 },
    비용계약: { 임대료대비객수효율: 5, 계약조건: 5 },
  };

  // 운영 계수는 config.py 가 아니라 설정.yaml 에서 온다. 불러온 심의결과의 값이 기준이고,
  // 아래는 설정 파일조차 없을 때의 폴백이다.
  const OPS_FALLBACK = {
    변동비: { 원재료율: 0.35, 로열티율: 0.03, 광고분담금율: 0.01, 기타변동비율: 0.022 },
    고정비: { 고정인건비_월_만원: 620, 기타_월_만원: 170 },
  };
  const OPS_META = {
    원재료율:          ['원재료율', 0, 0.8, 0.005, 'v = 원재료율 + 로열티율 + 광고분담금율 + 기타'],
    로열티율:          ['로열티율', 0, 0.3, 0.005, '가맹 로열티'],
    광고분담금율:      ['광고분담금율', 0, 0.2, 0.005, '광고 분담금'],
    기타변동비율:      ['기타변동비율', 0, 0.3, 0.001, '카드수수료 등 — 명세 원식에 없는 별도 항목'],
    고정인건비_월_만원: ['고정인건비(월)', 0, 3000, 10, 'F = 임대료 + 관리비 + 고정인건비 + 기타'],
    기타_월_만원:      ['기타 고정비(월)', 0, 2000, 10, '수도광열·소모품 등'],
  };

  const store = (() => {
    try { return (typeof localStorage !== 'undefined') ? localStorage : null; }
    catch (e) { return null; }
  })();

  const blank = () => ({ 계수: {}, 브랜드티어가중: {}, ModeB배점: {}, 운영: {} });
  let ov = load();

  function load() {
    if (!store) return blank();
    try {
      const raw = store.getItem(KEY);
      return raw ? Object.assign(blank(), JSON.parse(raw)) : blank();
    } catch (e) { return blank(); }
  }

  function save() {
    if (!store) return;
    try { store.setItem(KEY, JSON.stringify(ov)); }
    catch (e) { /* 시크릿 모드 등 — 화면은 계속 쓴다 */ }
  }

  /* ── 계수 ─────────────────────────────── */
  const names = () => Object.keys(SPEC);
  const meta = n => {
    const s = SPEC[n];
    if (!s) throw new Error(`등록되지 않은 계수: ${n}`);
    return { 값: s[0], 상태: s[1], 반영: s[2], 모듈: s[3], 설명: s[4], 최소: s[5], 최대: s[6], 증분: s[7] };
  };
  const spec = n => meta(n).값;
  const c = n => (n in ov.계수) ? ov.계수[n] : spec(n);
  const changed = n => (n in ov.계수) && ov.계수[n] !== spec(n);

  function set(n, v) {
    const m = meta(n);
    const num = Number(v);
    if (!Number.isFinite(num)) return c(n);
    const clamped = Math.min(m.최대, Math.max(m.최소, num));
    if (clamped === m.값) delete ov.계수[n]; else ov.계수[n] = clamped;
    save();
    return c(n);
  }

  /* ── 브랜드 티어 가중 · Mode B 배점 ────── */
  const tier = k => (k in ov.브랜드티어가중) ? ov.브랜드티어가중[k] : TIER_SPEC[k];
  const tierKeys = () => Object.keys(TIER_SPEC);
  function setTier(k, v) {
    const num = Math.min(3, Math.max(0, Number(v)));
    if (!Number.isFinite(num)) return tier(k);
    if (num === TIER_SPEC[k]) delete ov.브랜드티어가중[k]; else ov.브랜드티어가중[k] = num;
    save();
    return tier(k);
  }

  const axes = () => Object.keys(MODEB_SPEC);
  const items = a => Object.keys(MODEB_SPEC[a]);
  const weight = (a, k) => ((ov.ModeB배점[a] || {})[k] ?? MODEB_SPEC[a][k]);
  function setWeight(a, k, v) {
    const num = Math.min(100, Math.max(0, Number(v)));
    if (!Number.isFinite(num)) return weight(a, k);
    if (num === MODEB_SPEC[a][k]) {
      if (ov.ModeB배점[a]) { delete ov.ModeB배점[a][k];
                             if (!Object.keys(ov.ModeB배점[a]).length) delete ov.ModeB배점[a]; }
    } else {
      (ov.ModeB배점[a] = ov.ModeB배점[a] || {})[k] = num;
    }
    save();
    return weight(a, k);
  }
  const axisTotal = a => items(a).reduce((s, k) => s + weight(a, k), 0);
  const weightTotal = () => axes().reduce((s, a) => s + axisTotal(a), 0);

  /* ── 운영 계수 ────────────────────────── */
  // base: 불러온 심의결과의 설정.운영. 없으면 폴백을 쓴다.
  function opsBase(base) {
    const b = base || {};
    return {
      변동비: { ...OPS_FALLBACK.변동비, ...(b.변동비 || {}) },
      고정비: { ...OPS_FALLBACK.고정비, ...(b.고정비 || {}) },
    };
  }
  function ops(base) {
    const b = opsBase(base);
    return {
      변동비: { ...b.변동비, ...(ov.운영.변동비 || {}) },
      고정비: { ...b.고정비, ...(ov.운영.고정비 || {}) },
    };
  }
  const opsMeta = k => {
    const m = OPS_META[k] || [k, 0, 1e9, 0.01, ''];
    return { 라벨: m[0], 최소: m[1], 최대: m[2], 증분: m[3], 설명: m[4] };
  };
  function setOps(group, k, v, base) {
    const m = opsMeta(k);
    const num = Number(v);
    if (!Number.isFinite(num)) return ops(base)[group][k];
    const clamped = Math.min(m.최대, Math.max(m.최소, num));
    const baseline = opsBase(base)[group][k];
    if (clamped === baseline) {
      if (ov.운영[group]) { delete ov.운영[group][k];
                            if (!Object.keys(ov.운영[group]).length) delete ov.운영[group]; }
    } else {
      (ov.운영[group] = ov.운영[group] || {})[k] = clamped;
    }
    save();
    return ops(base)[group][k];
  }
  const opsChanged = (group, k) => ((ov.운영[group] || {})[k] !== undefined);

  /* ── 변경 상태 ────────────────────────── */
  const 콘솔반영 = n => meta(n).반영 === 콘솔;
  const dirtyNames = () => names().filter(changed);
  // 화면의 판정을 바꾸는 변경이 있는가 (M5 계수 또는 운영 계수)
  const liveDirty = () => dirtyNames().some(콘솔반영) ||
    Object.keys(ov.운영).some(g => Object.keys(ov.운영[g] || {}).length > 0);
  // 파이프라인을 다시 돌려야 반영되는 변경이 있는가
  const pipelineDirty = () => dirtyNames().some(n => !콘솔반영(n)) ||
    tierKeys().some(k => tier(k) !== TIER_SPEC[k]) ||
    axes().some(a => items(a).some(k => weight(a, k) !== MODEB_SPEC[a][k]));
  const anyDirty = () => liveDirty() || pipelineDirty();

  // 입력으로 명세값을 벗어난 항목 수 — 탭 배지에 그대로 쓴다
  function dirtyCount() {
    let n = dirtyNames().length;
    n += tierKeys().filter(k => tier(k) !== TIER_SPEC[k]).length;
    axes().forEach(a => { n += items(a).filter(k => weight(a, k) !== MODEB_SPEC[a][k]).length; });
    ['변동비', '고정비'].forEach(g => { n += Object.keys(ov.운영[g] || {}).length; });
    return n;
  }

  function reset() { ov = blank(); save(); }

  /* ── 파이프라인으로 넘기기 ────────────── */
  function exportObject(base) {
    const out = { 생성: '심의 콘솔 계수 입력', 계수: {}, 브랜드티어가중: {}, ModeB배점: {}, 운영: {} };
    dirtyNames().forEach(n => { out.계수[n] = c(n); });
    tierKeys().forEach(k => { if (tier(k) !== TIER_SPEC[k]) out.브랜드티어가중[k] = tier(k); });
    axes().forEach(a => items(a).forEach(k => {
      if (weight(a, k) !== MODEB_SPEC[a][k]) (out.ModeB배점[a] = out.ModeB배점[a] || {})[k] = weight(a, k);
    }));
    const b = opsBase(base), o = ops(base);
    ['변동비', '고정비'].forEach(g => Object.keys(o[g]).forEach(k => {
      if (o[g][k] !== b[g][k]) (out.운영[g] = out.운영[g] || {})[k] = o[g][k];
    }));
    return out;
  }

  function importObject(obj, base) {
    if (!obj || typeof obj !== 'object') throw new Error('계수.json 형식이 아닙니다');
    reset();
    Object.entries(obj.계수 || {}).forEach(([n, v]) => { if (SPEC[n]) set(n, v); });
    Object.entries(obj.브랜드티어가중 || {}).forEach(([k, v]) => { if (k in TIER_SPEC) setTier(k, v); });
    Object.entries(obj.ModeB배점 || {}).forEach(([a, its]) =>
      Object.entries(its || {}).forEach(([k, v]) => {
        if (MODEB_SPEC[a] && k in MODEB_SPEC[a]) setWeight(a, k, v);
      }));
    ['변동비', '고정비'].forEach(g =>
      Object.entries((obj.운영 || {})[g] || {}).forEach(([k, v]) => setOps(g, k, v, base)));
    save();
  }

  return {
    MEASURED, ESTIMATED, DERIVED, 콘솔, 파이프라인,
    names, meta, spec, c, set, changed,
    tierKeys, tier, setTier, TIER_SPEC,
    axes, items, weight, setWeight, axisTotal, weightTotal, MODEB_SPEC,
    ops, opsBase, opsMeta, setOps, opsChanged, OPS_META,
    dirtyNames, dirtyCount, liveDirty, pipelineDirty, anyDirty, reset,
    exportObject, importObject,
    _SPEC: SPEC,
  };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = CFG;
