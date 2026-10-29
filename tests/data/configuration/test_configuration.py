import shutil
from pathlib import Path

import pytest
import QuantLib as ql
import yaml
from pydantic import ValidationError

from quanttool.data.configuration import load_config
from quanttool.data.utilities import parsers

CONFIGS = Path(__file__).resolve().parents[3] / "configs"


def test_load_repo_configs():
    cfg = load_config(CONFIGS)
    ust = cfg.curve_configs["UST"]
    assert cfg.todaysmarket.yield_curves == ["UST"]
    assert ust.quote_ids()[0] == "UST/PAR/1M"
    assert ust.quote_ids()[-1] == "UST/PAR/30Y"
    assert cfg.conventions["UST"].settlement_days == 1
    assert cfg.engine_data["Bond"].engine == "DiscountingBondEngine"
    assert cfg.simmarket.root["UST"].tenors[0] == "1M"
    assert cfg.sensitivity.key_rate_bp == 1.0


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
    _edit(root / "market/todaysmarket.yaml", lambda d: d.update(yield_curves=["UST", "KRW_KTB"]))
    with pytest.raises(ValidationError, match="KRW_KTB"):
        load_config(root)


def test_qlmap():
    assert parsers.calendar("UnitedStates.GovernmentBond") == ql.UnitedStates(
        ql.UnitedStates.GovernmentBond
    )
    assert parsers.day_counter("Actual365Fixed") == ql.Actual365Fixed()
    assert parsers.frequency("Semiannual") == ql.Semiannual
    with pytest.raises(ValueError):
        parsers.day_counter("Actual999")
