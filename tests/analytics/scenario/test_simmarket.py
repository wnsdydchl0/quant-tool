from datetime import date

import pytest
import QuantLib as ql

from quanttool.analytics.engine import SensitivityAnalysis, ValuationEngine
from quanttool.analytics.scenario import Scenario, ScenarioSimMarket, SensitivityScenarioGenerator
from quanttool.analytics.scenario.simmarket import GRID_DAY_COUNTER, sample
from quanttool.data.configuration import ScenarioSimMarketParameters, YieldCurveSimParameters
from quanttool.data.marketdata.market import evaluation_date
from quanttool.data.portfolio import EngineFactory
from quanttool.qle.scenario import RiskFactorKey

BP = 1e-4


@pytest.fixture
def grid(cfg):
    return cfg.simmarket


@pytest.fixture
def smkt(snap, grid):
    return ScenarioSimMarket(snap, grid)


def _zero(curve, years):
    return curve.zeroRate(years, ql.Continuous).rate()


def test_grid_keys_and_sample(snap, grid):
    keys = grid.keys("UST")
    assert keys[0] == RiskFactorKey("zero", "UST", ("1M",))
    sampled = sample(snap, grid)
    assert set(sampled) == set(keys)
    with snap.active():
        d = snap.yield_curve("UST").referenceDate() + ql.Period("5Y")
        expected = snap.yield_curve("UST").zeroRate(d, GRID_DAY_COUNTER, ql.Continuous).rate()
    assert sampled[RiskFactorKey("zero", "UST", ("5Y",))] == pytest.approx(expected, abs=1e-15)


def test_grid_curve_matches_base_at_nodes(snap, grid, smkt):
    with smkt.active():
        base, ours = snap.yield_curve("UST"), smkt.yield_curve("UST")
        for d in grid.dates("UST", base.referenceDate()):
            assert ours.discount(d) == pytest.approx(base.discount(d), abs=1e-12)


def test_parallel_shift_is_exact_everywhere(smkt, grid):
    with smkt.active():
        curve = smkt.yield_curve("UST")
        times = [0.01, 0.3, 2.5, 13.0, 30.0, 45.0]  # 격자 앞, 사이, 뒤(외삽) 포함
        before = [_zero(curve, t) for t in times]
        smkt.apply_scenario(Scenario("par", {k: BP for k in grid.keys("UST")}))
        after = [_zero(curve, t) for t in times]
        smkt.reset()
        restored = [_zero(curve, t) for t in times]
    for b, a, r in zip(before, after, restored, strict=True):
        assert a - b == pytest.approx(BP, abs=1e-13)
        assert r == pytest.approx(b, abs=1e-15)


def test_apply_is_not_cumulative_and_checks_keys(smkt):
    key = RiskFactorKey("zero", "UST", ("5Y",))
    smkt.apply_scenario(Scenario("a", {key: BP}))
    smkt.apply_scenario(Scenario("b", {key: BP}))
    assert smkt.sim_data[key].value() == pytest.approx(smkt.base_values[key] + BP)
    smkt.reset()
    with pytest.raises(KeyError, match="simmarket.yaml"):
        smkt.apply_scenario(Scenario("x", {RiskFactorKey("zero", "UST", ("11Y",)): BP}))


def test_key_rate_shift_is_local(smkt):
    with smkt.active():
        curve = smkt.yield_curve("UST")
        before = [_zero(curve, t) for t in (3.0, 4.5, 5.0, 5.5, 7.0)]
        smkt.apply_scenario(Scenario("kr5y", {RiskFactorKey("zero", "UST", ("5Y",)): BP}))
        after = [_zero(curve, t) for t in (3.0, 4.5, 5.0, 5.5, 7.0)]
        smkt.reset()
    moved = [(a - b) / BP for a, b in zip(after, before, strict=True)]
    assert moved[0] == pytest.approx(0.0, abs=1e-9)  # 3Y: 영향 없음
    assert moved[-1] == pytest.approx(0.0, abs=1e-9)  # 7Y: 영향 없음
    assert 0.0 < moved[1] < 1.0 and 0.0 < moved[3] < 1.0
    assert moved[2] == pytest.approx(1.0, abs=0.01)


def test_base_reconciliation(cfg, snap, portfolio, smkt):
    recon = smkt.base_reconciliation(portfolio, cfg)
    assert recon["rel_diff"].abs().max() < 1e-3


def test_absolute_mode_denser_grid_reduces_reconciliation_error(cfg, snap, portfolio):
    def err(tenors):
        g = ScenarioSimMarketParameters(
            {"UST": YieldCurveSimParameters(kind="zero", tenors=tenors)}
        )
        smkt = ScenarioSimMarket(snap, g, spreaded=False)
        return smkt.base_reconciliation(portfolio, cfg)["rel_diff"].abs().max()

    coarse = err(["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"])
    dense = err(["1M", "2M", "3M", "6M", "9M", "1Y"] + [f"{m}M" for m in range(18, 361, 6)])
    assert dense < coarse / 10
    assert dense < 1e-4


@pytest.fixture
def analysis(cfg, snap, portfolio):
    sa = SensitivityAnalysis(portfolio, snap, cfg)
    sa.generate_sensitivities()
    return sa


