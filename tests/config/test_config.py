import shutil
from pathlib import Path

import pytest
import QuantLib as ql
import yaml
from pydantic import ValidationError

from quanttool.config import load_config, qlmap

CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def test_load_repo_configs():
    cfg = load_config(CONFIGS)
    ust = cfg.curves["UST"]
    assert cfg.todaysmarket.yield_curves == ["UST"]
    assert ust.quote_ids()[0] == "UST/PAR/1M"
    assert ust.quote_ids()[-1] == "UST/PAR/30Y"
    assert cfg.conventions["UST"].settlement_days == 1
    assert cfg.pricing["FixedBond"].engine == "DiscountingBond"
    assert cfg.grid.root["UST"].tenors[0] == "1M"
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
    assert qlmap.calendar("UnitedStates.GovernmentBond") == ql.UnitedStates(
        ql.UnitedStates.GovernmentBond
    )
    assert qlmap.day_counter("Actual365Fixed") == ql.Actual365Fixed()
    assert qlmap.frequency("Semiannual") == ql.Semiannual
    with pytest.raises(ValueError):
        qlmap.day_counter("Actual999")
