from datetime import date
from pathlib import Path

import pytest
import QuantLib as ql

from quanttool.market import Market, build_market
from quanttool.market.curves import to_ql_date
from quanttool.market.equity import HESTON_PARAMS
from quanttool.portfolio import Portfolio

ROOT = Path(__file__).resolve().parents[1]
ASOF = date(2026, 10, 23)
TRUE = {"theta": 0.045, "kappa": 1.8, "sigma": 0.6, "rho": -0.7, "v0": 0.033}  # 시세 생성 값
VOL_KEYS = lambda m: [k for k in m.factors() if k.startswith("SPX_VOL/")]  # noqa: E731


@pytest.fixture
def heston_book(config, market):
    recs = Portfolio.from_file(ROOT / "positions" / "spx_options.yaml").trades.values()
    rows = [{**t.model_dump(), "engine": "AnalyticHeston", "model": "SPX_HESTON"} for t in recs]
    return Portfolio.from_records(rows).build(market, config)


def test_calibration_recovers_generating_parameters(market):
    """시세 IV는 알려진 Heston 가격에서 역산(소수 4자리) → 캘리브레이션이 그 파라미터를 되찾는다."""
    h = market.objects["SPX_HESTON"]
    p = h.params()
    assert p["v0"] == pytest.approx(TRUE["v0"], abs=2e-4)
    assert p["theta"] == pytest.approx(TRUE["theta"], abs=1e-3)
    assert p["kappa"] == pytest.approx(TRUE["kappa"], abs=0.05)
    assert p["sigma"] == pytest.approx(TRUE["sigma"], abs=5e-3)
    assert p["rho"] == pytest.approx(TRUE["rho"], abs=2e-3)
    assert max(map(abs, h.calibration_errors())) < 5e-3


def test_analytic_heston_matches_direct(market, quotes, heston_book):
    q = quotes[ASOF]
    p = market.objects["SPX_HESTON"].params()
    npv = heston_book.npvs()
    with market.active():
        today = to_ql_date(ASOF)
        div = ql.YieldTermStructureHandle(
            ql.FlatForward(today, q["EQ/DIVYIELD/SPX"], ql.Actual365Fixed())
        )
        spot = ql.QuoteHandle(ql.SimpleQuote(q["EQ/SPOT/SPX"]))
        model = ql.HestonModel(ql.HestonProcess(market["UST"], div, spot, p["v0"], p["kappa"],
                                                p["theta"], p["sigma"], p["rho"]))  # fmt: skip
        for i, t in heston_book.trades.items():
            kind = ql.Option.Call if t.option_type == "Call" else ql.Option.Put
            opt = ql.VanillaOption(ql.PlainVanillaPayoff(kind, t.strike),
                                   ql.EuropeanExercise(to_ql_date(t.expiry)))  # fmt: skip
            opt.setPricingEngine(ql.AnalyticHestonEngine(model))
            assert npv[i] == pytest.approx(opt.NPV() * t.quantity, rel=1e-10)
    assert list(heston_book.engines)[0][0] == "AnalyticHeston"


def test_heston_close_to_bs_on_its_own_surface(heston_book, config, market):
    bs = Portfolio.from_file(ROOT / "positions" / "spx_options.yaml").build(market, config)
    assert heston_book.npvs().to_numpy() == pytest.approx(bs.npvs().to_numpy(), rel=1e-2)


def test_recalibrates_on_vol_but_not_on_rates(market):
    h = market.objects["SPX_HESTON"]
    base = h.params()
    with market.scenario(dict.fromkeys(VOL_KEYS(market), 0.01)):
        bumped = h.params()
        assert bumped["v0"] > base["v0"] + 1e-3  # vol ↑ → 분산 ↑
    assert h.params() == base  # reset → 캐시된 오늘 캘리브레이션
    with market.scenario({"UST/5Y": 0.001}):  # recalibrate_on 밖: 파라미터 고정
        assert h.params() == base
    n = len(h._cache)
    with market.scenario(dict.fromkeys(VOL_KEYS(market), 0.01)):
        assert h.params() == bumped and len(h._cache) == n  # 같은 입력은 캐시


def test_fixed_policy_keeps_parameters(config, quotes):
    spx = config.equities["SPX"]
    fixed = spx.model_copy(update={"heston": spx.heston.model_copy(update={"recalibrate_on": []})})
    cfg = config.model_copy(update={"equities": {"SPX": fixed}})
    market = build_market(ASOF, quotes[ASOF], cfg)
    h = market.objects["SPX_HESTON"]
    base = h.params()
    with market.scenario({**dict.fromkeys(VOL_KEYS(market), 0.01), "SPX/spot": 0.05}):
        assert h.params() == base


def test_parameter_factors(market, heston_book):
    h = market.objects["SPX_HESTON"]
    assert {f"SPX_HESTON/{p}" for p in HESTON_PARAMS} <= set(market.factors())
    base, npv0 = h.params(), heston_book.npv()
    with market.scenario({"SPX_HESTON/v0": 0.001}):
        assert h.params()["v0"] == pytest.approx(base["v0"] + 0.001, abs=1e-15)
        assert heston_book.npv() != pytest.approx(npv0, rel=1e-6)
    assert h.params() == base and heston_book.npv() == pytest.approx(npv0, rel=1e-14)


def test_dependency_order_and_cycle(market):
    order = market._order
    for dep in market.objects["SPX_HESTON"].depends_on:
        assert order.index(dep) < order.index("SPX_HESTON")

    class Obj:
        def __init__(self, deps):
            self.depends_on = deps

        def factors(self):
            return {}

    with pytest.raises(ValueError, match="순환"):
        Market(ASOF, {"a": Obj(["b"]), "b": Obj(["a"])})
