"""민감도 큐브: 시나리오별 NPV → delta, gamma, cross gamma.

ORE 대응: OREAnalytics/orea/cube/sensitivitycube.hpp/.cpp.

시나리오 설명(ScenarioDescription)으로 표본 번호를 찾는다: 요인마다 Up/Down 표본, 쌍마다 Cross 표본.
- delta: Forward (up − base), Backward (base − down), Central (up − down)/2
- gamma: up − 2·base + down
- cross gamma: up12 − up1 − up2 + base
모두 scaling = 목표 이동 크기 / 실제 이동 크기를 곱한다. 템플릿이 10bp로 계산했어도 1bp 기준으로
보고한다.
ORE와 같이 결과는 "설정한 이동 1회당 NPV 변화"다 (단위 이동당 미분이 아님).
"""

from __future__ import annotations

import pandas as pd

from quanttool.analytics.scenario.shiftscenariogenerator import DescriptionType, ScenarioDescription
from quanttool.qle.scenario import KeyType, RiskFactorKey

from .npvcube import NPVCube


class SensitivityCube:
    def __init__(
        self,
        cube: NPVCube,
        scenario_descriptions: list[ScenarioDescription],
        target_shift_sizes: dict[RiskFactorKey, float],
        actual_shift_sizes: dict[RiskFactorKey, float],
        shift_schemes: dict[RiskFactorKey, str],
    ) -> None:
        self.cube = cube
        self.scenario_descriptions = list(scenario_descriptions)
        self.target_shift_sizes = dict(target_shift_sizes)
        self.actual_shift_sizes = dict(actual_shift_sizes)
        self.shift_schemes = dict(shift_schemes)
        self._up: dict[RiskFactorKey, int] = {}
        self._down: dict[RiskFactorKey, int] = {}
        self._cross: dict[tuple[RiskFactorKey, RiskFactorKey], int] = {}
        self._index_desc: dict[RiskFactorKey, str] = {}
        for i, d in enumerate(self.scenario_descriptions):
            if d.type == DescriptionType.Up:
                self._up[d.key1] = i
                self._index_desc[d.key1] = d.index_desc1
            elif d.type == DescriptionType.Down:
                self._down[d.key1] = i
            elif d.type == DescriptionType.Cross:
                self._cross[(d.key1, d.key2)] = i

    # --- ORE 조회
    def factors(self) -> list[RiskFactorKey]:
        return list(self._up)

    def cross_factors(self) -> list[tuple[RiskFactorKey, RiskFactorKey]]:
        return list(self._cross)

    def factor_description(self, key: RiskFactorKey) -> str:
        return f"{key}/{self._index_desc[key]}"

    def base_npv(self, trade: str) -> float:
        return self.cube.get_t0(trade)

    def _npv(self, trade: str, sample: int) -> float:
        return self.cube.get(trade, 0, sample)

    def _scaling(self, key: RiskFactorKey) -> float:
        target = self.target_shift_sizes.get(key, self.actual_shift_sizes[key])
        return target / self.actual_shift_sizes[key]

    def delta(self, trade: str, key: RiskFactorKey) -> float:
        scheme = self.shift_schemes[key]
        base = self.base_npv(trade)
        if scheme == "Forward":
            return (self._npv(trade, self._up[key]) - base) * self._scaling(key)
        if scheme == "Backward":
            return (base - self._npv(trade, self._down[key])) * self._scaling(key)
        if scheme == "Central":
            up, down = self._npv(trade, self._up[key]), self._npv(trade, self._down[key])
            return (up - down) / 2.0 * self._scaling(key)
        raise ValueError(f"알 수 없는 이동 방식 {scheme!r}")

    def gamma(self, trade: str, key: RiskFactorKey) -> float:
        if key not in self._down:
            raise KeyError(f"{key}: Down 시나리오가 없다 (compute_gamma=false)")
        up, down = self._npv(trade, self._up[key]), self._npv(trade, self._down[key])
        return (up - 2.0 * self.base_npv(trade) + down) * self._scaling(key) ** 2

    def cross_gamma(self, trade: str, pair: tuple[RiskFactorKey, RiskFactorKey]) -> float:
        k1, k2 = pair
        if pair not in self._cross:
            pair = (k2, k1)
        both = self._npv(trade, self._cross[pair])
        up1, up2 = self._npv(trade, self._up[k1]), self._npv(trade, self._up[k2])
        return (both - up1 - up2 + self.base_npv(trade)) * self._scaling(k1) * self._scaling(k2)

    # --- 리포트 (ORE sensitivity 리포트 열과 같은 순서)
    def report(self) -> pd.DataFrame:
        rows = []
        for trade in self.cube.ids():
            for k in self.factors():
                rows.append(
                    {
                        "TradeId": trade,
                        "Factor_1": self.factor_description(k),
                        "ShiftSize_1": self.target_shift_sizes.get(k, self.actual_shift_sizes[k]),
                        "Factor_2": "",
                        "ShiftSize_2": float("nan"),
                        "Base NPV": self.base_npv(trade),
                        "Delta": self.delta(trade, k),
                        "Gamma": self.gamma(trade, k) if k in self._down else float("nan"),
                    }
                )
            for k1, k2 in self.cross_factors():
                rows.append(
                    {
                        "TradeId": trade,
                        "Factor_1": self.factor_description(k1),
                        "ShiftSize_1": self.actual_shift_sizes[k1],
                        "Factor_2": self.factor_description(k2),
                        "ShiftSize_2": self.actual_shift_sizes[k2],
                        "Base NPV": self.base_npv(trade),
                        "Delta": float("nan"),
                        "Gamma": self.cross_gamma(trade, (k1, k2)),
                    }
                )
        return pd.DataFrame(rows)

    def delta_table(
        self, key_type: KeyType | str, name: str, measure: str = "Delta"
    ) -> pd.DataFrame:
        """한 커브의 만기 × 거래 표 (+ total). measure: Delta | Gamma (QuantTool 보기)."""
        keys = [k for k in self.factors() if k.key_type == key_type and k.name == name]
        fn = self.delta if measure == "Delta" else self.gamma
        table = pd.DataFrame(
            {t: [fn(t, k) for k in keys] for t in self.cube.ids()},
            index=pd.Index([self._index_desc[k] for k in keys], name="tenor"),
        )
        table["total"] = table.sum(axis=1)
        return table
