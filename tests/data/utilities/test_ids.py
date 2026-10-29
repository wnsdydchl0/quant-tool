import pytest

from quanttool.data.utilities.ids import QuoteId, Unit, bp_to_decimal
from quanttool.qle.scenario import RiskFactorKey


def test_quote_id_round_trip():
    q = QuoteId.parse("UST/PAR/2Y")
    assert (q.family, q.field, q.point) == ("UST", "PAR", "2Y")
    assert str(q) == "UST/PAR/2Y"
    assert q.unit is Unit.DECIMAL


@pytest.mark.parametrize("text", ["UST/PAR", "UST/XYZ/2Y", "UST//2Y", "a/b/c/d"])
def test_quote_id_rejects(text):
    with pytest.raises(ValueError):
        QuoteId.parse(text)


def test_risk_factor_key():
    k = RiskFactorKey("zero", "UST", ["5Y"])
    assert k.point == ("5Y",)
    assert k == RiskFactorKey("zero", "UST", ("5Y",))
    assert hash(k) == hash(RiskFactorKey("zero", "UST", ("5Y",)))
    assert str(RiskFactorKey("equity_vol", "SPX", ("1Y", 1.0))) == "equity_vol/SPX/1Y/1.0"
    with pytest.raises(ValueError):
        RiskFactorKey("bogus", "UST")


def test_bp():
    assert bp_to_decimal(25) == pytest.approx(0.0025)
