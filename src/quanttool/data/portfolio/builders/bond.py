"""채권 엔진 빌더. ORE 대응: OREData/ored/portfolio/builders/bond.hpp.

같은 할인 커브를 쓰는 채권은 엔진 하나를 공유한다 (ORE CachingPricingEngineBuilder 대응).
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import QuantLib as ql

from quanttool.data.portfolio.enginefactory import EngineBuilder
from quanttool.data.utilities.registry import ENGINE_BUILDERS


@ENGINE_BUILDERS.register("DiscountingBondEngine")
class DiscountingBondEngineBuilder(EngineBuilder):
    def cache_key(self, trade: Any) -> Hashable:
        return trade.discount

    def make(self, trade: Any) -> ql.PricingEngine:
        return ql.DiscountingBondEngine(self.market.yield_curve(trade.discount))
