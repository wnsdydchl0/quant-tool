"""시뮬레이션 시장 격자와 민감도 설정.

ORE 대응: OREAnalytics/orea/scenario/scenariosimmarketparameters.hpp (simulation.xml),
sensitivityscenariodata.hpp (sensitivity.xml).
"""

from __future__ import annotations

from typing import Literal

import QuantLib as ql
from pydantic import BaseModel, ConfigDict, Field, RootModel

from quanttool.qle.scenario import RiskFactorKey


class YieldCurveSimParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["zero"]
    tenors: list[str] = Field(min_length=2)
    interpolation: Literal["Linear(Zero)", "LogLinear(Discount)"] = "Linear(Zero)"
    extrapolation: Literal["flat_zero"] = "flat_zero"


class ScenarioSimMarketParameters(RootModel[dict[str, YieldCurveSimParameters]]):
    """커브 이름 → 격자 정의. 격자점 하나가 RiskFactorKey 하나다."""

    def names(self) -> list[str]:
        return list(self.root)

    def keys(self, name: str | None = None) -> list[RiskFactorKey]:
        names = [name] if name else self.names()
        return [
            RiskFactorKey(self.root[n].kind, n, (t,)) for n in names for t in self.root[n].tenors
        ]

    def dates(self, name: str, reference: ql.Date) -> list[ql.Date]:
        return [reference + ql.Period(t) for t in self.root[name].tenors]


class SensitivityScenarioData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key_rate_bp: float = Field(1.0, gt=0)
    parallel_bp: float = Field(1.0, gt=0)
