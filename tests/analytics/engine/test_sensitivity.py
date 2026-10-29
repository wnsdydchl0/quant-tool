import math

import pytest
import QuantLib as ql

from quanttool.analytics.engine import SensitivityAnalysis
from quanttool.analytics.scenario import (
    DeltaScenario,
    DescriptionType,
    KeyType,
    RiskFactorKey,
    ScenarioSimMarket,
    SensitivityScenarioGenerator,
)
from quanttool.analytics.scenario.shiftscenariogenerator import triangle_weights
from quanttool.data.configuration import SensitivityScenarioData
from quanttool.data.portfolio import EngineFactory

BP = 1e-4
UST = (KeyType.YieldCurve, "UST")


@pytest.fixture
def analysis(cfg, snap, portfolio):
    sa = SensitivityAnalysis.from_config(portfolio, snap, cfg)
    sa.generate_sensitivities()
    return sa


@pytest.fixture
def cube(analysis):
    (c,) = analysis.sensi_cubes()
    return c


def _key(cfg, tenor):
    return RiskFactorKey(*UST, cfg.sensitivity.yield_curves["UST"].shift_tenors.index(tenor))


def _direct_parallel(cfg, snap, portfolio, size):
    """초기 커브에 ZeroSpreadedTermStructure로 평행 이동을 얹은 직접 계산 (QuantLib)."""
    spread = ql.SimpleQuote(0.0)
    with snap.active():
        shifted = ql.YieldTermStructureHandle(
            ql.ZeroSpreadedTermStructure(
                snap.yield_curve("UST"),
                ql.QuoteHandle(spread),
                ql.Continuous,
                ql.NoFrequency,
                ql.Actual365Fixed(),
            )  # fmt: skip
        )
        portfolio.build(EngineFactory.from_config(cfg, snap))
        for t in portfolio:
            t.instrument().ql_instrument().setPricingEngine(ql.DiscountingBondEngine(shifted))
        base = portfolio.npvs()
        out = {}
        for s in size:
            spread.setValue(s)
            out[s] = portfolio.npvs() - base
    return out


def test_generator_scenarios_and_descriptions(cfg, snap):
    sim = ScenarioSimMarket(snap, cfg.simmarket, use_spreaded_term_structures=True)
    gen = SensitivityScenarioGenerator(cfg.sensitivity, sim.base_scenario(), cfg.simmarket, sim)
    n = len(cfg.sensitivity.yield_curves["UST"].shift_tenors)
    assert gen.samples() == 1 + 2 * n  # 기준 + Up + Down (compute_gamma)
    d = gen.scenario_descriptions()
    assert d[0].type == DescriptionType.Base
    assert str(d[10]) == "Up:YieldCurve/UST/9/5Y"
    assert str(d[n + 10]) == "Down:YieldCurve/UST/9/5Y"
    assert gen.shift_sizes()[_key(cfg, "5Y")] == BP
    # 시나리오 값: 기준 비율 × exp(−1bp·t), 다른 점은 기준 그대로
    s = gen.scenarios[10]
    k = _key(cfg, "5Y")
    assert s.get(k) == pytest.approx(math.exp(-BP * sim.sim_data_times[k]), rel=1e-15)
    assert s.get(_key(cfg, "7Y")) == 1.0


def test_triangle_weights_coarser_shift_grid():
    """ORE applyShift: 이동 만기 사이 격자점은 선형 가중, 양 끝 밖은 평탄."""
    shift = [1.0, 5.0, 10.0]
    assert triangle_weights(shift, 0, 0.5) == 1.0
    assert triangle_weights(shift, 0, 3.0) == pytest.approx(0.5)
    assert triangle_weights(shift, 1, 3.0) == pytest.approx(0.5)
    assert triangle_weights(shift, 1, 7.5) == pytest.approx(0.5)
    assert triangle_weights(shift, 2, 20.0) == 1.0
    assert triangle_weights(shift, 1, 12.0) == 0.0
    # 합은 어디서나 1 (평행 이동과 같다)
    for t in [0.2, 2.0, 6.0, 9.9, 25.0]:
        assert sum(triangle_weights(shift, j, t) for j in range(3)) == pytest.approx(1.0)


def test_cube_shapes_and_market_reset(analysis, cube, portfolio):
    sim = analysis.sim_market
    assert cube.cube.ids() == ["UST_2Y", "UST_5Y", "UST_10Y", "UST_30Y"]
    assert all(q.value() == sim.base_scenario().get(k) for k, q in sim.sim_data.items())
    assert sim.date == sim.asof and sim.scenario is None


def test_sum_of_deltas_matches_direct_parallel(cfg, snap, portfolio, cube):
    """Σ key rate delta ≈ 평행 1bp 직접 계산 (1차 같음, 차이는 2차 항)."""
    direct = _direct_parallel(cfg, snap, portfolio, [BP])[BP]
    table = cube.delta_table(*UST)
    for t in portfolio.ids():
        assert table[t].sum() == pytest.approx(direct[t], rel=5e-4)


def test_parallel_scenario_matches_direct_exactly(cfg, snap, portfolio, analysis):
    """모든 격자점 +1bp 시나리오 = 초기 커브 + 평행 1bp (spreaded라 정확히)."""
    sim = analysis.sim_market
    base = sim.base_scenario()
    up = DeltaScenario(base, {k: math.exp(-BP * sim.sim_data_times[k]) for k in sim.sim_data})
    with sim.active():
        portfolio.build(EngineFactory.from_config(cfg, sim))
        b = portfolio.npvs()
        sim.apply_scenario(up)
        moved = portfolio.npvs() - b
        sim.reset()
    direct = _direct_parallel(cfg, snap, portfolio, [BP])[BP]
    assert ((moved - direct) / direct).abs().max() < 1e-10


