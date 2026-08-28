/* 상태 — 파이프라인이 만든 심의결과.json 을 담아 둔다.
   콘솔은 M1~M4 를 다시 계산하지 않는다(등시선·격자인구·회귀표본이 필요하다).
   여기 담긴 값은 review_sites.py 가 낸 그대로이고, 콘솔이 다시 계산하는 것은
   M5 판정 산술뿐이다. */
const S = (() => {
  const KEY = 'cafe-trade-area/심의결과/v2';
  let data = load();

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      console.warn('저장된 심의결과를 읽지 못했습니다.', e);
      return null;
    }
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(data));
    } catch (e) {
      U.toast('브라우저에 저장하지 못했습니다(용량·시크릿 모드). 화면은 계속 씁니다.');
    }
  }

  function set(next) {
    if (!next || !Array.isArray(next.후보지)) throw new Error('심의결과.json 형식이 아닙니다');
    data = next;
    save();
  }

  const get = () => data;
  const has = () => !!(data && data.후보지 && data.후보지.length);
  const settings = () => (data && data.설정) || {};
  const kappa = () => CFG.c('잠식계수_카파');   // 계수 탭에서 입력하면 그 값을 따른다

  const sites = () => (data && data.후보지) || [];
  const find = name => sites().find(r => r.이름 === name) || sites()[0] || null;

  function clear() {
    data = null;
    try { localStorage.removeItem(KEY); } catch (e) { /* 무시 */ }
  }

  /* 데이터 경고를 한곳에 모은다 — 어떤 입력이 비어 있는지가 심의에서 제일 중요하다. */
  function warnings() {
    const bag = new Map();
    sites().forEach(r => (r.경고 || []).forEach(w => {
      const cur = bag.get(w) || [];
      cur.push(r.이름);
      bag.set(w, cur);
    }));
    return [...bag.entries()].map(([w, who]) => ({ 경고: w, 대상: who }))
      .sort((a, b) => b.대상.length - a.대상.length);
  }

  return { get, set, has, sites, find, settings, kappa, clear, warnings,
           demo: () => set(structuredClone(DEMO)) };
})();
