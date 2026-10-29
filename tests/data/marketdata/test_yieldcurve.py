from datetime import date

import pytest
import QuantLib as ql

from quanttool.data.marketdata import InMemoryLoader, MarketDatum, TodaysMarket
from quanttool.data.marketdata.diagnostics import helper_repricing
from quanttool.data.utilities import parsers
from quanttool.qle.termstructures import bill_price, bill_yield

ASOF = date(2026, 10, 23)


@pytest.mark.parametrize("days", [28, 91, 182, 183, 364])
def test_bill_price_yield_round_trip(days):
    assert bill_yield(bill_price(0.042, days), days) == pytest.approx(0.042, abs=1e-14)


def test_bill_price_continuous_at_half_year():
    # 단리 구간과 반기복리 구간이 반년(182.5일)에서 이어진다
    h = 182.5
    simple = 100.0 / (1.0 + 0.04 * h / 365.0)
    compounded = 100.0 / (1.0 + 0.04 / 2.0)
    assert simple == pytest.approx(compounded, rel=1e-15)
    assert bill_price(0.04, 182) == pytest.approx(simple, rel=1e-3)


def test_par_bond_priced_at_par(cfg, snap):
    # 쿠폰 = par yield이고 정규 일정이므로 구축 시점 쿠폰채 헬퍼 가격은 정확히 100
    bond_ids = {
        q
        for seg in cfg.curve_configs["UST"].segments
        if seg.type == "FixedRateBond"
        for q in seg.quote_ids()
    }
    checked = [h for h in snap.curve_helpers("UST") if h.quote_id in bond_ids]
    assert len(checked) == 7
    for h in checked:
        assert h.helper.quote().value() == pytest.approx(100.0, abs=1e-10)


def test_helper_repricing_error_below_tolerance(snap):
    table = helper_repricing(snap, "UST")
    assert len(table) == 13
    assert table["error_bp"].abs().max() < 0.01


def _direct_quantlib_curve(cfg, quotes: dict[str, float]):
    """같은 커브를 표준 QuantLib 헬퍼로 직접 조립 (가격 100 par bond = FixedRateBondHelper)."""
    conv = cfg.conventions["UST"]
    cal = parsers.calendar(conv.calendar)
    dc = parsers.day_counter(conv.day_count)
    today = ql.Settings.instance().evaluationDate
    settle = cal.advance(today, conv.settlement_days, ql.Days)
    helpers = []
    for seg in cfg.curve_configs["UST"].segments:
        for qid, tenor in zip(seg.quote_ids(), seg.tenors, strict=True):
            y = quotes[qid]
            mat = settle + ql.Period(tenor)
            if seg.type == "ZeroCouponBill":
                mat = cal.adjust(mat, ql.Following)
                bond = ql.ZeroCouponBond(1, cal, 100.0, mat, ql.Following, 100.0, settle)
                price = ql.QuoteHandle(ql.SimpleQuote(bill_price(y, mat - settle)))
                helpers.append(ql.BondHelper(price, bond))
            else:
                sch = ql.Schedule(
                    settle,
                    mat,
                    ql.Period(ql.Semiannual),
                    cal,
                    ql.Unadjusted,
                    ql.Unadjusted,
                    ql.DateGeneration.Backward,
                    False,
                )
                helpers.append(
                    ql.FixedRateBondHelper(
                        ql.QuoteHandle(ql.SimpleQuote(100.0)),
                        1,
                        100.0,
                        sch,
                        [y],
                        dc,
                        ql.Unadjusted,
                        100.0,
                        settle,
                    )
                )
    return ql.PiecewiseLogCubicDiscount(0, cal, helpers, ql.Actual365Fixed())


def test_matches_direct_quantlib(cfg, snap, loader):
    with snap.active():
        direct = _direct_quantlib_curve(cfg, {q.id: q.value for q in loader.load(ASOF)})
        ours = snap.yield_curve("UST")
        for years in [0.1, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]:
            d = direct.referenceDate() + ql.Period(int(years * 12), ql.Months)
            assert ours.discount(d) == pytest.approx(direct.discount(d), abs=1e-12)


def test_quote_change_propagates(linked_snap):
    snap = linked_snap
    with snap.active():
        curve = snap.yield_curve("UST")
        before = curve.zeroRate(10.0, ql.Continuous).rate()
        snap.quotes["UST/PAR/10Y"].setValue(0.0398 + 0.0010)
        after = curve.zeroRate(10.0, ql.Continuous).rate()
    assert after - before == pytest.approx(0.0010, abs=0.0003)
    # 쿠폰은 고정이고 가격으로 전달되므로, 바뀐 시세도 정확히 재현해야 한다
    table = helper_repricing(snap, "UST").set_index("quote_id")
    assert table.loc["UST/PAR/10Y", "market"] == pytest.approx(0.0408)
    assert table["error_bp"].abs().max() < 0.01


def test_todays_market_is_frozen_at_asof(cfg, loader, snap):
    """기준일은 asof 고정이고, 이후 시세·평가일·다른 날짜 시장과 무관하다 (ORE TodaysMarket)."""
    curve = snap.yield_curve("UST")
    d = ql.Date(17, 3, 2031)
    assert curve.referenceDate() == ql.Date(23, 10, 2026)
    before = curve.discount(d)
    TodaysMarket.from_config(date(2026, 10, 22), cfg, loader)  # 다른 날짜 시장 구축
    snap.quotes["UST/PAR/10Y"].setValue(0.05)
    settings = ql.Settings.instance()
    previous = settings.evaluationDate
    settings.evaluationDate = ql.Date(1, 1, 2027)
    try:
        assert curve.referenceDate() == ql.Date(23, 10, 2026)
        assert curve.discount(d) == before
    finally:
        settings.evaluationDate = previous


def test_active_restores_evaluation_date(snap):
    settings = ql.Settings.instance()
    settings.evaluationDate = ql.Date(1, 1, 2020)
    with snap.active():
        assert settings.evaluationDate == ql.Date(23, 10, 2026)
    assert settings.evaluationDate == ql.Date(1, 1, 2020)


def test_missing_quote_raises(cfg):
    loader = InMemoryLoader([MarketDatum(ASOF, "UST/PAR/2Y", 0.035)])
    with pytest.raises(KeyError, match="UST/PAR/1M"):
        TodaysMarket.from_config(ASOF, cfg, loader)


def test_unknown_curve(snap):
    with pytest.raises(KeyError, match="KRW_KTB"):
        snap.yield_curve("KRW_KTB")


def test_names_share_one_recipe_curve(snap):
    """discount_curve("USD")와 yield_curve("UST")가 같은 레시피 → 같은 커브 객체."""
    d = ql.Date(15, 8, 2036)
    assert snap.discount_curve("USD").discount(d) == snap.yield_curve("UST").discount(d)
    assert snap.discount_curve("USD") is snap.yield_curve("UST")  # 같은 Handle


def test_configuration_falls_back_to_default(snap):
    """없는 configuration은 default에서 찾는다 (ORE marketimpl.cpp lookup)."""
    d = ql.Date(15, 8, 2036)
    assert snap.yield_curve("UST", "pricing").discount(d) == snap.yield_curve("UST").discount(d)
    with pytest.raises(KeyError, match="Discount"):
        snap.discount_curve("EUR")
