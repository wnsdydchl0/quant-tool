"""시뮬레이션 시장.

ORE 대응: OREAnalytics/orea/simulation/simmarket.hpp, orea/scenario/scenariosimmarket.hpp.

초기 시장의 커브를 격자점 SimpleQuote로 재표현하고, 그 Quote를 보간한 커브를 내준다.
시나리오는 격자점 Quote만 흔든다 (원래 헬퍼·부트스트랩은 쓰지 않음, docs/architecture.md 원칙 7-1).

격자 커브 모드 (ORE scenariosimmarket.cpp makeYieldCurve):
- spreaded(기본): 격자 Quote = 초기 커브 대비 제로금리 이동량(0에서 시작).
  커브 = 초기 커브 + 보간된 이동량.
  기준 상태에서 초기 커브와 정확히 같다 (ORE SpreadedDiscountCurve).
- 절대: 격자 Quote = 제로금리 자체. 격자점 사이는 보간이라 초기 커브와 조금 다르다.

시간 축: update(d)가 평가일을 d로 옮긴다. spreaded 모드의 기준 커브는 ForwardForward로 굴린다
(오늘의 선도가 실현: DF_d(t) = DF(t0 + t) / DF(t0), ORE 기본값, QuantExt spreadeddiscountcurve.cpp).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pandas as pd
import QuantLib as ql

from quanttool.data.configuration import DEFAULT_CONFIGURATION, ScenarioSimMarketParameters
from quanttool.data.marketdata.market import (
    Market,
    MarketImpl,
    YieldCurveType,
    evaluation_date,
    to_ql_date,
)

from .scenario import RiskFactorKey, Scenario

if TYPE_CHECKING:
    from quanttool.data.configuration import Config
    from quanttool.data.portfolio import Portfolio

    from .sensitivityscenariogenerator import ScenarioGenerator

GRID_DAY_COUNTER = ql.Actual365Fixed()  # 격자 제로금리: 연속복리, Act/365

_FLAT_EXTRAPOLATION_LIMIT = "100Y"


def sample(market: Market, params: ScenarioSimMarketParameters) -> dict[RiskFactorKey, float]:
    """시장의 커브에서 격자점 제로금리를 읽는다 (평가일 기준)."""
    out: dict[RiskFactorKey, float] = {}
    with market.active():
        for name in params.names():
            curve = market.yield_curve(name)
            ref = curve.referenceDate()
            for key, d in zip(params.keys(name), params.dates(name, ref), strict=True):
                out[key] = curve.zeroRate(d, GRID_DAY_COUNTER, ql.Continuous).rate()
    return out


class SimMarket(MarketImpl):
    """바꿀 수 있는 시장. ORE 대응: OREAnalytics/orea/simulation/simmarket.hpp.

    update(d): 평가일을 d로 옮기고, 생성기가 있으면 그 날의 시나리오를 받아 적용한다.
    """

    def __init__(self, asof: date) -> None:
        super().__init__(asof)
        self.date = asof
        self.scenario_generator: ScenarioGenerator | None = None
        self.scenario: Scenario | None = None  # 지금 적용된 시나리오 (None = 기준)

    def active(self):
        """현재 시뮬레이션 날짜로 evaluationDate를 둔 컨텍스트."""
        return evaluation_date(self.date)

    def update(self, d: date) -> None:
        self.date = d
        ql.Settings.instance().evaluationDate = to_ql_date(d)
        self._roll(d)
        if self.scenario_generator is not None:
            self.apply_scenario(self.scenario_generator.next(d))
        else:
            self._reset_quotes()

    def reset(self) -> None:
        """초기 상태(날짜 asof, 기준 시나리오)로 되돌린다."""
        self.date = self.asof
        self._roll(self.asof)
        self._reset_quotes()

    def apply_scenario(self, scenario: Scenario) -> None:
        raise NotImplementedError

    def _roll(self, d: date) -> None:
        """날짜 이동에 맞춰 기준 구조물을 굴린다."""

    def _reset_quotes(self) -> None:
        """격자 Quote를 기준값으로."""


class ScenarioSimMarket(SimMarket):
    def __init__(
        self,
        init_market: Market,
        params: ScenarioSimMarketParameters,
        spreaded: bool | None = None,
    ) -> None:
        super().__init__(init_market.asof)
        self.init_market = init_market
        self.params = params
        self.base_zero = sample(init_market, params)  # 초기 커브의 격자점 제로금리
        self.spreaded: dict[str, bool] = {
            n: spec.spreaded if spreaded is None else spreaded for n, spec in params.root.items()
        }
        # 격자 Quote의 기준값: spreaded는 이동량 0, 절대는 제로금리
        self.base_values: dict[RiskFactorKey, float] = {
            k: 0.0 if self.spreaded[k.name] else v for k, v in self.base_zero.items()
        }
        self.sim_data: dict[RiskFactorKey, ql.SimpleQuote] = {
            k: ql.SimpleQuote(v) for k, v in self.base_values.items()
        }
        self._base_links: dict[str, ql.RelinkableYieldTermStructureHandle] = {}
        with self.active():
            for name in params.names():
                self._set_yield_curve(YieldCurveType.Yield, name, self._grid_curve(name))
        self._names = set(params.names())

    def _grid_curve(self, name: str) -> ql.RelinkableYieldTermStructureHandle:
        spec = self.params.root[name]
        if spec.interpolation != "Linear(Zero)":
            raise NotImplementedError(f"격자 보간 {spec.interpolation!r} 미구현")
        init = self.init_market.yield_curve(name)
        ref = init.referenceDate()
        if self.spreaded[name]:
            # 초기 커브(날짜 이동 시 ForwardForward로 굴림) + 격자 이동량
            base = ql.RelinkableYieldTermStructureHandle()
            base.linkTo(init.currentLink())
            self._base_links[name] = base
        else:
            # 기준일이 평가일을 따라가는 0% 커브 + 격자 제로금리 = 격자점 사이 선형, 바깥 평탄
            base = ql.YieldTermStructureHandle(
                ql.FlatForward(0, ql.NullCalendar(), 0.0, GRID_DAY_COUNTER)
            )
        quotes = [ql.QuoteHandle(self.sim_data[k]) for k in self.params.keys(name)]
        dates = self.params.dates(name, ref)
        # QuantLib 1.44의 이 클래스는 Quote 변경으로 update()되면 enableExtrapolation 설정이
        # 풀린다. 외삽 플래그에 기대지 않고, 마지막 격자 Quote에 묶인 먼 끝점으로 평탄 외삽한다.
        quotes.append(quotes[-1])
        dates.append(ref + ql.Period(_FLAT_EXTRAPOLATION_LIMIT))
        curve = ql.PiecewiseZeroSpreadedTermStructure(
            base, quotes, dates, ql.Continuous, ql.NoFrequency, GRID_DAY_COUNTER
        )
        handle = ql.RelinkableYieldTermStructureHandle()
        handle.linkTo(curve)
        return handle

    # --- Market 규격: 격자에 없는 커브는 흔들 수 없고 초기 시장 그대로
    def yield_curve(
        self, name: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle:
        if name in self._names:
            return super().yield_curve(name, configuration)
        return self.init_market.yield_curve(name, configuration)

    def discount_curve(
        self, ccy: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle:
        return self.init_market.discount_curve(ccy, configuration)

    def quote(self, quote_id: str) -> ql.QuoteHandle:
        return self.init_market.quote(quote_id)

    # --- 시나리오 적용
    def apply_scenario(self, scenario: Scenario) -> None:
        """기준값 + 이동량. 누적되지 않는다 (적용 전 상태와 무관)."""
        for key in scenario.shifts:
            if key not in self.sim_data:
                raise KeyError(
                    f"격자에 없는 리스크 요인 {key}: 흔들 대상은 simmarket.yaml에 있어야 한다"
                )
        for key, quote in self.sim_data.items():
            quote.setValue(self.base_values[key] + scenario.shifts.get(key, 0.0))
        self.scenario = scenario

    def _reset_quotes(self) -> None:
        for key, quote in self.sim_data.items():
            quote.setValue(self.base_values[key])
        self.scenario = None

    def _roll(self, d: date) -> None:
        for name, base in self._base_links.items():
            init = self.init_market.yield_curve(name)
            if d == self.asof:
                base.linkTo(init.currentLink())
            else:
                rolled = ql.ImpliedTermStructure(init, to_ql_date(d))  # ForwardForward
                rolled.enableExtrapolation()
                base.linkTo(rolled)

    def base_reconciliation(self, portfolio: Portfolio, cfg: Config) -> pd.DataFrame:
        """초기 시장과 시뮬레이션 시장의 거래별 NPV 대사.

        끝나면 포트폴리오는 이 시장으로 조립된 상태다.
        """
        from quanttool.data.portfolio import EngineFactory

        with self.init_market.active():
            portfolio.build(EngineFactory.from_config(cfg, self.init_market))
            base = portfolio.npvs()
        with self.active():
            portfolio.build(EngineFactory.from_config(cfg, self))
            grid = portfolio.npvs()
        out = pd.DataFrame({"base_npv": base, "grid_npv": grid})
        out["diff"] = out["grid_npv"] - out["base_npv"]
        out["rel_diff"] = out["diff"] / out["base_npv"].abs()
        return out
