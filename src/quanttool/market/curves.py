"""시세 → 일드커브 (QuantLib 부트스트랩), 그리고 요인 층(CurveFactors).

- 구간 종류마다 헬퍼 함수 하나(HELPERS): 시세 하나 → QuantLib 헬퍼 하나.
  bill(1Y 이하)은 BEY → 할인채 가격, 쿠폰채(2Y~)는 par yield = 쿠폰인 가상 채권(가격 100),
  예금·OIS·스왑은 금리 헬퍼.
- 부트스트랩은 PiecewiseXxx 하나가 헬퍼 전부를 맞춘다.
- 시세는 SimpleQuote로 만든다. linked=True면 시세 값만 바꿔도 커브가 따라온다.
- 기준일은 asof로 고정한다. linked=False(기본)면 부트스트랩 직후 얼려(freeze)
  시세·평가일과 무관해진다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date

import QuantLib as ql

from ..config import Conventions, CurveConfig

_HALF_YEAR_DAYS = 182.5
_CURVES = {
    "LogCubicDiscount": ql.PiecewiseLogCubicDiscount,
    "LogLinearDiscount": ql.PiecewiseLogLinearDiscount,
    "LinearZero": ql.PiecewiseLinearZero,
}
DC = ql.Actual365Fixed()  # 커브 시간·제로금리 표시 기준


def to_ql_date(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


@contextmanager
def evaluation_date(d: date) -> Iterator[None]:
    """전역 Settings.evaluationDate를 d로 두고, 끝나면 되돌린다."""
    settings = ql.Settings.instance()
    previous = settings.evaluationDate
    settings.evaluationDate = to_ql_date(d)
    try:
        yield
    finally:
        settings.evaluationDate = previous


# --- bill bond-equivalent yield → 가격 (QuantLib에 없음)
def bill_price(bey: float, days: int) -> float:
    """BEY(Act/365) → 액면 100 bill 가격.

    반년 이하 단리, 넘으면 반기 복리 한 번 + 남은 기간 단리.
    """
    if days <= _HALF_YEAR_DAYS:
        return 100.0 / (1.0 + bey * days / 365.0)
    h = (days - _HALF_YEAR_DAYS) / 365.0
    return 100.0 / ((1.0 + bey / 2.0) * (1.0 + bey * h))


@dataclass
class Context:
    """헬퍼 함수가 받는 이 커브 공통 재료: 관례, 달력, 결제일, 할인 커브, 지수 만들기.

    커브마다 한 번 만들어 헬퍼 함수 모두에 넘긴다. 그래서 헬퍼 함수 모양이 같고 HELPERS 사전이 된다.
    """

    curve: str
    conv: Conventions
    cal: ql.Calendar
    settle: ql.Date
    discount: ql.YieldTermStructureHandle  # Swap·OIS 헬퍼 할인 (빈 Handle이면 자기 자신)
    index: Callable[[str], ql.IborIndex]  # 지수 이름 → QuantLib 지수


def build_curve(
    cfg: CurveConfig,
    conv: Conventions,
    quotes: dict[str, float],
    asof: date,
    linked: bool = False,
    curves: dict[str, ql.YieldTermStructureHandle] | None = None,
    indices: dict | None = None,
) -> tuple[ql.YieldTermStructure, dict[str, ql.SimpleQuote]]:
    """구간마다 HELPERS[종류]로 헬퍼를 만들고 부트스트랩한다. → (커브, {시세 키: SimpleQuote}).

    curves: 이미 만든 커브 (할인·다른 지수 예측용, 의존 순서는 Config.build_order).
    indices: 지수 이름 → IndexConfig. 이 커브가 예측하는 지수는 커브 미연결로 넘긴다
    (부트스트랩 대상).
    """
    curves, indices = curves or {}, indices or {}

    def index(name: str) -> ql.IborIndex:
        ic = indices[name]
        return ic.make(name) if ic.curve == cfg.name else ic.make(name, curves[ic.curve])

    today = to_ql_date(asof)
    cal = conv.ql_calendar()
    with evaluation_date(asof):  # 헬퍼 결제일 계산이 평가일을 쓴다
        discount = (
            curves[cfg.discount_curve] if cfg.discount_curve else ql.YieldTermStructureHandle()
        )
        ctx = Context(
            cfg.name, conv, cal, cal.advance(today, conv.settlement_days, ql.Days), discount, index
        )
        used, helpers = {}, []
        for seg in cfg.segments:
            for tenor in seg.tenors:
                key = cfg.key(seg, tenor)
                if key not in quotes:
                    raise KeyError(f"{cfg.name}: 시세 {key!r}가 {asof}에 없다")
                used[key] = ql.SimpleQuote(quotes[key])
                helpers.append(HELPERS[seg.type](used[key], tenor, seg, ctx))
        helpers.sort(key=lambda h: h.maturityDate())
        curve = _CURVES[cfg.interpolation](today, helpers, DC)
        curve.enableExtrapolation()
        curve.discount(1.0)  # 지금 부트스트랩
        if not linked:
            curve.freeze()
    return curve, used


# --- 헬퍼 함수: (시세 Quote, 만기, 구간, Context) → QuantLib 헬퍼
def _bill(q, tenor, seg, ctx: Context) -> ql.RateHelper:
    conv, cal, settle = ctx.conv, ctx.cal, ctx.settle
    maturity = cal.adjust(settle + ql.Period(tenor), ql.Following)
    days = maturity - settle
    bond = ql.ZeroCouponBond(
        conv.settlement_days, cal, 100.0, maturity, ql.Following, 100.0, settle
    )
    price = ql.DerivedQuote(ql.QuoteHandle(q), lambda y: bill_price(y, days))
    return ql.BondHelper(ql.QuoteHandle(price), bond)


def _bond(q, tenor, seg, ctx: Context) -> ql.RateHelper:
    conv, cal, settle = ctx.conv, ctx.cal, ctx.settle
    maturity = settle + ql.Period(tenor)  # 정규 일정이 되도록 명목 만기 (par yield에서 가격 100)
    dc, freq, bdc = conv.ql_day_count(), conv.ql_frequency(), conv.ql_bdc()
    sch = ql.Schedule(
        settle, maturity, ql.Period(freq), cal, bdc, bdc, ql.DateGeneration.Backward, False
    )
    # 쿠폰은 구축 시점 par yield로 고정하고, 이후 수익률 변화는 가격으로 전달한다
    bond = ql.FixedRateBond(
        conv.settlement_days, 100.0, sch, [q.value()], dc, conv.ql_payment(), 100.0, settle
    )

    def price(y: float) -> float:
        return bond.cleanPrice(y, dc, ql.Compounded, freq, settle)

    return ql.BondHelper(ql.QuoteHandle(ql.DerivedQuote(ql.QuoteHandle(q), price)), bond)


def _deposit(q, tenor, seg, ctx: Context) -> ql.RateHelper:
    return ql.DepositRateHelper(ql.QuoteHandle(q), ctx.index(seg.index))


def _ois(q, tenor, seg, ctx: Context) -> ql.RateHelper:
    return ql.OISRateHelper(
        ctx.conv.settlement_days,
        ql.Period(tenor),
        ql.QuoteHandle(q),
        ctx.index(seg.index),
        ctx.discount,
    )


def _swap(q, tenor, seg, ctx: Context) -> ql.RateHelper:
    """고정 레그는 커브 관례(주기·일수·영업일), 변동 레그는 지수.

    할인은 discount_curve (듀얼 커브).
    """
    c = ctx.conv
    return ql.SwapRateHelper(
        ql.QuoteHandle(q),
        ql.Period(tenor),
        ctx.cal,
        c.ql_frequency(),
        c.ql_bdc(),
        c.ql_day_count(),
        ctx.index(seg.index),
        ql.QuoteHandle(),
        ql.Period(0, ql.Days),
        ctx.discount,
    )


HELPERS = {"Bill": _bill, "Bond": _bond, "Deposit": _deposit, "OIS": _ois, "Swap": _swap}


# --- 요인 층: 기준 커브 + 격자 제로 이동 (시장 객체)
_FAR = "100Y"  # 마지막 격자점 뒤 평탄 외삽 끝점


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
