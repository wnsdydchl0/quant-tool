"""포트폴리오: 포지션 명세(YAML) → QuantLib 상품, 시장의 이름 붙은 커브로 가격.

- 거래는 커브를 이름으로 가리킨다 (curve: UST). build(market, cfg)가 market["UST"]에 연결한다.
- 같은 커브를 쓰는 거래는 엔진 하나를 같이 쓴다.
- 상품 종류가 늘면 TRADES(명세)와 BUILDERS(조립 함수)에 한 줄씩 더한다.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
import QuantLib as ql
import yaml
from pydantic import BaseModel, ConfigDict

from .config import Config
from .curves import to_ql_date
from .market import Market


class Bond(BaseModel):
    """고정금리 채권. notional < 0이면 매도 포지션 (액면 기준)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    type: Literal["Bond"] = "Bond"
    notional: float
    coupon: float  # 소수
    issue_date: date
    maturity_date: date
    conventions: str
    curve: str  # 할인 커브 이름 (market[curve])


def build_bond(t: Bond, market: Market, cfg: Config, engines: dict) -> ql.Bond:
    conv = cfg.conventions[t.conventions]
    issue = to_ql_date(t.issue_date)
    schedule = ql.Schedule(issue, to_ql_date(t.maturity_date), ql.Period(conv.ql_frequency()),
                           conv.ql_calendar(), conv.ql_bdc(), conv.ql_bdc(),
                           ql.DateGeneration.Backward, False)  # fmt: skip
    bond = ql.FixedRateBond(conv.settlement_days, 100.0, schedule, [t.coupon], conv.ql_day_count(),
                            conv.ql_payment(), 100.0, issue)  # fmt: skip
    if t.curve not in engines:
        engines[t.curve] = ql.DiscountingBondEngine(market[t.curve])
    bond.setPricingEngine(engines[t.curve])
    return bond


TRADES = {"Bond": Bond}
BUILDERS = {"Bond": build_bond}


class Portfolio:
    def __init__(self, trades: Iterable[BaseModel]) -> None:
        self.trades: dict[str, BaseModel] = {}
        for t in trades:
            if t.id in self.trades:
                raise ValueError(f"거래 id 중복: {t.id}")
            self.trades[t.id] = t
        self.instruments: dict[str, ql.Instrument] = {}
        self.engines: dict[str, ql.PricingEngine] = {}  # 커브 이름 → 엔진 (공유)
        self.market: Market | None = None

    @classmethod
    def from_records(cls, records: Iterable[dict]) -> Portfolio:
        return cls(TRADES[r.get("type", "Bond")].model_validate(r) for r in records)

    @classmethod
    def from_file(cls, path: str | Path) -> Portfolio:
        with Path(path).open(encoding="utf-8") as f:
            return cls.from_records(yaml.safe_load(f) or [])

    def ids(self) -> list[str]:
        return list(self.trades)

    def build(self, market: Market, cfg: Config) -> Portfolio:
        """거래마다 QuantLib 상품을 만들어 market에 연결한다. 다른 시장에 붙이려면 다시 부른다."""
        self.engines = {}
        with market.active():
            self.instruments = {
                i: BUILDERS[t.type](t, market, cfg, self.engines) for i, t in self.trades.items()
            }
        self.market = market
        return self

    def npvs(self) -> pd.Series:
        """거래별 NPV (포지션 크기 반영). 시장의 현재 날짜·시나리오 기준."""
        if self.market is None:
            raise RuntimeError("build(market, cfg) 전에 평가할 수 없다")
        with self.market.active():
            return pd.Series(
                {i: self.instruments[i].NPV() * t.notional / 100.0 for i, t in self.trades.items()},
                name="npv",
                dtype=float,
            )

    def npv(self) -> float:
        return float(self.npvs().sum())
