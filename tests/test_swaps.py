from datetime import date

import pytest
import QuantLib as ql

from quanttool import portfolio as pf
from quanttool.analysis.risk import key_rate
from quanttool.analysis.scenarios import parallel
from quanttool.market.curves import to_ql_date
from quanttool.portfolio import Portfolio

ASOF = date(2026, 10, 23)
CAL = ql.SouthKorea(ql.SouthKorea.Settlement)


def _spot():
    d = CAL.advance(to_ql_date(ASOF), 1, ql.Days)  # CD91 fixing_days = 1
    return date(d.year(), d.month(), d.dayOfMonth())


def _par_swap(rate, years, pay_fixed=True, **kw):
    s = _spot()
    rec = dict(id=f"IRS_{years}Y", type="IRSwap", notional=1e10, fixed_rate=rate,
               pay_fixed=pay_fixed, start_date=s, maturity_date=s.replace(year=s.year + years),
               conventions="KRW_IRS", index="CD91", discount="KOFR")  # fmt: skip
    return {**rec, **kw}


@pytest.fixture
def swaps(config, market, load):
    return load("krw_swaps").build(market, config)


@pytest.mark.parametrize("years", [2, 5, 10])
def test_par_swap_reprices_quote(config, market, quotes, years):
    q = quotes[ASOF][f"IRS/RATE/KRW/CD91/{years}Y"]
    book = Portfolio.from_records([_par_swap(q, years)]).build(market, config)
    inst = book.instruments[f"IRS_{years}Y"]
    with market.active():
        assert inst.fairRate() == pytest.approx(q, abs=1e-10)
    assert abs(book.npv()) < 1e-8 * 1e10


def test_swap_matches_direct_quantlib(config, market, swaps):
    """같은 시장 Handle·지수로 직접 만든 VanillaSwap + DiscountingSwapEngine과 같다."""
    t = swaps.trades["IRS_5Y_PAY"]
    with market.active():
        idx = market.index("CD91")
        start, end = to_ql_date(t.start_date), to_ql_date(t.maturity_date)
        mf = ql.ModifiedFollowing
        fixed = ql.Schedule(start, end, ql.Period(ql.Quarterly), CAL, mf, mf,
                            ql.DateGeneration.Backward, False)  # fmt: skip
        flt = ql.Schedule(start, end, ql.Period("3M"), CAL, mf, mf,
                          ql.DateGeneration.Backward, False)  # fmt: skip
        sw = ql.VanillaSwap(ql.VanillaSwap.Payer, t.notional, fixed, t.fixed_rate,
                            ql.Actual365Fixed(), flt, idx, 0.0, ql.Actual365Fixed())  # fmt: skip
        sw.setPricingEngine(ql.DiscountingSwapEngine(market["KOFR"]))
        expected = sw.NPV()
    assert swaps.npvs()["IRS_5Y_PAY"] == pytest.approx(expected, abs=1e-6)


def test_engine_from_pricing_config_and_override(config, market, monkeypatch):
    """products.yaml engines.defaults가 기본 엔진을 고르고, 거래의 engine 필드가 덮어쓴다."""
    assert config.pricing.defaults["IRSwap"] == "DiscountingSwap"
    # 같은 스왑을 CD91로 할인하는 엔진 (예: 단일 커브 비교)
    monkeypatch.setitem(pf.ENGINES, "SingleCurveSwap",
                        lambda t, m, p: ql.DiscountingSwapEngine(m[t.index]))  # fmt: skip
    rec = _par_swap(0.03, 10)
    book = Portfolio.from_records([rec, {**rec, "id": "single", "engine": "SingleCurveSwap"}])
    book.build(market, config)
    assert set(book.engines) == {("DiscountingSwap", "KOFR", "CD91"),
                                 ("SingleCurveSwap", "KOFR", "CD91")}  # fmt: skip
    npv = book.npvs()
    assert npv["single"] != pytest.approx(npv["IRS_10Y"], rel=1e-6)
    with pytest.raises(KeyError, match="엔진"):
        Portfolio.from_records([{**rec, "engine": "Nope"}]).build(market, config)


def test_swaps_share_one_engine(swaps):
    assert list(swaps.engines) == [("DiscountingSwap", "KOFR", "CD91")]


def test_dual_curve_key_rates_separate(config, market, swaps):
    """할인(KOFR)과 예측(CD91) 민감도가 따로 나온다. 고정 지급 5Y는 CD91 상승에 이익."""
    kr_cd = key_rate(swaps, market, config.risk, "CD91")["delta"]
    kr_ois = key_rate(swaps, market, config.risk, "KOFR")["delta"]
    assert kr_cd.loc[:, "IRS_5Y_PAY"].sum() > 0
    assert kr_cd.loc[:, "IRS_10Y_REC"].sum() < 0
    assert abs(kr_ois["total"]).sum() > 0
    # 예측 커브 key rate 합 ≈ 평행 1bp (1차)
    base = swaps.npv()
    with market.scenario(parallel(market, "CD91", 1e-4)):
        par = swaps.npv() - base
    assert kr_cd["total"].sum() == pytest.approx(par, rel=1e-2)


def test_theta_realizes_index_fixing_from_forward(market, swaps):
    """roll 뒤 지난 fixing(asof)은 오늘의 예측 선도로 채워지고, 되돌리면 지워진다."""
    from quanttool.analysis.risk import theta

    idx = market.index("CD91")
    fix = to_ql_date(ASOF)
    with market.active():
        forward = idx.fixing(fix, True)
    th = theta(swaps, market, date(2026, 10, 26))
    assert th.notna().all()
    assert not idx.hasHistoricalFixing(fix)
    market.roll(date(2026, 10, 26))
    try:
        assert idx.pastFixing(fix) == pytest.approx(forward, abs=1e-15)
    finally:
        market.roll(ASOF)
    assert not idx.hasHistoricalFixing(fix)
