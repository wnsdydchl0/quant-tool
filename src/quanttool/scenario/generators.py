"""시나리오(데이터)와 생성기. ORE 대응: OREAnalytics/orea/scenario/scenario.hpp,
sensitivityscenariogenerator.hpp.

시나리오는 격자점별 이동량이다. 생성·적용·평가는 분리한다 (원칙 7).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from quanttool.config import SensitivityConfig
from quanttool.core.ids import RiskFactorKey, bp_to_decimal

from .factors import KeyRateFactors
from .grid import ScenarioGrid


@dataclass(frozen=True)
class Scenario:
    label: tuple | str
    shifts: dict[RiskFactorKey, float] = field(default_factory=dict)  # 소수 (금리 0.0001 = 1bp)


class ScenarioGenerator(ABC):
    @abstractmethod
    def generate(self) -> Iterable[Scenario]: ...


class SensitivityGenerator(ScenarioGenerator):
    """격자점별 key rate 이동과 커브별 평행 이동 (한쪽 방향, 위로)."""

    def __init__(
        self, grid: ScenarioGrid, cfg: SensitivityConfig, curves: list[str] | None = None
    ) -> None:
        self.grid = grid
        self.cfg = cfg
        self.curves = curves or grid.names()

    def generate(self) -> Iterator[Scenario]:
        kr = bp_to_decimal(self.cfg.key_rate_bp)
        par = bp_to_decimal(self.cfg.parallel_bp)
        for name in self.curves:
            factors = KeyRateFactors(self.grid, name)
            for label, loading in factors.loadings().items():
                yield Scenario(("key_rate", name, label), {k: kr * w for k, w in loading.items()})
            yield Scenario(("parallel", name), {k: par for k in self.grid.keys(name)})
