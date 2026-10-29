"""민감도 시나리오 생성기. ORE 대응: OREAnalytics/orea/scenario/sensitivityscenariogenerator.hpp."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from datetime import date

from quanttool.data.configuration import ScenarioSimMarketParameters, SensitivityScenarioData
from quanttool.data.utilities.ids import bp_to_decimal

from .scenario import Scenario


class ScenarioGenerator(ABC):
    """시나리오를 차례로 내준다. SimMarket.update(d)는 next(d)로 받는다 (ORE와 같은 방식).

    next(d)는 지금 표본(경로)의 날짜 d 시나리오를 준다. 날짜가 앞으로 가면 같은 표본에 머물고,
    날짜가 처음(이전 이하)으로 돌아오면 다음 표본으로 넘어간다. 민감도·스트레스처럼 시간에
    따라 변하지 않는 시나리오는 표본 하나가 모든 날짜에 같다.
    """

    _iter: Iterator[Scenario] | None = None
    _current: Scenario | None = None
    _last_date: date | None = None

    @abstractmethod
    def generate(self) -> Iterable[Scenario]: ...

    def next(self, d: date) -> Scenario:
        if self._iter is None:
            self._iter = iter(self.generate())
        if self._current is None or self._last_date is None or d <= self._last_date:
            self._current = next(self._iter)
        self._last_date = d
        return self._current

    def reset(self) -> None:
        self._iter = None
        self._current = None
        self._last_date = None

    def samples(self) -> int:
        """시나리오(표본) 개수 (ORE ScenarioGenerator::samples)."""
        return sum(1 for _ in self.generate())


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
