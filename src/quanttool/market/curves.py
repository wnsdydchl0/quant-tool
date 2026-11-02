"""시세 → 일드커브 (QuantLib 부트스트랩), 커브 표·진단, 요인 층(CurveFactors).

- bill(1Y 이하): 재무부 bond-equivalent yield → 할인채 가격 헬퍼
- 쿠폰채(2Y~): par yield = 쿠폰인 가상 채권(가격 100) 헬퍼
- 시세는 SimpleQuote로 만들고 헬퍼가 DerivedQuote로 연결한다.
  linked=True면 시세 값만 바꿔도 커브가 따라온다.
- 기준일은 asof로 고정한다. linked=False(기본)면 부트스트랩 직후 얼려(freeze)
  시세·평가일과 무관해진다.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import QuantLib as ql

from ..config import Config, Conventions, CurveConfig

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


# --- bill bond-equivalent yield ↔ 가격 (QuantLib에 없음)
def bill_price(bey: float, days: int) -> float:
    """BEY(Act/365) → 액면 100 bill 가격.

    반년 이하 단리, 넘으면 반기 복리 한 번 + 남은 기간 단리.
    """
    if days <= _HALF_YEAR_DAYS:
        return 100.0 / (1.0 + bey * days / 365.0)
    h = (days - _HALF_YEAR_DAYS) / 365.0
    return 100.0 / ((1.0 + bey / 2.0) * (1.0 + bey * h))


def bill_yield(price: float, days: int) -> float:
    """bill_price의 역함수 (상쇄 오차를 피하는 근의 공식)."""
    if days <= _HALF_YEAR_DAYS:
        return (100.0 / price - 1.0) * 365.0 / days
    h = (days - _HALF_YEAR_DAYS) / 365.0
    a, b, c = h / 2.0, 0.5 + h, 1.0 - 100.0 / price
    return -2.0 * c / (b + math.sqrt(b * b - 4 * a * c))


@dataclass
class Helper:
    key: str
    quote: ql.SimpleQuote  # 시장 시세 (수익률)
    helper: ql.RateHelper
    maturity: ql.Date
    to_quote: Callable[[float], float]  # 헬퍼 가격 → 시세 단위


@dataclass
class BuiltCurve:
    name: str
    curve: ql.YieldTermStructure
    helpers: list[Helper] = field(default_factory=list)

    def quotes(self) -> dict[str, ql.SimpleQuote]:
        return {h.key: h.quote for h in self.helpers}


@dataclass
class Context:
    """헬퍼 함수가 받는 것: 관례, 결제일, 이미 만든 다른 커브, 지수 만들기."""

    curve: str
    conv: Conventions
    cal: ql.Calendar
    settle: ql.Date
    discount: ql.YieldTermStructureHandle  # Swap 헬퍼 할인 (빈 Handle이면 자기 자신)
    index: Callable[[str], ql.IborIndex]  # 지수 이름 → QuantLib 지수


def build_curve(
    cfg: CurveConfig,
    conv: Conventions,
    quotes: dict[str, float],
    asof: date,
    linked: bool = False,
    curves: dict[str, ql.YieldTermStructureHandle] | None = None,
    indices: dict | None = None,
) -> BuiltCurve:
    """구간마다 HELPERS[종류]로 헬퍼를 만들고 부트스트랩한다.

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
        helpers = []
        for seg in cfg.segments:
            for tenor in seg.tenors:
                key = cfg.key(seg, tenor)
                if key not in quotes:
                    raise KeyError(f"{cfg.name}: 시세 {key!r}가 {asof}에 없다")
                helpers.append(HELPERS[seg.type](key, ql.SimpleQuote(quotes[key]), tenor, seg, ctx))
        helpers.sort(key=lambda h: h.maturity)
        curve = _CURVES[cfg.interpolation](today, [h.helper for h in helpers], DC)
        curve.enableExtrapolation()
        curve.discount(1.0)  # 지금 부트스트랩
        if not linked:
            curve.freeze()
    return BuiltCurve(cfg.name, curve, helpers)


# --- 헬퍼 함수: (시세 키, 시세 Quote, 만기, 구간, Context) → Helper
def _bill(key, q, tenor, seg, ctx: Context) -> Helper:
    conv, cal, settle = ctx.conv, ctx.cal, ctx.settle
    maturity = cal.adjust(settle + ql.Period(tenor), ql.Following)
    days = maturity - settle
    bond = ql.ZeroCouponBond(
        conv.settlement_days, cal, 100.0, maturity, ql.Following, 100.0, settle
    )
    price = ql.DerivedQuote(ql.QuoteHandle(q), lambda y: bill_price(y, days))
    helper = ql.BondHelper(ql.QuoteHandle(price), bond)
    return Helper(key, q, helper, maturity, lambda p: bill_yield(p, days))


