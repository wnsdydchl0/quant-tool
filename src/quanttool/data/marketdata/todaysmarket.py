"""오늘 시장: 레시피와 시세로 구축한 관측 시장.

ORE 대응: OREData/ored/marketdata/todaysmarket.hpp (+ marketimpl.hpp 보관소).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import QuantLib as ql

from quanttool.data.utilities.registry import BUILDERS

from .dependencygraph import DependencyGraph, Node
from .loader import Loader, QuoteStore
from .market import BuiltCurve, HelperInfo, Market, to_ql_date

if TYPE_CHECKING:
    from quanttool.data.configuration import Config


class TodaysMarket(Market):
    """관측 시장. 레시피와 시세로 구축하고 이름 → Handle 보관소로 내준다."""

    def __init__(self, asof: date, quotes: QuoteStore) -> None:
        self.asof = asof
        self.quotes = quotes
        self._yield_curves: dict[str, ql.RelinkableYieldTermStructureHandle] = {}
        self._built: dict[str, BuiltCurve] = {}

    @classmethod
    def build(cls, asof: date, cfg: Config, loader: Loader) -> TodaysMarket:
        ql.Settings.instance().evaluationDate = to_ql_date(asof)
        snap = cls(asof, QuoteStore(loader.load(asof)))

        recipes = {("YieldCurve", name): cfg.curve_configs[name] for name in cfg.curve_configs}
        builders = {node: BUILDERS[node[0]](cfg) for node in recipes}
        graph = DependencyGraph({n: builders[n].requires(r) for n, r in recipes.items()})
        targets = [("YieldCurve", n) for n in cfg.todaysmarket.yield_curves]
        for node in graph.order(targets):
            built = builders[node].build(recipes[node], snap.quotes, snap)
            snap._register(node, built)
        return snap

    def _register(self, node: Node, built: BuiltCurve) -> None:
        kind, name = node
        if kind != "YieldCurve":
            raise NotImplementedError(kind)
        handle = ql.RelinkableYieldTermStructureHandle()
        handle.linkTo(built.curve)
        self._yield_curves[name] = handle
        self._built[name] = built

    def quote(self, quote_id: str) -> ql.QuoteHandle:
        return self.quotes.handle(quote_id)

    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle:
        try:
            return self._yield_curves[name]
        except KeyError:
            raise KeyError(f"커브 {name!r}가 없다: {sorted(self._yield_curves)}") from None

    def yield_curve_names(self) -> list[str]:
        return list(self._yield_curves)

    def curve_helpers(self, name: str) -> list[HelperInfo]:
        return self._built[name].helpers
