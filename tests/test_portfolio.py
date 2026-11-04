from datetime import date

import pytest
import QuantLib as ql

from quanttool.market import build_market
from quanttool.market.curves import to_ql_date
from quanttool.portfolio import Portfolio, trade

ASOF = date(2026, 10, 23)


def _direct_npv(t, curve) -> float:
    """QuantLib으로 직접 조립한 같은 채권의 NPV × 포지션."""
    cal = ql.UnitedStates(ql.UnitedStates.GovernmentBond)
    sch = ql.Schedule(
        to_ql_date(t.issue_date),
        to_ql_date(t.maturity_date),
        ql.Period(ql.Semiannual),
        cal,
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        False,
    )
    bond = ql.FixedRateBond(
        1,
        100.0,
        sch,
        [t.coupon],
        ql.ActualActual(ql.ActualActual.Bond),
        ql.Unadjusted,
        100.0,
        to_ql_date(t.issue_date),
    )
    bond.setPricingEngine(ql.DiscountingBondEngine(curve))
    return bond.NPV() * t.notional / 100.0


def test_npv_matches_direct_quantlib(book, market):
    npvs = book.npvs()
    with market.active():
        for i, t in book.trades.items():
            direct = _direct_npv(t, ql.YieldTermStructureHandle(market.objects["UST"].base))
            assert npvs[i] == pytest.approx(direct, rel=1e-12)
    assert npvs["UST_30Y"] < 0  # 매도


def test_one_engine_per_curve(book):
    assert len(book.instruments) == 4 and list(book.engines) == [("DiscountingBond", "UST")]


def test_same_trades_on_another_market(config, quotes, book):
    prev = build_market(date(2026, 10, 22), quotes[date(2026, 10, 22)], config)
    today = book.npvs()
    book.build(prev, config)
    yesterday = book.npvs()
    assert (today != yesterday).all()


def test_scenario_moves_every_trade_on_the_curve(book, market):
    base = book.npvs()
    with market.scenario({k: 1e-4 for k in market.factors()}):
        up = book.npvs()
    assert ((up - base)[["UST_2Y", "UST_5Y", "UST_10Y"]] < 0).all() and (up - base)["UST_30Y"] > 0
    assert (book.npvs() == base).all()  # 해제 후 원상태


def test_errors(config, market):
    rec = {
        "id": "X",
        "notional": 1.0,
        "coupon": 0.04,
        "issue_date": "2026-01-01",
        "maturity_date": "2030-01-01",
        "conventions": "UST",
        "curve": "UST",
    }
    with pytest.raises(ValueError, match="중복"):
        Portfolio.from_records([rec, rec])
    with pytest.raises(KeyError):
        Portfolio.from_records([{**rec, "type": "Swaption"}])
    with pytest.raises(RuntimeError):
        Portfolio.from_records([rec]).npvs()
    with pytest.raises(KeyError, match="KRW"):
        Portfolio.from_records([{**rec, "curve": "KRW"}]).build(market, config)


def test_product_template_equals_explicit_record(config, market):
    """템플릿 + 거래 값 = 모든 필드를 직접 쓴 레코드 (같은 명세, 같은 NPV)."""
    explicit = {"id": "N", "notional": 1e7, "coupon": 0.04, "issue_date": "2026-08-15",
                "maturity_date": "2036-08-15", "conventions": "UST", "curve": "UST"}  # fmt: skip
    t = trade(
        config,
        "UST_NOTE",
        **{k: v for k, v in explicit.items() if k not in ("conventions", "curve")},
    )
    assert t.product == "UST_NOTE" and t.conventions == "UST" and t.curve == "UST"
    a = Portfolio([t]).build(market, config)
    b = Portfolio.from_records([explicit]).build(market, config)
    assert a.npv() == pytest.approx(b.npv(), rel=1e-15)


def test_record_overrides_template_and_unknown_template(config, market):
    rec = {"id": "s", "product": "KRW_IRS_CD91", "notional": 1e10, "fixed_rate": 0.03,
           "start_date": "2026-10-26", "maturity_date": "2031-10-26",
           "discount": "CD91"}  # fmt: skip
    t = Portfolio.from_records([rec], config.products).trades["s"]
    assert t.discount == "CD91" and t.index == "CD91" and t.conventions == "KRW_IRS"
    with pytest.raises(KeyError, match="템플릿"):
        Portfolio.from_records([{**rec, "product": "NOPE"}], config.products)


def test_trades_from_code_reproduce_position_file(config, market, load):
    file_book = load("krw_swaps")
    code_book = Portfolio([
        trade(config, "KRW_IRS_CD91", id="IRS_5Y_PAY", notional=1e10, fixed_rate=0.0288,
              pay_fixed=True, start_date=date(2026, 10, 26), maturity_date=date(2031, 10, 26)),
        trade(config, "KRW_IRS_CD91", id="IRS_10Y_REC", notional=5e9, fixed_rate=0.03,
              pay_fixed=False, start_date=date(2026, 10, 26), maturity_date=date(2036, 10, 26)),
    ])  # fmt: skip
    assert code_book.trades == file_book.trades
    assert code_book.build(market, config).npv() == pytest.approx(
        file_book.build(market, config).npv(), rel=1e-15
    )
