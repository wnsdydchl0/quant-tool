"""시세 창구. ORE 대응: OREData/ored/marketdata/loader.hpp, csvloader.hpp, inmemoryloader.hpp.

Loader는 출처를 감춘다. 파일이든 DB든 ``load_quotes(asof)``, ``get(이름, asof)`` 하나로 같다.
시세 파일 형식은 ORE market.txt와 같다: 한 줄에 ``날짜 키 값`` (공백·쉼표·탭 구분, ``#`` 주석).
"""

from __future__ import annotations

import fnmatch
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from .marketdatum import Fixing, MarketDatum, parse_market_datum


class Wildcard:
    """``IR_SWAP/RATE/EUR/2D/6M/*`` 같은 패턴. ORE ``Wildcard``."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern

    def matches(self, name: str) -> bool:
        return fnmatch.fnmatchcase(name, self.pattern)


class Loader(ABC):
    @abstractmethod
    def load_quotes(self, d: date) -> list[MarketDatum]: ...

    @abstractmethod
    def asof_dates(self) -> list[date]: ...

    def load_fixings(self) -> list[Fixing]:
        return []

    def get(self, name: str, d: date) -> MarketDatum:
        for q in self.load_quotes(d):
            if q.name == name:
                return q
        raise KeyError(f"시세 {name!r}가 {d}에 없다")

    def get_wildcard(self, wildcard: Wildcard | str, d: date) -> list[MarketDatum]:
        w = wildcard if isinstance(wildcard, Wildcard) else Wildcard(wildcard)
        return [q for q in self.load_quotes(d) if w.matches(q.name)]

    def has(self, name: str, d: date) -> bool:
        return any(q.name == name for q in self.load_quotes(d))

    def has_quotes(self, d: date) -> bool:
        return bool(self.load_quotes(d))


class InMemoryLoader(Loader):
    """ORE ``InMemoryLoader``: ``add(날짜, 키, 값)``으로 채운다."""

    def __init__(self) -> None:
        self._quotes: dict[date, dict[str, MarketDatum]] = {}
        self._fixings: list[Fixing] = []

    def add(self, d: date, name: str, value: float) -> None:
        day = self._quotes.setdefault(d, {})
        if name in day:
            raise ValueError(f"시세 중복: {d} {name}")
        day[name] = parse_market_datum(d, name, value)

    def add_fixing(self, d: date, name: str, value: float) -> None:
        self._fixings.append(Fixing(d, name, value))

    def load_quotes(self, d: date) -> list[MarketDatum]:
        return list(self._quotes.get(d, {}).values())

    def get(self, name: str, d: date) -> MarketDatum:
        try:
            return self._quotes[d][name]
        except KeyError:
            raise KeyError(f"시세 {name!r}가 {d}에 없다") from None

    def asof_dates(self) -> list[date]:
        return sorted(self._quotes)

    def load_fixings(self) -> list[Fixing]:
        return list(self._fixings)


_SPLIT = re.compile(r"[,;\t ]+")


def _read_lines(paths: Iterable[Path]) -> Iterable[tuple[date, str, float]]:
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            tokens = _SPLIT.split(line)
            if len(tokens) != 3:
                raise ValueError(f"{path}: '날짜 키 값' 형식이 아니다: {line!r}")
            d = date.fromisoformat(tokens[0].replace("/", "-")) if "-" in tokens[0] else None
            if d is None:  # ORE는 20160205 형식도 허용
                d = date(int(tokens[0][:4]), int(tokens[0][4:6]), int(tokens[0][6:8]))
            yield d, tokens[1], float(tokens[2])


class CSVLoader(InMemoryLoader):
    """ORE ``CSVLoader``: 시세·fixing 파일을 읽는다."""

    def __init__(
        self,
        market_files: str | Path | Iterable[str | Path],
        fixing_files: str | Path | Iterable[str | Path] = (),
    ) -> None:
        super().__init__()
        for d, name, value in _read_lines(_paths(market_files)):
            self.add(d, name, value)
        for d, name, value in _read_lines(_paths(fixing_files)):
            self.add_fixing(d, name, value)


def _paths(p: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(p, str | Path):
        return [Path(p)]
    return [Path(x) for x in p]
