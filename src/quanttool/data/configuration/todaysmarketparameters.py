"""오늘 시장에 둘 객체와 그 레시피. ORE 대응: OREData/ored/marketdata/todaysmarketparameters.hpp.

구조 (ORE todaysmarket.xml과 같음):
- configurations: configuration id → 시장 객체 종류별 "묶음 id"
- discounting_curves / yield_curves: 묶음 id → {시장에서 부르는 이름: 커브 지정 문자열}

가격결정 코드는 ``discount_curve("USD")``처럼 이름만 부르고, 그 이름이 어떤 레시피로 만들어지는지는
여기서 정한다. 여러 이름이 같은 레시피를 가리키면 커브 객체 하나를 공유한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .conventions import _Strict
from .curvespec import parse_curve_spec

DEFAULT_CONFIGURATION = "default"


class MarketObject(StrEnum):
    """시장에 둘 수 있는 객체 종류. ORE 대응: market.hpp ``MarketObject``의 필요한 부분."""

    DiscountCurve = "DiscountCurve"
    YieldCurve = "YieldCurve"


class MarketConfiguration(_Strict):
    """configuration 하나 = 시장 객체 종류별 묶음 id. ORE ``MarketConfiguration``."""

    discounting_curves_id: str = DEFAULT_CONFIGURATION
    yield_curves_id: str = DEFAULT_CONFIGURATION

    def id(self, o: MarketObject) -> str:
        return {
            MarketObject.DiscountCurve: self.discounting_curves_id,
            MarketObject.YieldCurve: self.yield_curves_id,
        }[o]


class TodaysMarketParameters(_Strict):
    configurations: dict[str, MarketConfiguration] = Field(
        default_factory=lambda: {DEFAULT_CONFIGURATION: MarketConfiguration()}
    )
    discounting_curves: dict[str, dict[str, str]] = {}
    yield_curves: dict[str, dict[str, str]] = {}

    @model_validator(mode="after")
    def _check(self) -> TodaysMarketParameters:
        for conf_id, conf in self.configurations.items():
            for o in MarketObject:
                group = conf.id(o)
                if group not in self._groups(o) and self._groups(o):
                    raise ValueError(f"configuration {conf_id!r}: {o.value} 묶음 {group!r}가 없다")
        for o in MarketObject:
            for mapping in self._groups(o).values():
                for spec in mapping.values():
                    parse_curve_spec(spec)
        return self

    def _groups(self, o: MarketObject) -> dict[str, dict[str, str]]:
        return {
            MarketObject.DiscountCurve: self.discounting_curves,
            MarketObject.YieldCurve: self.yield_curves,
        }[o]

    def mapping(
        self, o: MarketObject, configuration: str = DEFAULT_CONFIGURATION
    ) -> dict[str, str]:
        """{시장에서 부르는 이름: 커브 지정}. 예: {"USD": "Yield/USD/UST"}."""
        return dict(self._groups(o).get(self.configurations[configuration].id(o), {}))

    def curve_specs(self, configuration: str = DEFAULT_CONFIGURATION) -> list[str]:
        """이 configuration에서 만들어야 하는 커브 지정 문자열 (중복 없이)."""
        out: list[str] = []
        for o in MarketObject:
            for spec in self.mapping(o, configuration).values():
                if spec not in out:
                    out.append(spec)
        return out
