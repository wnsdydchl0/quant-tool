"""평가 날짜 격자. ORE 대응: OREData/ored/utilities/dategrid.hpp.

ORE는 ``DateGrid("1,0W")``(오늘 하나)나 ``DateGrid("10,1Y")``처럼 문자열로 만든다.
여기서는 날짜 목록
또는 ORE 문자열 "n,기간"(asof부터 기간 간격 n개, "1,0W"는 asof 하나)으로 만든다.
"""

from __future__ import annotations

from datetime import date

import QuantLib as ql


class DateGrid:
    def __init__(self, dates: list[date]) -> None:
        if not dates:
            raise ValueError("DateGrid가 비었다")
        self._dates = list(dates)

    @classmethod
    def from_string(cls, spec: str, asof: date, calendar: ql.Calendar | None = None) -> DateGrid:
        n_str, tenor = spec.split(",")
        n, period = int(n_str), ql.Period(tenor.strip())
        if period.length() == 0:
            return cls([asof])
        cal = calendar or ql.NullCalendar()
        start = ql.Date(asof.day, asof.month, asof.year)
        out = []
        for i in range(1, n + 1):
            d = cal.adjust(start + ql.Period(period.length() * i, period.units()))
            out.append(date(d.year(), d.month(), d.dayOfMonth()))
        return cls(out)

    def dates(self) -> list[date]:
        return list(self._dates)

    def size(self) -> int:
        return len(self._dates)

    def __iter__(self):
        return iter(self._dates)

    def __len__(self) -> int:
        return len(self._dates)


__all__ = ["DateGrid"]
