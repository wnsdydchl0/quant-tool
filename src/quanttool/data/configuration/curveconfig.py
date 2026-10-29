"""커브 레시피.

ORE 대응: OREData/ored/configuration/yieldcurveconfig.hpp, curveconfigurations.hpp.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .conventions import _Strict


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
