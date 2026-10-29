"""오늘 시장: 레시피와 시세로 구축한, 이후 바뀌지 않는 관측 시장.

ORE 대응: OREData/ored/marketdata/todaysmarket.hpp.
- 커브 기준일은 asof로 고정한다 (ORE yieldcurve.cpp가 asofDate_를 기준일로 넘김).
- 구축 직후 부트스트랩하고 커브를 얼린다(freeze). 그래서 이후 평가일이나 시세가 바뀌어도
  커브가 변하지 않는다. ORE TodaysMarket의 preserveQuoteLinkage=false(기본값)와 같은 시맨틱이다.
  흔들기는 SimMarket의 몫이다. 시세 연결을 남기려면 preserve_quote_linkage=True.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING

import QuantLib as ql

from quanttool.data.utilities.registry import BUILDERS

from .dependencygraph import DependencyGraph, Node
from .loader import Loader, QuoteStore
from .market import BuiltCurve, HelperInfo, MarketImpl, evaluation_date

if TYPE_CHECKING:
    from quanttool.data.configuration import (
        Config,
        RateConventions,
        TodaysMarketParameters,
        YieldCurveConfig,
    )


class TodaysMarket(MarketImpl):
    def __init__(
        self,
        asof: date,
        params: TodaysMarketParameters,
        loader: Loader,
        curve_configs: Mapping[str, YieldCurveConfig],
        conventions: Mapping[str, RateConventions],
        preserve_quote_linkage: bool = False,
    ) -> None:
        super().__init__(asof, QuoteStore(loader.load(asof)))
        self.preserve_quote_linkage = preserve_quote_linkage
        self._built: dict[str, BuiltCurve] = {}

        recipes = {("YieldCurve", name): cfg for name, cfg in curve_configs.items()}
        builders = {node: BUILDERS[node[0]](conventions) for node in recipes}
        graph = DependencyGraph({n: builders[n].requires(r) for n, r in recipes.items()})
        targets = [("YieldCurve", n) for n in params.yield_curves]
        with evaluation_date(asof):  # 헬퍼 결제일 계산이 평가일을 쓰므로 asof에서 구축
            for node in graph.order(targets):
                built = builders[node].build(recipes[node], self.quotes, self)
                built.curve.discount(1.0)  # 지금(asof) 부트스트랩
                if not preserve_quote_linkage:
                    built.curve.freeze()
                self._register(node, built)

    @classmethod
    def from_config(
        cls, asof: date, cfg: Config, loader: Loader, preserve_quote_linkage: bool = False
    ) -> TodaysMarket:
        return cls(
            asof,
            cfg.todaysmarket,
            loader,
            cfg.curve_configs,
            cfg.conventions,
            preserve_quote_linkage,
        )

    def _register(self, node: Node, built: BuiltCurve) -> None:
        kind, name = node
        if kind != "YieldCurve":
            raise NotImplementedError(kind)
        handle = ql.RelinkableYieldTermStructureHandle()
        handle.linkTo(built.curve)
        self._set_yield_curve(name, handle)
        self._built[name] = built

    def curve_helpers(self, name: str) -> list[HelperInfo]:
        return self._built[name].helpers
