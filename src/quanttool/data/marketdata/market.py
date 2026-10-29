"""시장 규격, 보관소, 빌더 공통 부품.

ORE 대응: OREData/ored/marketdata/market.hpp, marketimpl.hpp.

가격결정·시나리오 코드는 Market 규격 메소드만 쓴다 (docs/architecture.md 1.6 불변 조건).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

import QuantLib as ql

from quanttool.data.configuration import (
    DEFAULT_CONFIGURATION,
    InstrumentConventions,
    RateConventions,
)

from .dependencygraph import Node
from .loader import Loader


class YieldCurveType(StrEnum):
    """보관소에서 같은 이름이라도 용도를 구분하는 키. ORE 대응: market.hpp ``YieldCurveType``."""

    Discount = "Discount"  # discount_curve(통화)
    Yield = "Yield"  # yield_curve(이름)


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
    """시장 규격 (메뉴판). TodaysMarket과 ScenarioSimMarket이 구현한다. ORE 대응: market.hpp.

    모든 조회는 configuration을 받는다. 없는 configuration이면 "default"에서 찾는다(ORE와 같음).
    """

    asof: date

    @abstractmethod
    def discount_curve(
        self, ccy: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle: ...

    @abstractmethod
    def yield_curve(
        self, name: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle: ...

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
    quote: ql.Quote  # 시장 시세 (MarketDatum.quote)
    helper: ql.RateHelper
    maturity: ql.Date
    to_quote: Callable[[float], float]  # 헬퍼 시세(가격) → 시장 시세 단위(수익률)


@dataclass
class BuiltCurve:
    curve: ql.YieldTermStructure
    helpers: list[HelperInfo] = field(default_factory=list)


class MarketImpl(Market):
    """보관소: 종류별 이름 → Handle과 조회 구현. ORE 대응: OREData/ored/marketdata/marketimpl.hpp.

    TodaysMarket(구축)과 SimMarket(변경)이 같은 보관소를 쓰고, 채우는 방식만 다르다.
    """

    def __init__(self, asof: date) -> None:
        self.asof = asof
        # (configuration, 용도, 이름) → Handle. ORE marketimpl.hpp ``yieldCurves_``
        self._yield_curves: dict[tuple[str, YieldCurveType, str], ql.YieldTermStructureHandle] = {}

    def discount_curve(
        self, ccy: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle:
        return self._lookup(YieldCurveType.Discount, ccy, configuration)

    def yield_curve(
        self, name: str, configuration: str = DEFAULT_CONFIGURATION
    ) -> ql.YieldTermStructureHandle:
        return self._lookup(YieldCurveType.Yield, name, configuration)

    def yield_curve_names(
        self,
        curve_type: YieldCurveType = YieldCurveType.Yield,
        configuration: str = DEFAULT_CONFIGURATION,
    ) -> list[str]:
        return [n for (c, t, n) in self._yield_curves if c == configuration and t == curve_type]

    def _lookup(
        self, curve_type: YieldCurveType, name: str, configuration: str
    ) -> ql.YieldTermStructureHandle:
        for conf in (
            configuration,
            DEFAULT_CONFIGURATION,
        ):  # ORE marketimpl.cpp lookup: default로 대체
            h = self._yield_curves.get((conf, curve_type, name))
            if h is not None:
                return h
        names = sorted(n for (_, t, n) in self._yield_curves if t == curve_type)
        raise KeyError(f"{curve_type.value} 커브 {name!r}가 없다 ({configuration}): {names}")

    def _set_yield_curve(
        self,
        curve_type: YieldCurveType,
        name: str,
        handle: ql.YieldTermStructureHandle,
        configuration: str = DEFAULT_CONFIGURATION,
    ) -> None:
        self._yield_curves[(configuration, curve_type, name)] = handle


class MarketBuilder(ABC):
    """레시피 하나로 시장 객체 하나를 만든다. ORE 대응: marketdata/yieldcurve.hpp 등 빌더 계열."""

    kind: str

    @staticmethod
    def conventions(id: str) -> RateConventions:
        """전역 관례 등록부에서 꺼낸다 (ORE InstrumentConventions::instance().conventions())."""
        return InstrumentConventions.instance().conventions().get(id)

    def requires(self, recipe: Any) -> list[Node]:
        """의존 그래프용: 이 레시피가 참조하는 다른 시장 객체."""
        return []

    @abstractmethod
    def build(self, recipe: Any, loader: Loader, market: Market) -> BuiltCurve:
        """ORE YieldCurve(asof, spec, curveConfigs, loader, …)와 같이 시세는 loader에서 꺼낸다."""
