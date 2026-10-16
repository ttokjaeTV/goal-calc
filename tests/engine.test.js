// 목표금액 계산기 엔진 회귀 테스트
//
// 실행:  node tests/engine.test.js
//
// index.html 안의 계산 엔진(포맷 ~ 계산 엔진 구간)을 그대로 뽑아 실행하고,
// tests/reference.json 의 기준 답안과 비교한다.
// 기준 답안은 tests/reference.py 가 엔진과 다른 방법(월별 시뮬레이션 + 이분탐색)으로 만든 값이다.
// 계산 가정을 일부러 바꿨다면 reference.py 를 먼저 고치고 다시 실행해 reference.json 을 갱신한다.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(process.env.GOAL_CALC_HTML || path.join(ROOT, 'index.html'), 'utf8');
const ref = JSON.parse(fs.readFileSync(path.join(__dirname, 'reference.json'), 'utf8'));

// ---------- 엔진 뽑기 ----------
const START = '// ============== 포맷 ==============';
const END = "// ============== 적립액 증가율 비교 ('물가만큼만 늘리면?') ==============";
const s = html.indexOf(START), e = html.indexOf(END);
if (s < 0 || e < 0 || e < s) {
  console.error('index.html 에서 엔진 구간 표시(포맷 / 적립액 증가율 비교 주석)를 찾지 못했습니다. 주석을 바꿨다면 이 파일의 START·END도 바꿔 주세요.');
  process.exit(1);
}
const code = html.slice(s, e) + `
globalThis.__api = { setMode: m => { MODE = m; }, compute, buildPath, solvePmt, solveMonths, monthsUntilBelow,
  monthlyRate, effRate, targetAt, formatKRW, wonToManText, yearsMonthsText, MAX_MONTHS };`;
const ctx = { Math, Date, Number, String, isFinite, parseFloat, console };
vm.createContext(ctx);
vm.runInContext(code, ctx, { filename: 'index.html(엔진 구간)' });
const E = ctx.__api;

// ---------- 작은 테스트 도구 ----------
let pass = 0, fail = 0;
const fails = [];
function check(name, ok, detail) {
  if (ok) pass++;
  else { fail++; fails.push(`✗ ${name}${detail ? '\n    ' + detail : ''}`); }
}
const man = v => (v / 10000).toFixed(2) + '만';
function near(name, got, want, tol = 1) {   // 기본 허용 오차 1원
  const ok = typeof got === 'number' && isFinite(got) && Math.abs(got - want) <= tol;
  check(name, ok, `계산기 ${typeof got === 'number' ? man(got) : got} / 기준 ${man(want)} (차이 ${typeof got === 'number' ? (got - want).toFixed(4) : '-'}원)`);
}
function same(name, got, want) {
  check(name, got === want, `계산기 ${JSON.stringify(got)} / 기준 ${JSON.stringify(want)}`);
}

// ---------- 1. 모드별 핵심 결과 ----------
for (const [name, c] of Object.entries(ref.cases)) {
  E.setMode(c.mode);
  // 연 비용이 있는 경우는 화면과 똑같이 입력 수익률·비용 → effRate() 를 거쳐 계산에 쓸 수익률을 만든다
  const fee = c.inp.fee || 0, rateGross = fee ? c.inp.rate_gross : c.inp.rate;
  const inp = { ...c.inp, rateGross, fee, rate: E.effRate(rateGross, fee), inflationOn: c.inp.inflation > 0 };
  const r = E.compute(inp);
  const x = c.expect;
  const tag = `[${c.mode}] ${name}`;
  if (c.mode === 'time') {
    same(`${tag} · 달성 개월 수`, r.months, x.months);
    if (x.months) {
      near(`${tag} · 평가액`, r.final, x.final);
      near(`${tag} · 넣은 원금`, r.principal, x.principal);
      near(`${tag} · 그때의 목표`, r.target, x.target);
    }
    continue;
  }
  if ('pmt' in x) near(`${tag} · 월 적립액`, r.pmt, x.pmt);
  near(`${tag} · 목표`, r.target, x.target);
  near(`${tag} · 평가액`, r.final, x.final);
  near(`${tag} · 넣은 원금`, r.principal, x.principal);
  near(`${tag} · 오늘 돈 가치`, r.real, x.real);
  if (c.mode === 'pmt' && x.pmt > 0) near(`${tag} · 평가액 = 목표`, r.final, r.target);   // 필요한 만큼 넣으면 정확히 목표
  if (c.mode === 'pmt') check(`${tag} · 월 적립액이 음수가 아님`, r.pmt >= 0, `pmt=${r.pmt}`);
}

