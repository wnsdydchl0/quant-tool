"""커브 지정 문자열. ORE 대응: OREData/ored/marketdata/curvespec.hpp, curvespecparser.cpp.

todaysmarket.yaml은 "시장에서 부르는 이름 → 레시피"를 ``Yield/USD/UST`` 같은 문자열로 적는다.
문자열은 ``종류/통화/레시피 id``이고, 레시피 id는 curve_configs의 키다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CurveType(StrEnum):
    Yield = "Yield"


@dataclass(frozen=True)
class CurveSpec:
    curve_config_id: str

    @property
    def base_type(self) -> CurveType:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class YieldCurveSpec(CurveSpec):
    ccy: str = ""

    @property
    def base_type(self) -> CurveType:
        return CurveType.Yield

    @property
    def name(self) -> str:
        return f"Yield/{self.ccy}/{self.curve_config_id}"


def parse_curve_spec(s: str) -> CurveSpec:
    tokens = s.split("/")
    if tokens[0] == CurveType.Yield.value:
        if len(tokens) != 3:
            raise ValueError(f"Yield 커브 지정은 Yield/통화/레시피id 형식이어야 한다: {s!r}")
        return YieldCurveSpec(curve_config_id=tokens[2], ccy=tokens[1])
    raise ValueError(f"지원하지 않는 커브 종류 {tokens[0]!r}: {s!r}")
