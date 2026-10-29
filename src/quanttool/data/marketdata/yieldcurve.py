"""금리 커브 빌더. ORE 대응: OREData/ored/marketdata/yieldcurve.cpp (Simple, FittedBond 구간 등).

시세는 수익률, 헬퍼는 가격을 받는다. 둘을 DerivedQuote로 잇기 때문에 시세 SimpleQuote 값을
바꾸면 헬퍼 → 커브로 변경이 전파된다 (원칙 2).
"""

from __future__ import annotations

import QuantLib as ql

from quanttool.data.configuration import RateConventions, YieldCurveConfig
from quanttool.data.configuration.curveconfig import FixedRateBondSegment, ZeroCouponBillSegment
from quanttool.data.utilities import parsers
from quanttool.data.utilities.registry import BUILDERS
from quanttool.qle.termstructures import bill_price, bill_yield

from .loader import QuoteStore
from .market import BuiltCurve, HelperInfo, Market, MarketBuilder, to_ql_date

_CURVES = {
    "LogCubic(Discount)": ql.PiecewiseLogCubicDiscount,
    "LogLinear(Discount)": ql.PiecewiseLogLinearDiscount,
    "Linear(Zero)": ql.PiecewiseLinearZero,
}


@BUILDERS.register("YieldCurve")
class YieldCurveBuilder(MarketBuilder):
    kind = "YieldCurve"

    def build(self, recipe: YieldCurveConfig, quotes: QuoteStore, market: Market) -> BuiltCurve:
        conv = self.conventions[recipe.conventions]
        calendar = parsers.calendar(conv.calendar)
        today = to_ql_date(market.asof)
        settle = calendar.advance(today, conv.settlement_days, ql.Days)

        helpers: list[HelperInfo] = []
        for seg in recipe.segments:
            for quote_id, tenor in zip(seg.quote_ids(), seg.tenors, strict=True):
                ytm = quotes.handle(quote_id)
                nominal = settle + ql.Period(tenor)
                if isinstance(seg, ZeroCouponBillSegment):
                    maturity = calendar.adjust(nominal, ql.Following)
                    info = self._bill(quote_id, ytm, settle, maturity, calendar, conv)
                elif isinstance(seg, FixedRateBondSegment):
                    # 정규 일정이 되도록 명목 만기를 쓴다 (par yield에서 가격이 정확히 100)
                    info = self._bond(quote_id, ytm, settle, nominal, calendar, conv)
                else:  # pragma: no cover - pydantic이 막는다
                    raise TypeError(type(seg))
                helpers.append(info)
        helpers.sort(key=lambda h: h.maturity)

        # 기준일 = asof 고정 (ORE TodaysMarket과 같음). 시간 이동은 SimMarket이 맡는다.
        rate_helpers = [h.helper for h in helpers]
        curve = _CURVES[recipe.interpolation](today, rate_helpers, ql.Actual365Fixed())
        curve.enableExtrapolation()
        return BuiltCurve(curve, helpers)

    @staticmethod
    def _bill(quote_id, ytm, settle, maturity, calendar, conv: RateConventions) -> HelperInfo:
        days = maturity - settle
        bond = ql.ZeroCouponBond(
            conv.settlement_days, calendar, 100.0, maturity, ql.Following, 100.0, settle
        )
        price = ql.DerivedQuote(ytm, lambda y: bill_price(y, days))
        helper = ql.BondHelper(ql.QuoteHandle(price), bond)
        return HelperInfo(quote_id, helper, maturity, lambda p: bill_yield(p, days))

    @staticmethod
    def _bond(quote_id, ytm, settle, maturity, calendar, conv: RateConventions) -> HelperInfo:
        dc = parsers.day_counter(conv.day_count)
        freq = parsers.frequency(conv.frequency)
        bdc = parsers.business_day_convention(conv.business_day_convention)
        schedule = ql.Schedule(
            settle,
            maturity,
            ql.Period(freq),
            calendar,
            bdc,
            bdc,
            ql.DateGeneration.Backward,
            False,
        )
        # 쿠폰은 구축 시점 par yield로 고정하고, 이후 수익률 변화는 가격으로 전달한다.
        coupon = ytm.value()
        bond = ql.FixedRateBond(
            conv.settlement_days,
            100.0,
            schedule,
            [coupon],
            dc,
            parsers.business_day_convention(conv.payment_convention),
            100.0,
            settle,
        )

        def price(y: float) -> float:
            return bond.cleanPrice(y, dc, ql.Compounded, freq, settle)

        def to_yield(p: float) -> float:
            bp = ql.BondPrice(p, ql.BondPrice.Clean)
            return bond.bondYield(bp, dc, ql.Compounded, freq, settle, 1e-12, 200)

        helper = ql.BondHelper(ql.QuoteHandle(ql.DerivedQuote(ytm, price)), bond)
        return HelperInfo(quote_id, helper, maturity, to_yield)
