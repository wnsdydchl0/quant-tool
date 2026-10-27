"""엔진 팩토리 (접수 창구). ORE 대응: OREData/ored/portfolio/enginefactory.hpp.

engines.yaml에서 trade_type → 엔진 이름을 찾고, 그 엔진 빌더(시장당 하나, 캐시)에 조립을 맡긴다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import QuantLib as ql

from quanttool.config import Config, RateConventions
from quanttool.core.registry import ENGINE_BUILDERS
from quanttool.market.market import Market

if TYPE_CHECKING:
    from .engines import EngineBuilder
    from .trades import Trade


class EngineFactory:
    def __init__(self, market: Market, cfg: Config) -> None:
        self.market = market
        self.cfg = cfg
        self._builders: dict[str, EngineBuilder] = {}

    def engine_for(self, trade: Trade) -> ql.PricingEngine:
        spec = self.cfg.pricing[trade.trade_type]
        if spec.engine not in self._builders:
            self._builders[spec.engine] = ENGINE_BUILDERS[spec.engine](self.market, spec)
        return self._builders[spec.engine].engine(trade)

    def conventions(self, name: str) -> RateConventions:
        try:
            return self.cfg.conventions[name]
        except KeyError:
            raise KeyError(f"관례 {name!r}가 없다: {sorted(self.cfg.conventions)}") from None
