"""시뮬레이션 시장.

ORE 대응: OREAnalytics/orea/simulation/simmarket.hpp/.cpp, orea/scenario/scenariosimmarket.hpp/.cpp.

초기 시장의 커브를 격자점 SimpleQuote(sim_data)로 다시 표현하고, 그 Quote로 만든 커브를 내준다.
시나리오는 격자점 Quote만 바꾼다 (원래 헬퍼·부트스트랩은 쓰지 않음, docs/architecture.md 원칙 7-1).

격자 Quote의 뜻 (ORE scenariosimmarket.cpp addYieldCurve, makeYieldCurve):
- spreaded(use_spreaded_term_structures=True): 초기 커브 대비 할인계수 비율. 기준 상태 1.0이고,
  커브 = 초기 커브 × 보간된 비율이라 기준 상태에서 초기 커브와 정확히 같다 (ORE
  SpreadedDiscountCurve).
- 절대: 할인계수 자체. 격자점 사이는 보간이라 초기 커브와 조금 다르다 (ORE
  InterpolatedDiscountCurve).

시간 축: update(d)가 평가일을 d로 옮긴다. spreaded 모드의 기준 커브는 ForwardForward로 굴린다
(오늘의 선도가 실현: DF_d(t) = DF(t0 + t) / DF(t0), ORE YieldCurveRollDown 기본값).
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
from quanttool.data.utilities import parsers
from quanttool.qle.scenario import KeyType, RiskFactorKey, Scenario, SimpleScenario
from quanttool.qle.termstructures import interpolated_discount_curve, spreaded_discount_curve

if TYPE_CHECKING:
    from quanttool.data.configuration import Config
    from quanttool.data.portfolio import Portfolio

    from .sensitivityscenariogenerator import ScenarioGenerator

_CURVE_TYPE = {
    KeyType.DiscountCurve: YieldCurveType.Discount,
    KeyType.YieldCurve: YieldCurveType.Yield,
}


class SimMarket(MarketImpl):
    """바꿀 수 있는 시장. ORE 대응: orea/simulation/simmarket.hpp.

    update(d): 평가일을 d로 옮기고, 생성기에서 그 날의 시나리오를 받아 적용한다.
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
        """ORE SimMarket::update 순서: 다음 시나리오 → 날짜 이동 → 적용."""
        scenario = self._load_next_scenario(d)
        self._update_date(d)
        if scenario is None:
            self._apply_base()
        else:
            self.apply_scenario(scenario)

    def update_scenario(self, d: date) -> None:
        """날짜는 그대로 두고 다음 시나리오만 적용 (ORE SimMarket::updateScenario)."""
        scenario = self._load_next_scenario(d)
        if scenario is not None:
            self.apply_scenario(scenario)

    def reset(self) -> None:
        """초기 상태(날짜 asof, 기준 시나리오)로 되돌린다."""
        self._update_date(self.asof)
        self._apply_base()

    def _load_next_scenario(self, d: date) -> Scenario | None:
        if self.scenario_generator is None:
            return None
        return self.scenario_generator.next(d)

    def _update_date(self, d: date) -> None:
        self.date = d
        ql.Settings.instance().evaluationDate = to_ql_date(d)

    def apply_scenario(self, scenario: Scenario) -> None:
        raise NotImplementedError

    def _apply_base(self) -> None:
        raise NotImplementedError


