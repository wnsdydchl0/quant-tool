"""엔진 팩토리(접수 창구)와 엔진 빌더(기술자). ORE 대응: OREData/ored/portfolio/enginefactory.hpp.

engines.yaml에서 trade_type → 엔진 이름을 찾고, 그 엔진 빌더(시장당 하나, 캐시)에 조립을 맡긴다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import TYPE_CHECKING, Any

import QuantLib as ql

from quanttool.data.configuration import Config, EngineSpec, RateConventions
from quanttool.data.marketdata.market import Market
from quanttool.data.utilities.registry import ENGINE_BUILDERS

if TYPE_CHECKING:
    from .trade import Trade


class EngineBuilder(ABC):
    def __init__(self, market: Market, spec: EngineSpec) -> None:
        self.market = market
        self.spec = spec
        self._cache: dict[Hashable, ql.PricingEngine] = {}

    def engine(self, trade: Any) -> ql.PricingEngine:
        key = self.cache_key(trade)
        if key not in self._cache:
            self._cache[key] = self.make(trade)
        return self._cache[key]

    @abstractmethod
    def cache_key(self, trade: Any) -> Hashable: ...

    @abstractmethod
    def make(self, trade: Any) -> ql.PricingEngine: ...


class EngineFactory:
    def __init__(self, market: Market, cfg: Config) -> None:
        self.market = market
        self.cfg = cfg
        self._builders: dict[str, EngineBuilder] = {}

    def engine_for(self, trade: Trade) -> ql.PricingEngine:
        spec = self.cfg.engine_data[trade.trade_type]
        if spec.engine not in self._builders:
            self._builders[spec.engine] = ENGINE_BUILDERS[spec.engine](self.market, spec)
        return self._builders[spec.engine].engine(trade)

    def conventions(self, name: str) -> RateConventions:
        try:
            return self.cfg.conventions[name]
        except KeyError:
            raise KeyError(f"관례 {name!r}가 없다: {sorted(self.cfg.conventions)}") from None
