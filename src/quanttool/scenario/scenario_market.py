"""시나리오 시장. ORE 대응: OREAnalytics/orea/scenario/scenariosimmarket.hpp.

기준 시장의 커브를 격자점 제로금리 SimpleQuote로 재표현하고, 그 Quote를 보간한 커브를 내준다.
시나리오는 격자점 Quote만 흔든다 (원래 헬퍼·부트스트랩은 쓰지 않음, docs/architecture.md 원칙 7-1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import QuantLib as ql

from quanttool.core.ids import RiskFactorKey
from quanttool.market.market import Market

from .generators import Scenario
from .grid import GRID_DAY_COUNTER, ScenarioGrid

if TYPE_CHECKING:
    from quanttool.config import Config
    from quanttool.derivatives import Portfolio


_FLAT_EXTRAPOLATION_LIMIT = "100Y"


class ScenarioMarket(Market):
    def __init__(self, base: Market, grid: ScenarioGrid) -> None:
        self.base = base
        self.grid = grid
        self.asof = base.asof
        self.base_values: dict[RiskFactorKey, float] = grid.sample(base)
        self.sim_data: dict[RiskFactorKey, ql.SimpleQuote] = {
            k: ql.SimpleQuote(v) for k, v in self.base_values.items()
        }
        self._curves: dict[str, ql.RelinkableYieldTermStructureHandle] = {}
        with self.active():
            for name in grid.names():
                self._curves[name] = self._grid_curve(name)

    def _grid_curve(self, name: str) -> ql.RelinkableYieldTermStructureHandle:
        spec = self.grid.specs[name]
        if spec.interpolation != "Linear(Zero)":
            raise NotImplementedError(f"격자 보간 {spec.interpolation!r} 미구현")
        # 기준일이 평가일을 따라가는 0% 커브 + 격자 제로금리 = 격자점 사이 제로금리 선형, 바깥 평탄
        zero = ql.YieldTermStructureHandle(
            ql.FlatForward(0, ql.NullCalendar(), 0.0, GRID_DAY_COUNTER)
        )
        ref = self.base.yield_curve(name).referenceDate()
        quotes = [ql.QuoteHandle(self.sim_data[k]) for k in self.grid.keys(name)]
        dates = self.grid.dates(name, ref)
        # QuantLib 1.44의 이 클래스는 Quote 변경으로 update()되면 enableExtrapolation 설정이
        # 풀린다. 외삽 플래그에 기대지 않고, 마지막 격자 Quote에 묶인 먼 끝점으로 평탄 외삽한다.
        quotes.append(quotes[-1])
        dates.append(ref + ql.Period(_FLAT_EXTRAPOLATION_LIMIT))
        curve = ql.PiecewiseZeroSpreadedTermStructure(
            zero, quotes, dates, ql.Continuous, ql.NoFrequency, GRID_DAY_COUNTER
        )
        handle = ql.RelinkableYieldTermStructureHandle()
        handle.linkTo(curve)
        return handle

    # --- Market 규격
    def quote(self, quote_id: str) -> ql.QuoteHandle:
        return self.base.quote(quote_id)

    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle:
        if name in self._curves:
            return self._curves[name]
        return self.base.yield_curve(name)  # 격자에 없는 커브는 흔들 수 없고 기준 그대로

    # --- 시나리오 적용
    def apply(self, scenario: Scenario) -> None:
        """기준값 + 이동량. 누적되지 않는다 (적용 전 상태와 무관)."""
        for key in scenario.shifts:
            if key not in self.sim_data:
                raise KeyError(
                    f"격자에 없는 리스크 요인 {key}: 흔들 대상은 grid.yaml에 있어야 한다"
                )
        for key, quote in self.sim_data.items():
            quote.setValue(self.base_values[key] + scenario.shifts.get(key, 0.0))

    def reset(self) -> None:
        for key, quote in self.sim_data.items():
            quote.setValue(self.base_values[key])

    def base_reconciliation(self, portfolio: Portfolio, cfg: Config) -> pd.DataFrame:
        """기준 시장과 격자 시장의 거래별 NPV 대사. 끝나면 포트폴리오는 이 시장으로 조립된 상태."""
        from quanttool.derivatives import EngineFactory

        with self.base.active():
            portfolio.build(EngineFactory(self.base, cfg))
            base = portfolio.npvs()
        with self.active():
            portfolio.build(EngineFactory(self, cfg))
            grid = portfolio.npvs()
        out = pd.DataFrame({"base_npv": base, "grid_npv": grid})
        out["diff"] = out["grid_npv"] - out["base_npv"]
        out["rel_diff"] = out["diff"] / out["base_npv"].abs()
        return out
