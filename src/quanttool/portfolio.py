"""포트폴리오: 거래 명세 → QuantLib 상품 + 엔진, 시장의 이름 붙은 객체로 가격.

- 거래 = 상품 템플릿(configs/products.yaml templates: 관례·지수·할인처럼 거래마다 같은 값)
  + 거래 값(쿠폰·고정금리·만기·액면 …). 코드에서는 trade(cfg, "KRW_IRS_CD91", fixed_rate=…, …),
  파일에서는 {product: KRW_IRS_CD91, fixed_rate: …}. 템플릿 없이 모든 필드를 직접 써도 된다.

- 거래는 시장 객체를 이름으로 가리킨다 (curve: UST, discount: KOFR, index: CD91 …).
- 상품 종류마다 명세(TRADES)와 조립 함수(BUILDERS) 하나. 조립 함수는 상품만 만들고 엔진은 모른다.
- 엔진은 configs/products.yaml engines.defaults가 상품 종류별로 고르고
  (템플릿·거래의 engine 필드로 덮어쓰기), ENGINES의 함수가 시장 객체로 만든다.
  같은 (엔진, 시장 객체) 조합은 엔진 하나를 공유한다.
  같은 상품을 다른 방법(예: 단일 커브 / 듀얼 커브 할인)으로 평가해 비교하는 자리다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
import QuantLib as ql
import yaml
from pydantic import BaseModel, ConfigDict

from .config import Config
from .market import Market


class Trade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    product: str = ""  # 상품 템플릿 이름 (있으면)
    engine: str = ""  # 비우면 configs/products.yaml engines.defaults의 상품 종류 기본값

    def market_names(self) -> tuple[str, ...]:
        """이 거래가 쓰는 시장 객체 이름 (엔진 공유 키)."""
        raise NotImplementedError

    def multiplier(self) -> float:
        return 1.0


# --- 채권
class Bond(Trade):
    """고정금리 채권. notional < 0이면 매도 포지션 (액면 기준)."""

    type: Literal["Bond"] = "Bond"
    notional: float
    coupon: float  # 소수
    issue_date: date
    maturity_date: date
    conventions: str
    curve: str  # 할인 커브 이름 (market[curve])

    def market_names(self):
        return (self.curve,)

    def multiplier(self) -> float:
        return self.notional / 100.0


def build_bond(t: Bond, market: Market, cfg: Config) -> ql.Bond:
    conv = cfg.conventions[t.conventions]
    issue, maturity = ql.Date.from_date(t.issue_date), ql.Date.from_date(t.maturity_date)
    schedule = ql.Schedule(issue, maturity, ql.Period(conv.ql_frequency()),
                           conv.ql_calendar(), conv.ql_bdc(), conv.ql_bdc(),
                           ql.DateGeneration.Backward, False)  # fmt: skip
    return ql.FixedRateBond(conv.settlement_days, 100.0, schedule, [t.coupon],
                            conv.ql_day_count(), conv.ql_payment(), 100.0, issue)  # fmt: skip


# --- 금리 스왑 (고정 vs Ibor 지수)
class IRSwap(Trade):
    """고정 vs 변동. 고정 레그는 conventions(주기·일수·영업일), 변동 레그는 지수(index) 주기.
    지수 예측은 그 지수의 커브, 할인은 discount 커브 (듀얼 커브)."""

    type: Literal["IRSwap"] = "IRSwap"
    notional: float
    fixed_rate: float
    pay_fixed: bool = True
    start_date: date
    maturity_date: date
    conventions: str
    index: str
    discount: str
    spread: float = 0.0

    def market_names(self):
        return (self.discount, self.index)


def build_irswap(t: IRSwap, market: Market, cfg: Config) -> ql.VanillaSwap:
    conv = cfg.conventions[t.conventions]
    index = market.index(t.index)
    start, end = ql.Date.from_date(t.start_date), ql.Date.from_date(t.maturity_date)
    bdc = conv.ql_bdc()
    fixed = ql.Schedule(start, end, ql.Period(conv.ql_frequency()), conv.ql_calendar(), bdc, bdc,
                        ql.DateGeneration.Backward, False)  # fmt: skip
    floating = ql.Schedule(start, end, index.tenor(), index.fixingCalendar(), bdc, bdc,
                           ql.DateGeneration.Backward, False)  # fmt: skip
    kind = ql.VanillaSwap.Payer if t.pay_fixed else ql.VanillaSwap.Receiver
    return ql.VanillaSwap(kind, t.notional, fixed, t.fixed_rate, conv.ql_day_count(), floating,
                          index, t.spread, index.dayCounter())  # fmt: skip


# --- 엔진: 이름 → (거래, 시장, 엔진 인자) → QuantLib 엔진. 인자는 products.yaml engines.params
Engine = Callable[[Trade, Market, dict], ql.PricingEngine]
ENGINES: dict[str, Engine] = {
    "DiscountingBond": lambda t, m, p: ql.DiscountingBondEngine(m[t.curve]),
    "DiscountingSwap": lambda t, m, p: ql.DiscountingSwapEngine(m[t.discount]),
}


def expand(record: Mapping, products: Mapping[str, Mapping] | None) -> dict:
    """상품 템플릿 위에 거래 값을 덮는다. product가 없거나 products를 안 넘기면 그대로
    (이미 펼친 레코드, 예: trade.model_dump())."""
    name = record.get("product")
    if not name or products is None:
        return dict(record)
    if name not in products:
        raise KeyError(
            f"상품 템플릿 {name!r}가 없다 (configs/products.yaml templates): {sorted(products)}"
        )
    return {**products[name], **record}


def make_trade(record: Mapping, products: Mapping[str, Mapping] | None = None) -> Trade:
    r = expand(record, products)
    kind = r.get("type", "Bond")
    if kind not in TRADES:
        raise KeyError(f"{r.get('id')}: 상품 종류 {kind!r}가 없다: {sorted(TRADES)}")
    return TRADES[kind].model_validate(r)


def trade(cfg: Config, product: str, **fields) -> Trade:
    """코드에서 거래 하나: trade(cfg, "KRW_IRS_CD91", id="s1", fixed_rate=0.03, …)."""
    return make_trade({"product": product, **fields}, cfg.products)


TRADES = {"Bond": Bond, "IRSwap": IRSwap}
BUILDERS = {"Bond": build_bond, "IRSwap": build_irswap}


def engine_name(t: Trade, cfg: Config) -> str:
    name = t.engine or cfg.pricing.defaults.get(t.type, "")
    if name not in ENGINES:
        raise KeyError(
            f"{t.id}: 엔진 {name!r}가 없다 (products.yaml engines {t.type}): {sorted(ENGINES)}"
        )
    return name


class Portfolio:
    def __init__(self, trades: Iterable[Trade]) -> None:
        self.trades: dict[str, Trade] = {}
        for t in trades:
            if t.id in self.trades:
                raise ValueError(f"거래 id 중복: {t.id}")
            self.trades[t.id] = t
        self.instruments: dict[str, ql.Instrument] = {}
        self.engines: dict[tuple, ql.PricingEngine] = {}  # (엔진 이름, 시장 객체들) → 엔진 (공유)
        self.market: Market | None = None

    @classmethod
    def from_records(
        cls, records: Iterable[Mapping], products: Mapping[str, Mapping] | None = None
    ) -> Portfolio:
        """레코드(dict) → 거래. product 필드가 있으면 products(보통 cfg.products) 템플릿을 쓴다."""
        return cls(make_trade(r, products) for r in records)

    @classmethod
    def from_file(
        cls, *paths: str | Path, products: Mapping[str, Mapping] | None = None
    ) -> Portfolio:
        records = []
        for path in paths:
            with Path(path).open(encoding="utf-8") as f:
                records += yaml.safe_load(f) or []
        return cls.from_records(records, products)

    def ids(self) -> list[str]:
        return list(self.trades)

    def build(self, market: Market, cfg: Config) -> Portfolio:
        """거래마다 QuantLib 상품을 만들어 엔진을 붙인다. 다른 시장에 붙이려면 다시 부른다."""
        self.engines, self.instruments = {}, {}
        with market.active():
            for i, t in self.trades.items():
                inst = BUILDERS[t.type](t, market, cfg)
                name = engine_name(t, cfg)
                key = (name, *t.market_names())
                if key not in self.engines:
                    self.engines[key] = ENGINES[name](t, market, cfg.pricing.params.get(name, {}))
                inst.setPricingEngine(self.engines[key])
                self.instruments[i] = inst
        self.market = market
        return self

    def npvs(self) -> pd.Series:
        """거래별 NPV (포지션 크기 반영). 시장의 현재 날짜·시나리오 기준."""
        if self.market is None:
            raise RuntimeError("build(market, cfg) 전에 평가할 수 없다")
        with self.market.active():
            return pd.Series(
                {i: self.instruments[i].NPV() * t.multiplier() for i, t in self.trades.items()},
                name="npv",
                dtype=float,
            )

    def npv(self) -> float:
        return float(self.npvs().sum())
