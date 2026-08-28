/* 데모 데이터 생성기 — analysis 가 만든 심의결과.json 을 js/demo.js 로 굽는다.
   콘솔은 file:// 로도 열려야 해서 JSON 을 fetch 할 수 없다.
   파이프라인을 다시 돌렸다면:  node app/js/gen_demo.js
   (analysis/tests/test_demo_sync.py 가 어긋남을 잡아준다) */
const fs = require('fs');
const path = require('path');
const src = path.resolve(__dirname, '..', '..', 'analysis', 'output', '심의결과.json');
if (!fs.existsSync(src)) {
  console.error('심의결과.json 이 없습니다. 먼저: cd analysis && python3 review_sites.py');
  process.exit(1);
}
const data = JSON.parse(fs.readFileSync(src, 'utf-8'));
// 회귀 잔차는 화면에서 쓰지 않고 용량만 차지한다
if (data.모델 && data.모델.잔차) delete data.모델.잔차;
fs.writeFileSync(path.join(__dirname, 'demo.js'),
  `/* 데모 — analysis/output/심의결과.json 에서 생성됨. 직접 고치지 말고
   파이프라인을 다시 돌린 뒤 \`node app/js/gen_demo.js\` 로 구우세요. */
const DEMO = ${JSON.stringify(data, null, 1)};

if (typeof module !== 'undefined' && module.exports) module.exports = { DEMO };
`, 'utf-8');
console.log(`demo.js 생성 — 후보지 ${data.후보지.length} · 모드 ${data.모드}`);
