"""시장: 기초 객체(커브, 주식 현물·배당·vol 서페이스 …)를 이름으로 한 번에 묶는다.

- 상품 A가 a·b·c, B가 b·c·d를 쓰더라도 b는 한 번만 만들고, 둘 다 market["b"]에 연결된다.
  그래서 시나리오로 b를 흔들면 A와 B가 같은 b로 함께 움직인다.
- 시나리오 = {요인 키: 기준 대비 이동}. 요인 키는 "객체 이름/요인 이름" (예: "UST/5Y").
  apply는 누적되지 않는다 (요인 = 기준 + 이동). reset 또는 with market.scenario(s): 로 되돌린다.
- roll(d): 시장은 그대로 두고 평가일만 d로 (theta).
- 파생 객체(Heston 모델 …)는 depends_on으로 기대는 객체 이름을 밝힌다. 기초 객체가 바뀌면
  그 뒤에 의존 순서로 refresh된다 (다시 캘리브레이션할지는 객체의 정책).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date

import QuantLib as ql

from .config import Config
from .curves import BuiltCurve, build_curve, evaluation_date
from .equity import build_equity, build_heston
from .factors import CurveFactors, MarketObject


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
        self._order = _dependency_order(self.objects)
        self._base = {k: q.value() for k, q in self.factors().items()}
        self.current: Mapping[str, float] | None = None

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
        touched = {k.split("/", 1)[0] for k in scenario}
        for name in self._order:  # 바뀐 객체와 그에 기대는 객체를 의존 먼저 순서로
            deps = getattr(self.objects[name], "depends_on", [])
            if name in touched or touched.intersection(deps):
                touched.add(name)
                self.objects[name].refresh()
        self.current = scenario

    def reset(self) -> None:
        for k, q in self.factors().items():
            q.setValue(self._base[k])
        for name in self._order:
            self.objects[name].refresh()
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
        self.date = d
        for name in self._order:
            self.objects[name].roll(d)


def _dependency_order(objects: Mapping[str, MarketObject]) -> list[str]:
    """depends_on(파생 객체가 기대는 객체 이름)를 따라 의존 먼저 순서."""
    order: list[str] = []

    def visit(n: str, path: tuple[str, ...]) -> None:
        if n in path:
            raise ValueError("시장 객체 의존 순환: " + " → ".join([*path, n]))
        if n in order:
            return
        for d in getattr(objects[n], "depends_on", []):
            visit(d, (*path, n))
        order.append(n)

    for n in objects:
        visit(n, ())
    return order


def build_market(
    asof: date, quotes: Mapping[str, float], cfg: Config, linked: bool = False
) -> Market:
    """그 날의 시세로 설정의 모든 커브를 의존 먼저 순서로 만들어 시장 하나로 묶는다.

    다른 커브에 기대는 커브(듀얼 커브의 프로젝션 커브)는 먼저 만든 커브의 시장 Handle(요인 포함)을
    할인·지수 예측에 쓴다. 지수는 예측 커브 Handle에 연결된 파생 객체다(Market.index).
    """
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
    for e in cfg.equities.values():
        objects.update(build_equity(e, quotes, asof))
        if e.heston:  # 파생 객체: 위 기초 객체에 캘리브레이션
            objects[e.heston.name] = build_heston(e, objects, asof)
    return Market(asof, objects, built, indices)
