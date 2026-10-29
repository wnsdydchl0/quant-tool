"""NPV 큐브: 거래 × 날짜 × 표본(× 깊이).

ORE 대응: OREAnalytics/orea/cube/npvcube.hpp, inmemorycube.hpp.

- set_t0/get_t0: 기준(오늘) 값
- set/get: (거래, 날짜 번호, 표본 번호, 깊이)의 값. 깊이는 계산기가 여러 값을 남길 때 쓴다.
민감도에서는 날짜 1개, 표본 = 시나리오 (ORE NPVSensiCube).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


class NPVCube:
    def __init__(self, ids: list[str], asof: date, dates: list[date], samples: int, depth: int = 1):
        self._ids = list(ids)
        self._index = {t: i for i, t in enumerate(self._ids)}
        self.asof = asof
        self._dates = list(dates)
        self._t0 = np.full((len(ids), depth), np.nan)
        self._data = np.full((len(ids), len(dates), samples, depth), np.nan)

    # --- ORE 조회
    def ids(self) -> list[str]:
        return list(self._ids)

    def dates(self) -> list[date]:
        return list(self._dates)

    def num_ids(self) -> int:
        return len(self._ids)

    def num_dates(self) -> int:
        return len(self._dates)

    def samples(self) -> int:
        return self._data.shape[2]

    def depth(self) -> int:
        return self._data.shape[3]

    def get_trade_index(self, trade_id: str) -> int:
        return self._index[trade_id]

    def _i(self, trade: str | int) -> int:
        return self._index[trade] if isinstance(trade, str) else trade

    def set_t0(self, value: float, trade: str | int, depth: int = 0) -> None:
        self._t0[self._i(trade), depth] = value

    def get_t0(self, trade: str | int, depth: int = 0) -> float:
        return float(self._t0[self._i(trade), depth])

    def set(self, value: float, trade: str | int, date_idx: int, sample: int, depth: int = 0):
        self._data[self._i(trade), date_idx, sample, depth] = value

    def get(self, trade: str | int, date_idx: int, sample: int, depth: int = 0) -> float:
        return float(self._data[self._i(trade), date_idx, sample, depth])

    # --- pandas 보기 (QuantTool)
    def t0(self, depth: int = 0) -> pd.Series:
        return pd.Series(self._t0[:, depth], index=self._ids, name="t0")

    def to_frame(
        self, date_idx: int = 0, depth: int = 0, labels: list | None = None
    ) -> pd.DataFrame:
        """행: 표본(시나리오), 열: 거래. labels가 있으면 행 이름으로 쓴다."""
        frame = pd.DataFrame(self._data[:, date_idx, :, depth].T, columns=self._ids)
        if labels is not None:
            frame.index = pd.Index(labels, tupleize_cols=False, dtype=object, name="scenario")
        return frame