def test_key_rate_beyond_maturity_is_zero(cfg, cube):
    assert cube.delta("UST_2Y", _key(cfg, "3Y")) == 0.0
    assert cube.delta("UST_10Y", _key(cfg, "30Y")) == 0.0
    assert cube.delta("UST_10Y", _key(cfg, "10Y")) < 0 < cube.delta("UST_30Y", _key(cfg, "30Y"))


def test_gamma_matches_second_difference(cfg, snap, portfolio, cube):
    """gamma = up − 2·base + down. 평행 이동으로 합하면 직접 2차 차분과 2차까지 같다."""
    d = _direct_parallel(cfg, snap, portfolio, [BP, -BP])
    direct_gamma = d[BP] + d[-BP]
    key_gamma = cube.delta_table(*UST, measure="Gamma")
    sign = {"UST_2Y": 1, "UST_5Y": 1, "UST_10Y": 1, "UST_30Y": -1}  # 롱 +, 숏 −
    for t in portfolio.ids():
        diag = key_gamma[t].sum()
        assert diag * sign[t] > 0 and direct_gamma[t] * sign[t] > 0
        # 대각 합은 교차항이 빠져 평행 gamma보다 작다
        assert abs(diag) < abs(direct_gamma[t])


def test_central_scheme_with_template(cfg, snap, portfolio, cube):
    """민감도 템플릿: 엔진 파라미터 SensitivityTemplate=IR_FD인 거래는 10bp 중심 차분으로 계산하고
    1bp 기준으로 다시 환산한다 (ORE keyed ShiftSize / ShiftScheme + scaling)."""
    ed = cfg.engine_data.model_copy(deep=True)
    ed.products["Bond"] = ed.products["Bond"].model_copy(
        update={"engine_parameters": {"SensitivityTemplate": "IR_FD"}}
    )
    ust = cfg.sensitivity.yield_curves["UST"].model_copy(
        update={"keyed_shift_size": {"IR_FD": 10 * BP}, "keyed_shift_scheme": {"IR_FD": "Central"}}
    )
    data = cfg.sensitivity.model_copy(update={"yield_curves": {"UST": ust}})
    sa = SensitivityAnalysis(portfolio, snap, "default", ed, cfg.simmarket, data)
    portfolio.reset()
    sa.generate_sensitivities()
    (fd,) = sa.sensi_cubes()
    k = _key(cfg, "10Y")
    assert fd.actual_shift_sizes[k] == pytest.approx(10 * BP) and fd.target_shift_sizes[k] == BP
    assert fd.shift_schemes[k] == "Central"
    # 중심 차분 10bp ≈ 전진 차분 1bp (차이는 gamma 항 정도)
    assert fd.delta("UST_10Y", k) == pytest.approx(cube.delta("UST_10Y", k), rel=2e-3)


def test_cross_gamma(cfg, snap, portfolio):
    data = cfg.sensitivity.model_copy(
        update={"cross_gamma_filter": [("YieldCurve/UST", "YieldCurve/UST")]}
    )
    sa = SensitivityAnalysis(portfolio, snap, "default", cfg.engine_data, cfg.simmarket, data)
    sa.generate_sensitivities()
    (c,) = sa.sensi_cubes()
    k5, k10 = _key(cfg, "5Y"), _key(cfg, "10Y")
    assert (k5, k10) in c.cross_factors()
    # 직접: 두 점을 함께 올린 시나리오
    sim = sa.sim_market
    base = sim.base_scenario()

    def shifted(*keys):
        delta = {}
        for kk in keys:
            for k in sim.sim_data:
                if k.index == kk.index:
                    delta[k] = math.exp(-BP * sim.sim_data_times[k])
        return DeltaScenario(base, delta)

    with sim.active():
        portfolio.build(EngineFactory.from_config(cfg, sim))
        b = portfolio.get("UST_10Y").npv()
        vals = {}
        for name, s in {"1": shifted(k5), "2": shifted(k10), "12": shifted(k5, k10)}.items():
            sim.apply_scenario(s)
            vals[name] = portfolio.get("UST_10Y").npv()
        sim.reset()
    direct = vals["12"] - vals["1"] - vals["2"] + b
    assert c.cross_gamma("UST_10Y", (k5, k10)) == pytest.approx(direct, abs=1e-6)


def test_report_columns(analysis):
    r = analysis.report()
    cols = ["TradeId", "Factor_1", "ShiftSize_1", "Factor_2", "ShiftSize_2"]
    assert list(r.columns) == [*cols, "Base NPV", "Delta", "Gamma"]
    assert r["Factor_1"].iloc[9] == "YieldCurve/UST/9/5Y"


def test_sensitivity_data_requires_grid(cfg, snap, portfolio):
    bad = cfg.sensitivity.model_copy(
        update={"discount_curves": {"EUR": cfg.sensitivity.yield_curves["UST"]}}
    )
    sa = SensitivityAnalysis(portfolio, snap, "default", cfg.engine_data, cfg.simmarket, bad)
    with pytest.raises(KeyError, match="격자에 없다"):
        sa.generate_sensitivities()
    assert isinstance(cfg.sensitivity, SensitivityScenarioData)
