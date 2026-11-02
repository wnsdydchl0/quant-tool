"""요인화된 시장 객체: 상품이 연결되는 Handle + 흔들 수 있는 값(요인).

시장 객체 하나가 지키는 규격 (MarketObject):
    handle               상품·엔진이 연결되는 자리 (RelinkableHandle)
    factors()            {이름: SimpleQuote} — 흔들 수 있는 값. 기준 상태 값은 Market이 기억한다
    refresh()            요인이 바뀐 뒤 객체를 다시 만들어야 하면 여기서
                         (Observer로 따라오면 할 일 없음)
    roll(d)              평가일을 d로 옮길 때 기준 구조물을 굴린다

지금은 커브(CurveFactors) 하나다. vol 서페이스는 같은 규격으로 두 방식을 넣을 수 있다:
  - 격자 vol 이동: 요인 = 격자 vol Quote
  - 피팅 파라미터 이동: 요인 = SVI·SABR 파라미터, refresh가 서페이스를 다시 만들어 연결
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import QuantLib as ql

from .curves import DC, to_ql_date

_FAR = "100Y"  # 마지막 격자점 뒤 평탄 외삽 끝점


class MarketObject(Protocol):
    handle: ql.RelinkableYieldTermStructureHandle

    def factors(self) -> dict[str, ql.SimpleQuote]: ...

    def refresh(self) -> None: ...

    def roll(self, d: date) -> None: ...


class CurveFactors:
    """기준 커브 + 격자 만기별 제로금리 이동량(연속복리, 소수).

    커브 = PiecewiseZeroSpreadedTermStructure(기준 커브, 이동량).
    이동량이 0이면 기준 커브와 정확히 같다 (ORE spreaded 시뮬레이션 커브와 같은 아이디어).
    격자점 사이 이동은 선형, 바깥은 평탄.
    """

    def __init__(self, base: ql.YieldTermStructure, asof: date, tenors: list[str]) -> None:
        self.base = base
        self.asof = asof
        self.tenors = list(tenors)
        ref = base.referenceDate()
        dates = [ref + ql.Period(t) for t in self.tenors]
        self.times = {t: DC.yearFraction(ref, d) for t, d in zip(self.tenors, dates, strict=True)}
        self._quotes = {t: ql.SimpleQuote(0.0) for t in self.tenors}
        self._base_link = ql.RelinkableYieldTermStructureHandle(base)
        spreads = [ql.QuoteHandle(q) for q in self._quotes.values()]
        # QuantLib 1.44의 이 클래스는 Quote 변경 시 enableExtrapolation 설정이 풀린다.
        # 외삽 플래그 대신 마지막 Quote에 묶인 먼 끝점으로 평탄 외삽한다.
        curve = ql.PiecewiseZeroSpreadedTermStructure(
            self._base_link,
            [*spreads, spreads[-1]],
            [*dates, ref + ql.Period(_FAR)],
            ql.Continuous,
            ql.NoFrequency,
            DC,
        )
        self.handle = ql.RelinkableYieldTermStructureHandle(curve)

    def factors(self) -> dict[str, ql.SimpleQuote]:
        return dict(self._quotes)

    def refresh(self) -> None:
        """Quote 변경이 Observer로 전파되므로 할 일 없음."""

    def roll(self, d: date) -> None:
        """ForwardForward: 오늘의 선도가 실현된다 (DF_d(t) = DF(d + t) / DF(d))."""
        if d == self.asof:
            self._base_link.linkTo(self.base)
        else:
            rolled = ql.ImpliedTermStructure(ql.YieldTermStructureHandle(self.base), to_ql_date(d))
            rolled.enableExtrapolation()
            self._base_link.linkTo(rolled)
