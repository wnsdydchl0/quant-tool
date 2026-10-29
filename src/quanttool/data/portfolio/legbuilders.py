"""레그 빌더: LegData → QuantLib Leg. ORE 대응: OREData/ored/portfolio/legbuilders.hpp.

레그 종류마다 빌더 하나를 등록하고, EngineFactory.leg_builder(leg_type)로 꺼낸다.
변동 레그 빌더는 여기서 시장(지수)을 쓴다: factory.market().ibor_index(...) (예정).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

import QuantLib as ql

from quanttool.data.utilities.registry import LEG_BUILDERS

from .legdata import LegData, make_fixed_leg

if TYPE_CHECKING:
    from .enginefactory import EngineFactory


class LegBuilder(ABC):
    leg_type: ClassVar[str]

    @abstractmethod
    def build_leg(
        self,
        data: LegData,
        engine_factory: EngineFactory,
        required_fixings: set,
        configuration: str,
    ) -> ql.Leg: ...


@LEG_BUILDERS.register("Fixed")
class FixedLegBuilder(LegBuilder):
    leg_type = "Fixed"

    def build_leg(self, data, engine_factory, required_fixings, configuration) -> ql.Leg:
        return make_fixed_leg(data)
