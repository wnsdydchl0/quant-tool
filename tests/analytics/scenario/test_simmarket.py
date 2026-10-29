import math
from datetime import date

import pytest
import QuantLib as ql

from quanttool.analytics.cube import NPVCube
from quanttool.analytics.engine import NPVCalculator, ValuationEngine
from quanttool.analytics.scenario import (
    DeltaScenario,
    KeyType,
    ListScenarioGenerator,
    RiskFactorKey,
    ScenarioSimMarket,
    SimpleScenario,
    zero_rate_shift_scenario,
)
from quanttool.data.configuration import ScenarioSimMarketParameters
from quanttool.data.marketdata.market import evaluation_date
from quanttool.data.portfolio import EngineFactory

BP = 1e-4
UST = (KeyType.YieldCurve, "UST")


@pytest.fixture
def sim(snap, cfg):
    return ScenarioSimMarket(snap, cfg.simmarket, use_spreaded_term_structures=True)


@pytest.fixture
def sim_abs(snap, cfg):
    return ScenarioSimMarket(snap, cfg.simmarket, use_spreaded_term_structures=False)


def _zero(curve, years):
    return curve.zeroRate(years, ql.Continuous).rate()


def _zero_shift(sim, label, shifts: dict[int, float]) -> DeltaScenario:
    """격자점 i의 제로금리를 dz만큼: 값 × exp(−dz·t)."""
    return zero_rate_shift_scenario(
        sim, {RiskFactorKey(*UST, i): dz for i, dz in shifts.items()}, label
    )


def _index(cfg, tenor):
    return cfg.simmarket.yield_curve_tenors("UST").index(tenor)


def test_grid_keys_and_base_scenarios(snap, cfg, sim, sim_abs):
    keys = cfg.simmarket.keys(*UST)
    assert keys[0] == RiskFactorKey(KeyType.YieldCurve, "UST", 0)
    assert str(keys[9]) == "YieldCurve/UST/9"
    assert set(sim.sim_data) == set(keys)
    # spreaded: 비율 1, 절대: 초기 커브 할인계수 (ORE baseScenario / baseScenarioAbsolute)
    assert all(sim.base_scenario().get(k) == 1.0 for k in keys)
    assert not sim.base_scenario().is_absolute() and sim_abs.base_scenario().is_absolute()
    with snap.active():
        d = snap.yield_curve("UST").referenceDate() + ql.Period("5Y")
        df5 = snap.yield_curve("UST").discount(d)
    k5 = keys[_index(cfg, "5Y")]
    assert sim.base_scenario_absolute().get(k5) == pytest.approx(df5, abs=1e-15)
    assert sim_abs.base_scenario().get(k5) == pytest.approx(df5, abs=1e-15)


def test_spreaded_equals_init_curve_everywhere(snap, sim):
    with sim.active():
        base, ours = snap.yield_curve("UST"), sim.yield_curve("UST")
        for years in [0.01, 0.3, 1.7, 4.2, 11.0, 27.0, 30.0, 45.0]:
            assert ours.discount(years) == pytest.approx(base.discount(years), abs=1e-14)


def test_absolute_matches_init_at_nodes(snap, cfg, sim_abs):
    with sim_abs.active():
        base, ours = snap.yield_curve("UST"), sim_abs.yield_curve("UST")
        ref = base.referenceDate()
        for t in cfg.simmarket.yield_curve_tenors("UST"):
            d = ref + ql.Period(t)
            assert ours.discount(d) == pytest.approx(base.discount(d), abs=1e-13)


def test_parallel_shift_is_exact_everywhere(cfg, sim):
    n = len(cfg.simmarket.keys(*UST))
    with sim.active():
        curve = sim.yield_curve("UST")
        times = [0.01, 0.3, 2.5, 13.0, 30.0, 45.0]  # 격자 앞, 사이, 뒤(외삽) 포함
        before = [_zero(curve, t) for t in times]
        sim.apply_scenario(_zero_shift(sim, "par", dict.fromkeys(range(n), BP)))
        after = [_zero(curve, t) for t in times]
        sim.reset()
        restored = [_zero(curve, t) for t in times]
    for b, a, r in zip(before, after, restored, strict=True):
        assert a - b == pytest.approx(BP, abs=1e-12)
        assert r == pytest.approx(b, abs=1e-15)


def test_key_rate_shift_is_local(cfg, sim):
    i5 = _index(cfg, "5Y")
    with sim.active():
        curve = sim.yield_curve("UST")
        before = [_zero(curve, t) for t in (3.0, 4.5, 5.0, 5.5, 7.0)]
        sim.apply_scenario(_zero_shift(sim, "kr5y", {i5: BP}))
        after = [_zero(curve, t) for t in (3.0, 4.5, 5.0, 5.5, 7.0)]
        sim.reset()
    moved = [(a - b) / BP for a, b in zip(after, before, strict=True)]
    assert moved[0] == pytest.approx(0.0, abs=1e-9)  # 3Y: 영향 없음
    assert moved[-1] == pytest.approx(0.0, abs=1e-9)  # 7Y: 영향 없음
    assert 0.0 < moved[1] < 1.0 and 0.0 < moved[3] < 1.0
    assert moved[2] == pytest.approx(1.0, abs=0.01)


