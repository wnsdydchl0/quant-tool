import math

import pytest

from quanttool.analytics.app.marketmonitor import curve_shape, curve_table
from quanttool.analytics.engine import SensitivityAnalysis


def test_curve_table_par_reproduces_market_quotes(cfg, snap, loader):
    table = curve_table(snap, "UST", cfg)
    # 쿠폰채 구간 par yield는 부트스트랩에 쓴 par 시세를 그대로 재현해야 한다
    for tenor in ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]:
        market = loader.get(f"BOND/YIELD/USD/UST/PAR/{tenor}", snap.asof).value
        assert table.loc[tenor, "par"] == pytest.approx(market, abs=1e-8)
    assert math.isnan(table.loc["3M", "par"])
    t = table.loc["5Y"]
    assert t["discount"] == pytest.approx(math.exp(-t["zero_cc"] * t["years"]), rel=1e-12)
    assert (1 + t["zero_sa"] / 2) ** 2 == pytest.approx(math.exp(t["zero_cc"]), rel=1e-12)


def test_curve_shape(cfg, snap, loader):
    shape = curve_shape(curve_table(snap, "UST", cfg))
    q = {
        t: loader.get(f"BOND/YIELD/USD/UST/PAR/{t}", snap.asof).value * 1e4
        for t in ["2Y", "5Y", "10Y", "30Y"]
    }
    assert shape["2s10s"] == pytest.approx(q["10Y"] - q["2Y"], abs=1e-4)
    assert shape["5s30s"] == pytest.approx(q["30Y"] - q["5Y"], abs=1e-4)


def test_sensitivity_tables(cfg, snap, portfolio):
    sa = SensitivityAnalysis(portfolio, snap, cfg)
    sa.generate_sensitivities()
    krd = sa.sensi_cube().key_rate_dv01("UST")
    par = sa.sensi_cube().parallel_dv01("UST")
    assert list(krd.index) == cfg.simmarket.root["UST"].tenors
    assert krd["total"].sum() == pytest.approx(krd.drop(columns="total").sum().sum())
    assert krd["total"].sum() == pytest.approx(par["total"], rel=5e-4)
    assert par["UST_10Y"] < 0 < par["UST_30Y"]  # 롱 10Y, 숏 30Y
