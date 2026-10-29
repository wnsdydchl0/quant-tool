"""포트폴리오. ORE 대응: OREData/ored/portfolio/portfolio.hpp.

ORE와 같이 trades()는 id → Trade 사전이다. npvs()/npv()는 결과를 pandas로 보는 편의 함수.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import pandas as pd
import yaml

from quanttool.data.utilities.registry import TRADES

from .enginefactory import EngineFactory
from .trade import Trade


class Portfolio:
    def __init__(self, trades: Iterable[Trade] = ()) -> None:
        self._trades: dict[str, Trade] = {}
        for t in trades:
            self.add(t)

    @classmethod
    def from_records(cls, records: Iterable[dict]) -> Portfolio:
        return cls(TRADES[r["trade_type"]].model_validate(r) for r in records)

    @classmethod
    def from_file(cls, path: str | Path) -> Portfolio:
        """ORE Portfolio::fromFile (portfolio.xml) 대응: positions/*.yaml."""
        with Path(path).open(encoding="utf-8") as f:
            return cls.from_records(yaml.safe_load(f) or [])

    def add(self, trade: Trade) -> None:
        if trade.id in self._trades:
            raise ValueError(f"거래 id 중복: {trade.id}")
        self._trades[trade.id] = trade

    def trades(self) -> dict[str, Trade]:
        return self._trades

    def get(self, trade_id: str) -> Trade:
        return self._trades[trade_id]

    def has(self, trade_id: str) -> bool:
        return trade_id in self._trades

    def ids(self) -> list[str]:
        return list(self._trades)

    def size(self) -> int:
        return len(self._trades)

    def __iter__(self) -> Iterator[Trade]:
        return iter(self._trades.values())

    def __len__(self) -> int:
        return len(self._trades)

    def build(self, engine_factory: EngineFactory) -> None:
        for t in self:
            t.build(engine_factory)

    def reset(self) -> None:
        for t in self:
            t.reset()

    def is_built(self) -> bool:
        return all(t.is_built() for t in self)

    def npvs(self) -> pd.Series:
        return pd.Series({t.id: t.npv() for t in self}, name="npv", dtype=float)

    def npv(self) -> float:
        return float(self.npvs().sum())
