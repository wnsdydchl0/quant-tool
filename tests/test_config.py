from datetime import date

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
    assert list(config.equities) == ["SPX"] and config.equities["SPX"].name == "SPX"
    assert sorted(config.products) == ["KRW_IRS_CD91", "SPX_EURO", "UST_NOTE"]
    assert config.pricing.defaults["EquityOption"] == "AnalyticBS"
    assert config.pricing.params["FdBS"]["t_grid"] == 400


def test_template_engine_overrides_type_default(config, market):
    t = trade(config, "SPX_EURO", id="c", option_type="Call", strike=6000,
              expiry=date(2027, 10, 22), quantity=1, engine="FdBS")  # fmt: skip
    book = Portfolio([t]).build(market, config)
    assert list(book.engines)[0][0] == "FdBS"
