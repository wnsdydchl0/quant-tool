from datetime import date
from pathlib import Path

import pytest

from quanttool.config import load_config
from quanttool.market import build_market
from quanttool.market.quotes import read_quotes
from quanttool.portfolio import Portfolio

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
def load(config):
    """positions/{name}.yaml 예시 북 (configs/products.yaml templates 적용)."""
    return lambda name: Portfolio.from_file(
        ROOT / "positions" / f"{name}.yaml", products=config.products
    )


@pytest.fixture
def book(config, market, load):
    return load("ust_book").build(market, config)
