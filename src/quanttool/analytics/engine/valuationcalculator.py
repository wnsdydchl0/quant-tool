"""평가 후 무엇을 큐브에 남길지. ORE 대응: OREAnalytics/orea/engine/valuationcalculator.hpp.

ValuationEngine은 시장을 갱신한 뒤 거래마다 계산기를 부른다. 계산기를 바꿔 끼우면 같은 반복으로
NPV, 현금흐름 등 다른 값을 남긴다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quanttool.analytics.cube import NPVCube
    from quanttool.analytics.scenario import SimMarket
    from quanttool.data.portfolio import Trade


class ValuationCalculator(ABC):
    @abstractmethod
    def calculate(
        self,
        trade: Trade,
        trade_index: int,
        sim_market: SimMarket,
        output_cube: NPVCube,
        date_index: int,
        sample: int,
    ) -> None: ...

    @abstractmethod
    def calculate_t0(
        self, trade: Trade, trade_index: int, sim_market: SimMarket, output_cube: NPVCube
    ) -> None: ...


class NPVCalculator(ValuationCalculator):
    """거래 NPV를 기준 통화로 기록 (ORE NPVCalculator). 지금은 기준 통화 거래만 지원한다."""

    def __init__(self, base_ccy: str, index: int = 0) -> None:
        self.base_ccy = base_ccy
        self.index = index

    def _npv(self, trade: Trade) -> float:
        ccy = trade.npv_currency()
        if ccy and ccy != self.base_ccy:
            raise NotImplementedError(f"{trade.id}: {ccy} → {self.base_ccy} 환산은 아직 없다")
        return trade.npv()

    def calculate(self, trade, trade_index, sim_market, output_cube, date_index, sample) -> None:
        output_cube.set(self._npv(trade), trade_index, date_index, sample, self.index)

    def calculate_t0(self, trade, trade_index, sim_market, output_cube) -> None:
        output_cube.set_t0(self._npv(trade), trade_index, self.index)
