"""계약서. ORE 대응: OREData/ored/portfolio/trade.hpp, instrumentwrapper.hpp.

계약서는 순수 데이터이고 엔진·모델을 모른다. build(factory)에서 QuantLib 상품을 만들고
엔진은 팩토리에서 받는다 (docs/architecture.md 원칙 6).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import QuantLib as ql
from pydantic import BaseModel, ConfigDict, PrivateAttr

if TYPE_CHECKING:
    from .factory import EngineFactory


@dataclass
class InstrumentWrapper:
    """QuantLib 상품 + 승수 (액면/100 같은 포지션 크기)."""

    instrument: ql.Instrument
    multiplier: float = 1.0

    def npv(self) -> float:
        return self.instrument.NPV() * self.multiplier


class Trade(BaseModel, ABC):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str  # registry 키 = engines.yaml 키

    _wrapper: InstrumentWrapper | None = PrivateAttr(default=None)

    @property
    def trade_type(self) -> str:
        return self.type

    @abstractmethod
    def build(self, factory: EngineFactory) -> None: ...

    @property
    def instrument(self) -> InstrumentWrapper:
        if self._wrapper is None:
            raise RuntimeError(f"{self.id}: build(factory) 전에 평가할 수 없다")
        return self._wrapper

    def npv(self) -> float:
        return self.instrument.npv()
