/* 상담 조건 → 고정비 → BEP.  analysis/consult.py 의 웹 대응물이다.
   두 곳의 산술이 갈리면 상담사가 고객 앞에서 본 숫자와 심의표의 숫자가 달라진다
   (analysis/tests/test_consult.py 가 대조한다). */
const CCALC = (() => {
  'use strict';

  /* 고정비 폴백. 진짜 값은 analysis/설정.yaml 에 있고 파이프라인은 그것을 쓴다.
     브라우저는 설정 파일을 읽을 수 없어 아래 값으로 미리보기만 한다. */
  const 기본고정비 = { 고정인건비_월_만원: 620, 기타_월_만원: 170 };
  const 기본변동비율 = 0.412;      // 설정.example.yaml 의 변동비 합
  const 영업일수 = 30;

  const num = v => {
    const n = parseFloat(String(v ?? '').replace(/[^0-9.\-]/g, ''));
    return Number.isFinite(n) ? n : 0;
  };

  /* 월이자 = (보증금 + 권리금) × 대출비율 × 연금리 ÷ 12
     차입 원금을 (보증금+권리금)으로 잡는 것은 시설자금·운전자금이 빠진 과소 추정이다. */
  function 금융비용(cond) {
    const 사양 = CFIELDS.투자금형태[String(cond.투자금형태 || '').trim()];
    if (!사양) return { 적용: false, 월_금융비용_만원: 0 };
    const 원금 = num(cond.보증금_만원) + num(cond.권리금_만원);
    const 차입 = 원금 * 사양.대출비율;
    const 이자 = 차입 * 사양.연금리 / 12;
    return { 적용: true, 차입_추정_만원: 차입, 월이자_만원: 이자,
             리스_월_만원: 사양.리스_월_만원,
             월_금융비용_만원: 이자 + 사양.리스_월_만원, 설명: 사양.설명 };
  }

  function 인건비(cond) {
    const 사양 = CFIELDS.운영형태[String(cond.운영형태 || '').trim()];
    if (!사양) return { 적용: false, 고정인건비_월_만원: 기본고정비.고정인건비_월_만원 };
    return { 적용: true, 고정인건비_월_만원: 사양.고정인건비_월_만원, 설명: 사양.설명 };
  }

  /* BEP = F ÷ (1 − 변동비율).  m5_verdict 와 같은 식이다.
     임대료는 상담 단계에서 모르므로 인자로 받는다(구간표를 그리는 데 쓴다). */
  function bep(cond, 임대료, 변동비율) {
    const v = 변동비율 === undefined ? 기본변동비율 : 변동비율;
    const 노무 = 인건비(cond), 금융 = 금융비용(cond);
    const rent = num(임대료);
    const 관리비 = rent * 0.12;
    const 기타 = 기본고정비.기타_월_만원 + 금융.월_금융비용_만원;
    const F = rent + 관리비 + 노무.고정인건비_월_만원 + 기타;
    return { 노무: 노무, 금융: 금융, 관리비: 관리비, 기타: 기타, F: F,
             변동비율: v, 월BEP: F / (1 - v), 일BEP: F / (1 - v) / 영업일수 };
  }

  function curve(cond, rents) {
    return (rents || [200, 300, 400, 600, 800]).map(r => {
      const b = bep(cond, r);
      return { 임대료: r, 월BEP: b.월BEP, 일BEP: b.일BEP };
    });
  }

  /* 운영 형태를 바꾸면 BEP 가 얼마나 움직이는지 — 상담에서 제일 설득력 있는 표다. */
  function 형태비교(cond, 임대료) {
    return Object.keys(CFIELDS.운영형태).map(형태 => {
      const b = bep(Object.assign({}, cond, { 운영형태: 형태 }), 임대료);
      return { 형태: 형태, 인건비: b.노무.고정인건비_월_만원, 월BEP: b.월BEP,
               설명: CFIELDS.운영형태[형태].설명 };
    });
  }

  const 투자합계 = cond => num(cond.보증금_만원) + num(cond.권리금_만원);

  return { bep, curve, 형태비교, 금융비용, 인건비, 투자합계,
           기본고정비, 기본변동비율, 영업일수, num };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = CCALC;
