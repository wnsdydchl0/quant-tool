"""민감도 분석. ORE 대응: OREAnalytics/orea/engine/sensitivityanalysis.cpp (generateSensitivities).

ORE와 같은 순서:
  0) 포트폴리오가 아직 조립 전이면 초기 시장에 한 번 조립해 거래별 민감도 템플릿을 읽는다
  a) 초기 시장으로 시뮬레이션 시장(ScenarioSimMarket)을 만든다
  b) 템플릿마다 민감도 시나리오 생성기를 만든다 (기본 템플릿 "" 포함)
  c) 포트폴리오를 템플릿별로 나누고, 묶음마다 생성기를 시뮬레이션 시장에 건다
  d) 그 묶음을 시뮬레이션 시장에 다시 연결해 조립한다 (EngineFactory의 시장만 바뀐다)
  e) ValuationEngine + NPVCalculator로 시나리오마다 평가해 큐브를 채운다
  f) 큐브 → SensitivityCube (delta, gamma, cross gamma)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from quanttool.analytics.cube import NPVCube, SensitivityCube
from quanttool.analytics.scenario import ScenarioSimMarket, SensitivityScenarioGenerator
from quanttool.data.configuration import (
    DEFAULT_CONFIGURATION,
    EngineData,
    ScenarioSimMarketParameters,
    SensitivityScenarioData,
)
from quanttool.data.marketdata import Market
from quanttool.data.portfolio import EngineFactory, MarketContext, Portfolio
from quanttool.data.utilities.dategrid import DateGrid

from .valuationcalculator import NPVCalculator
from .valuationengine import ValuationEngine

if TYPE_CHECKING:
    from quanttool.data.configuration import Config


class SensitivityAnalysis:
    def __init__(
        self,
        portfolio: Portfolio,
        market: Market,
        market_configuration: str,
        engine_data: EngineData,
        sim_market_data: ScenarioSimMarketParameters,
        sensitivity_data: SensitivityScenarioData,
        recalibrate_models: bool = False,
    ) -> None:
        self.portfolio = portfolio
        self.market = market
        self.market_configuration = market_configuration
        self.engine_data = engine_data
        self.sim_market_data = sim_market_data
        self.sensitivity_data = sensitivity_data
        self.recalibrate_models = recalibrate_models
        self.sim_market: ScenarioSimMarket | None = None
        self.scenario_generator: SensitivityScenarioGenerator | None = None
        self._sensi_cubes: list[SensitivityCube] = []

    @classmethod
    def from_config(
        cls,
        portfolio: Portfolio,
        market: Market,
        cfg: Config,
        market_configuration: str = DEFAULT_CONFIGURATION,
    ) -> SensitivityAnalysis:
        if cfg.simmarket is None:
            raise ValueError("configs/scenario/simmarket.yaml이 없다")
        return cls(
            portfolio, market, market_configuration, cfg.engine_data, cfg.simmarket, cfg.sensitivity
        )

    def generate_sensitivities(self) -> None:
        asof = self.market.asof
        configurations = {MarketContext.pricing: self.market_configuration}
        # 0) 템플릿 id (기본 "" + 설정과 포트폴리오 양쪽에 있는 것)
        if not self.portfolio.is_built():
            with self.market.active():
                self.portfolio.build(EngineFactory(self.engine_data, self.market, configurations))
        in_portfolio = {t.sensitivity_template() for t in self.portfolio}
        templates = [""] + sorted((self.sensitivity_data.templates() & in_portfolio) - {""})

        # a) 시뮬레이션 시장
        sim = ScenarioSimMarket(
            self.market,
            self.sim_market_data,
            self.market_configuration,
            use_spreaded_term_structures=self.sensitivity_data.use_spreaded_term_structures,
        )
        # b) 템플릿별 생성기
        generators = {
            tpl: SensitivityScenarioGenerator(
                self.sensitivity_data, sim.base_scenario(), self.sim_market_data, sim, tpl
            )
            for tpl in templates
        }
        self.scenario_generator = generators[""]
        run_type = (
            "SensitivityDeltaGamma" if self.sensitivity_data.compute_gamma else "SensitivityDelta"
        )
        ed = self.engine_data.copy_with_global(RunType=run_type)
        calculators = [NPVCalculator(self.sim_market_data.base_currency)]

        self._sensi_cubes = []
        for tpl, gen in generators.items():
            group = [t for t in self.portfolio if (t.sensitivity_template() or "") == tpl]
            if tpl == "":
                group += [t for t in self.portfolio if t.sensitivity_template() not in templates]
            if not group:
                continue
            pf = Portfolio(group)
            # c) 생성기를 시장에 건다
            sim.scenario_generator = gen
            # d) 같은 계약을 시뮬레이션 시장에 다시 연결
            factory = EngineFactory(ed, sim, configurations)
            pf.reset()
            with sim.active():
                pf.build(factory)
            # e) 반복 평가
            cube = NPVCube(pf.ids(), asof, [asof], gen.samples())
            ValuationEngine(
                asof, DateGrid([asof]), sim, recalibrate_models=self.recalibrate_models
            ).build_cube(pf, cube, calculators)
            # f) 민감도
            self._sensi_cubes.append(
                SensitivityCube(
                    cube,
                    gen.scenario_descriptions(),
                    generators[""].shift_sizes(),
                    gen.shift_sizes(),
                    gen.shift_schemes(),
                )
            )
        self.sim_market = sim

    def sensi_cubes(self) -> list[SensitivityCube]:
        if not self._sensi_cubes and self.sim_market is None:
            raise RuntimeError("generate_sensitivities()를 먼저 불러야 한다")
        return list(self._sensi_cubes)

    def report(self) -> pd.DataFrame:
        """모든 템플릿 묶음의 민감도 리포트를 합친 표 (ORE sensitivity 리포트)."""
        return pd.concat([c.report() for c in self.sensi_cubes()], ignore_index=True)

    def delta_table(self, key_type, name: str, measure: str = "Delta") -> pd.DataFrame:
        """만기 × 거래 표 (모든 묶음을 열로 합침)."""
        tables = [
            c.delta_table(key_type, name, measure).drop(columns="total") for c in self.sensi_cubes()
        ]
        out = pd.concat(tables, axis=1)
        out["total"] = out.sum(axis=1)
        return out
