"""시장 규격과 관측 시장.

ORE 대응: OREData/ored/marketdata/market.hpp, marketimpl.hpp, todaysmarket.hpp.

가격결정·시나리오 코드는 Market 규격 메소드만 쓴다 (docs/architecture.md 6.4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import QuantLib as ql

from quanttool.core.dependency import DependencyGraph, Node
from quanttool.core.registry import BUILDERS

from .quotes import Loader, QuoteStore

if TYPE_CHECKING:
    from quanttool.config import Config


def to_ql_date(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


@contextmanager
def evaluation_date(d: date) -> Iterator[None]:
    """전역 Settings.evaluationDate를 d로 두고, 끝나면 이전 값으로 되돌린다."""
    settings = ql.Settings.instance()
    previous = settings.evaluationDate
    settings.evaluationDate = to_ql_date(d)
    try:
        yield
    finally:
        settings.evaluationDate = previous


class Market(ABC):
    """시장 규격 (메뉴판). Snapshot과 ScenarioMarket이 구현한다."""

    asof: date

    @abstractmethod
    def quote(self, quote_id: str) -> ql.QuoteHandle: ...

    @abstractmethod
    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle: ...

    def index(self, name: str) -> ql.Index:
        raise NotImplementedError(f"{type(self).__name__}: index 미지원")

    def equity_spot(self, name: str) -> ql.QuoteHandle:
        raise NotImplementedError(f"{type(self).__name__}: equity_spot 미지원")

    def dividend_curve(self, name: str) -> ql.YieldTermStructureHandle:
        raise NotImplementedError(f"{type(self).__name__}: dividend_curve 미지원")

    def equity_vol(self, name: str) -> ql.BlackVolTermStructureHandle:
        raise NotImplementedError(f"{type(self).__name__}: equity_vol 미지원")

    def active(self):
        """이 시장의 기준일로 evaluationDate를 둔 컨텍스트. 날짜가 다른 시장은 순차 평가."""
        return evaluation_date(self.asof)


@dataclass
class HelperInfo:
    """부트스트랩 헬퍼 하나와 진단용 정보."""

    quote_id: str
    helper: ql.RateHelper
    maturity: ql.Date
    to_quote: Callable[[float], float]  # 헬퍼 시세(가격) → 시장 시세 단위(수익률)


@dataclass
class BuiltCurve:
    curve: ql.YieldTermStructure
    helpers: list[HelperInfo] = field(default_factory=list)


class MarketBuilder(ABC):
    """레시피 하나로 시장 객체 하나를 만든다. ORE 대응: marketdata/yieldcurve.hpp 등 빌더 계열."""

    kind: str

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def requires(self, recipe: Any) -> list[Node]:
        """의존 그래프용: 이 레시피가 참조하는 다른 시장 객체."""
        return []

    @abstractmethod
    def build(self, recipe: Any, quotes: QuoteStore, market: Market) -> BuiltCurve: ...


class Snapshot(Market):
    """관측 시장. 레시피와 시세로 구축하고 이름 → Handle 보관소로 내준다."""

    def __init__(self, asof: date, quotes: QuoteStore) -> None:
        self.asof = asof
        self.quotes = quotes
        self._yield_curves: dict[str, ql.RelinkableYieldTermStructureHandle] = {}
        self._built: dict[str, BuiltCurve] = {}

    @classmethod
    def build(cls, asof: date, cfg: Config, loader: Loader) -> Snapshot:
        ql.Settings.instance().evaluationDate = to_ql_date(asof)
        snap = cls(asof, QuoteStore(loader.load(asof)))

        recipes = {("YieldCurve", name): cfg.curves[name] for name in cfg.curves}
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
