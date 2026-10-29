import copy

import pytest
import QuantLib as ql

from quanttool.data.configuration import EngineData
from quanttool.data.marketdata.market import to_ql_date
from quanttool.data.portfolio import Bond, EngineFactory, MarketContext, Portfolio
from quanttool.data.utilities import parsers

K10 = "BOND/YIELD/USD/UST/PAR/10Y"


def _direct_npv(trade: Bond, curve) -> float:
    """QuantLib FixedRateBond으로 직접 조립한 같은 채권의 NPV (부호 포함)."""
    bd = trade.bond_data
    leg = bd.coupons[0]
    rules = leg.schedule_data.rules[0]
    sch = ql.Schedule(
        to_ql_date(rules.start_date),
        to_ql_date(rules.end_date),
        ql.Period(ql.Semiannual),
        parsers.calendar(rules.calendar),
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Backward,
        False,
    )
    face = leg.notionals[0]
    bond = ql.FixedRateBond(
        bd.settlement_days,
        face,
        sch,
        leg.fixed_leg_data.rates,
        ql.ActualActual(ql.ActualActual.Bond),
        ql.Unadjusted,
        100.0,
        to_ql_date(bd.issue_date),
    )
    bond.setPricingEngine(ql.DiscountingBondEngine(curve))
    return bond.NPV() * (-1.0 if leg.payer else 1.0)


def test_npv_matches_direct_quantlib(cfg, snap, portfolio):
    with snap.active():
        portfolio.build(EngineFactory.from_config(cfg, snap))
        for t in portfolio:
            assert t.npv() == pytest.approx(_direct_npv(t, snap.yield_curve("UST")), rel=1e-12)
        assert portfolio.get("UST_30Y").npv() < 0  # 매도 포지션 (payer)


def test_build_fills_trade_fields(cfg, snap, portfolio):
    """ORE Trade::build가 채우는 것: 상품, 레그, NPV 통화, 원금, 만기."""
    with snap.active():
        portfolio.build(EngineFactory.from_config(cfg, snap))
    t = portfolio.get("UST_10Y")
    assert t.is_built() and portfolio.is_built()
    assert t.npv_currency() == "USD"
    assert t.notional() == pytest.approx(1.0e7)
    assert t.maturity().isoformat() == "2036-08-15"
    assert len(t.legs()[0]) == 21  # 쿠폰 20 + 상환 1
    assert isinstance(t.instrument().ql_instrument(), ql.Bond)
    portfolio.reset()
    assert not t.is_built()


def test_engine_cached_per_key(cfg, snap, portfolio):
    factory = EngineFactory.from_config(cfg, snap)
    builder = factory.builder("Bond")
    assert factory.builder("Bond") is builder  # 상품 유형당 빌더 하나
    e1 = builder.engine("USD", "", "UST_10Y", "UST", "")
    assert builder.engine("USD", "", "UST_10Y", "UST", "") is e1  # 같은 키 → 같은 엔진
    assert builder.engine("USD", "", "UST_2Y", "UST", "") is not e1  # 키에 증권 id 포함 (ORE)
    assert builder.configuration(MarketContext.pricing) == "default"


def test_engine_data_mismatch_rejected(cfg, snap):
    bad = EngineData(products={"Bond": {"model": "BlackScholes", "engine": "Analytic"}})
    with pytest.raises(KeyError, match="엔진 빌더가 없다"):
        EngineFactory(bad, snap).builder("Bond")
    with pytest.raises(KeyError, match="설정이 없다"):
        EngineFactory(cfg.engine_data, snap).builder("Swap")


def test_sensitivity_template_from_engine_parameters(cfg, snap, portfolio):
    """엔진 파라미터 SensitivityTemplate이 거래에 붙는다 (ORE Trade::setSensitivityTemplate)."""
    ed = cfg.engine_data.model_copy(deep=True)
    ed.products["Bond"] = ed.products["Bond"].model_copy(
        update={"engine_parameters": {"SensitivityTemplate": "IR_FD"}}
    )
    with snap.active():
        portfolio.build(EngineFactory(ed, snap))
    assert {t.sensitivity_template() for t in portfolio} == {"IR_FD"}


def test_npv_reacts_to_quote(cfg, linked_snap, loader, portfolio):
    snap = linked_snap
    with snap.active():
        portfolio.build(EngineFactory.from_config(cfg, snap))
        before = portfolio.get("UST_10Y").npv()
        q = loader.get(K10, snap.asof).quote
        q.setValue(q.value() + 0.0001)
        after = portfolio.get("UST_10Y").npv()
    # 10Y 1bp 상승 → 롱 포지션 손실, 크기는 대략 액면 × 듀레이션 × 1bp
    assert -1.0e7 * 9 * 1e-4 < after - before < -1.0e7 * 6 * 1e-4


def _record(portfolio_path):
    import yaml

    return yaml.safe_load(portfolio_path.read_text(encoding="utf-8"))[2]


def test_portfolio_errors(cfg, snap):
    from pathlib import Path

    rec = _record(Path(__file__).resolve().parents[3] / "positions" / "ust_book.yaml")
    with pytest.raises(ValueError):
        Portfolio.from_records([rec, rec])
    with pytest.raises(KeyError):
        Portfolio.from_records([{**rec, "trade_type": "Swaption"}])
    p = Portfolio.from_records([rec])
    with pytest.raises(RuntimeError):
        p.npv()
    bad = copy.deepcopy(rec)
    bad["bond_data"]["reference_curve_id"] = "KRW"
    with pytest.raises(KeyError, match="KRW"):
        Portfolio.from_records([bad]).build(EngineFactory.from_config(cfg, snap))
    no_rates = copy.deepcopy(rec)
    del no_rates["bond_data"]["coupons"][0]["fixed_leg_data"]
    with pytest.raises(ValueError, match="fixed_leg_data"):
        Portfolio.from_records([no_rates])
