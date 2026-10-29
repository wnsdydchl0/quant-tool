"""채권 계약서. ORE 대응: OREData/ored/portfolio/bond.hpp/.cpp (BondData, Bond::build).

쿠폰은 LegData(레그 하나)로 적고 LegBuilder가 현금흐름을 만든다. 상품은 QuantLib Bond(현금흐름).
포지션 크기와 방향: 승수 = bond_notional × (지급이면 −1). 지급 여부는 쿠폰 레그의 payer.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import QuantLib as ql
from pydantic import Field

from quanttool.data.configuration.conventions import Calendar, _Strict
from quanttool.data.utilities import parsers
from quanttool.data.utilities.registry import TRADES

from .enginefactory import EngineFactory, MarketContext
from .legdata import LegData, _ql_date
from .trade import Trade, VanillaInstrument


class BondData(_Strict):
    """ORE ``BondData``."""

    issuer_id: str = ""
    credit_curve_id: str = ""  # 신용은 범위 밖 (비워 둔다)
    security_id: str
    reference_curve_id: str  # 할인 기준 커브: market.yield_curve(이 이름)
    income_curve_id: str = ""
    settlement_days: int = Field(ge=0)
    calendar: Calendar
    issue_date: date
    bond_notional: float = 1.0  # 포지션 수량 승수
    coupons: list[LegData] = Field(min_length=1)

    def currency(self) -> str:
        return self.coupons[0].currency

    def is_payer(self) -> bool:
        return self.coupons[0].payer


@TRADES.register("Bond")
class Bond(Trade):
    trade_type: Literal["Bond"] = "Bond"
    bond_data: BondData

    def build(self, engine_factory: EngineFactory) -> None:
        bd = self.bond_data
        builder = engine_factory.builder("Bond")
        configuration = builder.configuration(MarketContext.pricing)
        calendar = parsers.calendar(bd.calendar)
        mult = bd.bond_notional * (-1.0 if bd.is_payer() else 1.0)

        leg: list = []
        for leg_data in bd.coupons:
            leg_builder = engine_factory.leg_builder(leg_data.leg_type)
            leg.extend(leg_builder.build_leg(leg_data, engine_factory, set(), configuration))
        bond = ql.Bond(bd.settlement_days, calendar, _ql_date(bd.issue_date), leg)

        bond.setPricingEngine(
            builder.engine(
                bd.currency(),
                bd.credit_curve_id,
                bd.security_id,
                bd.reference_curve_id,
                bd.income_curve_id,
            )
        )
        self.set_sensitivity_template(builder)
        self._instrument = VanillaInstrument(bond, mult)
        self._legs = [list(bond.cashflows())]
        self._npv_currency = bd.currency()
        last = bond.cashflows()[-1].date()
        self._maturity = date(last.year(), last.month(), last.dayOfMonth())
        self._notional = bond.notional() * bd.bond_notional
