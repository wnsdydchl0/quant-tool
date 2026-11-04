from datetime import date

import pytest
import QuantLib as ql

from quanttool.config import Config

ASOF = date(2026, 10, 23)
CAL = ql.SouthKorea(ql.SouthKorea.Settlement)
DC = ql.Actual365Fixed()


def _direct(q):
    """KOFR OIS 커브와 CD91 듀얼 커브를 QuantLib 헬퍼로 직접 조립."""
    today = ql.Date.from_date(ASOF)
    ql.Settings.instance().evaluationDate = today
    kofr_idx = ql.OvernightIndex("KOFR", 0, ql.KRWCurrency(), CAL, DC)
    ois = [
        ql.OISRateHelper(
            1, ql.Period(t), ql.QuoteHandle(ql.SimpleQuote(q[f"OIS/RATE/KRW/KOFR/{t}"])), kofr_idx
        )
        for t in ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]
    ]
    kofr = ql.PiecewiseLogLinearDiscount(today, ois, ql.Actual365Fixed())
    kofr.enableExtrapolation()
    disc = ql.YieldTermStructureHandle(kofr)
    cd = ql.IborIndex(
        "CD91", ql.Period("3M"), 1, ql.KRWCurrency(), CAL, ql.ModifiedFollowing, False, DC
    )
    helpers = [ql.DepositRateHelper(ql.QuoteHandle(ql.SimpleQuote(q["MM/RATE/KRW/CD91/3M"])), cd)]
    for t in ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y"]:
        r = ql.QuoteHandle(ql.SimpleQuote(q[f"IRS/RATE/KRW/CD91/{t}"]))
        helpers.append(
            ql.SwapRateHelper(
                r,
                ql.Period(t),
                CAL,
                ql.Quarterly,
                ql.ModifiedFollowing,
                DC,
                cd,
                ql.QuoteHandle(),
                ql.Period(0, ql.Days),
                disc,
            )
        )
    cd91 = ql.PiecewiseLogLinearDiscount(today, helpers, ql.Actual365Fixed())
    return kofr, cd91


def test_build_order_puts_discount_curve_first(config):
    order = config.build_order()
    assert order.index("KOFR") < order.index("CD91")


def test_dual_curve_matches_direct_quantlib(market, quotes):
    kofr, cd91 = _direct(quotes[ASOF])
    with market.active():
        for years in [0.1, 0.5, 1, 2, 4, 7, 10]:
            assert market["KOFR"].discount(years) == pytest.approx(kofr.discount(years), abs=1e-12)
            assert market["CD91"].discount(years) == pytest.approx(cd91.discount(years), abs=1e-12)


def test_index_forecasts_from_its_curve(market):
    idx = market.index("CD91")
    with market.active():
        d = CAL.adjust(ql.Date(14, 1, 2028))
        value = idx.valueDate(d)
        expected = market["CD91"].forwardRate(value, idx.maturityDate(value), DC, ql.Simple).rate()
        assert idx.fixing(d) == pytest.approx(expected, abs=1e-14)
        with market.scenario({"CD91/2Y": 1e-4}):  # 예측 커브 요인을 흔들면 지수도 따라온다
            assert idx.fixing(d) > expected


def test_cycle_and_missing_dependency_rejected(config):
    data = config.model_dump()
    data["curves"]["KOFR"]["discount_curve"] = "CD91"
    with pytest.raises(ValueError, match="순환"):
        Config.model_validate(data).build_order()
    data = config.model_dump()
    data["curves"]["CD91"]["discount_curve"] = "NOPE"
    with pytest.raises(ValueError, match="NOPE"):
        Config.model_validate(data)


def test_frozen_projection_curve_ignores_discount_shock(market):
    """얼린 커브는 의존 커브 요인을 흔들어도 다시 부트스트랩하지 않는다 (요인끼리 독립)."""
    with market.active():
        before, kofr = market["CD91"].discount(5.0), market["KOFR"].discount(5.0)
        with market.scenario({"KOFR/5Y": 1e-4}):
            assert market["CD91"].discount(5.0) == before
            assert market["KOFR"].discount(5.0) < kofr
