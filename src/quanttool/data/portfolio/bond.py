"""채권 계약서. ORE 대응: OREData/ored/portfolio/bond.hpp."""

from __future__ import annotations

from datetime import date
from typing import Literal

import QuantLib as ql

from quanttool.data.marketdata.market import to_ql_date
from quanttool.data.utilities import parsers
from quanttool.data.utilities.registry import TRADES

from .enginefactory import EngineFactory
from .trade import InstrumentWrapper, Trade


@TRADES.register("Bond")
class Bond(Trade):
    """고정금리 채권. 일정·일수 관례는 conventions 이름으로 받는다."""

    trade_type: Literal["Bond"] = "Bond"
    notional: float
    coupon: float  # 소수
    issue_date: date
    maturity_date: date
    conventions: str
    discount: str  # 할인 커브 이름 (Market.yield_curve)

    def build(self, factory: EngineFactory) -> None:
        conv = factory.conventions(self.conventions)
        calendar = parsers.calendar(conv.calendar)
        bdc = parsers.business_day_convention(conv.business_day_convention)
        schedule = ql.Schedule(
            to_ql_date(self.issue_date),
            to_ql_date(self.maturity_date),
            ql.Period(parsers.frequency(conv.frequency)),
            calendar,
            bdc,
            bdc,
            ql.DateGeneration.Backward,
            False,
        )
        bond = ql.FixedRateBond(
            conv.settlement_days,
            100.0,
            schedule,
            [self.coupon],
            parsers.day_counter(conv.day_count),
            parsers.business_day_convention(conv.payment_convention),
            100.0,
            to_ql_date(self.issue_date),
        )
        builder = factory.builder(self.trade_type)
        bond.setPricingEngine(builder.engine(self.discount))
        self._wrapper = InstrumentWrapper(bond, self.notional / 100.0)