def test_apply_scenario_checks(cfg, sim):
    k5 = RiskFactorKey(*UST, _index(cfg, "5Y"))
    s = _zero_shift(sim, "a", {k5.index: BP})
    sim.apply_scenario(s)
    sim.apply_scenario(s)  # 누적되지 않는다: 값을 그대로 둔다
    assert sim.sim_data[k5].value() == pytest.approx(math.exp(-BP * sim.sim_data_times[k5]))
    sim.reset()
    assert sim.scenario is None and sim.sim_data[k5].value() == 1.0
    partial = SimpleScenario(sim.asof, "partial", {k5: 0.99}, absolute=False)
    with pytest.raises(KeyError, match="DeltaScenario"):
        sim.apply_scenario(partial)
    with pytest.raises(KeyError, match="simmarket.yaml"):
        bad = sim.base_scenario().clone()
        bad.add(RiskFactorKey(*UST, 99), 1.0)
        sim.apply_scenario(bad)
    with pytest.raises(ValueError, match="absolute"):
        sim.apply_scenario(SimpleScenario(sim.asof, "abs", sim.base_scenario().values(), True))


def test_base_reconciliation_spreaded_exact_absolute_close(cfg, portfolio, sim, sim_abs):
    """spreaded: 기준 상태 = 초기 커브 (ORE SpreadedDiscountCurve). 절대: 격자 보간 차이."""
    assert sim.base_reconciliation(portfolio, cfg)["rel_diff"].abs().max() < 1e-12
    assert sim_abs.base_reconciliation(portfolio, cfg)["rel_diff"].abs().max() < 1e-3


def test_absolute_mode_denser_grid_reduces_reconciliation_error(cfg, snap, portfolio):
    def err(tenors):
        params = ScenarioSimMarketParameters(
            base_currency="USD",
            yield_curves={"names": ["UST"], "tenors": {"": tenors}, "interpolation": "LinearZero"},
        )
        smkt = ScenarioSimMarket(snap, params)
        return smkt.base_reconciliation(portfolio, cfg)["rel_diff"].abs().max()

    coarse = err(["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"])
    dense = err(["1M", "2M", "3M", "6M", "9M", "1Y"] + [f"{m}M" for m in range(18, 361, 6)])
    assert dense < coarse / 10
    assert dense < 1e-4


def test_loglinear_not_supported(snap):
    params = ScenarioSimMarketParameters(
        base_currency="USD",
        yield_curves={"names": ["UST"], "tenors": {"": ["1Y", "2Y"]}, "interpolation": "LogLinear"},
    )
    with pytest.raises(NotImplementedError, match="LinearZero"):
        ScenarioSimMarket(snap, params)


def test_update_moves_date_forward_forward(cfg, snap, portfolio, sim):
    """update(d): 평가일 이동, 기준 커브는 ForwardForward로 굴린다. 직접 계산은
    ImpliedTermStructure."""
    nxt = date(2026, 10, 26)
    with sim.active():
        portfolio.build(EngineFactory.from_config(cfg, sim))
        base = portfolio.npvs()
    sim.update(nxt)
    with sim.active():
        assert ql.Settings.instance().evaluationDate == ql.Date(26, 10, 2026)
        assert sim.yield_curve("UST").referenceDate() == ql.Date(26, 10, 2026)
        rolled = portfolio.npvs()
    sim.reset()
    assert sim.date == sim.asof

    with evaluation_date(nxt):
        implied = ql.YieldTermStructureHandle(
            ql.ImpliedTermStructure(snap.yield_curve("UST"), ql.Date(26, 10, 2026))
        )
        portfolio.build(EngineFactory.from_config(cfg, snap))
        for t in portfolio:
            t.instrument().ql_instrument().setPricingEngine(ql.DiscountingBondEngine(implied))
        direct = portfolio.npvs()
    assert ((rolled - direct) / direct).abs().max() < 1e-12
    assert (rolled != base).all()  # 시간이 흘러 값이 바뀐다 (theta)


def test_valuation_engine_over_dates_and_samples(cfg, portfolio, sim):
    """표본 × 날짜. 날짜가 처음으로 돌아오면 다음 표본 (ORE ScenarioGenerator::next)."""
    up = _zero_shift(sim, "up", dict.fromkeys(range(len(sim.sim_data)), BP))
    sim.scenario_generator = ListScenarioGenerator([sim.base_scenario(), up])
    with sim.active():
        portfolio.build(EngineFactory.from_config(cfg, sim))
    dates = [sim.asof, date(2026, 10, 26)]
    cube = NPVCube(portfolio.ids(), sim.asof, dates, samples=2)
    ValuationEngine(sim.asof, dates, sim).build_cube(portfolio, cube, [NPVCalculator("USD")])
    t = "UST_10Y"
    assert cube.get(t, 0, 0) == pytest.approx(cube.get_t0(t), rel=1e-15)  # 표본 0 = 기준, asof
    assert cube.get(t, 0, 1) < cube.get(t, 0, 0)  # 금리 상승 → 롱 손실
    assert cube.get(t, 1, 0) != cube.get(t, 0, 0)  # 날짜 이동
    assert sim.scenario is None and sim.date == sim.asof  # 끝나면 reset
    with pytest.raises(ValueError, match="표본"):
        ValuationEngine(sim.asof, dates, sim).build_cube(
            portfolio, NPVCube(portfolio.ids(), sim.asof, dates, samples=3), [NPVCalculator("USD")]
        )
