"""레시피(설정) 읽기. ORE 대응: OREData/ored/configuration/.

configs/의 YAML을 읽어 검증된 설정 객체로 만든다 (ORE의 XML fromFile 대응).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from .conventions import RateConventions
from .curveconfig import YieldCurveConfig
from .enginedata import EngineData, EngineSpec
from .simmarketparameters import (
    ScenarioSimMarketParameters,
    SensitivityScenarioData,
    YieldCurveSimParameters,
)
from .todaysmarketparameters import TodaysMarketParameters

__all__ = [
    "Config",
    "EngineData",
    "EngineSpec",
    "RateConventions",
    "ScenarioSimMarketParameters",
    "SensitivityScenarioData",
    "TodaysMarketParameters",
    "YieldCurveConfig",
    "YieldCurveSimParameters",
    "load_config",
]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    todaysmarket: TodaysMarketParameters
    conventions: dict[str, RateConventions]
    curve_configs: dict[str, YieldCurveConfig]
    engine_data: EngineData = EngineData({})
    simmarket: ScenarioSimMarketParameters = ScenarioSimMarketParameters({})
    sensitivity: SensitivityScenarioData = SensitivityScenarioData()

    @model_validator(mode="after")
    def _check_references(self) -> Config:
        for name in self.todaysmarket.yield_curves:
            if name not in self.curve_configs:
                raise ValueError(f"todaysmarket의 커브 {name!r}에 대한 레시피가 없다")
        for curve in self.curve_configs.values():
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
        "curve_configs": curves,
    }
    optional = {
        "engine_data": root / "pricing" / "engines.yaml",
        "simmarket": root / "scenario" / "simmarket.yaml",
        "sensitivity": root / "scenario" / "sensitivity.yaml",
    }
    for key, path in optional.items():
        if path.exists():
            data[key] = _read(path)
    return Config.model_validate(data)
