"""엔진 빌더 (기술자). ORE 대응: OREData/ored/portfolio/builders/bond.hpp 등.

엔진 빌더는 생성 시 시장을 쥐고, 계약서가 가리키는 이름으로 시장 재료를 꺼내 엔진을 조립한다.
같은 재료면 같은 엔진을 재사용한다 (ORE CachingPricingEngineBuilder 대응).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import Any

import QuantLib as ql

from quanttool.config import EngineSpec
from quanttool.core.registry import ENGINE_BUILDERS
from quanttool.market.market import Market


class EngineBuilder(ABC):
    def __init__(self, market: Market, spec: EngineSpec) -> None:
        self.market = market
        self.spec = spec
        self._cache: dict[Hashable, ql.PricingEngine] = {}

    def engine(self, trade: Any) -> ql.PricingEngine:
        key = self.cache_key(trade)
        if key not in self._cache:
            self._cache[key] = self.make(trade)
        return self._cache[key]

    @abstractmethod
    def cache_key(self, trade: Any) -> Hashable: ...

    @abstractmethod
    def make(self, trade: Any) -> ql.PricingEngine: ...


@ENGINE_BUILDERS.register("DiscountingBond")
class DiscountingBondEngineBuilder(EngineBuilder):
    def cache_key(self, trade: Any) -> Hashable:
        return trade.discount

    def make(self, trade: Any) -> ql.PricingEngine:
        return ql.DiscountingBondEngine(self.market.yield_curve(trade.discount))
