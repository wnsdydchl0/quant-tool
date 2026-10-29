"""엔진 팩토리(접수 창구)와 엔진 빌더(기술자). ORE 대응: OREData/ored/portfolio/enginefactory.hpp.

- EngineData(engines.yaml)가 상품 유형 → (model, engine)을 정한다.
- 팩토리는 builder(trade_type)로 그 엔진 빌더를 돌려준다(시장당 하나).
- 계약서는 자기 키(커브 이름 등)로 builder.engine(...)을 부른다. 같은 키면 같은 엔진을 재사용한다
  (ORE CachingEngineBuilder). ORE Swap::build도 builder("Swap") → engine(ccy) 순서다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import TYPE_CHECKING, ClassVar

import QuantLib as ql

from quanttool.data.configuration import (
    EngineData,
    EngineSpec,
    InstrumentConventions,
    RateConventions,
)
from quanttool.data.marketdata.market import Market
from quanttool.data.utilities.registry import ENGINE_BUILDERS

if TYPE_CHECKING:
    from quanttool.data.configuration import Config


class EngineBuilder(ABC):
    """(model, engine, trade_types)로 등록되는 엔진 빌더. 같은 키면 캐시된 엔진을 돌려준다."""

    model: ClassVar[str]
    engine_name: ClassVar[str]
    trade_types: ClassVar[frozenset[str]]

    def __init__(self, market: Market, spec: EngineSpec) -> None:
        self.market = market
        self.spec = spec
        self._cache: dict[Hashable, ql.PricingEngine] = {}

    def engine(self, *keys: Hashable) -> ql.PricingEngine:
        if keys not in self._cache:
            self._cache[keys] = self.make(*keys)
        return self._cache[keys]

    @abstractmethod
    def make(self, *keys: Hashable) -> ql.PricingEngine: ...


class EngineFactory:
    def __init__(self, engine_data: EngineData, market: Market) -> None:
        self.engine_data = engine_data
        self.market = market
        self._builders: dict[str, EngineBuilder] = {}

    @classmethod
    def from_config(cls, cfg: Config, market: Market) -> EngineFactory:
        return cls(cfg.engine_data, market)

    def builder(self, trade_type: str) -> EngineBuilder:
        spec = self.engine_data[trade_type]
        if trade_type not in self._builders:
            builder_cls = ENGINE_BUILDERS[spec.engine]
            if builder_cls.model != spec.model or trade_type not in builder_cls.trade_types:
                supported = sorted(builder_cls.trade_types)
                raise KeyError(
                    f"{spec.engine}: model {builder_cls.model!r}, 상품 {supported}"
                    f" — engines.yaml의 {trade_type}: {spec.model}/{spec.engine}과 맞지 않는다"
                )
            self._builders[trade_type] = builder_cls(self.market, spec)
        return self._builders[trade_type]

    @staticmethod
    def conventions(name: str) -> RateConventions:
        return InstrumentConventions.instance().conventions().get(name)
