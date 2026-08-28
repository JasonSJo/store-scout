/* 후보지 입력값 레지스트리 덤프 — app/js/inputs.js 의 필드 메타를 stdout 으로 낸다.
   tests/test_site_inputs.py 가 실제 파이프라인 코드와 대조한다. */
const path = require('path');
const INP = require(path.resolve(__dirname, '..', '..', 'app', 'js', 'inputs.js'));

const out = {};
INP.keys().forEach(k => {
  const m = INP.meta(k);
  out[k] = { 라벨: m.라벨, 종류: m.종류, 반영: m.반영, 모듈: m.모듈 };
});
process.stdout.write(JSON.stringify({ 필드: out, 치명: INP.FATAL }, null, 1));
