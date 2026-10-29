"""민감도 시나리오 생성기.

ORE 대응: OREAnalytics/orea/scenario/sensitivityscenariogenerator.hpp/.cpp.

시나리오 목록: 기준, 커브마다 shift tenor j를 위로(Up) 하나씩, 필요하면 아래로(Down:
Central·Backward
방식이거나 gamma 계산), cross_gamma_filter 쌍마다 두 점을 함께 위로(Cross).
- 이동량은 제로금리 기준이고, 격자 Quote 값에는 exp(−Δz·t)를 곱한다 (ORE와 같음).
- 템플릿(sensitivity_template)이 주어지면 keyed_shift_size·keyed_shift_scheme을 쓴다.
- 결과의 키는 RiskFactorKey(커브 종류, 이름, shift tenor 번호)다.
"""

from __future__ import annotations

import math

import QuantLib as ql

from quanttool.data.configuration import (
    CurveShiftData,
    ScenarioSimMarketParameters,
    SensitivityScenarioData,
)
from quanttool.data.utilities import parsers
from quanttool.qle.scenario import KeyType, RiskFactorKey, Scenario

from .shiftscenariogenerator import (
    DescriptionType,
    ScenarioDescription,
    ShiftScenarioGenerator,
    apply_curve_shift,
)
from .simmarket import ScenarioSimMarket


class SensitivityScenarioGenerator(ShiftScenarioGenerator):
    def __init__(
        self,
        sensitivity_data: SensitivityScenarioData,
        base_scenario: Scenario,
        sim_market_data: ScenarioSimMarketParameters,
        sim_market: ScenarioSimMarket,
        sensitivity_template: str = "",
    ) -> None:
        super().__init__(base_scenario)
        self.sensitivity_data = sensitivity_data
        self.sim_market_data = sim_market_data
        self.sim_market = sim_market
        self.sensitivity_template = sensitivity_template
        self._shift_sizes: dict[RiskFactorKey, float] = {}
        self._shift_schemes: dict[RiskFactorKey, str] = {}
        self._index_desc: dict[RiskFactorKey, str] = {}
        self._up: dict[RiskFactorKey, dict] = {}
        self._generate()

    # --- ORE 조회
    def shift_sizes(self) -> dict[RiskFactorKey, float]:
        return dict(self._shift_sizes)

    def shift_schemes(self) -> dict[RiskFactorKey, str]:
        return dict(self._shift_schemes)

    # --- 생성
    def _curve_data(self) -> list[tuple[KeyType, str, CurveShiftData]]:
        d = self.sensitivity_data
        out = [(KeyType.DiscountCurve, c, s) for c, s in d.discount_curves.items()]
        out += [(KeyType.YieldCurve, n, s) for n, s in d.yield_curves.items()]
        for key_type, name, _ in out:
            if (key_type, name) not in self.sim_market_data.curves():
                raise KeyError(f"{key_type}/{name}: 민감도 대상이 simmarket.yaml 격자에 없다")
        return out

    def _generate(self) -> None:
        tpl = self.sensitivity_template
        curves = self._curve_data()
        need_down = self.sensitivity_data.compute_gamma or any(
            s.scheme(tpl) != "Forward" for _, _, s in curves
        )
        for up in [True, False] if need_down else [True]:
            for key_type, name, data in curves:
                self._curve_scenarios(key_type, name, data, up)
        self._cross_gamma_scenarios(curves)

    def _grid(self, key_type: KeyType, name: str):
        keys = self.sim_market_data.keys(key_type, name)
        times = [self.sim_market.sim_data_times[k] for k in keys]
        return keys, times

    def _shift_times(self, data: CurveShiftData, ref_name: str) -> list[float]:
        dc = parsers.day_counter(self.sim_market_data.yield_curves.day_counter)
        ref = ql.Date(
            self.sim_market.asof.day, self.sim_market.asof.month, self.sim_market.asof.year
        )
        return [dc.yearFraction(ref, ref + ql.Period(t)) for t in data.shift_tenors]

    def _base_zero(self, keys, times) -> list[float]:
        absolute = self.sim_market.base_scenario_absolute()
        return [-math.log(absolute.get(k)) / t for k, t in zip(keys, times, strict=True)]

    def _curve_scenarios(self, key_type, name, data: CurveShiftData, up: bool) -> None:
        tpl = self.sensitivity_template
        keys, times = self._grid(key_type, name)
        shift_times = self._shift_times(data, name)
        size = data.size(tpl) * (1.0 if up else -1.0)
        zeros = self._base_zero(keys, times)
        for j, tenor in enumerate(data.shift_tenors):
            factor = RiskFactorKey(key_type, name, j)
            delta = apply_curve_shift(
                self.base_scenario, keys, times, shift_times, j, size, data.shift_type, zeros
            )
            desc = ScenarioDescription(
                DescriptionType.Up if up else DescriptionType.Down, factor, tenor
            )
            self._add(desc, delta)
            if up:
                self._up[factor] = delta
                self._shift_sizes[factor] = data.size(tpl)
                self._shift_schemes[factor] = data.scheme(tpl)
                self._index_desc[factor] = tenor

    def _cross_gamma_scenarios(self, curves) -> None:
        pairs = self.sensitivity_data.cross_gamma_filter
        if not pairs:
            return
        factors = list(self._up)
        for i, f1 in enumerate(factors):
            for f2 in factors[i + 1 :]:
                p1, p2 = f"{f1.key_type}/{f1.name}", f"{f2.key_type}/{f2.name}"
                if (p1, p2) not in pairs and (p2, p1) not in pairs:
                    continue
                delta = dict(self._up[f1])
                # 같은 격자점을 두 이동이 함께 건드리면 이동을 더한다 (값에 비율을 곱해 합성)
                for k, v in self._up[f2].items():
                    delta[k] = delta[k] * v / self.base_scenario.get(k) if k in delta else v
                desc = ScenarioDescription(
                    DescriptionType.Cross, f1, self._index_desc[f1], f2, self._index_desc[f2]
                )
                self._add(desc, delta)
