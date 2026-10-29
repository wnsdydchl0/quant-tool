"""시나리오 데이터. ORE 대응: OREAnalytics/orea/scenario/scenario.hpp.

시나리오는 격자점별 이동량이다. 생성·적용·평가는 분리한다 (원칙 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quanttool.qle.scenario import RiskFactorKey

__all__ = ["RiskFactorKey", "Scenario"]


@dataclass(frozen=True)
class Scenario:
    label: tuple | str
    shifts: dict[RiskFactorKey, float] = field(default_factory=dict)  # 소수 (금리 0.0001 = 1bp)
