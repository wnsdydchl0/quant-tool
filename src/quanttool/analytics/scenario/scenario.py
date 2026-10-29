"""시나리오 데이터.

ORE 대응: QuantExt/qle/termstructures/scenario.hpp, OREAnalytics/orea/scenario/deltascenario.hpp.

시나리오는 격자점 → 값이다. 생성(생성기)·적용(SimMarket)·평가(ValuationEngine)를 분리한다 (원칙 7).
"""

from quanttool.qle.scenario import DeltaScenario, KeyType, RiskFactorKey, Scenario, SimpleScenario

__all__ = ["DeltaScenario", "KeyType", "RiskFactorKey", "Scenario", "SimpleScenario"]
