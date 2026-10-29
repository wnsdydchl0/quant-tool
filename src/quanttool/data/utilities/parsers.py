"""설정 문자열 → QuantLib 객체. 지원 목록을 명시적으로 두고, 없는 이름은 오류로 막는다."""

from __future__ import annotations

from collections.abc import Callable

import QuantLib as ql

_CALENDARS: dict[str, Callable[[], ql.Calendar]] = {
    "UnitedStates.GovernmentBond": lambda: ql.UnitedStates(ql.UnitedStates.GovernmentBond),
    "UnitedStates.Settlement": lambda: ql.UnitedStates(ql.UnitedStates.Settlement),
    "UnitedStates.SOFR": lambda: ql.UnitedStates(ql.UnitedStates.SOFR),
    "SouthKorea.Settlement": lambda: ql.SouthKorea(ql.SouthKorea.Settlement),
    "SouthKorea.KRX": lambda: ql.SouthKorea(ql.SouthKorea.KRX),
    "TARGET": ql.TARGET,
    "NullCalendar": ql.NullCalendar,
}

_DAY_COUNTERS: dict[str, Callable[[], ql.DayCounter]] = {
    "ActualActual.Bond": lambda: ql.ActualActual(ql.ActualActual.Bond),
    "ActualActual.ISMA": lambda: ql.ActualActual(ql.ActualActual.ISMA),
    "ActualActual.ISDA": lambda: ql.ActualActual(ql.ActualActual.ISDA),
    "Actual365Fixed": ql.Actual365Fixed,
    "Actual360": ql.Actual360,
    "Thirty360.BondBasis": lambda: ql.Thirty360(ql.Thirty360.BondBasis),
    # ORE parsers.cpp 약칭
    "A365F": ql.Actual365Fixed,
    "A365": ql.Actual365Fixed,
    "A360": ql.Actual360,
}

_FREQUENCIES = {
    "Annual": ql.Annual,
    "Semiannual": ql.Semiannual,
    "Quarterly": ql.Quarterly,
    "Monthly": ql.Monthly,
}

_BDCS = {
    "Unadjusted": ql.Unadjusted,
    "Following": ql.Following,
    "ModifiedFollowing": ql.ModifiedFollowing,
    "Preceding": ql.Preceding,
    # ORE parsers.cpp 약칭
    "U": ql.Unadjusted,
    "F": ql.Following,
    "MF": ql.ModifiedFollowing,
    "P": ql.Preceding,
}


def _lookup(table: dict, kind: str, name: str):
    try:
        return table[name]
    except KeyError:
        raise ValueError(f"지원하지 않는 {kind} {name!r}: {sorted(table)}") from None


def calendar(name: str) -> ql.Calendar:
    return _lookup(_CALENDARS, "calendar", name)()


def day_counter(name: str) -> ql.DayCounter:
    return _lookup(_DAY_COUNTERS, "day count", name)()


def frequency(name: str) -> int:
    return _lookup(_FREQUENCIES, "frequency", name)


def business_day_convention(name: str) -> int:
    return _lookup(_BDCS, "business day convention", name)


def period(text: str) -> ql.Period:
    return ql.Period(text)


def check(table_name: str, name: str) -> str:
    """pydantic 검증용: 이름이 지원 목록에 있는지만 확인한다."""
    table = {
        "calendar": _CALENDARS,
        "day count": _DAY_COUNTERS,
        "frequency": _FREQUENCIES,
        "business day convention": _BDCS,
    }[table_name]
    _lookup(table, table_name, name)
    return name
