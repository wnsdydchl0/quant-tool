"""관례. ORE 대응: OREData/ored/configuration/conventions.hpp.

ORE와 같이 관례 사전(Conventions)을 전역 InstrumentConventions에 등록하고, 커브·상품 빌더가
id로 꺼낸다. 등록은 설정을 읽을 때 한다(load_config; ORE는 InputParameters가 setConventions).
"""

from __future__ import annotations

from collections.abc import Mapping
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


class Conventions:
    """관례 사전. ORE 대응: conventions.hpp ``Conventions``."""

    def __init__(self, items: Mapping[str, RateConventions] | None = None) -> None:
        self._items = dict(items or {})

    def get(self, id: str) -> RateConventions:
        try:
            return self._items[id]
        except KeyError:
            raise KeyError(f"관례 {id!r}가 없다: {sorted(self._items)}") from None

    def has(self, id: str) -> bool:
        return id in self._items

    def ids(self) -> list[str]:
        return list(self._items)


class InstrumentConventions:
    """전역 관례 등록부(싱글턴). ORE 대응: conventions.hpp ``InstrumentConventions``."""

    _instance: InstrumentConventions | None = None

    def __init__(self) -> None:
        self._conventions = Conventions()

    @classmethod
    def instance(cls) -> InstrumentConventions:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_conventions(self, conventions: Conventions) -> None:
        self._conventions = conventions

    def conventions(self) -> Conventions:
        return self._conventions
