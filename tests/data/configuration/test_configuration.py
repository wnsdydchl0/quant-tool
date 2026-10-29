import shutil
from pathlib import Path

import pytest
import QuantLib as ql
import yaml
from pydantic import ValidationError

from quanttool.data.configuration import (
    InstrumentConventions,
    MarketObject,
    YieldCurveSpec,
    load_config,
    parse_curve_spec,
)
from quanttool.data.utilities import parsers

CONFIGS = Path(__file__).resolve().parents[3] / "configs"


def test_load_repo_configs():
    cfg = load_config(CONFIGS)
    ust = cfg.curve_configs["UST"]
    assert cfg.todaysmarket.mapping(MarketObject.YieldCurve) == {"UST": "Yield/USD/UST"}
    assert cfg.todaysmarket.mapping(MarketObject.DiscountCurve) == {"USD": "Yield/USD/UST"}
    assert cfg.todaysmarket.curve_specs() == ["Yield/USD/UST"]
    assert ust.quotes()[0] == "BOND/YIELD/USD/UST/PAR/1M"
    assert ust.quotes()[-1] == "BOND/YIELD/USD/UST/PAR/30Y"
    assert ust.interpolation_method == "LogCubic"
    assert cfg.conventions["UST"].settlement_days == 1
    assert cfg.engine_data.engine("Bond") == "DiscountingRiskyBondEngine"
    assert cfg.simmarket.yield_curve_tenors("UST")[0] == "1M"
    assert cfg.simmarket.yield_curve_names() == ["UST"]
    assert cfg.sensitivity.yield_curves["UST"].shift_size == 1e-4
    assert cfg.sensitivity.use_spreaded_term_structures


def _copy(tmp_path: Path) -> Path:
    dst = tmp_path / "configs"
    shutil.copytree(CONFIGS, dst)
    return dst


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_bad_segment_type(tmp_path):
    root = _copy(tmp_path)
    _edit(root / "market/curves/ust.yaml", lambda d: d["segments"][0].update(type="Swap"))
    with pytest.raises(ValidationError):
        load_config(root)


def test_unsupported_calendar(tmp_path):
    root = _copy(tmp_path)
    _edit(root / "conventions/rates.yaml", lambda d: d["UST"].update(calendar="Mars"))
    with pytest.raises(ValidationError, match="Mars"):
        load_config(root)


def test_missing_curve_recipe(tmp_path):
    root = _copy(tmp_path)
    _edit(
        root / "market/todaysmarket.yaml",
        lambda d: d["yield_curves"]["default"].update(KTB="Yield/KRW/KRW_KTB"),
    )
    with pytest.raises(ValidationError, match="KRW_KTB"):
        load_config(root)


def test_spec_currency_must_match_recipe(tmp_path):
    root = _copy(tmp_path)
    _edit(
        root / "market/todaysmarket.yaml",
        lambda d: d["discounting_curves"]["default"].update(EUR="Yield/EUR/UST"),
    )
    with pytest.raises(ValidationError, match="통화"):
        load_config(root)


def test_unknown_configuration_group(tmp_path):
    root = _copy(tmp_path)
    _edit(
        root / "market/todaysmarket.yaml",
        lambda d: d["configurations"].update(pricing={"yield_curves_id": "nope"}),
    )
    with pytest.raises(ValidationError, match="nope"):
        load_config(root)


def test_parse_curve_spec():
    spec = parse_curve_spec("Yield/USD/UST")
    assert spec == YieldCurveSpec(curve_config_id="UST", ccy="USD")
    assert spec.name == "Yield/USD/UST"
    with pytest.raises(ValueError):
        parse_curve_spec("Yield/USD")
    with pytest.raises(ValueError):
        parse_curve_spec("Default/USD/X")


def test_load_config_registers_conventions():
    cfg = load_config(CONFIGS)
    conv = InstrumentConventions.instance().conventions()
    assert conv.get("UST") == cfg.conventions["UST"]
    with pytest.raises(KeyError, match="NOPE"):
        conv.get("NOPE")


def test_qlmap():
    assert parsers.calendar("UnitedStates.GovernmentBond") == ql.UnitedStates(
        ql.UnitedStates.GovernmentBond
    )
    assert parsers.day_counter("Actual365Fixed") == ql.Actual365Fixed()
    assert parsers.frequency("Semiannual") == ql.Semiannual
    with pytest.raises(ValueError):
        parsers.day_counter("Actual999")
