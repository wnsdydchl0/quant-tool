"""시세 → 일드커브 (QuantLib 부트스트랩), 그리고 커브 표·진단.

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

from .config import Config, Conventions, CurveConfig

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


def build_curve(
    cfg: CurveConfig, conv: Conventions, quotes: dict[str, float], asof: date, linked: bool = False
) -> BuiltCurve:
    today = to_ql_date(asof)
    cal = conv.ql_calendar()
    with evaluation_date(asof):  # 헬퍼 결제일 계산이 평가일을 쓴다
        settle = cal.advance(today, conv.settlement_days, ql.Days)
        helpers = []
        for seg in cfg.segments:
            for tenor in seg.tenors:
                key = cfg.quote_key.format(tenor=tenor)
                if key not in quotes:
                    raise KeyError(f"{cfg.name}: 시세 {key!r}가 {asof}에 없다")
                q = ql.SimpleQuote(quotes[key])
                nominal = settle + ql.Period(tenor)
                if seg.type == "Bill":
                    helpers.append(
                        _bill(key, q, settle, cal.adjust(nominal, ql.Following), cal, conv)
                    )
                else:  # 정규 일정이 되도록 명목 만기 (par yield에서 가격이 정확히 100)
                    helpers.append(_bond(key, q, settle, nominal, cal, conv))
        helpers.sort(key=lambda h: h.maturity)
        curve = _CURVES[cfg.interpolation](today, [h.helper for h in helpers], DC)
        curve.enableExtrapolation()
        curve.discount(1.0)  # 지금 부트스트랩
        if not linked:
            curve.freeze()
    return BuiltCurve(cfg.name, curve, helpers)


def _bill(key, q, settle, maturity, cal, conv: Conventions) -> Helper:
    days = maturity - settle
    bond = ql.ZeroCouponBond(
        conv.settlement_days, cal, 100.0, maturity, ql.Following, 100.0, settle
    )
    price = ql.DerivedQuote(ql.QuoteHandle(q), lambda y: bill_price(y, days))
    return Helper(
        key, q, ql.BondHelper(ql.QuoteHandle(price), bond), maturity, lambda p: bill_yield(p, days)
    )


def _bond(key, q, settle, maturity, cal, conv: Conventions) -> Helper:
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
        return bond.bondYield(
            ql.BondPrice(p, ql.BondPrice.Clean), dc, ql.Compounded, freq, settle, 1e-12, 200
        )

    helper = ql.BondHelper(ql.QuoteHandle(ql.DerivedQuote(ql.QuoteHandle(q), price)), bond)
    return Helper(key, q, helper, maturity, to_yield)


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