def _bond(key, q, tenor, seg, ctx: Context) -> Helper:
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

    def to_yield(p: float) -> float:
        bp = ql.BondPrice(p, ql.BondPrice.Clean)
        return bond.bondYield(bp, dc, ql.Compounded, freq, settle, 1e-12, 200)

    helper = ql.BondHelper(ql.QuoteHandle(ql.DerivedQuote(ql.QuoteHandle(q), price)), bond)
    return Helper(key, q, helper, maturity, to_yield)


def _rate_helper(key, q, helper) -> Helper:
    return Helper(key, q, helper, helper.maturityDate(), lambda r: r)


def _deposit(key, q, tenor, seg, ctx: Context) -> Helper:
    return _rate_helper(key, q, ql.DepositRateHelper(ql.QuoteHandle(q), ctx.index(seg.index)))


def _ois(key, q, tenor, seg, ctx: Context) -> Helper:
    helper = ql.OISRateHelper(
        ctx.conv.settlement_days,
        ql.Period(tenor),
        ql.QuoteHandle(q),
        ctx.index(seg.index),
        ctx.discount,
    )
    return _rate_helper(key, q, helper)


def _swap(key, q, tenor, seg, ctx: Context) -> Helper:
    """고정 레그는 커브 관례(주기·일수·영업일), 변동 레그는 지수.

    할인은 discount_curve (듀얼 커브).
    """
    c = ctx.conv
    helper = ql.SwapRateHelper(
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
    return _rate_helper(key, q, helper)


HELPERS = {"Bill": _bill, "Bond": _bond, "Deposit": _deposit, "OIS": _ois, "Swap": _swap}


# --- 진단과 표
def helper_repricing(built: BuiltCurve, asof: date) -> pd.DataFrame:
    """커브로 다시 계산한 시세 − 시장 시세 (bp). 부트스트랩이 맞으면 0에 가깝다."""
    with evaluation_date(asof):
        rows = [
            {
                "key": h.key,
                "maturity": h.maturity.ISO(),
                "market": h.quote.value(),
                "implied": h.to_quote(h.helper.impliedQuote()),
            }
            for h in built.helpers
        ]
    out = pd.DataFrame(rows)
    out["error_bp"] = (out["implied"] - out["market"]) * 1e4
    return out


DEFAULT_TENORS = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]


def curve_table(curve: ql.YieldTermStructureHandle, conv: Conventions, tenors=None) -> pd.DataFrame:
    """만기별 할인계수, 제로금리(연속·반기), 1Y 선도, par yield(관례의 결제일·쿠폰 주기)."""
    ref = curve.referenceDate()
    settle = conv.ql_calendar().advance(ref, conv.settlement_days, ql.Days)
    freq = conv.ql_frequency()
    rows = []
    for tenor in tenors or DEFAULT_TENORS:
        d = ref + ql.Period(tenor)
        months = _months(ql.Period(tenor))
        rows.append(
            {
                "tenor": tenor,
                "years": DC.yearFraction(ref, d),
                "discount": curve.discount(d),
                "zero_cc": curve.zeroRate(d, DC, ql.Continuous).rate(),
                "zero_sa": curve.zeroRate(d, DC, ql.Compounded, ql.Semiannual).rate(),
                "fwd_1y": curve.forwardRate(d, d + ql.Period("1Y"), DC, ql.Continuous).rate(),
                "par": _par(curve, settle, months, freq) if months >= 12 // freq else float("nan"),
            }
        )
    return pd.DataFrame(rows).set_index("tenor")


def _months(p: ql.Period) -> int:
    return p.length() * {ql.Months: 1, ql.Years: 12}[p.units()]


def _par(curve, settle: ql.Date, months: int, freq: int) -> float:
    step = 12 // freq
    dates = [settle + ql.Period(step * i, ql.Months) for i in range(1, months // step + 1)]
    annuity = sum(curve.discount(d) for d in dates) / freq
    return (curve.discount(settle) - curve.discount(dates[-1])) / annuity


def curve_shape(table: pd.DataFrame, column: str = "par") -> pd.Series:
    """기울기·곡률 (bp): 10Y 수준, 2s10s, 5s30s, 2s5s10s 나비."""
    r = table[column] * 1e4
    return pd.Series(
        {
            "level_10y": r["10Y"],
            "2s10s": r["10Y"] - r["2Y"],
            "5s30s": r["30Y"] - r["5Y"],
            "2s5s10s": 2 * r["5Y"] - r["2Y"] - r["10Y"],
        },
        name=f"{column}_bp",
    )


def conventions_for(cfg: Config, curve: str) -> Conventions:
    return cfg.conventions[cfg.curves[curve].conventions]


# --- 요인 층: 기준 커브 + 격자 제로 이동 (시장 객체)
_FAR = "100Y"  # 마지막 격자점 뒤 평탄 외삽 끝점  # 마지막 격자점 뒤 평탄 외삽 끝점


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
