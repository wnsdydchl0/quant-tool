"""시장 레시피 설정 (ORE configuration/ 대응: CurveConfig, Conventions, TodaysMarketParameters)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from . import qlmap

Calendar = Annotated[str, AfterValidator(lambda v: qlmap.check("calendar", v))]
DayCount = Annotated[str, AfterValidator(lambda v: qlmap.check("day count", v))]
Frequency = Annotated[str, AfterValidator(lambda v: qlmap.check("frequency", v))]
Bdc = Annotated[str, AfterValidator(lambda v: qlmap.check("business day convention", v))]


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


class _Segment(_Strict):
    quote_family: str
    quote_field: str
    tenors: list[str] = Field(min_length=1)

    def quote_ids(self) -> list[str]:
        return [f"{self.quote_family}/{self.quote_field}/{t}" for t in self.tenors]


class ZeroCouponBillSegment(_Segment):
    """bill bond-equivalent yield → 할인채 가격 헬퍼."""

    type: Literal["ZeroCouponBill"]


class FixedRateBondSegment(_Segment):
    """par yield = 쿠폰인 가상 채권, 시세 수익률 → 가격 헬퍼."""

    type: Literal["FixedRateBond"]


Segment = Annotated[ZeroCouponBillSegment | FixedRateBondSegment, Field(discriminator="type")]


class YieldCurveConfig(_Strict):
    name: str
    type: Literal["YieldCurve"]
    currency: str
    conventions: str
    segments: list[Segment] = Field(min_length=1)
    interpolation: Literal["LogCubic(Discount)", "LogLinear(Discount)", "Linear(Zero)"]

    def quote_ids(self) -> list[str]:
        return [q for s in self.segments for q in s.quote_ids()]


class TodaysMarketConfig(_Strict):
    """Snapshot.build가 구축할 대상."""

    yield_curves: list[str] = []
