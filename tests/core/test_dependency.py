import pytest

from quanttool.core.dependency import CycleError, DependencyGraph

FWD = ("EquityForward", "SPX_FWD")
VOL = ("EquityVol", "SPX_VOL")
USD = ("YieldCurve", "USD_SOFR")
DIV = ("YieldCurve", "SPX_DIV")


def test_diamond_order():
    g = DependencyGraph({VOL: [FWD], FWD: [USD, DIV], USD: [], DIV: []})
    order = g.order([VOL])
    assert order[-1] == VOL
    assert order.index(FWD) > order.index(USD)
    assert order.index(FWD) > order.index(DIV)
    assert len(order) == 4


def test_only_needed_nodes():
    g = DependencyGraph({VOL: [FWD], FWD: [USD], USD: [], DIV: []})
    assert g.order([FWD]) == [USD, FWD]


def test_cycle():
    g = DependencyGraph({FWD: [VOL], VOL: [FWD]})
    with pytest.raises(CycleError, match="SPX_FWD"):
        g.order([FWD])


def test_undefined():
    with pytest.raises(KeyError):
        DependencyGraph({FWD: [USD]})
    with pytest.raises(KeyError):
        DependencyGraph({}).order([FWD])
