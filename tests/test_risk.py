from datetime import date

import pytest
import QuantLib as ql

from quanttool.analysis.risk import cross_gamma, factor_delta, key_rate, scenario_pnl, theta
from quanttool.analysis.scenarios import bucket, combine, from_loadings, parallel, triangle_weight
from quanttool.config import Override
from quanttool.market.curves import DC, to_ql_date

ASOF = date(2026, 10, 23)
BP = 1e-4


def _direct_parallel(book, market, sizes):
    """초기 커브 + ZeroSpreadedTermStructure 평행 이동으로 같은 채권을 직접 평가 (QuantLib)."""
    spread = ql.SimpleQuote(0.0)
    out = {}
    with market.active():
        shifted = ql.YieldTermStructureHandle(
            ql.ZeroSpreadedTermStructure(
                ql.YieldTermStructureHandle(market.objects["UST"].base),
                ql.QuoteHandle(spread),
                ql.Continuous,
                ql.NoFrequency,
                DC,
            )
        )
        engine = ql.DiscountingBondEngine(shifted)
        for b in book.instruments.values():
            b.setPricingEngine(engine)
        mult = {i: t.notional / 100 for i, t in book.trades.items()}
        base = {i: book.instruments[i].NPV() * m for i, m in mult.items()}
        for s in sizes:
            spread.setValue(s)
            out[s] = {i: book.instruments[i].NPV() * m - base[i] for i, m in mult.items()}
    return out


def test_parallel_scenario_matches_direct_quantlib(config, market, book):
    pnl = scenario_pnl(book, market, {"par": parallel(market, "UST", BP)}).loc["par"]
    direct = _direct_parallel(book, market, [BP])[BP]
    for i in book.ids():
        assert pnl[i] == pytest.approx(direct[i], rel=1e-10)


def test_key_rate_delta_sum_and_locality(config, market, book):
    kr = key_rate(book, market, config.risk, "UST")
    delta = kr["delta"]
    par = scenario_pnl(book, market, {"p": parallel(market, "UST", BP)}).loc["p"]
    for i in book.ids():
        assert delta[i].sum() == pytest.approx(par[i], rel=5e-4)  # 차이는 2차 항
    assert delta.loc["3Y", "UST_2Y"] == 0.0 and delta.loc["30Y", "UST_10Y"] == 0.0
    assert delta["total"].sum() == pytest.approx(-8252.07, abs=0.01)  # 이전 구현과 같은 값


def test_gamma_sign(config, market, book):
    gamma = key_rate(book, market, config.risk, "UST")["gamma"]
    for i, sign in {"UST_2Y": 1, "UST_10Y": 1, "UST_30Y": -1}.items():
        assert gamma[i].sum() * sign > 0


def test_override_central_10bp_rescaled(config, market, book):
    """상품별 규칙: 10bp 중심 차분으로 계산해 1bp로 환산 ≈ 1bp 전진 차분."""
    default = key_rate(book, market, config.risk, "UST")["delta"]
    risk = config.risk.model_copy(
        update={"overrides": {"Bond": Override(shift_size=10 * BP, scheme="Central")}}
    )
    fd = key_rate(book, market, risk, "UST")["delta"]
    assert fd.loc["10Y", "UST_10Y"] == pytest.approx(default.loc["10Y", "UST_10Y"], rel=2e-3)


def test_coarse_shift_tenors_sum_to_parallel(config, market, book):
    risk = config.risk.model_copy(update={"shift_tenors": {"UST": ["1Y", "5Y", "10Y", "30Y"]}})
    delta = key_rate(book, market, risk, "UST")["delta"]
    assert list(delta.index) == ["1Y", "5Y", "10Y", "30Y"]
    par = scenario_pnl(book, market, {"p": parallel(market, "UST", BP)}).loc["p"]
    assert delta["UST_10Y"].sum() == pytest.approx(par["UST_10Y"], rel=5e-4)


def test_triangle_weights_sum_to_one():
    shift = [1.0, 5.0, 10.0]
    assert triangle_weight(shift, 0, 3.0) == pytest.approx(0.5)
    assert triangle_weight(shift, 1, 7.5) == pytest.approx(0.5)
    for t in [0.2, 2.0, 6.0, 25.0]:
        assert sum(triangle_weight(shift, j, t) for j in range(3)) == pytest.approx(1.0)


def test_cross_gamma_matches_direct(config, market, book):
    risk = config.risk.model_copy(update={"cross_gamma": [("UST/5Y", "UST/10Y")]})
    cg = cross_gamma(book, market, risk)
    base = book.npvs()["UST_10Y"]
    vals = {}
    for name, s in {
        "1": {"UST/5Y": BP},
        "2": {"UST/10Y": BP},
        "12": {"UST/5Y": BP, "UST/10Y": BP},
    }.items():
        with market.scenario(s):
            vals[name] = book.npvs()["UST_10Y"]
    direct = vals["12"] - vals["1"] - vals["2"] + base
    assert cg.loc[("UST/5Y", "UST/10Y"), "UST_10Y"] == pytest.approx(direct, abs=1e-9)


def test_scenario_helpers(market):
    s = combine(parallel(market, "UST", BP), from_loadings("UST", {"2Y": -1.0, "10Y": 1.0}, 5 * BP))
    assert s["UST/2Y"] == pytest.approx(BP - 5 * BP) and s["UST/10Y"] == pytest.approx(BP + 5 * BP)
    b = bucket(market, "UST", ["5Y"], 0, BP)
    assert len(b) == len(market.objects["UST"].tenors)  # 이동 만기 하나 = 평행


def test_theta_is_forward_forward(config, market, book):
    nxt = date(2026, 10, 26)
    th = theta(book, market, nxt)
    assert market.date == ASOF
    # 직접: 초기 커브를 nxt로 굴린 ImpliedTermStructure
    from quanttool.market.curves import evaluation_date

    with evaluation_date(nxt):
        implied = ql.YieldTermStructureHandle(
            ql.ImpliedTermStructure(
                ql.YieldTermStructureHandle(market.objects["UST"].base), to_ql_date(nxt)
            )
        )
        engine = ql.DiscountingBondEngine(implied)
        rolled = {}
        for i, t in book.trades.items():
            book.instruments[i].setPricingEngine(engine)
            rolled[i] = book.instruments[i].NPV() * t.notional / 100
    book.build(market, config)
    base = book.npvs()
    for i in book.ids():
        assert th[i] == pytest.approx(rolled[i] - base[i], rel=1e-9)


def test_factor_delta_is_central_difference(market, book):
    """factor_delta = (+h 손익 − (−h) 손익) / 2, 요인 키 하나도 규칙 함수도."""
    h = 1e-4
    fd = factor_delta(book, market, {"p": lambda x: parallel(market, "UST", x), "k": "UST/10Y"}, h)
    up_down = scenario_pnl(
        book,
        market,
        {"u": parallel(market, "UST", h), "d": parallel(market, "UST", -h),
         "ku": {"UST/10Y": h}, "kd": {"UST/10Y": -h}},
    )  # fmt: skip
    assert fd["delta"].loc["p", "total"] == pytest.approx(
        (up_down.loc["u", "total"] - up_down.loc["d", "total"]) / 2, rel=1e-12
    )
    assert fd["delta"].loc["k", "total"] == pytest.approx(
        (up_down.loc["ku", "total"] - up_down.loc["kd", "total"]) / 2, rel=1e-12
    )
    assert fd["gamma"].loc["p", "total"] == pytest.approx(
        up_down.loc["u", "total"] + up_down.loc["d", "total"], rel=1e-9
    )
