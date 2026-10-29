"""기준 시나리오를 흔들어 만드는 생성기.

ORE 대응: OREAnalytics/orea/scenario/shiftscenariogenerator.hpp.

ScenarioDescription: 시나리오가 무엇을 흔들었는지 (Base / Up / Down / Cross, 리스크 요인, 이름).
apply_curve_shift: 이동 만기(shift tenor)의 삼각형 이동을 격자 시간에 선형 보간해 제로금리에 더하고,
격자 Quote 값(할인계수 또는 비율)에 exp(−Δz·t)를 곱한다 (ORE ShiftScenarioGenerator::applyShift).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from quanttool.qle.scenario import DeltaScenario, RiskFactorKey, Scenario

from .scenariogenerator import ListScenarioGenerator


class DescriptionType(StrEnum):
    Base = "Base"
    Up = "Up"
    Down = "Down"
    Cross = "Cross"


@dataclass(frozen=True)
class ScenarioDescription:
    """ORE ``ShiftScenarioGenerator::ScenarioDescription``."""

    type: DescriptionType
    key1: RiskFactorKey | None = None
    index_desc1: str = ""  # 예: "5Y"
    key2: RiskFactorKey | None = None
    index_desc2: str = ""

    def factor1(self) -> str:
        return f"{self.key1}/{self.index_desc1}" if self.key1 else ""

    def factor2(self) -> str:
        return f"{self.key2}/{self.index_desc2}" if self.key2 else ""

    def __str__(self) -> str:
        if self.type == DescriptionType.Base:
            return "Base"
        if self.type == DescriptionType.Cross:
            return f"Cross:{self.factor1()}:{self.factor2()}"
        return f"{self.type}:{self.factor1()}"


def triangle_weights(shift_times: list[float], j: int, t: float) -> float:
    """shift tenor j의 삼각형 가중치를 시간 t에서 (양 끝 밖은 평탄). ORE applyShift와 같은 모양."""
    n = len(shift_times)
    tj = shift_times[j]
    if t == tj:
        return 1.0
    if t < tj:
        if j == 0:
            return 1.0
        lo = shift_times[j - 1]
        return max(0.0, (t - lo) / (tj - lo)) if t > lo else 0.0
    if j == n - 1:
        return 1.0
    hi = shift_times[j + 1]
    return max(0.0, (hi - t) / (hi - tj)) if t < hi else 0.0


def apply_curve_shift(
    base: Scenario,
    keys: list[RiskFactorKey],
    grid_times: list[float],
    shift_times: list[float],
    j: int,
    size: float,
    shift_type: str = "Absolute",
    base_zero: list[float] | None = None,
) -> dict[RiskFactorKey, float]:
    """shift tenor j를 size만큼 (제로금리) 흔든 격자 Quote 값."""
    out: dict[RiskFactorKey, float] = {}
    for i, (k, t) in enumerate(zip(keys, grid_times, strict=True)):
        w = triangle_weights(shift_times, j, t)
        if w == 0.0:
            continue
        dz = size * w
        if shift_type == "Relative":
            if base_zero is None:
                raise ValueError("Relative 이동에는 기준 제로금리가 필요하다")
            dz = base_zero[i] * size * w
        out[k] = base.get(k) * math.exp(-dz * t)
    return out


class ShiftScenarioGenerator(ListScenarioGenerator):
    """기준 + 흔든 시나리오 목록과 설명. ORE ``ShiftScenarioGenerator``."""

    def __init__(self, base_scenario: Scenario) -> None:
        self.base_scenario = base_scenario
        self.descriptions: list[ScenarioDescription] = [ScenarioDescription(DescriptionType.Base)]
        super().__init__([base_scenario])

    def _add(self, desc: ScenarioDescription, delta: dict[RiskFactorKey, float]) -> None:
        self.scenarios.append(DeltaScenario(self.base_scenario, delta, label=str(desc)))
        self.descriptions.append(desc)

    def scenario_descriptions(self) -> list[ScenarioDescription]:
        return list(self.descriptions)
