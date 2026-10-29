"""채권 엔진 빌더. ORE 대응: OREData/ored/portfolio/builders/bond.hpp.

키 = 통화 + 신용 커브 + 증권 id + 기준 커브 + income 커브 (ORE BondEngineBuilder::keyImpl).
기준 커브는 market.yield_curve(reference_curve_id)로 받는다.
ORE의 DiscountingRiskyBondEngine은 신용 커브·증권 스프레드가 있으면 위험 할인을 하지만,
이 프로젝트는 신용을 범위에서 뺐으므로, 둘이 비어 있을 때와 같은
QuantLib DiscountingBondEngine을 쓴다.
"""

from __future__ import annotations

import QuantLib as ql

from quanttool.data.portfolio.enginefactory import (
    CachingPricingEngineBuilder,
    MarketContext,
    register_engine_builder,
)


class BondEngineBuilder(CachingPricingEngineBuilder):
    trade_types = frozenset({"Bond"})

    def key_impl(self, ccy, credit_curve_id, security_id, reference_curve_id, income_curve_id=""):
        return "_".join([ccy, credit_curve_id, security_id, reference_curve_id, income_curve_id])


@register_engine_builder
class BondDiscountingEngineBuilder(BondEngineBuilder):
    model = "DiscountedCashflows"
    engine_name = "DiscountingRiskyBondEngine"

    def engine_impl(
        self, ccy, credit_curve_id, security_id, reference_curve_id, income_curve_id=""
    ) -> ql.PricingEngine:
        if credit_curve_id:
            raise NotImplementedError("신용 커브는 범위 밖이다 (docs/architecture.md 2.1)")
        yts = self.market.yield_curve(reference_curve_id, self.configuration(MarketContext.pricing))
        return ql.DiscountingBondEngine(yts)
