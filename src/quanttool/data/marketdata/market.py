"""시장 규격과 빌더 공통 부품.

ORE 대응: OREData/ored/marketdata/market.hpp.

가격결정·시나리오 코드는 Market 규격 메소드만 쓴다 (docs/architecture.md 1.7 불변 조건).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import QuantLib as ql

from .dependencygraph import Node
from .loader import QuoteStore

if TYPE_CHECKING:
    from quanttool.data.configuration import Config


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
    """시장 규격 (메뉴판). TodaysMarket과 ScenarioSimMarket이 구현한다."""

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
