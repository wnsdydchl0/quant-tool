"""시세 한 줄. ORE 대응: OREData/ored/marketdata/marketdatum.hpp, marketdatumparser.cpp.

키가 스스로를 설명한다: ``종류/시세유형/…``. 파서가 키를 읽어 하위 클래스(만기·통화 등)를 만든다.
값은 SimpleQuote로 들고 있어서, 커브 헬퍼가 이 Quote에 연결된다.

ORE에 없는 것 (QuantTool 확장):
- ``BOND/YIELD/{통화}/{발행자}/PAR/{만기}``: 정부가 고시하는 par yield 곡선의 한 점.
  ORE는 국채 커브를 개별 채권 가격(``BOND/PRICE/{securityId}``)에서 만들고,
  par yield 시세 유형이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

import QuantLib as ql


class InstrumentType(StrEnum):
    """ORE ``MarketDatum::InstrumentType``의 필요한 부분."""

    ZERO = "ZERO"
    DISCOUNT = "DISCOUNT"
    MM = "MM"
    IR_SWAP = "IR_SWAP"
    BOND = "BOND"
    EQUITY_SPOT = "EQUITY_SPOT"
    EQUITY_OPTION = "EQUITY_OPTION"


class QuoteType(StrEnum):
    """ORE ``MarketDatum::QuoteType``의 필요한 부분 + YIELD(확장)."""

    RATE = "RATE"
    PRICE = "PRICE"
    RATE_LNVOL = "RATE_LNVOL"
    YIELD = "YIELD"


@dataclass(eq=False)
class MarketDatum:
    asof_date: date
    name: str
    value: float
    instrument_type: InstrumentType
    quote_type: QuoteType
    quote: ql.SimpleQuote = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.quote = ql.SimpleQuote(self.value)

    def handle(self) -> ql.QuoteHandle:
        return ql.QuoteHandle(self.quote)


@dataclass(eq=False)
class BondYieldQuote(MarketDatum):
    """``BOND/YIELD/USD/UST/PAR/10Y`` (확장)."""

    ccy: str = ""
    issuer: str = ""
    yield_type: str = ""  # PAR
    tenor: str = ""


@dataclass(eq=False)
class ZeroQuote(MarketDatum):
    """``ZERO/RATE/USD/UST/A365F/10Y`` (ORE ZeroQuote)."""

    ccy: str = ""
    curve: str = ""
    day_counter: str = ""
    tenor: str = ""


@dataclass(eq=False)
class MoneyMarketQuote(MarketDatum):
    """``MM/RATE/EUR/2D/6M`` (ORE MoneyMarketQuote)."""

    ccy: str = ""
    fwd_start: str = ""
    term: str = ""


@dataclass(eq=False)
class SwapQuote(MarketDatum):
    """``IR_SWAP/RATE/EUR/2D/6M/10Y`` (ORE SwapQuote)."""

    ccy: str = ""
    fwd_start: str = ""
    tenor: str = ""  # 변동 레그 주기
    term: str = ""


def parse_market_datum(asof: date, name: str, value: float) -> MarketDatum:
    """키 문자열 → MarketDatum 하위 클래스. ORE ``parseMarketDatum``."""
    tokens = name.split("/")
    if len(tokens) < 3:
        raise ValueError(f"시세 키는 '종류/시세유형/…' 형식이어야 한다: {name!r}")
    try:
        it, qt = InstrumentType(tokens[0]), QuoteType(tokens[1])
    except ValueError:
        raise ValueError(f"알 수 없는 시세 종류 또는 유형: {name!r}") from None

    def need(n: int) -> None:
        if len(tokens) != n:
            raise ValueError(f"{it.value}/{qt.value}는 토큰 {n}개여야 한다: {name!r}")

    base = (asof, name, value, it, qt)
    if it == InstrumentType.BOND and qt == QuoteType.YIELD:
        need(6)
        return BondYieldQuote(*base, ccy=tokens[2], issuer=tokens[3], yield_type=tokens[4],
                              tenor=tokens[5])  # fmt: skip
    if it == InstrumentType.ZERO and qt == QuoteType.RATE:
        need(6)
        return ZeroQuote(*base, ccy=tokens[2], curve=tokens[3], day_counter=tokens[4],
                         tenor=tokens[5])  # fmt: skip
    if it == InstrumentType.MM and qt == QuoteType.RATE:
        need(5)
        return MoneyMarketQuote(*base, ccy=tokens[2], fwd_start=tokens[3], term=tokens[4])
    if it == InstrumentType.IR_SWAP and qt == QuoteType.RATE:
        need(6)
        return SwapQuote(*base, ccy=tokens[2], fwd_start=tokens[3], tenor=tokens[4],
                         term=tokens[5])  # fmt: skip
    raise ValueError(f"아직 지원하지 않는 시세 {it.value}/{qt.value}: {name!r}")


@dataclass(frozen=True)
class Fixing:
    """과거 지수 고시값 한 줄. ORE ``Fixing`` (``2016-02-02 EUR-EURIBOR-6M -0.0013``)."""

    date: date
    name: str
    fixing: float
