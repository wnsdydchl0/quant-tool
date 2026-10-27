"""평가 방법 설정 (ORE pricingengine.xml / EngineData 대응)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, RootModel


class EngineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    engine: str
    params: dict[str, Any] = {}


class PricingConfig(RootModel[dict[str, EngineSpec]]):
    """trade_type → EngineSpec."""

    def __getitem__(self, trade_type: str) -> EngineSpec:
        try:
            return self.root[trade_type]
        except KeyError:
            raise KeyError(
                f"engines.yaml에 {trade_type!r} 설정이 없다: {sorted(self.root)}"
            ) from None
