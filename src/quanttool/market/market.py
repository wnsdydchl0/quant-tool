from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date
from typing import Protocol

import QuantLib as ql

from ..config import Config
from .curves import BuiltCurve, CurveFactors, build_curve, evaluation_date, to_ql_date


class MarketObject(Protocol):
    """시장 기본객체의 규격.

    handle      의존성 관리
    factors()   요인 딕셔너리. {이름: SimpleQuote}
    refresh()   요인이 바뀐 뒤 객체를 다시 만들어야 하면 여기서 (Observer로 따라오면 할 일 없음)
    roll(d)     평가일을 d로 옮길 때 -> 근데 굳이 필요해? 그니까 어차피 하루 옮기고 refresh랑 달라? 

    """

    handle: object

    def factors(self) -> dict[str, ql.SimpleQuote]: ...

    def refresh(self) -> None: ...

    def roll(self, d: date) -> None: ...


class Market:
    def __init__(
        self,
        asof: date,
        objects: Mapping[str, MarketObject],
        built: Mapping[str, BuiltCurve] | None = None,
        indices: Mapping[str, ql.Index] | None = None,
    ) -> None:
        self.asof = asof
        self.date = asof
        self.objects = dict(objects)
        self.built = dict(built or {})  # 부트스트랩 결과 (진단용)
        self.indices = dict(indices or {})  # 파생 객체: 예측 커브 Handle에 연결된 지수
        self._base = {k: q.value() for k, q in self.factors().items()}
        self.current: Mapping[str, float] | None = None
        self._saved: dict[str, tuple[list, list]] = {}  # roll이 채우기 전 지수 이력

    def __getitem__(self, name: str):
        """상품이 연결되는 Handle (커브·vol: RelinkableHandle, 현물: QuoteHandle)."""
        try:
            return self.objects[name].handle
        except KeyError:
            raise KeyError(f"시장에 {name!r}가 없다: {sorted(self.objects)}") from None

    def index(self, name: str) -> ql.Index:
        """예측 커브(요인 포함)에 연결된 지수. 커브를 흔들면 지수 선도도 따라 움직인다."""
        try:
            return self.indices[name]
        except KeyError:
            raise KeyError(f"시장에 지수 {name!r}가 없다: {sorted(self.indices)}") from None

    def factors(self) -> dict[str, ql.SimpleQuote]:
        return {f"{n}/{k}": q for n, o in self.objects.items() for k, q in o.factors().items()}

    def active(self):
        """평가일을 이 시장의 날짜로 두는 with 블록 (상품 평가는 이 안에서)."""
        return evaluation_date(self.date)

    # --- 시나리오
    def apply(self, scenario: Mapping[str, float]) -> None:
        factors = self.factors()
        unknown = [k for k in scenario if k not in factors]
        if unknown:
            raise KeyError(f"시장에 없는 요인 {unknown[:3]}: {list(factors)[:3]} …")
        for k, q in factors.items():
            q.setValue(self._base[k] + scenario.get(k, 0.0))
        for name in {k.split("/", 1)[0] for k in scenario}:  # 바뀐 객체만
            self.objects[name].refresh()
        self.current = scenario

    def reset(self) -> None:
        for k, q in self.factors().items():
            q.setValue(self._base[k])
        for o in self.objects.values():
            o.refresh()
        self.current = None

    @contextmanager
    def scenario(self, scenario: Mapping[str, float]) -> Iterator[Market]:
        self.apply(scenario)
        try:
            yield self
        finally:
            self.reset()

    # --- 시간
    def roll(self, d: date) -> None:
        """평가일을 d로. [asof, d) 사이 지수 fixing은 오늘 선도로 실현된다고 채운다
        (ForwardForward). asof로 돌아오면 채운 fixing을 지우고 원래 이력으로 되돌린다."""
        if self.date != self.asof:
            self._set_date(self.asof)
        self._restore_fixings()
        if d != self.asof:
            self._realize_fixings(d)
            self._set_date(d)

    def _set_date(self, d: date) -> None:
        self.date = d
        for o in self.objects.values():
            o.roll(d)

    def _realize_fixings(self, d: date) -> None:
        start, end = to_ql_date(self.asof), to_ql_date(d)
        self._saved = {}
        with self.active():
            for name, idx in self.indices.items():
                ts = idx.timeSeries()
                self._saved[name] = (list(ts.dates()), list(ts.values()))
                x = start
                while x < end:
                    if idx.isValidFixingDate(x) and not idx.hasHistoricalFixing(x):
                        idx.addFixing(x, idx.fixing(x, True))
                    x += 1

    def _restore_fixings(self) -> None:
        for name, (dates, values) in self._saved.items():
            idx = self.indices[name]
            idx.clearFixings()
            if dates:
                idx.addFixings(dates, values)
        self._saved = {}


def build_market(
    asof: date, quotes: Mapping[str, float], cfg: Config, linked: bool = False
) -> Market:
    built, objects, handles = {}, {}, {}
    for name in cfg.build_order():
        c = cfg.curves[name]
        b = build_curve(
            c, cfg.conventions[c.conventions], quotes, asof, linked, handles, cfg.indices
        )
        built[name] = b
        objects[name] = CurveFactors(b.curve, asof, c.factor_tenors)
        handles[name] = objects[name].handle
    indices = {n: ic.make(n, handles[ic.curve]) for n, ic in cfg.indices.items()}
    return Market(asof, objects, built, indices)
