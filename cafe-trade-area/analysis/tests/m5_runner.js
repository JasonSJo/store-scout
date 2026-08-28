/* M5 판정 산술 대조 러너 — stdin 으로 케이스 배열을 받아 판정 결과를 stdout 으로 낸다.
   사용: node m5_runner.js < cases.json */
const path = require('path');
const M5 = require(path.resolve(__dirname, '..', '..', 'app', 'js', 'm5.js'));

let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => { buf += d; });
process.stdin.on('end', () => {
  const cases = JSON.parse(buf);
  const out = cases.map(c => {
    const r = M5.judge(c.site, c.revenue, c.settings, c.S, c.overlaps, c.kappa, c.sPoolMax);
    return {
      판정: r.판정, 사유: r.사유, 비고: r.비고,
      치명플래그: r.치명플래그, 치명_미확인: r.치명_미확인,
      변동비율: r.변동비율, F: r.고정비.F, BEP_만원: r.BEP_만원,
      margin: r.margin, margin_low: r.margin_low,
      최대_overlap: r.카니발.최대_overlap, 잠식액_합_만원: r.카니발.잠식액_합_만원,
      순증_월매출_만원: r.순증_월매출_만원,
    };
  });
  process.stdout.write(JSON.stringify(out));
});
