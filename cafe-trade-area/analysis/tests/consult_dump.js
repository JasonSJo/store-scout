/* 상담 페이지 덤프 — test_consult.py 가 설정.yaml · consult.py 와 대조한다. */
const path = require('path');
const C = path.resolve(__dirname, '..', '..', 'consult', 'js');
global.CFIELDS = require(path.join(C, 'fields.js'));
const CCALC = require(path.join(C, 'calc.js'));

const 표본 = [];
[['현금', 0, 0], ['현금+대출', 8000, 3000], ['현금+대출+리스', 12000, 5000]].forEach(([형태, 보, 권]) => {
  ['오토', '점주+알바', '점주'].forEach(운영 => {
    const cond = { 투자금형태: 형태, 운영형태: 운영, 보증금_만원: 보, 권리금_만원: 권 };
    const b = CCALC.bep(cond, 300);
    표본.push({ 투자금형태: 형태, 운영형태: 운영, 보증금_만원: 보, 권리금_만원: 권,
                월_금융비용_만원: b.금융.월_금융비용_만원,
                고정인건비_월_만원: b.노무.고정인건비_월_만원,
                임대료: 300, F: b.F, 월BEP: b.월BEP });
  });
});

process.stdout.write(JSON.stringify({
  운영형태: global.CFIELDS.운영형태,
  투자금형태: global.CFIELDS.투자금형태,
  상권유형: global.CFIELDS.상권유형,
  개인정보키: global.CFIELDS.개인정보키(),
  알고리즘키: global.CFIELDS.알고리즘키(),
  필터키: global.CFIELDS.keys().filter(k => global.CFIELDS.meta(k).목적지 === '필터'),
  기본고정비: CCALC.기본고정비, 기본변동비율: CCALC.기본변동비율, 영업일수: CCALC.영업일수,
  표본: 표본,
}));
