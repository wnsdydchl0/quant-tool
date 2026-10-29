"""QuantLib에 없는 구조물·변환. ORE 대응: QuantExt/qle/termstructures/."""

from __future__ import annotations

import math

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
