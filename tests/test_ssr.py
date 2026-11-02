import math
from pathlib import Path

import pytest

from quanttool.analysis.risk import factor_delta
from quanttool.analysis.scenarios import ssr
from quanttool.market.curves import to_ql_date
from quanttool.portfolio import Portfolio

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def options(config, market):
    return Portfolio.from_file(ROOT / "positions" / "spx_options.yaml").build(market, config)


def _vol_keys(market):
    return [k for k in market.factors() if k.startswith("SPX_VOL/")]


def test_ssr_one_is_sticky_strike(market):
    assert ssr(market, "SPX", "SPX_VOL", 0.01, 1.0) == {"SPX/spot": 0.01}


def test_ssr_zero_is_sticky_moneyness(market):
    """ssr=0: 이동 뒤 격자 행사가 K의 vol = 기준 서페이스의 K/(1+r) vol (같은 K/S)."""
    s = market.objects["SPX_VOL"]
    r = 0.02
    sc = ssr(market, "SPX", "SPX_VOL", r, 0.0)
    d, k = s.dates[3], s.strikes[2]
    with market.active(), market.scenario(sc):
        assert market["SPX_VOL"].blackVol(d, k) == pytest.approx(s.vol(d, k / (1 + r)), abs=1e-14)


def test_factor_delta_spot_is_quantlib_delta(market, options):
    h = 1e-4
    fd = factor_delta(options, market, {"spot": "SPX/spot"}, h)["delta"]
    spot = market["SPX"].value()
    with market.active():
        for i, t in options.trades.items():
            delta = options.instruments[i].delta() * t.quantity
            assert fd.loc["spot", i] / (h * spot) == pytest.approx(delta, rel=1e-5)


def test_factor_delta_vega_rule(market, options):
    keys = _vol_keys(market)
    h = 1e-4
    fd = factor_delta(options, market, {"vega": lambda x: dict.fromkeys(keys, x)}, h)["delta"]
    with market.active():
        for i, t in options.trades.items():
            vega = options.instruments[i].vega() * t.quantity * h
            assert fd.loc["vega", i] == pytest.approx(vega, rel=1e-2)


def test_sticky_moneyness_delta_adds_vega_times_skew(market, options):
    """ssr=0 delta − ssr=1 delta ≈ vega × ∂σ/∂lnS, sticky moneyness면 ∂σ/∂lnS = −skew(T, K)."""
    h = 1e-3
    moves = {f"ssr={x}": (lambda r, x=x: ssr(market, "SPX", "SPX_VOL", r, x)) for x in [0.0, 1.0]}
    fd = factor_delta(options, market, moves, h)["delta"]
    s = market.objects["SPX_VOL"]
    with market.active():
        for i, t in options.trades.items():
            d, k = to_ql_date(t.expiry), t.strike
            e = 1e-3
            skew = (s.vol(d, k * math.exp(e)) - s.vol(d, k * math.exp(-e))) / (2 * e)
            vega = options.instruments[i].vega() * t.quantity
            expected = vega * (-skew) * math.log1p(h)
            assert fd.loc["ssr=0.0", i] - fd.loc["ssr=1.0", i] == pytest.approx(expected, rel=5e-2)
