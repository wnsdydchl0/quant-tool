"""민감도와 시나리오 손익. 모두 "시나리오 적용 → NPV → 되돌리기"의 반복이다.

- key_rate: 이동 만기마다 delta·gamma (만기 × 거래 표).
  값은 보고 단위(risk.shift_size, 1bp) 이동당 손익.
- 상품별 규칙: risk.overrides[거래 id 또는 상품 종류] = {shift_size, scheme}.
  예를 들어 수치 엔진 상품은 10bp 중심 차분으로 계산하고 1bp 기준으로 다시 환산한다.
- cross_gamma: 요인 쌍을 함께 이동.
- scenario_pnl: 시나리오 여러 개의 거래별 손익. theta: 시장 그대로, 날짜만 이동.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from .config import RiskConfig
from .market import Market
from .portfolio import Portfolio
from .scenarios import bucket


def rule(trade, risk: RiskConfig) -> tuple[float, str]:
    """거래의 (이동 크기, 방식): 거래 id → 상품 종류 → 기본값 순으로 찾는다."""
    o = risk.overrides.get(trade.id) or risk.overrides.get(trade.type)
    return (o.shift_size, o.scheme) if o else (risk.shift_size, risk.scheme)


def key_rate(
    portfolio: Portfolio, market: Market, risk: RiskConfig, curve: str
) -> dict[str, pd.DataFrame]:
    """{"delta": 만기 × 거래, "gamma": 만기 × 거래}. 각 표에 total 열."""
    tenors = risk.shift_tenors.get(curve) or market.objects[curve].tenors
    base = portfolio.npvs()
    groups: dict[tuple[float, str], list[str]] = {}
    for i, t in portfolio.trades.items():
        groups.setdefault(rule(t, risk), []).append(i)

    delta = pd.DataFrame(0.0, index=pd.Index(tenors, name="tenor"), columns=portfolio.ids())
    gamma = delta.copy()
    for (size, scheme), ids in groups.items():
        scale = risk.shift_size / size  # 보고 단위로 환산
        need_down = scheme == "Central" or risk.compute_gamma
        for j, tenor in enumerate(tenors):
            with market.scenario(bucket(market, curve, tenors, j, size)):
                up = portfolio.npvs()[ids]
            down = None
            if need_down:
                with market.scenario(bucket(market, curve, tenors, j, -size)):
                    down = portfolio.npvs()[ids]
            b = base[ids]
            delta.loc[tenor, ids] = ((up - down) / 2 if scheme == "Central" else up - b) * scale
            if risk.compute_gamma:
                gamma.loc[tenor, ids] = (up - 2 * b + down) * scale**2
    for table in (delta, gamma):
        table["total"] = table.sum(axis=1)
    return {"delta": delta, "gamma": gamma}


def cross_gamma(portfolio: Portfolio, market: Market, risk: RiskConfig) -> pd.DataFrame:
    """risk.cross_gamma 쌍마다 up12 − up1 − up2 + base (보고 단위 이동)."""
    s = risk.shift_size
    base = portfolio.npvs()
    rows = {}
    for k1, k2 in risk.cross_gamma:
        with market.scenario({k1: s}):
            up1 = portfolio.npvs()
        with market.scenario({k2: s}):
            up2 = portfolio.npvs()
        with market.scenario({k1: s, k2: s}):
            up12 = portfolio.npvs()
        rows[(k1, k2)] = up12 - up1 - up2 + base
    return pd.DataFrame(rows).T.rename_axis(["factor_1", "factor_2"])


def scenario_pnl(
    portfolio: Portfolio, market: Market, scenarios: Mapping[str, Mapping[str, float]]
) -> pd.DataFrame:
    """행: 시나리오 이름, 열: 거래 (+ total). 기준 NPV 대비 손익."""
    base = portfolio.npvs()
    rows = {}
    for name, s in scenarios.items():
        with market.scenario(s):
            rows[name] = portfolio.npvs() - base
    out = pd.DataFrame(rows).T
    out["total"] = out.sum(axis=1)
    return out


def theta(portfolio: Portfolio, market: Market, d: date) -> pd.Series:
    """시장 그대로 평가일만 d로 (ForwardForward). 끝나면 원래 날짜로 되돌린다."""
    base = portfolio.npvs()
    start = market.date
    market.roll(d)
    try:
        return (portfolio.npvs() - base).rename("theta")
    finally:
        market.roll(start)
