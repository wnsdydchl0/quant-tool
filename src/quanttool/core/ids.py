"""이름 규칙: 시세 id, 리스크 요인 키, 단위.

모든 시장 입력은 id가 붙은 SimpleQuote이고 (docs/architecture.md 6.4), id 형식은 여기서만 정한다.
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


# 리스크 요인 종류. ORE RiskFactorKey::KeyType의 필요한 부분집합.
RISK_FACTOR_KINDS = frozenset({"zero", "equity_spot", "dividend_yield", "equity_vol"})


@dataclass(frozen=True)
class RiskFactorKey:
    """시나리오 격자점 하나.

    ORE 대응: QuantExt/qle/termstructures/scenario.hpp ``RiskFactorKey(keytype, name, index)``.
    ORE는 격자 인덱스(정수)를 쓰지만, 여기서는 설정 파일·요인 로딩과 바로 맞물리도록
    격자 라벨 튜플을 쓴다. 예: ``("5Y",)``, ``("1Y", 1.0)`` (만기, moneyness).
    """

    kind: str
    name: str
    point: tuple = ()

    def __post_init__(self) -> None:
        if self.kind not in RISK_FACTOR_KINDS:
            raise ValueError(
                f"알 수 없는 리스크 요인 종류 {self.kind!r}: {sorted(RISK_FACTOR_KINDS)}"
            )
        if not isinstance(self.point, tuple):
            object.__setattr__(self, "point", tuple(self.point))

    def __str__(self) -> str:
        return "/".join([self.kind, self.name, *map(str, self.point)])
