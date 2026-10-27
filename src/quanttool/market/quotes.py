"""시세 읽기와 보관.

ORE 대응: OREData/ored/marketdata/loader.hpp, csvloader.hpp, inmemoryloader.hpp.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import QuantLib as ql

from quanttool.core.ids import QuoteId


@dataclass(frozen=True)
class MarketQuote:
    asof: date
    id: str
    value: float

    def __post_init__(self) -> None:
        QuoteId.parse(self.id)  # id 규칙 검증


class Loader(ABC):
    @abstractmethod
    def load(self, asof: date) -> list[MarketQuote]: ...


class InMemoryLoader(Loader):
    def __init__(self, quotes: Iterable[MarketQuote]) -> None:
        self._quotes = list(quotes)

    def load(self, asof: date) -> list[MarketQuote]:
        return [q for q in self._quotes if q.asof == asof]


# 미 재무부 Daily Treasury Par Yield Curve CSV 열 이름 → 만기 라벨
UST_CSV_COLUMNS = {
    "1 Mo": "1M",
    "1.5 Month": "6W",
    "2 Mo": "2M",
    "3 Mo": "3M",
    "4 Mo": "4M",
    "6 Mo": "6M",
    "1 Yr": "1Y",
    "2 Yr": "2Y",
    "3 Yr": "3Y",
    "5 Yr": "5Y",
    "7 Yr": "7Y",
    "10 Yr": "10Y",
    "20 Yr": "20Y",
    "30 Yr": "30Y",
}


class UstParCsvLoader(Loader):
    """재무부 par yield CSV(퍼센트, MM/DD/YYYY)를 ``UST/PAR/{tenor}`` 소수 시세로 읽는다."""

    def __init__(self, paths: str | Path | Iterable[str | Path]) -> None:
        if isinstance(paths, str | Path):
            paths = [paths]
        self._paths = [Path(p) for p in paths]

    def load(self, asof: date) -> list[MarketQuote]:
        out: list[MarketQuote] = []
        for path in self._paths:
            with path.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if datetime.strptime(row["Date"], "%m/%d/%Y").date() != asof:
                        continue
                    for col, tenor in UST_CSV_COLUMNS.items():
                        value = (row.get(col) or "").strip()
                        if value:
                            out.append(MarketQuote(asof, f"UST/PAR/{tenor}", float(value) / 100))
        return out


class QuoteStore:
    """시세 id → SimpleQuote. 시장의 모든 구조물은 여기 Quote에 연결된다."""

    def __init__(self, quotes: Iterable[MarketQuote]) -> None:
        self._quotes: dict[str, ql.SimpleQuote] = {}
        for q in quotes:
            if q.id in self._quotes:
                raise ValueError(f"시세 id 중복: {q.id}")
            self._quotes[q.id] = ql.SimpleQuote(q.value)

    def __getitem__(self, quote_id: str) -> ql.SimpleQuote:
        try:
            return self._quotes[quote_id]
        except KeyError:
            raise KeyError(f"시세 {quote_id!r}가 없다") from None

    def __contains__(self, quote_id: str) -> bool:
        return quote_id in self._quotes

    def handle(self, quote_id: str) -> ql.QuoteHandle:
        return ql.QuoteHandle(self[quote_id])

    def ids(self) -> list[str]:
        return list(self._quotes)

    def values(self) -> dict[str, float]:
        return {k: q.value() for k, q in self._quotes.items()}
