"""시나리오 생성기 규격. ORE 대응: OREAnalytics/orea/scenario/scenariogenerator.hpp.

next(d)는 지금 표본(경로)의 날짜 d 시나리오를 준다. 날짜가 앞으로 가면 같은 표본에 머물고,
날짜가 처음(이전 이하)으로 돌아오면 다음 표본으로 넘어간다. 민감도·스트레스처럼 시간에 따라
변하지 않는 시나리오는 표본 하나가 모든 날짜에 같다. SimMarket.update(d)가 next(d)를 부른다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from quanttool.qle.scenario import Scenario


class ScenarioGenerator(ABC):
    @abstractmethod
    def next(self, d: date) -> Scenario: ...

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def samples(self) -> int: ...


class ListScenarioGenerator(ScenarioGenerator):
    """정해진 시나리오 목록을 차례로 내주는 생성기 (민감도·스트레스·손으로 만든 시나리오)."""

    def __init__(self, scenarios: list[Scenario]) -> None:
        self.scenarios = list(scenarios)
        self.reset()

    def next(self, d: date) -> Scenario:
        if self._last_date is None or d <= self._last_date:
            self._counter += 1
        if self._counter >= len(self.scenarios):
            raise StopIteration(f"시나리오 {len(self.scenarios)}개를 모두 썼다")
        self._last_date = d
        return self.scenarios[self._counter]

    def reset(self) -> None:
        self._counter = -1
        self._last_date: date | None = None

    def samples(self) -> int:
        return len(self.scenarios)
