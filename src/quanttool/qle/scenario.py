"""리스크 요인 키와 시나리오. ORE 대응: QuantExt/qle/termstructures/scenario.hpp.

- RiskFactorKey(key_type, name, index): 시뮬레이션 시장의 격자점 하나. index는 격자 안 위치(정수).
  커브면 tenor 번호, vol 서페이스면 (만기 × 행사가)를 펼친 번호다.
- Scenario: 격자점 → 값. is_absolute()가 False면 값은 기준 대비 상대값(spreaded 모드: 할인계수
  비율).
- DeltaScenario: 기준 시나리오 + 바뀐 점만 들고 있는 시나리오 (ORE orea/scenario/deltascenario.hpp).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class KeyType(StrEnum):
    """ORE ``RiskFactorKey::KeyType``의 필요한 부분."""

    DiscountCurve = "DiscountCurve"
    YieldCurve = "YieldCurve"
    IndexCurve = "IndexCurve"
    EquitySpot = "EquitySpot"
    DividendYield = "DividendYield"
    EquityVolatility = "EquityVolatility"


@dataclass(frozen=True, order=True)
class RiskFactorKey:
    key_type: KeyType
    name: str
    index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_type", KeyType(self.key_type))

    def __str__(self) -> str:
        return f"{self.key_type}/{self.name}/{self.index}"


class Scenario(ABC):
    """ORE ``Scenario``."""

    @abstractmethod
    def asof(self) -> date: ...

    @abstractmethod
    def label(self) -> str: ...

    @abstractmethod
    def keys(self) -> list[RiskFactorKey]: ...

    @abstractmethod
    def has(self, key: RiskFactorKey) -> bool: ...

    @abstractmethod
    def get(self, key: RiskFactorKey) -> float: ...

    @abstractmethod
    def add(self, key: RiskFactorKey, value: float) -> None: ...

    @abstractmethod
    def is_absolute(self) -> bool: ...

    @abstractmethod
    def clone(self) -> Scenario: ...

    def values(self) -> dict[RiskFactorKey, float]:
        return {k: self.get(k) for k in self.keys()}


class SimpleScenario(Scenario):
    """dict 기반 시나리오. ORE ``SimpleScenario``."""

    def __init__(
        self,
        asof: date,
        label: str = "",
        values: dict[RiskFactorKey, float] | None = None,
        absolute: bool = True,
    ) -> None:
        self._asof = asof
        self._label = label
        self._values = dict(values or {})
        self._absolute = absolute

    def asof(self) -> date:
        return self._asof

    def set_asof(self, d: date) -> None:
        self._asof = d

    def label(self) -> str:
        return self._label

    def set_label(self, label: str) -> None:
        self._label = label

    def keys(self) -> list[RiskFactorKey]:
        return list(self._values)

    def has(self, key: RiskFactorKey) -> bool:
        return key in self._values

    def get(self, key: RiskFactorKey) -> float:
        try:
            return self._values[key]
        except KeyError:
            raise KeyError(f"시나리오 {self._label!r}에 {key}가 없다") from None

    def add(self, key: RiskFactorKey, value: float) -> None:
        self._values[key] = value

    def is_absolute(self) -> bool:
        return self._absolute

    def set_absolute(self, b: bool) -> None:
        self._absolute = b

    def clone(self) -> SimpleScenario:
        return SimpleScenario(self._asof, self._label, self._values, self._absolute)


class DeltaScenario(Scenario):
    """기준 시나리오 + 바뀐 점. 바뀌지 않은 점은 기준 값을 돌려준다. ORE ``DeltaScenario``."""

    def __init__(
        self, base: Scenario, delta: dict[RiskFactorKey, float] | None = None, label: str = ""
    ) -> None:
        self._base = base
        self._delta = dict(delta or {})
        self._label = label
        for k in self._delta:
            if not base.has(k):
                raise KeyError(f"기준 시나리오에 없는 리스크 요인 {k}")

    def asof(self) -> date:
        return self._base.asof()

    def label(self) -> str:
        return self._label

    def keys(self) -> list[RiskFactorKey]:
        return self._base.keys()

    def has(self, key: RiskFactorKey) -> bool:
        return self._base.has(key)

    def get(self, key: RiskFactorKey) -> float:
        return self._delta[key] if key in self._delta else self._base.get(key)

    def add(self, key: RiskFactorKey, value: float) -> None:
        if not self._base.has(key):
            raise KeyError(f"기준 시나리오에 없는 리스크 요인 {key}")
        self._delta[key] = value

    def is_absolute(self) -> bool:
        return self._base.is_absolute()

    def delta(self) -> dict[RiskFactorKey, float]:
        """기준과 다른 점만."""
        return dict(self._delta)

    def clone(self) -> DeltaScenario:
        return DeltaScenario(self._base, self._delta, self._label)
