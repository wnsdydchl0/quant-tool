from datetime import date

import pytest

from quanttool.data.marketdata import (
    BondYieldQuote,
    CSVLoader,
    InMemoryLoader,
    InstrumentType,
    QuoteType,
    Wildcard,
    parse_market_datum,
)

ASOF = date(2026, 10, 23)
K10 = "BOND/YIELD/USD/UST/PAR/10Y"


def test_csv_loader(loader):
    quotes = {q.name: q.value for q in loader.load_quotes(ASOF)}
    assert len(quotes) == 14
    assert quotes[K10] == pytest.approx(0.0398)
    assert quotes["BOND/YIELD/USD/UST/PAR/6W"] == pytest.approx(0.0400)
    assert loader.load_quotes(date(2026, 1, 1)) == []
    assert loader.asof_dates() == [date(2026, 10, 22), ASOF]
    assert loader.has(K10, ASOF) and not loader.has(K10, date(2026, 1, 1))
    assert loader.load_fixings() == []


def test_csv_loader_formats(tmp_path):
    """ORE market.txt: 공백·쉼표·탭 구분, # 주석, 20160205 날짜 형식."""
    p = tmp_path / "market.txt"
    p.write_text(
        "# 주석\n20260105, ZERO/RATE/USD/UST/A365F/1Y, 0.04\n2026-01-05\tMM/RATE/USD/0D/3M\t0.041\n"
    )
    f = tmp_path / "fixings.txt"
    f.write_text("2026-01-02 USD-SOFR 0.0405\n")
    loader = CSVLoader(p, f)
    d = date(2026, 1, 5)
    assert loader.get("ZERO/RATE/USD/UST/A365F/1Y", d).tenor == "1Y"
    assert loader.get("MM/RATE/USD/0D/3M", d).term == "3M"
    assert loader.load_fixings()[0].fixing == pytest.approx(0.0405)


def test_get_returns_same_quote_object(loader):
    """같은 시세는 같은 SimpleQuote: 커브 헬퍼가 이 Quote에 연결된다."""
    q = loader.get(K10, ASOF)
    assert loader.get(K10, ASOF).quote is q.quote
    with pytest.raises(KeyError, match="없다"):
        loader.get("BOND/YIELD/USD/UST/PAR/99Y", ASOF)


def test_wildcard(loader):
    got = loader.get_wildcard("BOND/YIELD/USD/UST/PAR/*Y", ASOF)
    assert {q.tenor for q in got} == {"1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"}
    assert Wildcard("IR_SWAP/RATE/EUR/2D/6M/*").matches("IR_SWAP/RATE/EUR/2D/6M/10Y")


def test_in_memory_loader():
    loader = InMemoryLoader()
    loader.add(ASOF, K10, 0.03)
    loader.add(date(2026, 10, 22), K10, 0.031)
    assert [q.value for q in loader.load_quotes(ASOF)] == [0.03]
    with pytest.raises(ValueError, match="중복"):
        loader.add(ASOF, K10, 0.03)


def test_parse_market_datum():
    q = parse_market_datum(ASOF, K10, 0.0398)
    assert isinstance(q, BondYieldQuote)
    assert (q.instrument_type, q.quote_type) == (InstrumentType.BOND, QuoteType.YIELD)
    assert (q.ccy, q.issuer, q.yield_type, q.tenor) == ("USD", "UST", "PAR", "10Y")
    s = parse_market_datum(ASOF, "IR_SWAP/RATE/EUR/2D/6M/10Y", 0.01)
    assert (s.ccy, s.fwd_start, s.tenor, s.term) == ("EUR", "2D", "6M", "10Y")
    for bad in ["UST-2Y", "FOO/RATE/USD/1Y", "BOND/YIELD/USD/UST/10Y"]:
        with pytest.raises(ValueError):
            parse_market_datum(ASOF, bad, 0.03)
