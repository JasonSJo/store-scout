/* 데이터 입력 폼의 항목 정의를 stdout 으로 낸다.
   tests/test_input_form.py 가 후보지 CSV 헤더·파이프라인 소스와 대조한다. */
const path = require('path');
const F = require(path.resolve(__dirname, '..', '..', 'input', 'js', 'fields.js'));

const 항목 = {};
F.keys().forEach(k => {
  const m = F.meta(k);
  항목[k] = { 라벨: m.라벨, 종류: m.종류, 모듈: m.모듈, 필수: !!m.필수 };
});
process.stdout.write(JSON.stringify({
  항목, 열: F.COLUMNS, 치명: F.FATAL,
  그룹: F.GROUPS.map(g => ({ 이름: g.이름, 항목: g.항목.map(a => a[0]) })),
}, null, 1));
