"""레그 데이터. ORE 대응: OREData/ored/portfolio/legdata.hpp, schedule.hpp.

레그 = 공통 필드(통화, 지급/수취, 원금, 일수, 지급 관례, 일정) + 종류별 내용.
종류별 내용은 ``fixed_leg_data``처럼 종류 이름의 필드에 둔다(ORE: LegData 안의 FixedLegData 노드).
QuantLib 현금흐름(Leg)으로 바꾸는 일은 LegBuilder가 한다(legbuilders.py).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import QuantLib as ql
from pydantic import Field, model_validator

from quanttool.data.configuration.conventions import Bdc, Calendar, DayCount, _Strict
from quanttool.data.utilities import parsers


def _ql_date(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


class ScheduleRules(_Strict):
    """ORE ``ScheduleRules``: 시작·끝·주기·달력·관례·생성 규칙."""

    start_date: date
    end_date: date
    tenor: str
    calendar: Calendar
    convention: Bdc = "Unadjusted"
    term_convention: Bdc = "Unadjusted"
    rule: Literal["Backward", "Forward", "Zero"] = "Backward"
    end_of_month: bool = False

    def schedule(self) -> ql.Schedule:
        return ql.Schedule(
            _ql_date(self.start_date),
            _ql_date(self.end_date),
            ql.Period(self.tenor),
            parsers.calendar(self.calendar),
            parsers.business_day_convention(self.convention),
            parsers.business_day_convention(self.term_convention),
            parsers.date_generation(self.rule),
            self.end_of_month,
        )


class ScheduleData(_Strict):
    """ORE ``ScheduleData``. 지금은 규칙 하나만 지원한다."""

    rules: list[ScheduleRules] = Field(min_length=1, max_length=1)


def make_schedule(data: ScheduleData) -> ql.Schedule:
    """ORE ``makeSchedule``."""
    return data.rules[0].schedule()


class FixedLegData(_Strict):
    """ORE ``FixedLegData``: 쿠폰률 (기간별이면 여러 개)."""

    rates: list[float] = Field(min_length=1)


class LegData(_Strict):
    """ORE ``LegData``."""

    leg_type: Literal["Fixed"]
    payer: bool
    currency: str
    notionals: list[float] = Field(min_length=1)
    day_counter: DayCount
    payment_convention: Bdc = "Following"
    schedule_data: ScheduleData
    fixed_leg_data: FixedLegData | None = None

    @model_validator(mode="after")
    def _check_concrete(self) -> LegData:
        if self.concrete_leg_data() is None:
            raise ValueError(
                f"leg_type {self.leg_type}에는 {self.leg_type.lower()}_leg_data가 필요하다"
            )
        return self

    def concrete_leg_data(self):
        return {"Fixed": self.fixed_leg_data}[self.leg_type]


def make_fixed_leg(data: LegData) -> ql.Leg:
    """ORE ``makeFixedLeg``: 원금·쿠폰률·일수로 고정 쿠폰 목록."""
    fixed = data.fixed_leg_data
    return ql.FixedRateLeg(
        make_schedule(data.schedule_data),
        parsers.day_counter(data.day_counter),
        data.notionals,
        fixed.rates,
        parsers.business_day_convention(data.payment_convention),
    )
