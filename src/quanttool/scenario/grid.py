"""시나리오 격자. ORE 대응: OREAnalytics/orea/scenario/scenariosimmarketparameters.hpp.

격자점 하나가 RiskFactorKey 하나다. 요인 로딩·과거 시나리오도 같은 격자 좌표를 쓴다.
"""

from __future__ import annotations

from pathlib import Path

import QuantLib as ql
import yaml

from quanttool.config import GridConfig, GridSpec
from quanttool.core.ids import RiskFactorKey
from quanttool.market.market import Market

GRID_DAY_COUNTER = ql.Actual365Fixed()  # 격자 제로금리: 연속복리, Act/365


class ScenarioGrid:
    def __init__(self, specs: GridConfig | dict[str, GridSpec]) -> None:
        self.specs: dict[str, GridSpec] = dict(
            specs.root if isinstance(specs, GridConfig) else specs
        )

    @classmethod
    def load(cls, path: str | Path) -> ScenarioGrid:
        with Path(path).open(encoding="utf-8") as f:
            return cls(GridConfig.model_validate(yaml.safe_load(f)))

    def names(self) -> list[str]:
        return list(self.specs)

    def keys(self, name: str | None = None) -> list[RiskFactorKey]:
        names = [name] if name else self.names()
        return [
            RiskFactorKey(self.specs[n].kind, n, (t,)) for n in names for t in self.specs[n].tenors
        ]

    def dates(self, name: str, reference: ql.Date) -> list[ql.Date]:
        return [reference + ql.Period(t) for t in self.specs[name].tenors]

    def sample(self, market: Market) -> dict[RiskFactorKey, float]:
        """시장의 커브에서 격자점 제로금리를 읽는다 (평가일 기준)."""
        out: dict[RiskFactorKey, float] = {}
        with market.active():
            for name in self.names():
                curve = market.yield_curve(name)
                ref = curve.referenceDate()
                for key, d in zip(self.keys(name), self.dates(name, ref), strict=True):
                    out[key] = curve.zeroRate(d, GRID_DAY_COUNTER, ql.Continuous).rate()
        return out
