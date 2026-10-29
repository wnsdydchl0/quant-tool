"""이름 규칙: 시세 id, 단위.

모든 시장 입력은 id가 붙은 SimpleQuote이고 (docs/architecture.md 1.7 불변 조건),
id 형식은 여기서만 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Unit(Enum):
    DECIMAL = "decimal"  # 0.0425 = 4.25%
    BP = "bp"  # 1 = 0.0001
    PRICE = "price"  # 액면 100 기준 가격


def bp_to_decimal(bp: float) -> float:
    return bp * 1e-4


# 시세 필드 → 단위. 새 필드는 여기에 등록해야 QuoteId로 만들 수 있다.
FIELD_UNITS: dict[str, Unit] = {
    "PAR": Unit.DECIMAL,  # par yield
    "YLD": Unit.DECIMAL,  # 만기수익률
    "ZERO": Unit.DECIMAL,  # 제로금리
    "PX": Unit.PRICE,
}


@dataclass(frozen=True)
class QuoteId:
    """시세 id ``{family}/{field}/{point}`` (예: ``UST/PAR/2Y``)."""

    family: str
    field: str
    point: str

    def __post_init__(self) -> None:
        if self.field not in FIELD_UNITS:
            raise ValueError(f"알 수 없는 시세 필드 {self.field!r}: {sorted(FIELD_UNITS)}")
        for part in (self.family, self.point):
            if not part or "/" in part:
                raise ValueError(f"잘못된 시세 id 구성 요소 {part!r}")

    @classmethod
    def parse(cls, text: str) -> QuoteId:
        parts = text.split("/")
        if len(parts) != 3:
            raise ValueError(f"시세 id는 'family/field/point' 형식이어야 한다: {text!r}")
        return cls(*parts)

    @property
    def unit(self) -> Unit:
        return FIELD_UNITS[self.field]

    def __str__(self) -> str:
        return f"{self.family}/{self.field}/{self.point}"
