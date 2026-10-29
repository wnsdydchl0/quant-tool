"""민감도 분석. ORE 대응: OREAnalytics/orea/engine/sensitivityanalysis.cpp (generateSensitivities).

ORE와 같은 순서:
  a) 초기 시장으로 시뮬레이션 시장(ScenarioSimMarket)을 만든다
  b) 민감도 시나리오 생성기를 만들고 시뮬레이션 시장에 건다
  c) 같은 포트폴리오를 시뮬레이션 시장에 다시 연결해 조립한다
  d) ValuationEngine으로 시나리오마다 평가해 NPV 표를 만든다
  e) (흔든 NPV − 기준 NPV) / shift → 민감도
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quanttool.analytics.scenario import ScenarioSimMarket, SensitivityScenarioGenerator
from quanttool.data.configuration import (
    Config,
    ScenarioSimMarketParameters,
    SensitivityScenarioData,
)
from quanttool.data.marketdata import Market
from quanttool.data.portfolio import EngineFactory, Portfolio

from .valuationengine import NPVCube, ValuationEngine


@dataclass
class SensitivityCube:
    """민감도 시나리오의 NPV 표와 이동 크기. ORE SensitivityCube 대응. 값은 1bp당 손익."""

    cube: NPVCube
    data: SensitivityScenarioData

    def key_rate_dv01(self, curve: str) -> pd.DataFrame:
        """행: 격자 만기, 열: 거래 + total. 해당 격자점 1bp 상승 시 손익."""
        pnl = self.cube.pnl
        mask = [isinstance(lb, tuple) and lb[:2] == ("key_rate", curve) for lb in pnl.index]
        table = pnl[mask] / self.data.key_rate_bp
        table.index = pd.Index([lb[2] for lb in table.index], name="tenor")
        table["total"] = table.sum(axis=1)
        return table

    def parallel_dv01(self, curve: str) -> pd.Series:
        """커브 전체 1bp 평행 상승 시 거래별 손익 (+ total)."""
        pnl = self.cube.pnl.loc[[("parallel", curve)]].iloc[0] / self.data.parallel_bp
        pnl["total"] = pnl.sum()
        return pnl.rename("parallel_dv01")


class SensitivityAnalysis:
    def __init__(
        self,
        portfolio: Portfolio,
        market: Market,
        cfg: Config,
        sim_params: ScenarioSimMarketParameters | None = None,
        sensi_data: SensitivityScenarioData | None = None,
    ) -> None:
        self.portfolio = portfolio
        self.market = market
        self.cfg = cfg
        self.sim_params = sim_params or cfg.simmarket
        self.sensi_data = sensi_data or cfg.sensitivity
        self.sim_market: ScenarioSimMarket | None = None
        self._cube: SensitivityCube | None = None

    def generate_sensitivities(self) -> None:
        sim = ScenarioSimMarket(self.market, self.sim_params)  # a
        sim.scenario_generator = SensitivityScenarioGenerator(self.sim_params, self.sensi_data)  # b
        with sim.active():
            self.portfolio.build(EngineFactory.from_config(self.cfg, sim))  # c
        cube = ValuationEngine(self.market.asof, [self.market.asof], sim).build_cube(self.portfolio)
        self.sim_market = sim
        self._cube = SensitivityCube(cube, self.sensi_data)  # e

    def sensi_cube(self) -> SensitivityCube:
        if self._cube is None:
            raise RuntimeError("generate_sensitivities()를 먼저 불러야 한다")
        return self._cube
