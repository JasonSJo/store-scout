/* 간편 입력 자리표시자 덤프 — test_quick_input.py 가 quick_site.py 와 대조한다. */
const path = require('path');
const Q = require(path.resolve(__dirname, '..', '..', 'input', 'js', 'quick.js'));

const 가정 = {};
Object.keys(Q.ASSUMED).forEach(k => { 가정[k] = { 값: String(Q.ASSUMED[k][0]), 근거: Q.ASSUMED[k][1] }; });

// 산술 대조용 표본 — 파이썬과 같은 입력으로 같은 BEP 가 나와야 한다
const 표본 = [];
[[55, 262], [30, 400], [70, 0], [45, 1200], [0.62, 180]].forEach(([m, r]) => {
  const b = Q.bep(m, r);
  표본.push({ 마진율: m, 임대료: r, 공헌이익률: b.공헌이익률, F: b.F, 월BEP: b.월BEP, 일BEP: b.일BEP });
});

process.stdout.write(JSON.stringify({
  가정: 가정, 치명: Q.FATAL_UNTOUCHED, 관리비율: Q.관리비율,
  고정비폴백: Q.고정비폴백, 영업일수: Q.영업일수, 표본: 표본,
}));
