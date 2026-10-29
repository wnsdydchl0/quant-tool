"""유형 이름 → 클래스 등록부. ORE의 등록용 클래스 계층을 딕셔너리 + 데코레이터로 대체한다."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Registry:
    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, Any] = {}

    def register(self, key: str) -> Callable[[Any], Any]:
        def deco(obj: Any) -> Any:
            if key in self._items:
                raise KeyError(f"{self.name}: {key!r}가 이미 등록되어 있다")
            self._items[key] = obj
            return obj

        return deco

    def __getitem__(self, key: str) -> Any:
        try:
            return self._items[key]
        except KeyError:
            raise KeyError(
                f"{self.name}: {key!r} 미등록. 등록된 키: {sorted(self._items)}"
            ) from None

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def keys(self) -> list[str]:
        return sorted(self._items)


BUILDERS = Registry("market builders")  # 시장 객체 유형 → MarketBuilder
TRADES = Registry("trades")  # trade_type → Trade
ENGINE_BUILDERS = Registry("engine builders")  # 엔진 이름 → EngineBuilder