class ScenarioSimMarket(SimMarket):
    """ORE ``ScenarioSimMarket``.

    ORE 생성자: (initMarket, parameters, configuration, …, useSpreadedTermStructures).
    """

    def __init__(
        self,
        init_market: Market,
        parameters: ScenarioSimMarketParameters,
        configuration: str = DEFAULT_CONFIGURATION,
        use_spreaded_term_structures: bool = False,
        allow_partial_scenarios: bool = False,
    ) -> None:
        super().__init__(init_market.asof)
        self.init_market = init_market
        self.parameters = parameters
        self.configuration = configuration
        self.use_spreaded_term_structures = use_spreaded_term_structures
        self.allow_partial_scenarios = allow_partial_scenarios
        self.sim_data: dict[RiskFactorKey, ql.SimpleQuote] = {}
        self.sim_data_times: dict[RiskFactorKey, float] = {}  # 격자점 시간 (격자 day counter)
        self._base_links: dict[tuple[KeyType, str], ql.RelinkableYieldTermStructureHandle] = {}
        self._simulated: set[tuple[YieldCurveType, str]] = set()
        base: dict[RiskFactorKey, float] = {}
        base_abs: dict[RiskFactorKey, float] = {}
        with self.active():
            for key_type, name in parameters.curves():
                b, ba = self._add_yield_curve(key_type, name)
                base.update(b)
                base_abs.update(ba)
        # ORE baseScenario / baseScenarioAbsolute
        self._base_scenario = SimpleScenario(
            self.asof, "BASE", base, absolute=not use_spreaded_term_structures
        )
        self._base_scenario_absolute = SimpleScenario(self.asof, "BASE", base_abs, absolute=True)

    def _init_curve(self, key_type: KeyType, name: str) -> ql.YieldTermStructureHandle:
        if key_type == KeyType.DiscountCurve:
            return self.init_market.discount_curve(name, self.configuration)
        return self.init_market.yield_curve(name, self.configuration)

    def _add_yield_curve(self, key_type: KeyType, name: str):
        p = self.parameters
        if p.interpolation != "LinearZero":
            raise NotImplementedError(
                f"격자 보간 {p.interpolation!r} 미지원 (QuantLib-Python에 ORE "
                "SpreadedDiscountCurve logLinear와 같은 구조물이 없다). LinearZero를 쓴다"
            )
        init = self._init_curve(key_type, name)
        ref = init.referenceDate()
        dc = parsers.day_counter(p.yield_curves.day_counter)
        dates = [ref + ql.Period(t) for t in p.yield_curve_tenors(name)]
        times = [dc.yearFraction(ref, d) for d in dates]
        keys = p.keys(key_type, name)
        dfs = [init.discount(d) for d in dates]
        spreaded = self.use_spreaded_term_structures
        values = [1.0] * len(dfs) if spreaded else dfs
        quotes = [ql.SimpleQuote(v) for v in values]
        if spreaded:
            reference = ql.RelinkableYieldTermStructureHandle()
            reference.linkTo(init.currentLink())
            self._base_links[(key_type, name)] = reference
            curve = spreaded_discount_curve(reference, dates, quotes, times, dc)
        else:
            curve = interpolated_discount_curve(dates, quotes, times, dc)
        handle = ql.RelinkableYieldTermStructureHandle()
        handle.linkTo(curve)
        curve_type = _CURVE_TYPE[key_type]
        self._set_yield_curve(curve_type, name, handle, self.configuration)
        self._simulated.add((curve_type, name))
        for k, q, t in zip(keys, quotes, times, strict=True):
            self.sim_data[k] = q
            self.sim_data_times[k] = t
        return dict(zip(keys, values, strict=True)), dict(zip(keys, dfs, strict=True))

    # --- Market 규격: 격자화하지 않은 커브는 초기 시장 그대로 (ORE도 시뮬레이션 안 하는 객체는
    # 복사)
    def discount_curve(
        self, ccy: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle:
        if (YieldCurveType.Discount, ccy) in self._simulated:
            return super().discount_curve(ccy, self.configuration)
        return self.init_market.discount_curve(ccy, configuration)

    def yield_curve(
        self, name: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle:
        if (YieldCurveType.Yield, name) in self._simulated:
            return super().yield_curve(name, self.configuration)
        return self.init_market.yield_curve(name, configuration)

    # --- 시나리오
    def base_scenario(self) -> SimpleScenario:
        return self._base_scenario

    def base_scenario_absolute(self) -> SimpleScenario:
        return self._base_scenario_absolute

    def apply_scenario(self, scenario: Scenario) -> None:
        """격자 Quote를 시나리오 값으로 둔다. ORE ScenarioSimMarket::applyScenario."""
        if scenario.is_absolute() != self._base_scenario.is_absolute():
            raise ValueError(
                f"시나리오 {scenario.label()!r}: absolute={scenario.is_absolute()}인데 시장은 "
                f"absolute={self._base_scenario.is_absolute()}"
            )
        keys = scenario.keys()
        for k in keys:
            if k not in self.sim_data:
                raise KeyError(
                    f"격자에 없는 리스크 요인 {k}: 흔들 대상은 simmarket.yaml에 있어야 한다"
                )
        if not self.allow_partial_scenarios and set(keys) != set(self.sim_data):
            missing = sorted(set(self.sim_data) - set(keys))[:3]
            raise KeyError(
                f"시나리오 {scenario.label()!r}에 격자점이 빠졌다(예: {missing}). "
                "DeltaScenario(기준, 바뀐 점)을 쓰거나 allow_partial_scenarios=True"
            )
        for k in keys:
            self.sim_data[k].setValue(scenario.get(k))
        self.scenario = scenario

    def _apply_base(self) -> None:
        for k, q in self.sim_data.items():
            q.setValue(self._base_scenario.get(k))
        self.scenario = None

    def _update_date(self, d: date) -> None:
        super()._update_date(d)
        for (key_type, name), reference in self._base_links.items():
            init = self._init_curve(key_type, name)
            if d == self.asof:
                reference.linkTo(init.currentLink())
            else:
                rolled = ql.ImpliedTermStructure(init, to_ql_date(d))  # ForwardForward
                rolled.enableExtrapolation()
                reference.linkTo(rolled)

    # --- 진단 (QuantTool)
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
