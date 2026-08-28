/* 계수 레지스트리 덤프 — app/js/config.js 의 명세 기본값을 stdout 으로 낸다.
   tests/test_config_parity.py 가 config.py 와 대조한다. */
const path = require('path');
const CFG = require(path.resolve(__dirname, '..', '..', 'app', 'js', 'config.js'));

const 계수 = {};
CFG.names().forEach(n => {
  const m = CFG.meta(n);
  계수[n] = { 값: m.값, 상태: m.상태, 모듈: m.모듈, 설명: m.설명, 반영: m.반영 };
});

process.stdout.write(JSON.stringify({
  계수,
  브랜드티어가중: CFG.TIER_SPEC,
  ModeB배점: CFG.MODEB_SPEC,
}, null, 1));
