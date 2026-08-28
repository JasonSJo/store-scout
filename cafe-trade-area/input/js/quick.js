/* 간편 입력 — 주소와 마진율만 받고 나머지를 채운다.
   analysis/quick_site.py 의 웹 대응물이며, 자리표시자 표는 두 곳이 같아야 한다
   (analysis/tests/test_quick_input.py 가 대조한다).

   여기서 채우는 값은 **근거가 없다.** 그래서 두 가지를 지킨다.
     1. 모르는 조건은 불리한 쪽으로 잡는다 — 유리하게 가정하면 통과가 쉬워지고
        그 통과는 실사에서 뒤집힌다.
     2. 치명 플래그는 절대 채우지 않는다 — 'N' 은 '실사해서 문제없었다' 는 뜻이고,
        실사하지 않은 것을 그렇게 적으면 그건 거짓말이다. */
const QUICK = (() => {
  'use strict';

  /* 받아올 수 없는 칸의 자리표시자. quick_site.py 의 ASSUMED 와 같아야 한다. */
  const ASSUMED = {
    전용면적_평:   [20,  '지역 평균대 소형 상가. 시세 대조의 건물가치 환산에 쓰인다'],
    좌석수:        [24,  '설정의 좌석수_기본과 같은 값. M3 흡인력 A'],
    층:            [1,   '1층 가정 — 2층 이상이면 Mode B 1층접근성 배점이 달라진다'],
    코너여부:      ['N', '모르면 코너가 아니다 (유리한 쪽으로 가정하지 않는다)'],
    전면폭_m:      [6.0, '소형 상가 전면 통상값'],
    주차가능대수:  [0,   '모르면 없다'],
    정차가능:      ['N', '모르면 불가'],
    도로변:        ['A', '같은편 가정 — 반대편이면 횡단저항으로 D_am 이 깎인다'],
    방향적합:      ['N', '출근 동선 방향은 현장에서만 확인된다'],
    계약조건점수:  [3,   '5점 만점의 중간'],
  };

  /* 고정비 폴백. 진짜 값은 analysis/설정.yaml 에 있고 파이프라인이 그것을 쓴다.
     브라우저는 설정 파일을 읽을 수 없어 아래 값으로 BEP 를 미리 보여줄 뿐이다. */
  const 고정비폴백 = { 고정인건비_월_만원: 620, 기타_월_만원: 170 };
  const 관리비율 = 0.12;      // 임대료 대비 통상 관리비
  const 영업일수 = 30;

  const num = v => {
    const n = parseFloat(String(v ?? '').replace(/[^0-9.\-]/g, ''));
    return Number.isFinite(n) ? n : 0;
  };

  /* 마진율은 0~1 로도 0~100 으로도 들어온다. 55 를 5500% 로 읽으면 BEP 가 0 이 된다. */
  function margin(v) {
    const n = num(v);
    if (!n) return null;
    const m = n > 1 ? n / 100 : n;
    return (m > 0 && m < 1) ? m : null;
  }

  /* BEP = F ÷ 공헌이익률.  m5_verdict 의 F/(1-v) 와 같은 식이다(공헌이익률 = 1-v). */
  function bep(마진율, 임대료, 관리비) {
    const m = margin(마진율);
    if (!m) return null;
    const rent = num(임대료);
    const mgmt = 관리비 === undefined || 관리비 === '' ? rent * 관리비율 : num(관리비);
    const F = rent + mgmt + 고정비폴백.고정인건비_월_만원 + 고정비폴백.기타_월_만원;
    return { 공헌이익률: m, 변동비율: 1 - m, 관리비, F: F, 월BEP: F / m,
             일BEP: F / m / 영업일수, 추정관리비: mgmt };
  }

  /* 임대료를 아직 모를 때 — 임대료 구간별로 BEP 가 어떻게 움직이는지 보여준다.
     '주소와 마진율만' 으로 답할 수 있는 것이 정확히 여기까지다. */
  function bepCurve(마진율, rents) {
    const m = margin(마진율);
    if (!m) return [];
    return (rents || [100, 200, 300, 400, 600, 800]).map(r => {
      const b = bep(마진율, r);
      return { 임대료: r, 월BEP: b.월BEP, 일BEP: b.일BEP };
    });
  }

  /* 자리표시자를 채운다. 이미 사람이 넣은 값은 건드리지 않는다. */
  function fill(site, opts) {
    const o = opts || {};
    const out = Object.assign({}, site);
    const 채움 = [];
    Object.keys(ASSUMED).forEach(k => {
      if (String(out[k] ?? '').trim() !== '') return;      // 사람이 넣은 값이 우선
      out[k] = String(ASSUMED[k][0]);
      채움.push(k);
    });
    if (o.월임대료_만원 !== undefined && String(o.월임대료_만원).trim() !== '') {
      out.월임대료_만원 = String(num(o.월임대료_만원));
      if (String(out.관리비_만원 ?? '').trim() === '') {
        out.관리비_만원 = String(Math.round(num(o.월임대료_만원) * 관리비율));
        채움.push('관리비_만원');
      }
    }
    // 치명 플래그는 여기서도 저기서도 채우지 않는다
    FATAL_UNTOUCHED.forEach(k => { if (out[k] === undefined) out[k] = ''; });
    out.비고 = String(out.비고 ?? '').trim() || '간편 입력 — 가정값 포함';
    return { site: out, 채움: 채움 };
  }

  const FATAL_UNTOUCHED = ['근저당_과다', '임대인_불일치', '소송_계류', '인허가_불가'];

  const 목록 = () => Object.keys(ASSUMED).map(k =>
    ({ 키: k, 값: ASSUMED[k][0], 근거: ASSUMED[k][1] }));

  return { ASSUMED, 목록, fill, bep, bepCurve, margin, 고정비폴백, 관리비율, 영업일수,
           FATAL_UNTOUCHED };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = QUICK;
