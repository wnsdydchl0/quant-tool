"""configs/의 YAML을 읽어 검증된 설정 객체로 만든다."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from .market import RateConventions, TodaysMarketConfig, YieldCurveConfig
from .pricing import EngineSpec, PricingConfig
from .scenario import GridConfig, GridSpec, SensitivityConfig

__all__ = [
    "Config",
    "EngineSpec",
    "GridConfig",
    "GridSpec",
    "PricingConfig",
    "RateConventions",
    "SensitivityConfig",
    "TodaysMarketConfig",
    "YieldCurveConfig",
    "load_config",
]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    todaysmarket: TodaysMarketConfig
    conventions: dict[str, RateConventions]
    curves: dict[str, YieldCurveConfig]
    pricing: PricingConfig = PricingConfig({})
    grid: GridConfig = GridConfig({})
    sensitivity: SensitivityConfig = SensitivityConfig()

    @model_validator(mode="after")
    def _check_references(self) -> Config:
        for name in self.todaysmarket.yield_curves:
            if name not in self.curves:
                raise ValueError(f"todaysmarket의 커브 {name!r}에 대한 레시피가 없다")
        for curve in self.curves.values():
            if curve.conventions not in self.conventions:
                raise ValueError(f"{curve.name}: 관례 {curve.conventions!r}가 없다")
        return self


def _read(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(root: str | Path = "configs") -> Config:
    root = Path(root)
    curves = {}
    for p in sorted((root / "market" / "curves").glob("*.yaml")):
        data = _read(p)
        if data["name"] in curves:
            raise ValueError(f"커브 이름 중복: {data['name']} ({p})")
        curves[data["name"]] = data
    data = {
        "todaysmarket": _read(root / "market" / "todaysmarket.yaml"),
        "conventions": _read(root / "conventions" / "rates.yaml"),
        "curves": curves,
    }
    optional = {
        "pricing": root / "pricing" / "engines.yaml",
        "grid": root / "scenario" / "grid.yaml",
        "sensitivity": root / "scenario" / "sensitivity.yaml",
    }
    for key, path in optional.items():
        if path.exists():
            data[key] = _read(path)
    return Config.model_validate(data)
