"""상품 유형 → 평가 방법. ORE 대응: OREData/ored/portfolio/enginedata.hpp (pricingengine.xml).

engines.yaml:
    global_parameters: {...}            # 모든 빌더에 전달 (예: RunType)
    products:
      Bond:
        model: DiscountedCashflows
        model_parameters: {}
        engine: DiscountingRiskyBondEngine
        engine_parameters: {SensitivityTemplate: ...}   # 거래별 민감도 규칙 (분석 단계에서 사용)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProductEngineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    model_parameters: dict[str, Any] = {}
    engine: str
    engine_parameters: dict[str, Any] = {}


class EngineData(BaseModel):
    """ORE ``EngineData``."""

    model_config = ConfigDict(extra="forbid")

    global_parameters: dict[str, Any] = {}
    products: dict[str, ProductEngineSpec] = {}

    def has_product(self, product: str) -> bool:
        return product in self.products

    def _spec(self, product: str) -> ProductEngineSpec:
        try:
            return self.products[product]
        except KeyError:
            raise KeyError(
                f"engines.yaml에 {product!r} 설정이 없다: {sorted(self.products)}"
            ) from None

    def model(self, product: str) -> str:
        return self._spec(product).model

    def engine(self, product: str) -> str:
        return self._spec(product).engine

    def model_parameters(self, product: str) -> dict[str, Any]:
        return dict(self._spec(product).model_parameters)

    def engine_parameters(self, product: str) -> dict[str, Any]:
        return dict(self._spec(product).engine_parameters)

    def copy_with_global(self, **params: Any) -> EngineData:
        """global_parameters를 덧붙인 복사본 (ORE SensitivityAnalysis가 RunType을 넣을 때처럼)."""
        return EngineData(
            global_parameters={**self.global_parameters, **params}, products=self.products
        )
