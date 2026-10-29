"""시나리오 실행. ORE 대응: OREAnalytics/orea/engine/valuationengine.hpp.

포트폴리오는 한 번 조립하고, 시나리오마다 apply → npv → reset 한다
(docs/architecture.md 1.7 불변 조건).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from quanttool.analytics.scenario import Scenario, ScenarioSimMarket
from quanttool.data.configuration import Config
from quanttool.data.portfolio import EngineFactory, Portfolio


@dataclass
class NPVCube:
    base: pd.Series  # 거래별 기준 NPV (격자 시장)
    npv: pd.DataFrame  # 행: 시나리오 label, 열: 거래 id
    reconciliation: pd.DataFrame | None = None

    @property
    def pnl(self) -> pd.DataFrame:
        return self.npv - self.base

    def total_pnl(self) -> pd.Series:
        return self.pnl.sum(axis=1)


class ValuationEngine:
    def __init__(self, portfolio: Portfolio, smkt: ScenarioSimMarket, cfg: Config) -> None:
        self.portfolio = portfolio
        self.smkt = smkt
        self.cfg = cfg

    def run(self, scenarios: Iterable[Scenario], reconcile: bool = True) -> NPVCube:
        recon = None
        if reconcile:
            recon = self.smkt.base_reconciliation(self.portfolio, self.cfg)  # 격자 시장으로 조립됨
        else:
            with self.smkt.active():
                self.portfolio.build(EngineFactory(self.smkt, self.cfg))

        labels, rows = [], []
        with self.smkt.active():
            self.smkt.reset()
            base = self.portfolio.npvs()
            try:
                for s in scenarios:
                    self.smkt.apply_scenario(s)
                    labels.append(s.label)
                    rows.append(self.portfolio.npvs())
            finally:
                self.smkt.reset()
        # label은 길이가 다른 튜플일 수 있어 MultiIndex로 풀지 않는다
        index = pd.Index(labels, tupleize_cols=False, name="scenario", dtype=object)
        npv = pd.DataFrame(rows, index=index, columns=base.index)
        return NPVCube(base, npv, recon)
