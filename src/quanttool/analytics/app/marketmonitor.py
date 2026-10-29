"""시장 상태 읽기: 커브 표와 모양 지표."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import QuantLib as ql

from quanttool.data.marketdata.market import Market
from quanttool.data.utilities import parsers

if TYPE_CHECKING:
    from quanttool.data.configuration import Config

DEFAULT_TENORS = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
_DC = ql.Actual365Fixed()


def _par_yield(curve, settle: ql.Date, tenor: str, freq: int) -> float:
    """settle에 발행하는 정규 일정 par 채권의 쿠폰 (명목 쿠폰일, 기간 1/freq)."""
    step = 12 // freq  # 개월
    n = _total_months(ql.Period(tenor)) // step
    dates = [settle + ql.Period(step * i, ql.Months) for i in range(1, n + 1)]
    annuity = sum(curve.discount(d) for d in dates) / freq
    return (curve.discount(settle) - curve.discount(dates[-1])) / annuity


def _total_months(p: ql.Period) -> int:
    return p.length() * {ql.Months: 1, ql.Years: 12}[p.units()]


def curve_table(
    market: Market,
    name: str,
    cfg: Config | None = None,
    tenors: list[str] | None = None,
) -> pd.DataFrame:
    """만기별 할인계수, 제로금리, 1Y 선도, par yield(관례가 있으면).

    par yield는 커브 레시피의 관례(결제일, 쿠폰 주기)로 계산해 시장 par 시세와 같은 단위가 된다.
    """
    tenors = tenors or DEFAULT_TENORS
    rows = []
    with market.active():
        curve = market.yield_curve(name)
        ref = curve.referenceDate()
        settle, freq = ref, ql.Semiannual
        if cfg is not None:
            conv = cfg.conventions[cfg.curve_configs[name].conventions]
            settle = parsers.calendar(conv.calendar).advance(ref, conv.settlement_days, ql.Days)
            freq = parsers.frequency(conv.frequency)
        for tenor in tenors:
            d = ref + ql.Period(tenor)
            t = _DC.yearFraction(ref, d)
            row = {
                "tenor": tenor,
                "date": d.ISO(),
                "years": t,
                "discount": curve.discount(d),
                "zero_cc": curve.zeroRate(d, _DC, ql.Continuous).rate(),
                "zero_sa": curve.zeroRate(d, _DC, ql.Compounded, ql.Semiannual).rate(),
                "fwd_1y": curve.forwardRate(d, d + ql.Period("1Y"), _DC, ql.Continuous).rate(),
            }
            if _total_months(ql.Period(tenor)) >= 12 // freq:
                row["par"] = _par_yield(curve, settle, tenor, freq)
            else:
                row["par"] = float("nan")
            rows.append(row)
    return pd.DataFrame(rows).set_index("tenor")


def curve_shape(table: pd.DataFrame, column: str = "par") -> pd.Series:
    """기울기·곡률 (bp). 2s10s, 5s30s, 2s5s10s 나비(2×5Y − 2Y − 10Y)."""
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
