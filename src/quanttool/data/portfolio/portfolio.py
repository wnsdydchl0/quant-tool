"""포트폴리오. ORE 대응: OREData/ored/portfolio/portfolio.hpp."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import pandas as pd
import yaml

from quanttool.data.utilities.registry import TRADES

from .enginefactory import EngineFactory
from .trade import Trade


class Portfolio:
    def __init__(self, trades: Iterable[Trade]) -> None:
        self.trades: dict[str, Trade] = {}
        for t in trades:
            if t.id in self.trades:
                raise ValueError(f"거래 id 중복: {t.id}")
            self.trades[t.id] = t

    @classmethod
    def from_records(cls, records: Iterable[dict]) -> Portfolio:
        return cls(TRADES[r["trade_type"]].model_validate(r) for r in records)

    @classmethod
    def load(cls, path: str | Path) -> Portfolio:
        with Path(path).open(encoding="utf-8") as f:
            return cls.from_records(yaml.safe_load(f) or [])

    def __iter__(self) -> Iterator[Trade]:
        return iter(self.trades.values())

    def __len__(self) -> int:
        return len(self.trades)

    def build(self, factory: EngineFactory) -> None:
        for t in self:
            t.build(factory)

    def npvs(self) -> pd.Series:
        return pd.Series({t.id: t.npv() for t in self}, name="npv", dtype=float)

    def npv(self) -> float:
        return float(self.npvs().sum())