// ---------- 2. 목표 아래로 다시 떨어지는 시점 ----------
{
  const EOK = 1e8, MAN = 1e4;
  const B = ref.below;
  const mk = (cur, monthly, rate, inflation, basis) => ({ goal: 5 * EOK, current: cur, monthly, rate, inflation, basis, growth: 0 });
  same('재이탈 · 6억·1%·물가4%·적립 0', E.monthsUntilBelow(mk(6 * EOK, 0, 0.01, 0.04, 'today'), 0.01, 0), B['6억 보유·5억 목표·1%·물가4%·적립 0']);
  same('재이탈 · 6억·1%·물가4%·월 100만', E.monthsUntilBelow(mk(6 * EOK, 0, 0.01, 0.04, 'today'), 0.01, 100 * MAN), B['6억 보유·5억 목표·1%·물가4%·월 100만']);
  same('재이탈 · 6억·6%·물가2.5%(안 떨어짐)', E.monthsUntilBelow(mk(6 * EOK, 0, 0.06, 0.025, 'today'), 0.06, 0), B['6억 보유·5억 목표·6%·물가2.5%(안 떨어짐)']);
  same('재이탈 · 6억·명목 5억·-3%', E.monthsUntilBelow(mk(6 * EOK, 0, -0.03, 0.025, 'future'), -0.03, 0), B['6억 보유·명목 5억·-3%']);
}

// ---------- 3. 연차별 표 ----------
{
  E.setMode('pmt');
  const inp = { goal: 5e8, current: 3e7, rate: 0.06, growth: 0, inflation: 0.025, basis: 'today' };
  const rows = E.buildPath(inp, ref.path.pmt, 20);
  for (const [y, w] of Object.entries(ref.path.rows)) {
    const row = rows[Number(y)];
    near(`연차표 ${y}년차 · 평가액`, row.value, w.value);
    near(`연차표 ${y}년차 · 누적 원금`, row.principal, w.principal);
    near(`연차표 ${y}년차 · 오늘 돈 가치`, row.real, w.real);
    // '그해 목표 대비' = 평가액 ÷ 그해 목표 = 오늘 돈 가치 ÷ 처음 목표 (지금 돈 기준일 때)
    near(`연차표 ${y}년차 · 그해 목표 대비 = 실질 ÷ 목표`, row.value / row.target, row.real / 5e8, 1e-12);
  }
}

// ---------- 4. 연 비용(실효 수익률) ----------
near('실효 수익률 · 7% − 비용 0.5%', E.effRate(0.07, 0.005), 1.07 * 0.995 - 1, 1e-15);
same('실효 수익률 · 비용 0이면 입력값 그대로', E.effRate(0.06, 0), 0.06);
near('월 수익률 · 연 6%', E.monthlyRate(0.06), Math.pow(1.06, 1 / 12) - 1, 1e-15);
near('월 수익률 12번 굴리면 정확히 연 6%', Math.pow(1 + E.monthlyRate(0.06), 12) - 1, 0.06, 1e-12);

// ---------- 5. 화면 표기 ----------
same('표기 · 8.19억', E.formatKRW(819308220), '8.19억');
same('표기 · 9,999.5만 이상은 1.00억', E.formatKRW(99999000), '1.00억');
same('표기 · 9,999만', E.formatKRW(99990000), '9,999만');
same('표기 · 손실은 마이너스', E.formatKRW(-282000000), '-2.82억');
same('표기 · 월 159만원', E.wonToManText(1594690), '159만원');
same('표기 · 월 60.2만원', E.wonToManText(602000), '60.2만원');
same('표기 · 18년 10개월', E.yearsMonthsText(226), '18년 10개월');
same('표기 · 6년 3개월', E.yearsMonthsText(75), '6년 3개월');

// ---------- 결과 ----------
if (fails.length) console.log(fails.join('\n') + '\n');
console.log(`${fail ? '실패' : '통과'}: ${pass}개 통과 / ${fail}개 실패 (총 ${pass + fail}개)`);
process.exit(fail ? 1 : 0);
