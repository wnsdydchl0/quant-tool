"""오늘 시장에 만들 객체 목록. ORE 대응: OREData/ored/marketdata/todaysmarketparameters.hpp."""

from __future__ import annotations

from .conventions import _Strict


class TodaysMarketParameters(_Strict):
    """TodaysMarket이 구축할 대상."""

    yield_curves: list[str] = []
