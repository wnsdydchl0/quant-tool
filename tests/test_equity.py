from datetime import date
from pathlib import Path

import pytest
import QuantLib as ql

from quanttool.market.curves import to_ql_date
from quanttool.portfolio import Portfolio

ROOT = Path(__file__).resolve().parents[1]
ASOF = date(2026, 10, 23)
NYSE = ql.UnitedStates(ql.UnitedStates.NYSE)
DC = ql.Actual365Fixed()
EXPIRIES = ["1M", "3M", "6M", "1Y", "2Y"]
STRIKES = [80, 90, 100, 110, 120]


@pytest.fixture
def options(config, market):
    return Portfolio.from_file(ROOT / "positions" / "spx_options.yaml").build(market, config)


def _direct_surface(q):
    today = to_ql_date(ASOF)
    spot = q["EQ/SPOT/SPX"]
    dates = [NYSE.advance(today, ql.Period(e)) for e in EXPIRIES]
    vols = ql.Matrix([[q[f"EQ/VOL/SPX/{e}/{k}"] for e in EXPIRIES] for k in STRIKES])
    flat = ql.BlackVarianceSurface.ConstantExtrapolation
    s = ql.BlackVarianceSurface(
        today, NYSE, dates, [spot * k / 100 for k in STRIKES], vols, DC, flat, flat
    )
    s.enableExtrapolation()
    return s, dates


def _direct_option(market, q, trade, engine):
    """시장 객체 대신 QuantLib으로 직접: 평탄 배당 커브 + 직접 서페이스 + 시장 UST Handle."""
    today = to_ql_date(ASOF)
    surface, _ = _direct_surface(q)
    div = ql.YieldTermStructureHandle(ql.FlatForward(today, q["EQ/DIVYIELD/SPX"], DC))
    process = ql.GeneralizedBlackScholesProcess(
        ql.QuoteHandle(ql.SimpleQuote(q["EQ/SPOT/SPX"])),
        div,
        market["UST"],
        ql.BlackVolTermStructureHandle(surface),
    )
    kind = ql.Option.Call if trade.option_type == "Call" else ql.Option.Put
    opt = ql.VanillaOption(
        ql.PlainVanillaPayoff(kind, trade.strike), ql.EuropeanExercise(to_ql_date(trade.expiry))
    )
    opt.setPricingEngine(engine(process))
    return opt


def test_surface_matches_direct(market, quotes):
    direct, dates = _direct_surface(quotes[ASOF])
    with market.active():
        vol = market["SPX_VOL"]
        for d in [dates[0], dates[2], dates[3] + 40, dates[4]]:
            for k in [4500.0, 5400.0, 6000.0, 6333.0, 7300.0]:
                assert vol.blackVol(d, k, True) == pytest.approx(
                    direct.blackVol(d, k, True), abs=1e-14
                )


def test_vol_and_spot_factors(market, quotes):
    q = quotes[ASOF]
    keys = [k for k in market.factors() if k.startswith("SPX_VOL/")]
    assert len(keys) == 25 and "SPX/spot" in market.factors() and "SPX_DIV/1Y" in market.factors()
    expiry = market.objects["SPX_VOL"].dates[3]
    with market.active(), market.scenario({**{k: 0.01 for k in keys}, "SPX/spot": 0.02}):
        assert market["SPX"].value() == pytest.approx(q["EQ/SPOT/SPX"] * 1.02, abs=1e-12)
        assert market["SPX_VOL"].blackVol(expiry, 6000.0) == pytest.approx(
            q["EQ/VOL/SPX/1Y/100"] + 0.01, abs=1e-14
        )
    with market.active():
        assert market["SPX"].value() == q["EQ/SPOT/SPX"]  # reset


def test_analytic_bs_matches_direct(market, quotes, options):
    npv = options.npvs()
    with market.active():
        for i, t in options.trades.items():
            opt = _direct_option(market, quotes[ASOF], t, ql.AnalyticEuropeanEngine)
            assert npv[i] == pytest.approx(opt.NPV() * t.quantity, rel=1e-13)


def test_fd_engine_close_to_analytic(config, market):
    recs = Portfolio.from_file(ROOT / "positions" / "spx_options.yaml").trades.values()
    fd = Portfolio.from_records([{**t.model_dump(), "engine": "FdBS"} for t in recs])
    fd.build(market, config)
    analytic = Portfolio.from_file(ROOT / "positions" / "spx_options.yaml").build(market, config)
    assert list(fd.engines)[0][0] == "FdBS"
    assert fd.npvs().to_numpy() == pytest.approx(analytic.npvs().to_numpy(), rel=1e-3)


def test_sticky_strike_spot_delta_is_quantlib_delta(market, options):
    """현물만 흔들면 행사가 고정 vol → QuantLib delta (vol 고정)와 같다."""
    h = 1e-4
    with market.scenario({"SPX/spot": h}):
        up = options.npvs()
    with market.scenario({"SPX/spot": -h}):
        down = options.npvs()
    spot = market["SPX"].value()
    with market.active():
        for i, t in options.trades.items():
            delta = options.instruments[i].delta() * t.quantity
            assert (up[i] - down[i]) / (2 * h * spot) == pytest.approx(delta, rel=1e-5)


def test_parallel_vol_shift_is_vega(market, options):
    """격자 전체 vol +1bp ≈ vega × 1bp (만기가 격자점 사이라 분산 보간 차이만큼 근사)."""
    keys = [k for k in market.factors() if k.startswith("SPX_VOL/")]
    base = options.npvs()
    with market.scenario(dict.fromkeys(keys, 1e-4)):
        bumped = options.npvs()
    with market.active():
        for i, t in options.trades.items():
            vega = options.instruments[i].vega() * t.quantity * 1e-4
            assert bumped[i] - base[i] == pytest.approx(vega, rel=1e-2)


def test_vol_roll_is_forward_forward(market):
    """roll 뒤 σ'²(T)·(T − t_d) = σ²(T)·T − σ²(d)·t_d (행사가별)."""
    s = market.objects["SPX_VOL"]
    today, d = to_ql_date(ASOF), to_ql_date(date(2026, 10, 26))
    k, x = s.strikes[1], s.dates[3]
    var_x, var_d = s.base.blackVariance(x, k), s.base.blackVariance(d, k)
    market.roll(date(2026, 10, 26))
    try:
        with market.active():
            rolled = market["SPX_VOL"]
            assert rolled.referenceDate() == d
            t_x = DC.yearFraction(today, x) - DC.yearFraction(today, d)
            assert rolled.blackVol(x, k) ** 2 * t_x == pytest.approx(var_x - var_d, rel=1e-12)
    finally:
        market.roll(ASOF)
