from datetime import date
from pathlib import Path

import pytest

from quanttool.data.configuration import load_config
from quanttool.data.marketdata import TodaysMarket, UstParCsvLoader

ROOT = Path(__file__).resolve().parents[1]
ASOF = date(2026, 10, 23)


@pytest.fixture
def cfg():
    return load_config(ROOT / "configs")


@pytest.fixture
def loader():
    return UstParCsvLoader(ROOT / "tests" / "fixtures" / "ust_par_sample.csv")


@pytest.fixture
def snap(cfg, loader):
    return TodaysMarket.from_config(ASOF, cfg, loader)


@pytest.fixture
def linked_snap(cfg, loader):
    """시세 연결을 유지한 오늘 시장 (Quote 변경이 커브로 전파된다)."""
    return TodaysMarket.from_config(ASOF, cfg, loader, preserve_quote_linkage=True)


@pytest.fixture
def portfolio():
    from quanttool.data.portfolio import Portfolio

    return Portfolio.load(ROOT / "positions" / "ust_book.yaml")
