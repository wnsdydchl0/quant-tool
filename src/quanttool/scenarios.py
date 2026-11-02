"""시나리오 = {요인 키: 기준 대비 이동}. 만드는 규칙은 보통 함수다.

- 요인 키는 "객체 이름/요인 이름" (커브면 "UST/5Y", 값은 제로금리 이동, 소수).
- 여러 객체의 요인을 한 시나리오에 함께 담을 수 있다 (예: spot과 vol을 SSR로 함께, PCA 요인).
- 적용은 market.apply(s) 또는 with market.scenario(s): ...
"""

from __future__ import annotations

from collections.abc import Mapping

import QuantLib as ql

from .curves import DC
from .market import Market

Scenario = dict[str, float]


def parallel(market: Market, curve: str, size: float) -> Scenario:
    """커브 전체 평행 이동."""
    return {f"{curve}/{t}": size for t in market.objects[curve].tenors}


def from_loadings(curve: str, loadings: Mapping[str, float], size: float) -> Scenario:
    """요인 크기 × 격자점별 로딩 (PCA 요인, 스티프닝 등). 로딩은 configs/estimated/에서 읽는다."""
    return {f"{curve}/{t}": size * w for t, w in loadings.items()}


def combine(*scenarios: Mapping[str, float]) -> Scenario:
    """이동을 더한다 (같은 요인이면 합)."""
    out: Scenario = {}
    for s in scenarios:
        for k, v in s.items():
            out[k] = out.get(k, 0.0) + v
    return out


def triangle_weight(shift_times: list[float], j: int, t: float) -> float:
    """이동 만기 j의 삼각형 가중치 (양 끝 밖은 평탄). 이동 만기가 격자보다 성길 때 쓴다."""
    tj, n = shift_times[j], len(shift_times)
    if t <= tj:
        if j == 0:
            return 1.0
        lo = shift_times[j - 1]
        return max(0.0, (t - lo) / (tj - lo))
    if j == n - 1:
        return 1.0
    hi = shift_times[j + 1]
    return max(0.0, (hi - t) / (hi - tj))


def bucket(market: Market, curve: str, shift_tenors: list[str], j: int, size: float) -> Scenario:
    """이동 만기 j를 size만큼: 격자점마다 삼각형 가중치를 곱해 이동한다 (합하면 평행 이동)."""
    obj = market.objects[curve]
    ref = obj.base.referenceDate()
    shift_times = [DC.yearFraction(ref, ref + ql.Period(t)) for t in shift_tenors]
    out: Scenario = {}
    for t, time in obj.times.items():
        w = triangle_weight(shift_times, j, time)
        if w:
            out[f"{curve}/{t}"] = size * w
    return out
