"""민감도 시나리오 생성기. ORE 대응: OREAnalytics/orea/scenario/sensitivityscenariogenerator.hpp."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from datetime import date

from quanttool.data.configuration import ScenarioSimMarketParameters, SensitivityScenarioData
from quanttool.data.utilities.ids import bp_to_decimal

from .scenario import Scenario


class ScenarioGenerator(ABC):
    """시나리오를 차례로 내준다. SimMarket.update(d)는 next(d)로 하나씩 받는다 (ORE와 같은 방식)."""

    _iter: Iterator[Scenario] | None = None

    @abstractmethod
    def generate(self) -> Iterable[Scenario]: ...

    def next(self, d: date) -> Scenario:
        if self._iter is None:
            self._iter = iter(self.generate())
        return next(self._iter)

    def reset(self) -> None:
        self._iter = None


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
