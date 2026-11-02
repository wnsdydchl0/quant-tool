from datetime import date
from pathlib import Path

import pytest
import QuantLib as ql

from quanttool.config import load_config
from quanttool.market import build_market
from quanttool.market.curves import (
    bill_price,
    bill_yield,
    curve_shape,
    curve_table,
    helper_repricing,
    to_ql_date,
)
from quanttool.market.quotes import read_quotes

ASOF = date(2026, 10, 23)
K = "BOND/YIELD/USD/UST/PAR/{}"
BP = 1e-4


@pytest.mark.parametrize("days", [28, 91, 182, 183, 364])
def test_bill_price_yield_round_trip(days):
    assert bill_yield(bill_price(0.042, days), days) == pytest.approx(0.042, abs=1e-14)


def test_read_quotes(quotes, tmp_path):
    assert list(quotes) == [date(2026, 10, 22), ASOF]
    assert quotes[ASOF][K.format("10Y")] == pytest.approx(0.0398)
    p = tmp_path / "m.txt"
    p.write_text("# 주석\n2026-01-05, A/B/1Y, 0.04\n2026-01-05\tA/B/1Y\t0.05\n")
    with pytest.raises(ValueError, match="중복"):
        read_quotes(p)


def test_config_errors(tmp_path):
    import shutil

    import yaml
    from pydantic import ValidationError

    root = tmp_path / "configs"
    shutil.copytree(Path(__file__).resolve().parents[1] / "configs", root)
    p = root / "conventions" / "rates.yaml"
    d = yaml.safe_load(p.read_text())
    d["UST"]["calendar"] = "Mars"
    p.write_text(yaml.safe_dump(d))
    with pytest.raises(ValidationError, match="Mars"):
        load_config(root)


def test_helper_repricing_and_par_bonds(market):
    table = helper_repricing(market.built["UST"], ASOF)
    assert len(table) == 13 and table["error_bp"].abs().max() < 0.01
    bond_keys = {K.format(t) for t in ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]}
    bonds = [h for h in market.built["UST"].helpers if h.key in bond_keys]
    assert len(bonds) == 7
    assert all(h.helper.quote().value() == pytest.approx(100.0, abs=1e-10) for h in bonds)


def _direct_curve(config, q: dict):
    """같은 커브를 표준 QuantLib 헬퍼로 직접 조립 (par bond = FixedRateBondHelper 가격 100)."""
    conv = config.conventions["UST"]
    cal, dc = conv.ql_calendar(), conv.ql_day_count()
    today = to_ql_date(ASOF)
    settle = cal.advance(today, 1, ql.Days)
    helpers = []
    for seg in config.curves["UST"].segments:
        for t in seg.tenors:
            y = q[K.format(t)]
            mat = settle + ql.Period(t)
            if seg.type == "Bill":
                mat = cal.adjust(mat, ql.Following)
                bond = ql.ZeroCouponBond(1, cal, 100.0, mat, ql.Following, 100.0, settle)
                price = ql.QuoteHandle(ql.SimpleQuote(bill_price(y, mat - settle)))
                helpers.append(ql.BondHelper(price, bond))
            else:
                sch = ql.Schedule(settle, mat, ql.Period(ql.Semiannual), cal, ql.Unadjusted,
                                  ql.Unadjusted, ql.DateGeneration.Backward, False)  # fmt: skip
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
                    )  # fmt: skip
                )
    return ql.PiecewiseLogCubicDiscount(today, helpers, ql.Actual365Fixed())


def test_matches_direct_quantlib(config, quotes, market):
    with market.active():
        direct = _direct_curve(config, quotes[ASOF])
        for m in range(1, 361, 7):
            d = direct.referenceDate() + ql.Period(m, ql.Months)
            assert market["UST"].discount(d) == pytest.approx(direct.discount(d), abs=1e-12)


def test_curve_table_par_reproduces_quotes(config, quotes, market):
    conv = config.conventions["UST"]
    with market.active():
        table = curve_table(market["UST"], conv)
    for t in ["2Y", "5Y", "10Y", "30Y"]:
        assert table.loc[t, "par"] == pytest.approx(quotes[ASOF][K.format(t)], abs=1e-8)
    shape = curve_shape(table)
    assert shape["2s10s"] == pytest.approx((table.loc["10Y", "par"] - table.loc["2Y", "par"]) * 1e4)


