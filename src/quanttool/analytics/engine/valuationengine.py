"""시나리오 × 날짜 반복 평가. ORE 대응: OREAnalytics/orea/engine/valuationengine.hpp (buildCube).

포트폴리오는 시뮬레이션 시장에 한 번 조립된 상태로 받고, 표본(시나리오)마다·날짜마다
sim_market.update(d) → NPV를 기록한다. 끝나면 시장을 reset한다 (docs/architecture.md 1.6 불변 조건).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from quanttool.analytics.scenario import SimMarket
from quanttool.data.portfolio import Portfolio


@dataclass
class NPVCube:
    """기준 NPV와 (시나리오[, 날짜]) × 거래 NPV 표. ORE NPVCube 대응 (pandas)."""

    base: pd.Series  # 거래별 기준 NPV (시뮬레이션 시장 기준 상태, asof)
    npv: pd.DataFrame  # 행: 시나리오 label (날짜가 여럿이면 (label, 날짜)), 열: 거래 id

    @property
    def pnl(self) -> pd.DataFrame:
        return self.npv - self.base

    def total_pnl(self) -> pd.Series:
        return self.pnl.sum(axis=1)


class ValuationEngine:
    def __init__(self, asof: date, dates: Sequence[date], sim_market: SimMarket) -> None:
        self.asof = asof
        self.dates = list(dates)
        self.sim_market = sim_market

    def build_cube(self, portfolio: Portfolio) -> NPVCube:
        sim = self.sim_market
        gen = sim.scenario_generator
        if gen is None:
            raise ValueError("ValuationEngine: sim_market.scenario_generator가 없다")
        gen.reset()
        samples = gen.samples()

        labels, rows = [], []
        try:
            sim.reset()
            with sim.active():
                base = portfolio.npvs()
            for _ in range(samples):
                for d in self.dates:
                    sim.update(d)  # 평가일 = d, 다음 시나리오 적용
                    with sim.active():
                        rows.append(portfolio.npvs())
                    label = sim.scenario.label
                    labels.append(label if len(self.dates) == 1 else (label, d))
        finally:
            gen.reset()
            sim.reset()
        # label은 길이가 다른 튜플일 수 있어 MultiIndex로 풀지 않는다
        index = pd.Index(labels, tupleize_cols=False, name="scenario", dtype=object)
        return NPVCube(base, pd.DataFrame(rows, index=index, columns=base.index))
