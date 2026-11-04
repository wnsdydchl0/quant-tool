from datetime import date

import QuantLib as ql

from quanttool import portfolio as pf
from quanttool.portfolio import Portfolio, trade


def test_anchor_inherits_convention(config):
    """conventions.yaml: KRW_IRS = KRW_OIS(<<: *KRW) + frequency만 분기."""
    ois, irs = config.conventions["KRW_OIS"], config.conventions["KRW_IRS"]
    assert (ois.frequency, irs.frequency) == ("Annual", "Quarterly")
    assert ois.model_dump(exclude={"frequency"}) == irs.model_dump(exclude={"frequency"})


def test_four_files_load_same_structure(config):
    order = config.build_order()  # market.yaml 순서를 따르되 의존 먼저
    assert sorted(order) == ["CD91", "KOFR", "UST"] and order.index("KOFR") < order.index("CD91")
    assert sorted(config.curves) == ["CD91", "KOFR", "UST"]
    assert config.curves["CD91"].name == "CD91" and config.curves["CD91"].discount_curve == "KOFR"
    assert sorted(config.indices) == ["CD91", "KOFR"]
    assert sorted(config.products) == ["KRW_IRS_CD91", "UST_NOTE"]
    assert config.pricing.defaults == {"Bond": "DiscountingBond", "IRSwap": "DiscountingSwap"}


def test_template_engine_overrides_type_default(config, market, monkeypatch):
    """거래(또는 템플릿)의 engine 필드가 종류 기본 엔진을 덮는다."""
    monkeypatch.setitem(pf.ENGINES, "SingleCurveSwap",
                        lambda t, m, p: ql.DiscountingSwapEngine(m[t.index]))  # fmt: skip
    t = trade(config, "KRW_IRS_CD91", id="s", notional=1e10, fixed_rate=0.03,
              start_date=date(2026, 10, 26), maturity_date=date(2031, 10, 26),
              engine="SingleCurveSwap")  # fmt: skip
    book = Portfolio([t]).build(market, config)
    assert list(book.engines)[0][0] == "SingleCurveSwap"
