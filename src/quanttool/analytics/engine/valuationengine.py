"""표본 × 날짜 반복 평가. ORE 대응: OREAnalytics/orea/engine/valuationengine.hpp (buildCube).

포트폴리오는 시뮬레이션 시장에 한 번 조립된 상태로 받고, 표본(시나리오)마다·날짜마다
sim_market.update(d) → 거래마다 계산기 → 큐브에 기록한다. 끝나면 시장을 reset한다
(docs/architecture.md 1.6 불변 조건).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from quanttool.analytics.cube import NPVCube
from quanttool.analytics.scenario import SimMarket
from quanttool.data.portfolio import Portfolio
from quanttool.data.utilities.dategrid import DateGrid

from .valuationcalculator import ValuationCalculator


class ValuationEngine:
    def __init__(
        self,
        today: date,
        date_grid: DateGrid | Sequence[date],
        sim_market: SimMarket,
        model_builders: dict | None = None,
        recalibrate_models: bool = False,
    ) -> None:
        self.today = today
        self.date_grid = date_grid if isinstance(date_grid, DateGrid) else DateGrid(list(date_grid))
        self.sim_market = sim_market
        self.model_builders = model_builders or {}
        self.recalibrate_models = recalibrate_models

    def build_cube(
        self,
        portfolio: Portfolio,
        output_cube: NPVCube,
        calculators: list[ValuationCalculator],
    ) -> None:
        sim = self.sim_market
        gen = sim.scenario_generator
        if gen is None:
            raise ValueError("ValuationEngine: sim_market.scenario_generator가 없다")
        trades = list(portfolio)
        if [t.id for t in trades] != output_cube.ids():
            raise ValueError("큐브의 거래 id와 포트폴리오가 다르다")
        if output_cube.samples() != gen.samples():
            raise ValueError(f"큐브 표본 {output_cube.samples()} ≠ 생성기 {gen.samples()}")
        gen.reset()
        try:
            sim.reset()
            with sim.active():
                for i, t in enumerate(trades):
                    for c in calculators:
                        c.calculate_t0(t, i, sim, output_cube)
            for sample in range(output_cube.samples()):
                for d_idx, d in enumerate(self.date_grid):
                    sim.update(d)  # 평가일 = d, 다음 시나리오 적용
                    if self.recalibrate_models:
                        for mb in self.model_builders.values():
                            mb.recalibrate()
                    with sim.active():
                        for i, t in enumerate(trades):
                            for c in calculators:
                                c.calculate(t, i, sim, output_cube, d_idx, sample)
        finally:
            gen.reset()
            sim.reset()
