from datetime import date

import pytest

from quanttool.market import InMemoryLoader, MarketQuote, QuoteStore

ASOF = date(2026, 10, 23)


def test_ust_csv_loader(loader):
    quotes = {q.id: q.value for q in loader.load(ASOF)}
    assert len(quotes) == 14
    assert quotes["UST/PAR/10Y"] == pytest.approx(0.0398)
    assert quotes["UST/PAR/6W"] == pytest.approx(0.0400)
    assert loader.load(date(2026, 1, 1)) == []
    assert loader.dates() == [date(2026, 10, 22), ASOF]


def test_in_memory_loader_filters_by_date():
    q1 = MarketQuote(ASOF, "UST/PAR/2Y", 0.03)
    q2 = MarketQuote(date(2026, 10, 22), "UST/PAR/2Y", 0.031)
    assert InMemoryLoader([q1, q2]).load(ASOF) == [q1]


def test_quote_store():
    store = QuoteStore([MarketQuote(ASOF, "UST/PAR/2Y", 0.03)])
    h = store.handle("UST/PAR/2Y")
    store["UST/PAR/2Y"].setValue(0.031)
    assert h.value() == pytest.approx(0.031)
    with pytest.raises(KeyError):
        store["UST/PAR/5Y"]
    with pytest.raises(ValueError):
        QuoteStore([MarketQuote(ASOF, "UST/PAR/2Y", 0.03)] * 2)
    with pytest.raises(ValueError):
        MarketQuote(ASOF, "UST-2Y", 0.03)
