"""엔진 팩토리(접수 창구)와 엔진 빌더(기술자). ORE 대응: OREData/ored/portfolio/enginefactory.hpp.

- 엔진 빌더는 (model, engine, trade_types)로 등록된다.
- EngineFactory(engine_data, market, configurations)는 builder(trade_type)에서 engines.yaml이 고른
  (model, engine)의 빌더를 찾아 시장·configuration·파라미터를 넣어(init) 돌려준다. 상품 유형당 하나.
- 계약서는 자기 키로 builder.engine(...)을 부른다. CachingPricingEngineBuilder는 key_impl(키)이
  같으면 engine_impl로 만든 엔진을 재사용한다.
  ORE Bond::build도 builder("Bond") → engine(ccy, …) 순서다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

import QuantLib as ql

from quanttool.data.configuration import DEFAULT_CONFIGURATION, EngineData
from quanttool.data.marketdata.market import Market
from quanttool.data.utilities.registry import ENGINE_BUILDERS, LEG_BUILDERS

if TYPE_CHECKING:
    from quanttool.data.configuration import Config

    from .legbuilders import LegBuilder


class MarketContext(StrEnum):
    """빌더가 시장의 어느 configuration을 쓸지 고르는 용도. ORE ``MarketContext``."""

    irCalibration = "irCalibration"
    fxCalibration = "fxCalibration"
    eqCalibration = "eqCalibration"
    pricing = "pricing"


class EngineBuilder(ABC):
    """ORE ``EngineBuilder``. 하위 클래스는 model, engine_name, trade_types를 정한다.

    ORE는 이름 조회 ``engine()``과 엔진 생성 ``engine(args…)``를 오버로드로 함께 쓰지만, 파이썬은
    오버로드가 없어 이름을 ``engine_name``으로 둔다.
    """

    model: ClassVar[str]
    engine_name: ClassVar[str]
    trade_types: ClassVar[frozenset[str]]

    def __init__(self) -> None:
        self.market: Market | None = None
        self.configurations: dict[MarketContext, str] = {}
        self.model_parameters: dict[str, Any] = {}
        self.engine_parameters: dict[str, Any] = {}
        self.global_parameters: dict[str, Any] = {}

    def init(
        self,
        market: Market,
        configurations: dict[MarketContext, str],
        model_parameters: dict[str, Any],
        engine_parameters: dict[str, Any],
        global_parameters: dict[str, Any],
    ) -> None:
        self.market = market
        self.configurations = configurations
        self.model_parameters = model_parameters
        self.engine_parameters = engine_parameters
        self.global_parameters = global_parameters

    def configuration(self, key: MarketContext) -> str:
        return self.configurations.get(key, DEFAULT_CONFIGURATION)

    def engine_parameter(self, name: str, default: Any = None) -> Any:
        return self.engine_parameters.get(name, default)

    def model_parameter(self, name: str, default: Any = None) -> Any:
        return self.model_parameters.get(name, default)


class CachingPricingEngineBuilder(EngineBuilder):
    """같은 키면 같은 엔진. ORE ``CachingPricingEngineBuilder<Key, Args...>``."""

    def __init__(self) -> None:
        super().__init__()
        self._engines: dict[Any, ql.PricingEngine] = {}

    def engine(self, *args: Any) -> ql.PricingEngine:  # type: ignore[override]
        key = self.key_impl(*args)
        if key not in self._engines:
            self._engines[key] = self.engine_impl(*args)
        return self._engines[key]

    @abstractmethod
    def key_impl(self, *args: Any) -> Any: ...

    @abstractmethod
    def engine_impl(self, *args: Any) -> ql.PricingEngine: ...


def register_engine_builder(cls: type[EngineBuilder]) -> type[EngineBuilder]:
    """ENGINE_BUILDERS에 "model/engine" 키로 등록하는 데코레이터."""
    return ENGINE_BUILDERS.register(f"{cls.model}/{cls.engine_name}")(cls)


class EngineFactory:
    """ORE ``EngineFactory(data, market, configurations)``."""

    def __init__(
        self,
        engine_data: EngineData,
        market: Market,
        configurations: dict[MarketContext, str] | None = None,
    ) -> None:
        self.engine_data = engine_data
        self._market = market
        self.configurations = dict(configurations or {})
        self._builders: dict[str, EngineBuilder] = {}
        self._leg_builders: dict[str, LegBuilder] = {}

    @classmethod
    def from_config(
        cls,
        cfg: Config,
        market: Market,
        configurations: dict[MarketContext, str] | None = None,
    ) -> EngineFactory:
        return cls(cfg.engine_data, market, configurations)

    def market(self) -> Market:
        return self._market

    def builder(self, trade_type: str) -> EngineBuilder:
        if trade_type not in self._builders:
            ed = self.engine_data
            model, engine = ed.model(trade_type), ed.engine(trade_type)
            key = f"{model}/{engine}"
            if key not in ENGINE_BUILDERS:
                raise KeyError(
                    f"engines.yaml의 {trade_type}: {key}에 맞는 엔진 빌더가 없다: "
                    f"{ENGINE_BUILDERS.keys()}"
                )
            builder_cls = ENGINE_BUILDERS[key]
            if trade_type not in builder_cls.trade_types:
                raise KeyError(
                    f"{key} 빌더는 {sorted(builder_cls.trade_types)}용이라 "
                    f"{trade_type}에 맞지 않는다"
                )
            b = builder_cls()
            b.init(
                self._market,
                self.configurations,
                ed.model_parameters(trade_type),
                ed.engine_parameters(trade_type),
                dict(ed.global_parameters),
            )
            self._builders[trade_type] = b
        return self._builders[trade_type]

    def leg_builder(self, leg_type: str) -> LegBuilder:
        if leg_type not in self._leg_builders:
            self._leg_builders[leg_type] = LEG_BUILDERS[leg_type]()
        return self._leg_builders[leg_type]
