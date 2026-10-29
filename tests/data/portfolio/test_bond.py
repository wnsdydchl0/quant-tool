import pytest
import QuantLib as ql

from quanttool.data.marketdata.market import to_ql_date
from quanttool.data.portfolio import Bond, EngineFactory, Portfolio
from quanttool.data.utilities import parsers


def _direct_npv(trade: Bond, cfg, curve) -> float:
    """QuantLib으로 직접 조립한 같은 채권의 NPV."""
    conv = cfg.conventions[trade.conventions]
    sch = ql.Schedule(
        to_ql_date(trade.issue_date),
        to_ql_date(trade.maturity_date),
        ql.Period(ql.Semiannual),
        parsers.calendar(conv.calendar),
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        False,
    )
    bond = ql.FixedRateBond(
        1,
        100.0,
        sch,
        [trade.coupon],
        ql.ActualActual(ql.ActualActual.Bond),
        ql.Unadjusted,
        100.0,
        to_ql_date(trade.issue_date),
    )
    bond.setPricingEngine(ql.DiscountingBondEngine(curve))
    return bond.NPV() * trade.notional / 100.0


def test_npv_matches_direct_quantlib(cfg, snap, portfolio):
    with snap.active():
        portfolio.build(EngineFactory(snap, cfg))
        for t in portfolio:
            assert t.npv() == pytest.approx(_direct_npv(t, cfg, snap.yield_curve("UST")), rel=1e-12)


def test_engine_cached_per_curve(cfg, snap, portfolio):
    factory = EngineFactory(snap, cfg)
    engines = {id(factory.engine_for(t)) for t in portfolio}
    assert len(engines) == 1


def test_npv_reacts_to_quote(cfg, linked_snap, portfolio):
    snap = linked_snap
    with snap.active():
        portfolio.build(EngineFactory(snap, cfg))
        before = portfolio.trades["UST_10Y"].npv()
        snap.quotes["UST/PAR/10Y"].setValue(snap.quotes["UST/PAR/10Y"].value() + 0.0001)
        after = portfolio.trades["UST_10Y"].npv()
    # 10Y 1bp 상승 → 롱 포지션 손실, 크기는 대략 액면 × 듀레이션 × 1bp
    assert -1.0e7 * 9 * 1e-4 < after - before < -1.0e7 * 6 * 1e-4


def test_portfolio_errors(cfg, snap):
    rec = {
        "id": "X",
        "trade_type": "Bond",
        "notional": 1.0,
        "coupon": 0.04,
        "issue_date": "2026-01-01",
        "maturity_date": "2030-01-01",
        "conventions": "UST",
        "discount": "UST",
    }
    with pytest.raises(ValueError):
        Portfolio.from_records([rec, rec])
    with pytest.raises(KeyError):
        Portfolio.from_records([{**rec, "trade_type": "Swaption"}])
    p = Portfolio.from_records([rec])
    with pytest.raises(RuntimeError):
        p.npv()
    with pytest.raises(KeyError, match="KRW"):
        Portfolio.from_records([{**rec, "discount": "KRW"}]).build(EngineFactory(snap, cfg))
