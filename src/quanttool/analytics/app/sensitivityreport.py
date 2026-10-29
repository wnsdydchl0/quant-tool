"""민감도 표: 시나리오 결과를 1bp당 손익으로 정리한다 (격자 제로금리 기준)."""

from __future__ import annotations

import pandas as pd

from quanttool.analytics.engine import NPVCube
from quanttool.data.configuration import SensitivityScenarioData


def key_rate_dv01(results: NPVCube, cfg: SensitivityScenarioData, curve: str) -> pd.DataFrame:
    """행: 격자 만기, 열: 거래 + total. 값: 해당 격자점 1bp 상승 시 손익."""
    pnl = results.pnl
    mask = [isinstance(lb, tuple) and lb[:2] == ("key_rate", curve) for lb in pnl.index]
    table = pnl[mask] / cfg.key_rate_bp
    table.index = pd.Index([lb[2] for lb in table.index], name="tenor")
    table["total"] = table.sum(axis=1)
    return table


def parallel_dv01(results: NPVCube, cfg: SensitivityScenarioData, curve: str) -> pd.Series:
    """커브 전체 1bp 평행 상승 시 거래별 손익 (+ total)."""
    pnl = results.pnl.loc[[("parallel", curve)]].iloc[0] / cfg.parallel_bp
    pnl["total"] = pnl.sum()
    return pnl.rename("parallel_dv01")