def test_frozen_curve_ignores_quotes_and_dates(config, quotes, market):
    built = market.built["UST"]
    d = ql.Date(17, 3, 2031)
    before = market["UST"].discount(d)
    built.quotes()[K.format("10Y")].setValue(0.05)  # 시세를 바꾸고
    build_market(date(2026, 10, 22), quotes[date(2026, 10, 22)], config)  # 다른 날짜 시장을 만들고
    with __import__("quanttool.market.curves", fromlist=["x"]).evaluation_date(
        date(2027, 1, 1)
    ):  # 평가일을 옮겨도
        assert market["UST"].referenceDate() == to_ql_date(ASOF)
        assert market["UST"].discount(d) == before


def test_linked_curve_follows_quote(config, quotes):
    m = build_market(ASOF, quotes[ASOF], config, linked=True)
    q = m.built["UST"].quotes()[K.format("10Y")]
    with m.active():
        before = m["UST"].zeroRate(10.0, ql.Continuous).rate()
        q.setValue(q.value() + 0.0010)
        moved = m["UST"].zeroRate(10.0, ql.Continuous).rate() - before
    assert moved == pytest.approx(0.0010, abs=0.0003)
    assert helper_repricing(m.built["UST"], ASOF)["error_bp"].abs().max() < 0.01


def test_base_factor_curve_equals_bootstrapped_curve(market):
    """요인 0이면 시장 커브 = 부트스트랩 커브 (격자 사이·바깥 포함)."""
    with market.active():
        for t in [0.01, 0.3, 1.7, 4.2, 11.0, 27.0, 45.0]:
            assert market["UST"].discount(t) == pytest.approx(
                market.built["UST"].curve.discount(t), abs=1e-14
            )


def test_parallel_shift_exact_and_reset(market):
    s = {k: BP for k in market.factors()}
    with market.active():
        c = market["UST"]
        times = [0.01, 2.5, 13.0, 45.0]
        before = [c.zeroRate(t, ql.Continuous).rate() for t in times]
        with market.scenario(s):
            after = [c.zeroRate(t, ql.Continuous).rate() for t in times]
        restored = [c.zeroRate(t, ql.Continuous).rate() for t in times]
    for b, a, r in zip(before, after, restored, strict=True):
        assert a - b == pytest.approx(BP, abs=1e-12) and r == pytest.approx(b, abs=1e-15)
    assert market.current is None


def test_key_rate_shift_is_local(market):
    with market.active(), market.scenario({"UST/5Y": BP}):
        c = market["UST"]
        moved = [c.zeroRate(t, ql.Continuous).rate() for t in (3.0, 5.0, 7.0)]
    with market.active():
        base = [market["UST"].zeroRate(t, ql.Continuous).rate() for t in (3.0, 5.0, 7.0)]
    diff = [(m - b) / BP for m, b in zip(moved, base, strict=True)]
    assert diff[0] == pytest.approx(0, abs=1e-9) and diff[2] == pytest.approx(0, abs=1e-9)
    assert diff[1] == pytest.approx(1.0, abs=0.01)


def test_apply_checks_and_is_not_cumulative(market):
    market.apply({"UST/5Y": BP})
    market.apply({"UST/5Y": BP})
    assert market.factors()["UST/5Y"].value() == BP
    market.reset()
    with pytest.raises(KeyError, match="없는 요인"):
        market.apply({"UST/11Y": BP})
    with pytest.raises(KeyError, match="KRW"):
        market["KRW"]


def test_roll_is_forward_forward(market):
    nxt = date(2026, 10, 26)
    market.roll(nxt)
    with market.active():
        assert market["UST"].referenceDate() == to_ql_date(nxt)
        implied = ql.ImpliedTermStructure(
            ql.YieldTermStructureHandle(market.built["UST"].curve), to_ql_date(nxt)
        )
        for t in [0.5, 5.0, 25.0]:
            assert market["UST"].discount(t) == pytest.approx(implied.discount(t), abs=1e-14)
    market.roll(ASOF)
    assert market["UST"].referenceDate() == to_ql_date(ASOF)
