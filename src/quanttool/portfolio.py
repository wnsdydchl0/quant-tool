"""포트폴리오: 포지션 명세(YAML) → QuantLib 상품 + 엔진, 시장의 이름 붙은 객체로 가격.

- 거래는 시장 객체를 이름으로 가리킨다 (curve: UST, discount: KOFR, index: CD91 …).
- 상품 종류마다 명세(TRADES)와 조립 함수(BUILDERS) 하나. 조립 함수는 상품만 만들고 엔진은 모른다.
- 엔진은 configs/pricing.yaml이 상품 종류별로 고르고(거래의 engine 필드로 덮어쓰기),
  ENGINES의 함수가 시장 객체로 만든다. 같은 (엔진, 시장 객체) 조합은 엔진 하나를 공유한다.
  같은 상품을 다른 방법(예: 옵션 BS 해석해 / FD / Heston)으로 평가해 비교하는 자리다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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


class Trade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    engine: str = ""  # 비우면 configs/pricing.yaml의 상품 종류 기본값

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
    issue = to_ql_date(t.issue_date)
    schedule = ql.Schedule(issue, to_ql_date(t.maturity_date), ql.Period(conv.ql_frequency()),
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
    start, end = to_ql_date(t.start_date), to_ql_date(t.maturity_date)
    bdc = conv.ql_bdc()
    fixed = ql.Schedule(start, end, ql.Period(conv.ql_frequency()), conv.ql_calendar(), bdc, bdc,
                        ql.DateGeneration.Backward, False)  # fmt: skip
    floating = ql.Schedule(start, end, index.tenor(), index.fixingCalendar(), bdc, bdc,
                           ql.DateGeneration.Backward, False)  # fmt: skip
    kind = ql.VanillaSwap.Payer if t.pay_fixed else ql.VanillaSwap.Receiver
    return ql.VanillaSwap(kind, t.notional, fixed, t.fixed_rate, conv.ql_day_count(), floating,
                          index, t.spread, index.dayCounter())  # fmt: skip


# --- 주식 옵션 (유럽형)
class EquityOption(Trade):
    """유럽형 콜·풋. quantity < 0이면 매도. 시장 객체: 현물, 할인 커브, 배당 커브, vol (, 모델)."""

    type: Literal["EquityOption"] = "EquityOption"
    quantity: float
    option_type: Literal["Call", "Put"]
    strike: float
    expiry: date
    underlying: str  # 현물 (예: SPX)
    curve: str  # 할인
    dividend: str  # 예: SPX_DIV
    vol: str  # 예: SPX_VOL
    model: str = ""  # Heston 엔진이 쓰는 모델 객체 (예: SPX_HESTON)

    def market_names(self):
        return (self.underlying, self.curve, self.dividend, self.vol, self.model)

    def multiplier(self) -> float:
        return self.quantity


def build_equity_option(t: EquityOption, market: Market, cfg: Config) -> ql.VanillaOption:
    kind = ql.Option.Call if t.option_type == "Call" else ql.Option.Put
    return ql.VanillaOption(ql.PlainVanillaPayoff(kind, t.strike),
                            ql.EuropeanExercise(to_ql_date(t.expiry)))  # fmt: skip


def bs_process(t: EquityOption, m: Market) -> ql.GeneralizedBlackScholesProcess:
    """현물 + 배당 + 할인 + vol 서페이스 Handle. 요인을 흔들면 프로세스가 따라온다."""
    return ql.GeneralizedBlackScholesProcess(m[t.underlying], m[t.dividend], m[t.curve], m[t.vol])


# --- 엔진: 이름 → (거래, 시장, 엔진 인자) → QuantLib 엔진. 인자는 pricing.yaml engines
Engine = Callable[[Trade, Market, dict], ql.PricingEngine]
ENGINES: dict[str, Engine] = {
    "DiscountingBond": lambda t, m, p: ql.DiscountingBondEngine(m[t.curve]),
    "DiscountingSwap": lambda t, m, p: ql.DiscountingSwapEngine(m[t.discount]),
    "AnalyticBS": lambda t, m, p: ql.AnalyticEuropeanEngine(bs_process(t, m)),
    "AnalyticHeston": lambda t, m, p: ql.AnalyticHestonEngine(m[t.model]),
    "FdBS": lambda t, m, p: ql.FdBlackScholesVanillaEngine(
        bs_process(t, m), int(p["t_grid"]), int(p["x_grid"]), int(p.get("damping_steps", 0))
    ),
}

TRADES = {"Bond": Bond, "IRSwap": IRSwap, "EquityOption": EquityOption}
BUILDERS = {"Bond": build_bond, "IRSwap": build_irswap, "EquityOption": build_equity_option}


def engine_name(t: Trade, cfg: Config) -> str:
    name = t.engine or cfg.pricing.products.get(t.type, "")
    if name not in ENGINES:
        raise KeyError(f"{t.id}: 엔진 {name!r}가 없다 (pricing.yaml {t.type}): {sorted(ENGINES)}")
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
    def from_records(cls, records: Iterable[dict]) -> Portfolio:
        return cls(TRADES[r.get("type", "Bond")].model_validate(r) for r in records)

    @classmethod
    def from_file(cls, *paths: str | Path) -> Portfolio:
        records = []
        for path in paths:
            with Path(path).open(encoding="utf-8") as f:
                records += yaml.safe_load(f) or []
        return cls.from_records(records)

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
                    self.engines[key] = ENGINES[name](t, market, cfg.pricing.engines.get(name, {}))
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
