"""리스크 요인: 요인 이름 → 격자점 로딩. PCA 등 추정 요인은 configs/estimated/에서 읽는다."""

from __future__ import annotations

from abc import ABC, abstractmethod

from quanttool.core.ids import RiskFactorKey

from .grid import ScenarioGrid


class RiskFactors(ABC):
    @abstractmethod
    def loadings(self) -> dict[str, dict[RiskFactorKey, float]]: ...


class KeyRateFactors(RiskFactors):
    """격자점 하나씩 1만큼 움직이는 요인. 요인 이름은 만기 라벨."""

    def __init__(self, grid: ScenarioGrid, name: str) -> None:
        self.keys = grid.keys(name)

    def loadings(self) -> dict[str, dict[RiskFactorKey, float]]:
        return {k.point[0]: {k: 1.0} for k in self.keys}
