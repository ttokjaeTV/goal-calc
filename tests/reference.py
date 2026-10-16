"""목표금액 계산기 기준 답안 산출기 (계산기 코드와 독립)

index.html 엔진은 닫힌 공식(연금 현가계수)으로 계산한다.
여기서는 일부러 다른 방법을 쓴다:
  - 평가액: 한 달씩 직접 굴리는 시뮬레이션
  - 필요 월 적립액: 이분탐색 (공식을 쓰지 않음)
  - 달성 기간: 한 달씩 굴려 처음 목표를 넘는 달
같은 가정을 서로 다른 계산법으로 풀어서 답이 같으면 엔진을 믿을 수 있다.

가정 (계산기 '계산 방법과 가정'과 동일)
  - 매달 말 적립, 월 수익률 = (1+연 수익률)^(1/12) - 1
  - 적립액은 해가 바뀔 때 증가율만큼 올림
  - 지금 돈 가치 기준이면 목표 = 목표 x (1+물가)^(개월/12)
  - 5년 늦게 시작: 지금 자산도 적립도 처음 skip개월은 굴리지 않음(수익 0%)
  - 연 비용: 실효 수익률 = (1+수익률)(1-비용) - 1

실행: python3 tests/reference.py  → tests/reference.json 갱신
"""
import json, os

def mrate(R):
    return (1 + R) ** (1 / 12) - 1

