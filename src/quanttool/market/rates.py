"""금리 커브 빌더. ORE 대응: OREData/ored/marketdata/yieldcurve.cpp (Simple, FittedBond 구간 등).

시세는 수익률, 헬퍼는 가격을 받는다. 둘을 DerivedQuote로 잇기 때문에 시세 SimpleQuote 값을
바꾸면 헬퍼 → 커브로 변경이 전파된다 (원칙 2).
"""

from __future__ import annotations

import math

import QuantLib as ql

from quanttool.config import YieldCurveConfig, qlmap
from quanttool.config.market import FixedRateBondSegment, RateConventions, ZeroCouponBillSegment
from quanttool.core.registry import BUILDERS

from .market import BuiltCurve, HelperInfo, Market, MarketBuilder
from .quotes import QuoteStore

_HALF_YEAR_DAYS = 182.5


def bill_price(bey: float, days: int) -> float:
    """bond-equivalent yield(Act/365) → 액면 100 bill 가격.

    반년 이하: 단리. 반년 초과: 반기 복리 한 번 + 남은 기간 단리 (재무부 BEY 관례).
    """
    if days <= _HALF_YEAR_DAYS:
        return 100.0 / (1.0 + bey * days / 365.0)
    h = (days - _HALF_YEAR_DAYS) / 365.0
    return 100.0 / ((1.0 + bey / 2.0) * (1.0 + bey * h))


def bill_yield(price: float, days: int) -> float:
    """bill_price의 역함수."""
    if days <= _HALF_YEAR_DAYS:
        return (100.0 / price - 1.0) * 365.0 / days
    h = (days - _HALF_YEAR_DAYS) / 365.0
    # (h/2) y^2 + (1/2 + h) y + (1 - 100/P) = 0. h가 작을 때 상쇄 오차를 피하는 형태로 푼다.
    a, b, c = h / 2.0, 0.5 + h, 1.0 - 100.0 / price
    return -2.0 * c / (b + math.sqrt(b * b - 4 * a * c))


_CURVES = {
    "LogCubic(Discount)": ql.PiecewiseLogCubicDiscount,
    "LogLinear(Discount)": ql.PiecewiseLogLinearDiscount,
    "Linear(Zero)": ql.PiecewiseLinearZero,
}


@BUILDERS.register("YieldCurve")
class YieldCurveBuilder(MarketBuilder):
    kind = "YieldCurve"

    def build(self, recipe: YieldCurveConfig, quotes: QuoteStore, market: Market) -> BuiltCurve:
        conv = self.cfg.conventions[recipe.conventions]
        calendar = qlmap.calendar(conv.calendar)
        today = ql.Settings.instance().evaluationDate
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

        # 기준일이 평가일을 따라 이동 (settlementDays=0 생성자)
        curve = _CURVES[recipe.interpolation](
            0, calendar, [h.helper for h in helpers], ql.Actual365Fixed()
        )
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
        dc = qlmap.day_counter(conv.day_count)
        freq = qlmap.frequency(conv.frequency)
        bdc = qlmap.business_day_convention(conv.business_day_convention)
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
            qlmap.business_day_convention(conv.payment_convention),
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