@pytest.fixture
def results(analysis):
    return analysis.sensi_cube().cube


def test_valuation_engine_shapes_and_reset(results, grid, analysis):
    sim = analysis.sim_market
    assert len(results.npv) == len(grid.keys("UST")) + 1
    assert list(results.npv.columns) == ["UST_2Y", "UST_5Y", "UST_10Y", "UST_30Y"]
    assert all(q.value() == sim.base_values[k] for k, q in sim.sim_data.items())
    assert sim.date == sim.asof and sim.scenario is None


def test_valuation_engine_over_dates(cfg, snap, portfolio, grid, smkt):
    """날짜가 여럿이면 (시나리오, 날짜)마다 평가한다. 생성기는 표본마다 다음 시나리오를 준다."""
    smkt.scenario_generator = SensitivityScenarioGenerator(grid, cfg.sensitivity, curves=["UST"])
    with smkt.active():
        portfolio.build(EngineFactory.from_config(cfg, smkt))
    dates = [smkt.asof, date(2026, 10, 26)]
    cube = ValuationEngine(smkt.asof, dates, smkt).build_cube(portfolio)
    assert len(cube.npv) == smkt.scenario_generator.samples() * 2
    first_label, first_date = cube.npv.index[0]
    assert first_date == smkt.asof and first_label == ("key_rate", "UST", "1M")


def test_key_rate_sum_equals_parallel(results):
    pnl = results.pnl
    kr = pnl[[label[0] == "key_rate" for label in pnl.index]].sum()
    par = pnl.loc[[("parallel", "UST")]].iloc[0]
    # 격자 보간이 격자값에 선형이므로 1차에서 정확히 같고, 차이는 2차(볼록성) 항
    assert ((kr - par) / par).abs().max() < 5e-4


def test_key_rate_beyond_maturity_is_zero(results):
    pnl = results.pnl
    assert pnl.loc[[("key_rate", "UST", "3Y")], "UST_2Y"].iloc[0] == 0.0
    assert pnl.loc[[("key_rate", "UST", "30Y")], "UST_10Y"].iloc[0] == 0.0


def test_parallel_dv01_matches_direct_quantlib(cfg, snap, portfolio, results):
    """격자 시장 평행 DV01 vs 기준 커브에 ZeroSpreadedTermStructure로 1bp 얹은 직접 계산."""
    spread = ql.SimpleQuote(0.0)
    with snap.active():
        shifted = ql.YieldTermStructureHandle(
            ql.ZeroSpreadedTermStructure(
                snap.yield_curve("UST"),
                ql.QuoteHandle(spread),
                ql.Continuous,
                ql.NoFrequency,
                GRID_DAY_COUNTER,
            )
        )
        portfolio.build(EngineFactory.from_config(cfg, snap))
        for t in portfolio:
            t.instrument().ql_instrument().setPricingEngine(ql.DiscountingBondEngine(shifted))
        base = portfolio.npvs()
        spread.setValue(BP)
        direct = portfolio.npvs() - base
    par = results.pnl.loc[[("parallel", "UST")]].iloc[0]
    # spreaded 격자: 평행 이동이 초기 커브 위 제로 스프레드와 같은 구조라 거의 일치
    assert ((par - direct) / direct).abs().max() < 1e-10


def test_spreaded_mode_reconciles_exactly(cfg, snap, portfolio, smkt):
    """spreaded: 기준 상태의 시뮬레이션 커브 = 초기 커브 (ORE SpreadedDiscountCurve)."""
    assert all(smkt.spreaded.values())
    recon = smkt.base_reconciliation(portfolio, cfg)
    assert recon["rel_diff"].abs().max() < 1e-12


def test_update_moves_date_forward_forward(cfg, snap, portfolio, smkt):
    """update(d): 평가일 이동, 기준 커브는 ForwardForward로 굴린다.

    직접 계산은 QuantLib ImpliedTermStructure.
    """
    nxt = date(2026, 10, 26)
    with smkt.active():
        portfolio.build(EngineFactory.from_config(cfg, smkt))
        base = portfolio.npvs()
    smkt.update(nxt)
    with smkt.active():
        assert ql.Settings.instance().evaluationDate == ql.Date(26, 10, 2026)
        assert smkt.yield_curve("UST").referenceDate() == ql.Date(26, 10, 2026)
        rolled = portfolio.npvs()
    smkt.reset()
    assert smkt.date == smkt.asof

    # 직접 계산: 초기 커브를 nxt로 굴린 ImpliedTermStructure로 같은 채권을 평가
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


def test_update_applies_generator_scenarios(cfg, grid, smkt):
    gen = SensitivityScenarioGenerator(grid, cfg.sensitivity)
    smkt.scenario_generator = gen
    first = next(iter(gen.generate()))
    smkt.update(smkt.asof)
    key = next(iter(first.shifts))
    assert smkt.sim_data[key].value() == pytest.approx(smkt.base_values[key] + first.shifts[key])
    smkt.scenario_generator = None
    smkt.reset()
    assert all(q.value() == smkt.base_values[k] for k, q in smkt.sim_data.items())