def simulate(pv, pmt, R, n, g=0.0, skip=0):
    """한 달씩 굴려 n개월 뒤 평가액과 넣은 원금을 돌려준다."""
    r = mrate(R)
    a, principal = pv, pv
    for m in range(1, n + 1):
        if m <= skip:
            continue  # 아직 시작 전: 굴리지도 넣지도 않음
        k = m - skip                      # 적립을 시작하고 몇 번째 달인지
        p = pmt * (1 + g) ** ((k - 1) // 12)
        a = a * (1 + r) + p
        principal += p
    return a, principal

def target(goal, infl, months, basis):
    return goal * (1 + infl) ** (months / 12) if basis == 'today' else goal

def solve_pmt(goal_amt, pv, R, n, g=0.0, skip=0):
    """이분탐색으로 n개월 뒤 평가액이 goal_amt가 되는 첫해 월 적립액."""
    if simulate(pv, 0, R, n, g, skip)[0] >= goal_amt:
        return 0.0
    lo, hi = 0.0, 1.0
    while simulate(pv, hi, R, n, g, skip)[0] < goal_amt:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if simulate(pv, mid, R, n, g, skip)[0] < goal_amt:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2

def solve_months(goal, pv, pmt, R, infl, basis, g=0.0, skip=0, cap=1200):
    r = mrate(R)
    a = pv
    if goal > 0 and a >= target(goal, infl, 0, basis):
        return 0
    for m in range(1, cap + 1):
        if m > skip:
            a = a * (1 + r) + pmt * (1 + g) ** ((m - skip - 1) // 12)
        if a >= target(goal, infl, m, basis):
            return m
    return None

def months_until_below(goal, pv, pmt, R, infl, basis, g=0.0, cap=1200):
    r = mrate(R)
    a = pv
    for m in range(1, cap + 1):
        a = a * (1 + r) + pmt * (1 + g) ** ((m - 1) // 12)
        if a < target(goal, infl, m, basis):
            return m
    return None

def year_row(pv, pmt, R, infl, year, g=0.0):
    v, p = simulate(pv, pmt, R, year * 12, g)
    return {'value': v, 'principal': p, 'real': v / (1 + infl) ** year}

MAN, EOK = 10_000, 100_000_000
cases = {}

def pmt_case(name, goal, cur, years, R, infl, basis='today', g=0.0, skip=0, fee=0.0):
    Re = (1 + R) * (1 - fee) - 1 if fee > 0 else R
    n = years * 12
    tgt = target(goal, infl, n, basis)
    pmt = solve_pmt(tgt, cur, Re, n, g, skip)
    final, principal = simulate(cur, pmt, Re, n, g, skip)
    cases[name] = {
        'mode': 'pmt',
        'inp': dict(goal=goal, current=cur, monthly=0, years=years, rate=Re, growth=g,
                    inflation=infl, basis=basis, skip=skip, rate_gross=R, fee=fee),
        'expect': dict(pmt=pmt, target=tgt, final=final, principal=principal,
                       real=final / (1 + infl) ** years),
    }

def fv_case(name, goal, cur, monthly, years, R, infl, basis='today', g=0.0, skip=0):
    n = years * 12
    final, principal = simulate(cur, monthly, R, n, g, skip)
    cases[name] = {
        'mode': 'fv',
        'inp': dict(goal=goal, current=cur, monthly=monthly, years=years, rate=R, growth=g,
                    inflation=infl, basis=basis, skip=skip),
        'expect': dict(final=final, principal=principal, target=target(goal, infl, n, basis),
                       real=final / (1 + infl) ** years),
    }

def time_case(name, goal, cur, monthly, R, infl, basis='today', g=0.0, skip=0):
    m = solve_months(goal, cur, monthly, R, infl, basis, g, skip)
    exp = {'months': m}
    if m:
        final, principal = simulate(cur, monthly, R, m, g, skip)
        exp.update(final=final, principal=principal, target=target(goal, infl, m, basis))
    cases[name] = {
        'mode': 'time',
        'inp': dict(goal=goal, current=cur, monthly=monthly, years=20, rate=R, growth=g,
                    inflation=infl, basis=basis, skip=skip),
        'expect': exp,
    }

# --- 필요한 월 적립액 (MODE 1) ---
pmt_case('기본: 5억·3천만·20년·6%·물가2.5%·지금 돈 기준', 5 * EOK, 3000 * MAN, 20, 0.06, 0.025)
pmt_case('미래 금액 기준(명목 5억)', 5 * EOK, 3000 * MAN, 20, 0.06, 0.025, basis='future')
pmt_case('적립액 매년 2.5% 증가', 5 * EOK, 3000 * MAN, 20, 0.06, 0.025, g=0.025)
pmt_case('5년 늦게 시작(모아둔 돈도 5년 묵힘)', 5 * EOK, 3000 * MAN, 20, 0.06, 0.025, skip=60)
pmt_case('5년 늦게 시작 + 미래 금액 기준', 5 * EOK, 3000 * MAN, 20, 0.06, 0.025, basis='future', skip=60)
pmt_case('수익률 0%', 5 * EOK, 3000 * MAN, 20, 0.0, 0.025)
pmt_case('수익률 -3%', 5 * EOK, 3000 * MAN, 20, -0.03, 0.025)
pmt_case('수익률 = 물가 = 증가율 2.5%', 5 * EOK, 3000 * MAN, 20, 0.025, 0.025, g=0.025)
pmt_case('수익률 1% < 물가 4%', 5 * EOK, 3000 * MAN, 20, 0.01, 0.04)
pmt_case('6억 보유·수익률 1%·물가 4%(지금은 목표 초과)', 5 * EOK, 6 * EOK, 20, 0.01, 0.04)
pmt_case('모아둔 돈만으로 충분(6억·6%)', 5 * EOK, 6 * EOK, 20, 0.06, 0.025)
pmt_case('기간 1년', 5 * EOK, 3000 * MAN, 1, 0.06, 0.025)
pmt_case('연 비용 0.5% 반영(7% → 실효)', 5 * EOK, 3000 * MAN, 20, 0.07, 0.025, fee=0.005)
pmt_case('물가 반영 끔', 5 * EOK, 3000 * MAN, 20, 0.06, 0.0, basis='future')

# --- 달성 기간 (MODE 2) ---
time_case('월 100만·명목 5억', 5 * EOK, 3000 * MAN, 100 * MAN, 0.06, 0.025, basis='future')
time_case('월 100만·지금 돈 5억', 5 * EOK, 3000 * MAN, 100 * MAN, 0.06, 0.025)
time_case('월 100만·5년 늦게 시작', 5 * EOK, 3000 * MAN, 100 * MAN, 0.06, 0.025, basis='future', skip=60)
time_case('수익률 0%·월 100만·5천만', 5000 * MAN, 0, 100 * MAN, 0.0, 0.0, basis='future')
time_case('100년 안에 못 닿음', 5 * EOK, 0, 10 * MAN, 0.02, 0.03)
time_case('이미 도달', 5000 * MAN, 1 * EOK, 100 * MAN, 0.06, 0.025)

# --- 만기 금액 (MODE 3) ---
fv_case('월 100만·20년', 5 * EOK, 3000 * MAN, 100 * MAN, 20, 0.06, 0.025)
fv_case('월 100만·20년·5년 늦게 시작', 5 * EOK, 3000 * MAN, 100 * MAN, 20, 0.06, 0.025, skip=60)
fv_case('월 100만·20년·매년 3% 증가', 5 * EOK, 3000 * MAN, 100 * MAN, 20, 0.06, 0.025, g=0.03)

# --- 목표 아래로 다시 떨어지는 시점 ---
below = {
    '6억 보유·5억 목표·1%·물가4%·적립 0': months_until_below(5 * EOK, 6 * EOK, 0, 0.01, 0.04, 'today'),
    '6억 보유·5억 목표·1%·물가4%·월 100만': months_until_below(5 * EOK, 6 * EOK, 100 * MAN, 0.01, 0.04, 'today'),
    '6억 보유·5억 목표·6%·물가2.5%(안 떨어짐)': months_until_below(5 * EOK, 6 * EOK, 0, 0.06, 0.025, 'today'),
    '6억 보유·명목 5억·-3%': months_until_below(5 * EOK, 6 * EOK, 0, -0.03, 0.025, 'future'),
}

# --- 연차별 표 (기본 조건, 월 적립액은 기본 케이스의 정답) ---
base_pmt = cases['기본: 5억·3천만·20년·6%·물가2.5%·지금 돈 기준']['expect']['pmt']
path = {str(y): year_row(3000 * MAN, base_pmt, 0.06, 0.025, y) for y in (1, 5, 10, 15, 20)}

out = {'cases': cases, 'below': below, 'path': {'pmt': base_pmt, 'rows': path}}
dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reference.json')
with open(dst, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

for k, v in cases.items():
    e = v['expect']
    key = 'pmt' if 'pmt' in e else ('months' if 'months' in e else 'final')
    val = e[key]
    print(f"{k:42s} {key}={val if val is None or key == 'months' else round(val / MAN, 2)}")
print('below', below)
print('saved', dst)
