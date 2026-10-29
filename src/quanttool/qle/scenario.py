"""리스크 요인 키. ORE 대응: QuantExt/qle/termstructures/scenario.hpp ``RiskFactorKey``."""

from __future__ import annotations

from dataclasses import dataclass

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
