"""민감도 설정. ORE 대응: OREAnalytics/orea/scenario/sensitivityscenariodata.hpp (sensitivity.xml).

sensitivity.yaml:
    use_spreaded_term_structures: true
    compute_gamma: true
    yield_curves:
      UST:
        shift_type: Absolute          # Absolute | Relative
        shift_size: 0.0001
        shift_scheme: Forward         # Forward | Backward | Central
        shift_tenors: [1M, ..., 30Y]
        keyed_shift_size: {IR_FD: 0.001}       # 템플릿별 덮어쓰기 (ORE ShiftSize key="IR_FD")
        keyed_shift_scheme: {IR_FD: Central}
    discount_curves: {}               # 통화 → 같은 형식
    cross_gamma_filter: [[YieldCurve/UST, YieldCurve/UST]]
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ShiftType = Literal["Absolute", "Relative"]
ShiftScheme = Literal["Forward", "Backward", "Central"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ShiftData(_Strict):
    """ORE ``SensitivityScenarioData::ShiftData``."""

    shift_type: ShiftType = "Absolute"
    shift_size: float = Field(gt=0)
    shift_scheme: ShiftScheme = "Forward"
    keyed_shift_size: dict[str, float] = {}
    keyed_shift_scheme: dict[str, ShiftScheme] = {}

    def size(self, template: str = "") -> float:
        return self.keyed_shift_size.get(template, self.shift_size)

    def scheme(self, template: str = "") -> ShiftScheme:
        return self.keyed_shift_scheme.get(template, self.shift_scheme)


class CurveShiftData(ShiftData):
    """ORE ``CurveShiftData``: 이동할 만기(격자와 달라도 된다)."""

    shift_tenors: list[str] = Field(min_length=1)


class SensitivityScenarioData(_Strict):
    """ORE ``SensitivityScenarioData``."""

    use_spreaded_term_structures: bool = True
    compute_gamma: bool = True
    discount_curves: dict[str, CurveShiftData] = {}
    yield_curves: dict[str, CurveShiftData] = {}
    cross_gamma_filter: list[tuple[str, str]] = []  # ("YieldCurve/UST", "YieldCurve/UST")

    def templates(self) -> set[str]:
        """설정에 나오는 템플릿 id (ORE getShiftSpecKeys)."""
        out: set[str] = set()
        for d in [*self.discount_curves.values(), *self.yield_curves.values()]:
            out |= set(d.keyed_shift_size) | set(d.keyed_shift_scheme)
        return out
