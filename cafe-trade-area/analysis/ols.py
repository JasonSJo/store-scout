#!/usr/bin/env python3
"""
최소자승 회귀 — numpy 없이

M4 Mode A 가 쓰는 로그선형 OLS 다. numpy 를 쓰지 않는 이유는 두 가지다.

  1. 저장소 의존성을 PyYAML 하나로 유지한다.
  2. **같은 알고리즘이 웹앱(app/js/ols.js)에도 있어야 한다.** 정규방정식 +
     부분피벗 가우스 소거는 양쪽에서 연산 순서까지 똑같이 옮길 수 있다.
     라이브러리에 맡기면 그 순간 두 구현이 갈린다.

표본이 작을 때(n < 40) 정규방정식의 조건수 악화는 실무상 문제되지 않는 규모지만,
피벗이 0 에 가까우면 특이행렬로 보고 명시적으로 실패한다 — 조용히 이상한 계수를
내놓는 것보다 낫다.
"""
from __future__ import annotations

import math


class SingularMatrix(Exception):
    """설계행렬이 특이(공선성·표본부족). 계수를 만들 수 없다."""


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """A x = b 를 부분피벗 가우스 소거로 푼다. A 는 정방·대칭(XᵀX)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise SingularMatrix(f"{col}번째 열이 특이 — 설명변수 공선성 또는 표본 부족")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / pv
            if f == 0.0:
                continue
            for cc in range(col, n + 1):
                m[r][cc] -= f * m[col][cc]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit(X: list[list[float]], y: list[float]) -> list[float]:
    """절편은 호출자가 X 의 첫 열에 1 로 넣어 둔다."""
    n, p = len(X), len(X[0])
    if n < p:
        raise SingularMatrix(f"표본 {n}개 < 설명변수 {p}개")
    xtx = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(p)] for i in range(p)]
    xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(p)]
    return solve(xtx, xty)


def predict(beta: list[float], x: list[float]) -> float:
    return sum(b * v for b, v in zip(beta, x))


def r_squared(X, y, beta) -> float:
    yb = sum(y) / len(y)
    ss_res = sum((y[i] - predict(beta, X[i])) ** 2 for i in range(len(y)))
    ss_tot = sum((v - yb) ** 2 for v in y)
    return 1 - ss_res / ss_tot if ss_tot else 0.0


def quantile(sorted_vals: list[float], q: float) -> float:
    """선형보간 분위수(numpy 기본 'linear' 과 동일 규칙). 양쪽 구현을 맞추려 명시한다."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[int(pos)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def cross_validate(X: list[list[float]], y: list[float], folds: int = 0) -> dict:
    """folds=0 이면 LOOCV. 명세대로 표본이 작으면 LOOCV, 충분하면 5-fold 를 쓴다.

    반환하는 잔차는 **로그 공간**의 out-of-fold 잔차다. 예측구간은 이 잔차의
    분위수로 만든다 — 정규성 가정 없이 실제 빗나간 만큼만 벌린다.
    """
    n = len(y)
    k = n if folds <= 0 else min(folds, n)
    resid, ape = [], []
    for f in range(k):
        test = [i for i in range(n) if i % k == f] if folds > 0 else [f]
        train = [i for i in range(n) if i not in set(test)]
        if len(train) < len(X[0]):
            continue
        try:
            beta = fit([X[i] for i in train], [y[i] for i in train])
        except SingularMatrix:
            continue
        for i in test:
            pred = predict(beta, X[i])
            resid.append(y[i] - pred)
            # y 가 log(일매출) 이므로 원 단위 오차율로 되돌려 MAPE 를 잰다
            actual, guess = math.exp(y[i]), math.exp(pred)
            if actual > 0:
                ape.append(abs(actual - guess) / actual)
    return {
        "방식": "LOOCV" if folds <= 0 else f"{k}-fold",
        "폴드수": k,
        "잔차": sorted(resid),
        "MAPE": sum(ape) / len(ape) if ape else None,
        "표본수": n,
    }
