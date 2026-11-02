from datetime import date
from pathlib import Path

import pytest

from quanttool.config import load_config
from quanttool.market import build_market
from quanttool.portfolio import Portfolio
from quanttool.quotes import read_quotes

ROOT = Path(__file__).resolve().parents[1]
ASOF = date(2026, 10, 23)


@pytest.fixture
def config():
    return load_config(ROOT / "configs")


@pytest.fixture
def quotes():
    return read_quotes(ROOT / "tests" / "fixtures" / "market_sample.txt")


@pytest.fixture
def market(config, quotes):
    return build_market(ASOF, quotes[ASOF], config)


@pytest.fixture
def book(config, market):
    return Portfolio.from_file(ROOT / "positions" / "ust_book.yaml").build(market, config)
