"""오늘 시장: 레시피와 시세로 구축한, 이후 바뀌지 않는 관측 시장.

ORE 대응: OREData/ored/marketdata/todaysmarket.hpp/.cpp (initialise, buildNode).
- configuration마다 TodaysMarketParameters의 매핑(이름 → 커브 지정)을 읽어, 필요한 레시피를
  의존 순서대로 구축한다. 같은 레시피는 한 번만 만들고 여러 이름이 공유한다
  (ORE requiredYieldCurves_).
- 커브 기준일은 asof로 고정한다 (ORE yieldcurve.cpp가 asofDate_를 기준일로 넘김).
- 구축 직후 부트스트랩하고 커브를 얼린다(freeze). ORE preserveQuoteLinkage=false(기본값)와 같다.
  시세 연결을 남기려면 preserve_quote_linkage=True.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING

import QuantLib as ql

from quanttool.data.configuration import MarketObject, parse_curve_spec
from quanttool.data.utilities.registry import BUILDERS

from .dependencygraph import DependencyGraph
from .loader import Loader, QuoteStore
from .market import BuiltCurve, HelperInfo, MarketImpl, YieldCurveType, evaluation_date

if TYPE_CHECKING:
    from quanttool.data.configuration import Config, TodaysMarketParameters, YieldCurveConfig

_CURVE_TYPE = {
    MarketObject.DiscountCurve: YieldCurveType.Discount,
    MarketObject.YieldCurve: YieldCurveType.Yield,
}


class TodaysMarket(MarketImpl):
    def __init__(
        self,
        asof: date,
        params: TodaysMarketParameters,
        loader: Loader,
        curve_configs: Mapping[str, YieldCurveConfig],
        preserve_quote_linkage: bool = False,
    ) -> None:
        super().__init__(asof, QuoteStore(loader.load(asof)))
        self.params = params
        self.preserve_quote_linkage = preserve_quote_linkage
        self._required_yield_curves: dict[str, BuiltCurve] = {}  # 레시피 id → 구축 결과
        self._handles: dict[str, ql.RelinkableYieldTermStructureHandle] = {}

        recipes = {("YieldCurve", cid): rc for cid, rc in curve_configs.items()}
        builders = {node: BUILDERS[node[0]]() for node in recipes}
        graph = DependencyGraph({n: builders[n].requires(r) for n, r in recipes.items()})
        with evaluation_date(asof):  # 헬퍼 결제일 계산이 평가일을 쓰므로 asof에서 구축
            for configuration in params.configurations:
                specs = [parse_curve_spec(s) for s in params.curve_specs(configuration)]
                targets = [("YieldCurve", s.curve_config_id) for s in specs]
                for node in graph.order(targets):
                    self._build_node(node, builders[node], recipes[node])
                self._register(configuration)

    @classmethod
    def from_config(
        cls, asof: date, cfg: Config, loader: Loader, preserve_quote_linkage: bool = False
    ) -> TodaysMarket:
        return cls(asof, cfg.todaysmarket, loader, cfg.curve_configs, preserve_quote_linkage)

    def _build_node(self, node, builder, recipe) -> None:
        cid = node[1]
        if cid in self._required_yield_curves:
            return
        built = builder.build(recipe, self.quotes, self)
        built.curve.discount(1.0)  # 지금(asof) 부트스트랩
        if not self.preserve_quote_linkage:
            built.curve.freeze()
        handle = ql.RelinkableYieldTermStructureHandle()
        handle.linkTo(built.curve)
        self._required_yield_curves[cid] = built
        self._handles[cid] = handle

    def _register(self, configuration: str) -> None:
        """매핑의 이름마다 레시피 커브 Handle을 보관소에 둔다 (ORE buildNode yieldCurves_)."""
        for o, curve_type in _CURVE_TYPE.items():
            for name, spec in self.params.mapping(o, configuration).items():
                handle = self._handles[parse_curve_spec(spec).curve_config_id]
                self._set_yield_curve(curve_type, name, handle, configuration)

    def curve_helpers(self, curve_config_id: str) -> list[HelperInfo]:
        """레시피 id의 부트스트랩 헬퍼 (진단용)."""
        return self._required_yield_curves[curve_config_id].helpers
