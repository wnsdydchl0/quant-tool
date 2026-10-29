"""커브 레시피. ORE 대응: OREData/ored/configuration/yieldcurveconfig.hpp, curveconfigurations.hpp.

ORE와 같이 세그먼트마다 시세 키 목록과 관례 id를 적고, 보간은 변수(Discount/Zero)와 방법으로 나눈다.

세그먼트 종류 (ORE에 없는 QuantTool 확장, 국채 par yield 곡선용):
- ZeroCouponBill: bill bond-equivalent yield → 할인채 가격 헬퍼
- FixedRateBond: par yield = 쿠폰, 가격 100인 가상 채권 헬퍼
ORE는 국채 커브를 개별 채권 가격(FittedBond, Bond 세그먼트)으로 만든다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .conventions import DayCount, _Strict


class YieldCurveSegment(_Strict):
    """ORE ``YieldCurveSegment``: 이 시세들을 이 관례의 헬퍼로."""

    quotes: list[str] = Field(min_length=1)
    conventions: str


class ZeroCouponBillSegment(YieldCurveSegment):
    type: Literal["ZeroCouponBill"]


class FixedRateBondSegment(YieldCurveSegment):
    type: Literal["FixedRateBond"]


Segment = Annotated[ZeroCouponBillSegment | FixedRateBondSegment, Field(discriminator="type")]

_INTERPOLATION = {
    ("Discount", "LogCubic"),
    ("Discount", "LogLinear"),
    ("Zero", "Linear"),
}


class YieldCurveConfig(_Strict):
    """ORE ``YieldCurveConfig``."""

    curve_id: str
    curve_description: str = ""
    currency: str
    discount_curve: str = ""  # 헬퍼 할인에 쓰는 다른 레시피 id (비우면 자기 자신)
    segments: list[Segment] = Field(min_length=1)
    interpolation_variable: Literal["Discount", "Zero"] = "Discount"
    interpolation_method: Literal["LogCubic", "LogLinear", "Linear"] = "LogCubic"
    yield_curve_day_counter: DayCount = "A365F"

    @model_validator(mode="after")
    def _check_interpolation(self) -> YieldCurveConfig:
        pair = (self.interpolation_variable, self.interpolation_method)
        if pair not in _INTERPOLATION:
            raise ValueError(
                f"{self.curve_id}: 지원하지 않는 보간 {pair}: {sorted(_INTERPOLATION)}"
            )
        return self

    def quotes(self) -> list[str]:
        return [q for s in self.segments for q in s.quotes]

    def required_curve_ids(self) -> list[str]:
        """먼저 만들어야 하는 다른 레시피 (의존 그래프 간선). ORE ``requiredCurveIds``."""
        return [self.discount_curve] if self.discount_curve else []
