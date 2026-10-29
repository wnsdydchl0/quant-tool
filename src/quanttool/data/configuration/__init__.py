"""레시피(설정) 읽기. ORE 대응: OREData/ored/configuration/.

configs/의 YAML을 읽어 검증된 설정 객체로 만든다 (ORE의 XML fromFile 대응).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from .conventions import Conventions, InstrumentConventions, RateConventions
from .curveconfig import YieldCurveConfig
from .curvespec import CurveSpec, YieldCurveSpec, parse_curve_spec
from .enginedata import EngineData, ProductEngineSpec
from .simmarketparameters import (
    ScenarioSimMarketParameters,
    SensitivityScenarioData,
    YieldCurveSimParameters,
)
from .todaysmarketparameters import (
    DEFAULT_CONFIGURATION,
    MarketConfiguration,
    MarketObject,
    TodaysMarketParameters,
)

__all__ = [
    "DEFAULT_CONFIGURATION",
    "Config",
    "Conventions",
    "CurveSpec",
    "InstrumentConventions",
    "MarketConfiguration",
    "MarketObject",
    "ProductEngineSpec",
    "EngineData",
    "RateConventions",
    "ScenarioSimMarketParameters",
    "SensitivityScenarioData",
    "TodaysMarketParameters",
    "YieldCurveConfig",
    "YieldCurveSimParameters",
    "YieldCurveSpec",
    "load_config",
    "parse_curve_spec",
]


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    todaysmarket: TodaysMarketParameters
    conventions: dict[str, RateConventions]
    curve_configs: dict[str, YieldCurveConfig]
    engine_data: EngineData = EngineData()
    simmarket: ScenarioSimMarketParameters = ScenarioSimMarketParameters({})
    sensitivity: SensitivityScenarioData = SensitivityScenarioData()

    @model_validator(mode="after")
    def _check_references(self) -> Config:
        for conf in self.todaysmarket.configurations:
            for spec_str in self.todaysmarket.curve_specs(conf):
                spec = parse_curve_spec(spec_str)
                recipe = self.curve_configs.get(spec.curve_config_id)
                if recipe is None:
                    raise ValueError(f"todaysmarket의 {spec_str!r}에 대한 레시피가 없다")
                if isinstance(spec, YieldCurveSpec) and recipe.currency != spec.ccy:
                    raise ValueError(f"{spec_str!r}: 레시피 통화 {recipe.currency!r}와 다르다")
        for curve in self.curve_configs.values():
            for seg in curve.segments:
                if seg.conventions not in self.conventions:
                    raise ValueError(f"{curve.curve_id}: 관례 {seg.conventions!r}가 없다")
            for dep in curve.required_curve_ids():
                if dep not in self.curve_configs:
                    raise ValueError(f"{curve.curve_id}: 의존 레시피 {dep!r}가 없다")
        return self


def _read(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(root: str | Path = "configs") -> Config:
    root = Path(root)
    curves = {}
    for p in sorted((root / "market" / "curves").glob("*.yaml")):
        data = _read(p)
        if data["curve_id"] in curves:
            raise ValueError(f"커브 id 중복: {data['curve_id']} ({p})")
        curves[data["curve_id"]] = data
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
    cfg = Config.model_validate(data)
    # ORE InputParameters와 같이 관례를 전역 등록부에 둔다
    InstrumentConventions.instance().set_conventions(Conventions(cfg.conventions))
    return cfg
