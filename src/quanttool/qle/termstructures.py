"""QuantLib에 없는 구조물·변환. ORE 대응: QuantExt/qle/termstructures/."""

from __future__ import annotations

import math

import QuantLib as ql

_HALF_YEAR_DAYS = 182.5


def bill_price(bey: float, days: int) -> float:
    """bond-equivalent yield(Act/365) → 액면 100 bill 가격.

    반년 이하: 단리. 반년 초과: 반기 복리 한 번 + 남은 기간 단리 (재무부 BEY 관례).
    """
    if days <= _HALF_YEAR_DAYS:
        return 100.0 / (1.0 + bey * days / 365.0)
    h = (days - _HALF_YEAR_DAYS) / 365.0
    return 100.0 / ((1.0 + bey / 2.0) * (1.0 + bey * h))


def bill_yield(price: float, days: int) -> float:
    """bill_price의 역함수."""
    if days <= _HALF_YEAR_DAYS:
        return (100.0 / price - 1.0) * 365.0 / days
    h = (days - _HALF_YEAR_DAYS) / 365.0
    # (h/2) y^2 + (1/2 + h) y + (1 - 100/P) = 0. h가 작을 때 상쇄 오차를 피하는 형태로 푼다.
    a, b, c = h / 2.0, 0.5 + h, 1.0 - 100.0 / price
    return -2.0 * c / (b + math.sqrt(b * b - 4 * a * c))


# --- 시뮬레이션 시장 격자 커브. ORE 대응: QuantExt/qle/termstructures/spreadeddiscountcurve.hpp,
#     interpolateddiscountcurve.hpp (Interpolation::linearZero, Extrapolation::flatZero).
#
# 두 커브 모두 격자점 Quote를 "격자점의 제로금리(연속복리)"로 바꿔 날짜 사이를 선형 보간하고,
# 마지막 격자점 뒤는 평탄 제로로 둔다. ORE linearZero와 같은 식이다:
#   spreaded: DF(t) = DF_ref(t) · exp(−s(t)·t),  s_i = −ln(비율_i)/t_i
#   절대:     DF(t) = exp(−z(t)·t),              z_i = −ln(DF_i)/t_i
# ORE의 logLinear·logCubic 모드(할인계수 비율의 로그 보간)는 QuantLib-Python에 같은 구조물이 없어
# 지원하지 않는다 (docs/architecture.md 2.1).

_FLAT_EXTRAPOLATION_LIMIT = "100Y"


def _zero_from_df_quotes(dates, quotes, times) -> list:
    """격자 할인계수(또는 비율) Quote → 격자점 제로금리 Quote (연동)."""
    return [
        ql.QuoteHandle(ql.DerivedQuote(ql.QuoteHandle(q), lambda v, t=t: -math.log(v) / t))
        for q, t in zip(quotes, times, strict=True)
    ]


def spreaded_discount_curve(reference, dates, ratio_quotes, times, day_counter):
    """기준 커브 × 격자 할인계수 비율. ORE SpreadedDiscountCurve.

    기준 상태(비율 = 1)에서 기준 커브와 같다.
    """
    spreads = _zero_from_df_quotes(dates, ratio_quotes, times)
    # QuantLib 1.44의 이 클래스는 Quote 변경으로 update()되면 enableExtrapolation 설정이 풀린다.
    # 외삽 플래그에 기대지 않고 마지막 격자 Quote에 묶인 먼 끝점으로 평탄 외삽한다.
    far = reference.referenceDate() + ql.Period(_FLAT_EXTRAPOLATION_LIMIT)
    return ql.PiecewiseZeroSpreadedTermStructure(
        reference,
        [*spreads, spreads[-1]],
        [*dates, far],
        ql.Continuous,
        ql.NoFrequency,
        day_counter,
    )


def interpolated_discount_curve(dates, df_quotes, times, day_counter):
    """격자 할인계수 자체로 만든 커브. 기준일은 평가일을 따라간다. ORE InterpolatedDiscountCurve."""
    zero = ql.YieldTermStructureHandle(ql.FlatForward(0, ql.NullCalendar(), 0.0, day_counter))
    zeros = _zero_from_df_quotes(dates, df_quotes, times)
    far = dates[-1] + ql.Period(_FLAT_EXTRAPOLATION_LIMIT)
    return ql.PiecewiseZeroSpreadedTermStructure(
        zero, [*zeros, zeros[-1]], [*dates, far], ql.Continuous, ql.NoFrequency, day_counter
    )
