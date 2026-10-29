"""민감도 시나리오 생성기. ORE 대응: OREAnalytics/orea/scenario/sensitivityscenariogenerator.hpp."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

from quanttool.data.configuration import ScenarioSimMarketParameters, SensitivityScenarioData
from quanttool.data.utilities.ids import bp_to_decimal

from .scenario import Scenario


class ScenarioGenerator(ABC):
    @abstractmethod
    def generate(self) -> Iterable[Scenario]: ...


class SensitivityScenarioGenerator(ScenarioGenerator):
    """격자점별 key rate 이동과 커브별 평행 이동 (한쪽 방향, 위로)."""

    def __init__(
        self,
        params: ScenarioSimMarketParameters,
        data: SensitivityScenarioData,
        curves: list[str] | None = None,
    ) -> None:
        self.params = params
        self.data = data
        self.curves = curves or params.names()

    def generate(self) -> Iterator[Scenario]:
        kr = bp_to_decimal(self.data.key_rate_bp)
        par = bp_to_decimal(self.data.parallel_bp)
        for name in self.curves:
            keys = self.params.keys(name)
            for k in keys:
                yield Scenario(("key_rate", name, k.point[0]), {k: kr})
            yield Scenario(("parallel", name), {k: par for k in keys})
