"""관례. ORE 대응: OREData/ored/configuration/conventions.hpp.

ORE는 관례를 전역 InstrumentConventions에 등록하지만, 여기서는 설정 객체로 전달한다.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from quanttool.data.utilities import parsers

Calendar = Annotated[str, AfterValidator(lambda v: parsers.check("calendar", v))]
DayCount = Annotated[str, AfterValidator(lambda v: parsers.check("day count", v))]
Frequency = Annotated[str, AfterValidator(lambda v: parsers.check("frequency", v))]
Bdc = Annotated[str, AfterValidator(lambda v: parsers.check("business day convention", v))]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RateConventions(_Strict):
    calendar: Calendar
    day_count: DayCount
    bill_day_count: DayCount = "Actual365Fixed"
    settlement_days: int = Field(ge=0)
    frequency: Frequency
    business_day_convention: Bdc = "Unadjusted"
    payment_convention: Bdc = "Following"
