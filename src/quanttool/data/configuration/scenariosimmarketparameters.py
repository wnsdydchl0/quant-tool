"""시뮬레이션 시장 격자. ORE 대응: OREAnalytics/orea/scenario/scenariosimmarketparameters.hpp.

simmarket.yaml (ORE simulation.xml의 Market 블록):
    base_currency: USD
    currencies: [USD]          # 할인 커브(DiscountCurve/통화)를 격자화할 통화
    yield_curves:
      names: [UST]             # yield_curve(이름)으로 부르는 커브(YieldCurve/이름)를 격자화
      tenors: {"": [...]}      # "" = 기본, 이름별로 덮어쓸 수 있다 (ORE Configuration curve="…")
      interpolation: LinearZero | LogLinear
      extrapolation: FlatZero
      roll_down: ForwardForward
격자점 하나가 RiskFactorKey(KeyType, 이름, 만기 번호) 하나다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quanttool.qle.scenario import KeyType, RiskFactorKey


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class YieldCurveSimData(_Strict):
    names: list[str] = []
    tenors: dict[str, list[str]] = Field(default_factory=dict)
    interpolation: Literal["LinearZero", "LogLinear"] = "LogLinear"
    extrapolation: Literal["FlatZero"] = "FlatZero"
    roll_down: Literal["ForwardForward"] = "ForwardForward"  # ORE YieldCurveRollDown 기본
    day_counter: str = "A365F"  # 격자 시간 (ORE yieldCurveDayCounters 기본)

    @model_validator(mode="after")
    def _check(self) -> YieldCurveSimData:
        if (self.names or self.tenors) and "" not in self.tenors:
            raise ValueError('yield_curves.tenors에 기본("") 격자가 필요하다')
        for key, ts in self.tenors.items():
            if len(ts) < 2:
                raise ValueError(f"격자 {key or '기본'}의 만기가 2개 미만이다")
        return self


class ScenarioSimMarketParameters(_Strict):
    """ORE ``ScenarioSimMarketParameters``."""

    base_currency: str
    currencies: list[str] = []
    yield_curves: YieldCurveSimData = YieldCurveSimData()

    # --- ORE 조회 메소드
    def discount_curve_names(self) -> list[str]:
        return list(self.currencies)

    def yield_curve_names(self) -> list[str]:
        return list(self.yield_curves.names)

    def yield_curve_tenors(self, name: str) -> list[str]:
        t = self.yield_curves.tenors
        return list(t.get(name, t[""]))

    @property
    def interpolation(self) -> str:
        return self.yield_curves.interpolation

    @property
    def extrapolation(self) -> str:
        return self.yield_curves.extrapolation

    def curves(self) -> list[tuple[KeyType, str]]:
        """격자화할 커브 (종류, 이름)."""
        return [(KeyType.DiscountCurve, c) for c in self.currencies] + [
            (KeyType.YieldCurve, n) for n in self.yield_curves.names
        ]

    def keys(self, key_type: KeyType, name: str) -> list[RiskFactorKey]:
        return [RiskFactorKey(key_type, name, i) for i in range(len(self.yield_curve_tenors(name)))]
