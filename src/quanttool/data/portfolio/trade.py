"""계약서. ORE 대응: OREData/ored/portfolio/trade.hpp, envelope.hpp, instrumentwrapper.hpp.

계약서는 순수 데이터이고 엔진·모델을 모른다. build(factory)에서 QuantLib 상품을 만들고
엔진은 팩토리의 빌더에서 받는다 (docs/architecture.md 원칙 6).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

import QuantLib as ql
from pydantic import BaseModel, ConfigDict, PrivateAttr

if TYPE_CHECKING:
    from .enginefactory import EngineBuilder, EngineFactory


class Envelope(BaseModel):
    """계약 바깥 정보. ORE ``Envelope`` (상대방, 네팅셋, 추가 필드)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    counterparty: str = ""
    netting_set_id: str = ""
    additional_fields: dict[str, str] = {}


class InstrumentWrapper:
    """QuantLib 상품 + 승수. ORE ``InstrumentWrapper``."""

    def __init__(self, instrument: ql.Instrument, multiplier: float = 1.0) -> None:
        self.instrument = instrument
        self.multiplier = multiplier

    def ql_instrument(self) -> ql.Instrument:
        return self.instrument

    def npv(self) -> float:
        return self.instrument.NPV() * self.multiplier


class VanillaInstrument(InstrumentWrapper):
    """ORE ``VanillaInstrument``: 옵션 행사 등 부가 처리 없는 상품."""


class Trade(BaseModel, ABC):
    """ORE ``Trade``. build 후 instrument, legs, npv_currency, notional, maturity가 채워진다."""

    model_config = ConfigDict(extra="forbid")

    id: str
    trade_type: str  # registry 키 = engines.yaml products 키
    envelope: Envelope = Envelope()

    _instrument: InstrumentWrapper | None = PrivateAttr(default=None)
    _legs: list = PrivateAttr(default_factory=list)
    _npv_currency: str = PrivateAttr(default="")
    _notional: float = PrivateAttr(default=0.0)
    _maturity: date | None = PrivateAttr(default=None)
    _sensitivity_template: str = PrivateAttr(default="")

    @abstractmethod
    def build(self, engine_factory: EngineFactory) -> None: ...

    def reset(self) -> None:
        """build 결과를 지운다 (ORE Trade::reset)."""
        self._instrument = None
        self._legs = []

    def is_built(self) -> bool:
        return self._instrument is not None

    def instrument(self) -> InstrumentWrapper:
        if self._instrument is None:
            raise RuntimeError(f"{self.id}: build(factory) 전에 평가할 수 없다")
        return self._instrument

    def legs(self) -> list:
        return self._legs

    def npv_currency(self) -> str:
        return self._npv_currency

    def notional(self) -> float:
        return self._notional

    def maturity(self) -> date | None:
        return self._maturity

    def sensitivity_template(self) -> str:
        """민감도 규칙 템플릿 id. 엔진 파라미터 SensitivityTemplate에서 온다 (ORE)."""
        return self._sensitivity_template

    def set_sensitivity_template(self, builder: EngineBuilder) -> None:
        self._sensitivity_template = str(builder.engine_parameter("SensitivityTemplate", ""))

    def npv(self) -> float:
        return self.instrument().npv()
