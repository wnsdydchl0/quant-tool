"""주식 시장 객체: 현물, 배당 커브, IV 서페이스. 모두 MarketObject 규격(factors.py)을 따른다.

    SPX       EquitySpot   요인 "SPX/spot" = 상대 이동 (값 = 기준 × (1 + 이동))
    SPX_DIV   CurveFactors 평탄 배당률 기준 커브 + 격자 제로 이동 (금리 커브와 같은 클래스)
    SPX_VOL   VolSurface   요인 "SPX_VOL/1Y/90" = 격자 vol 이동 (만기 / 현물 대비 % 행사가)

서페이스의 행사가는 asof 현물 기준 절대 행사가로 고정된다. 그래서 현물만 흔들면 sticky strike다.
다른 연동(sticky moneyness, SSR)은 scenarios.ssr처럼 현물과 vol 요인을 한 시나리오에 함께 담는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import QuantLib as ql

from .config import EquityConfig
from .curves import to_ql_date
from .factors import CurveFactors


class EquitySpot:
    def __init__(self, spot: float, asof: date) -> None:
        self.base = spot
        self.asof = asof
        self._move = ql.SimpleQuote(0.0)
        self.quote = ql.SimpleQuote(spot)
        self.handle = ql.QuoteHandle(self.quote)

    def factors(self) -> dict[str, ql.SimpleQuote]:
        return {"spot": self._move}

    def refresh(self) -> None:
        self.quote.setValue(self.base * (1.0 + self._move.value()))

    def roll(self, d: date) -> None:
        """현물은 그대로 (시간이 지나도 시장은 움직이지 않는다는 theta 가정)."""

    def value(self) -> float:
        return self.quote.value()


class VolSurface:
    """격자 IV → BlackVarianceSurface (분산 쌍선형 보간, 행사가 바깥은 평탄).

    refresh는 기준 + 격자 이동으로 서페이스를 다시 만들어 handle에 연결한다.
    roll(d)는 ForwardForward: 오늘 서페이스의 선도 분산이 실현된다
    (σ'²(T)·(T − t_d) = σ²(T)·T − σ²(d)·t_d, 행사가별).
    """

    def __init__(
        self,
        asof: date,
        spot: float,
        expiries: list[str],
        strikes: list[int],
        vols: Mapping[tuple[str, int], float],
        calendar: ql.Calendar,
        day_counter: ql.DayCounter,
    ) -> None:
        self.asof = asof
        self.date = asof
        self.cal, self.dc = calendar, day_counter
        self.ref = to_ql_date(asof)
        self.expiries, self.strike_pcts = list(expiries), list(strikes)
        self.dates = [calendar.advance(self.ref, ql.Period(e)) for e in expiries]
        self.strikes = [spot * k / 100.0 for k in strikes]
        self.base_vols = [[vols[(e, k)] for e in expiries] for k in strikes]  # 행사가 × 만기
        self._quotes = {f"{e}/{k}": ql.SimpleQuote(0.0) for e in expiries for k in strikes}
        self.base = self._surface(self.ref, self.dates, self.base_vols)
        self.handle = ql.RelinkableBlackVolTermStructureHandle(self.base)

    def _surface(self, ref, dates, vols) -> ql.BlackVarianceSurface:
        flat = ql.BlackVarianceSurface.ConstantExtrapolation
        s = ql.BlackVarianceSurface(ref, self.cal, dates, self.strikes, ql.Matrix(vols), self.dc,
                                    flat, flat)  # fmt: skip
        s.enableExtrapolation()
        return s

    def factors(self) -> dict[str, ql.SimpleQuote]:
        return dict(self._quotes)

    def shifted_vols(self) -> list[list[float]]:
        q = self._quotes
        return [
            [v + q[f"{e}/{k}"].value() for e, v in zip(self.expiries, row, strict=True)]
            for k, row in zip(self.strike_pcts, self.base_vols, strict=True)
        ]

    def vol(self, expiry: ql.Date, strike: float) -> float:
        """기준(asof, 이동 없음) 서페이스의 IV."""
        return self.base.blackVol(expiry, strike, True)

    def refresh(self) -> None:
        today = self._surface(self.ref, self.dates, self.shifted_vols())
        if self.date == self.asof:
            self.handle.linkTo(today)
            return
        d = to_ql_date(self.date)
        t_d = self.dc.yearFraction(self.ref, d)
        dates = [x for x in self.dates if x > d]
        tau = [self.dc.yearFraction(self.ref, x) - t_d for x in dates]
        vols = []
        for k in self.strikes:
            var_d = today.blackVariance(d, k, True)
            row = [
                (today.blackVariance(x, k, True) - var_d) / t
                for x, t in zip(dates, tau, strict=True)
            ]
            vols.append([v**0.5 for v in row])
        self.handle.linkTo(self._surface(d, dates, vols))

    def roll(self, d: date) -> None:
        self.date = d
        self.refresh()


def build_equity(cfg: EquityConfig, quotes: Mapping[str, float], asof: date) -> dict[str, object]:
    """{name: EquitySpot, name_DIV: CurveFactors, name_VOL: VolSurface}."""
    spot = quotes[cfg.spot_key]
    dc = cfg.ql_day_count()
    div = ql.FlatForward(to_ql_date(asof), quotes[cfg.dividend_key], dc, ql.Continuous)
    div.enableExtrapolation()
    g = cfg.vol
    vols = {
        (e, k): quotes[g.quote_key.format(expiry=e, strike=k)]
        for e in g.expiries
        for k in g.strikes
    }
    return {
        cfg.name: EquitySpot(spot, asof),
        f"{cfg.name}_DIV": CurveFactors(div, asof, cfg.dividend_tenors),
        f"{cfg.name}_VOL": VolSurface(
            asof, spot, g.expiries, g.strikes, vols, cfg.ql_calendar(), dc
        ),
    }
