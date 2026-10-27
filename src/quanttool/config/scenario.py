"""시나리오 설정 (ORE simulation.xml 격자, sensitivity.xml 대응)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class GridSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["zero"]
    tenors: list[str] = Field(min_length=2)
    interpolation: Literal["Linear(Zero)", "LogLinear(Discount)"] = "Linear(Zero)"
    extrapolation: Literal["flat_zero"] = "flat_zero"


class GridConfig(RootModel[dict[str, GridSpec]]):
    """시장 객체 이름 → 격자 정의."""


class SensitivityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key_rate_bp: float = Field(1.0, gt=0)
    parallel_bp: float = Field(1.0, gt=0)
