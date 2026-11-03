"""설정 읽기: configs/의 YAML 네 개 → 검증된 Config 하나.

문자열 설정을 QuantLib 기본 부품(달력·일수 계산·지수)으로 바꾸는 데까지만 한다.
커브·상품 조립은 market/curves.py, portfolio.py가 한다.

파일 ↔ 클래스
  conventions.yaml   Conventions                         금리 관례 (날짜 규칙)
  market.yaml        indices  → IndexConfig              금리 지수
                     curves   → CurveConfig (Segment)    커브 레시피
  products.yaml      engines   → PricingConfig           상품 종류 → 엔진, 엔진 인자
                     templates → dict                    상품 템플릿 (portfolio.expand)
  risk.yaml          RiskConfig (Override)               그릭 정의

흐름
  load_config → YAML 읽기 → pydantic 필드 검사(각 클래스의 field_validator, ① _check)
  → Config.model_post_init 교차 검사(이름 참조가 실제로 있나) → Config.build_order(커브 의존 순서)

이 파일의 구획
  ① 바탕  ② 관례  ③ 시장 설정(금리)  ④ 상품·가격결정 설정
  ⑤ 분석 설정  ⑥ 최상위 설정  ⑦ 파일 읽기
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import QuantLib as ql
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ==== ① 바탕: 문자열 → QuantLib 매핑, 검사 함수, 설정 모델 바탕
# 지원 목록을 명시해 YAML 오타를 읽는 순간 잡는다.

CALENDARS = {
    "UnitedStates.GovernmentBond": lambda: ql.UnitedStates(ql.UnitedStates.GovernmentBond),
    "UnitedStates.Settlement": lambda: ql.UnitedStates(ql.UnitedStates.Settlement),
    "SouthKorea.Settlement": lambda: ql.SouthKorea(ql.SouthKorea.Settlement),
    "TARGET": ql.TARGET,
    "UnitedStates.NYSE": lambda: ql.UnitedStates(ql.UnitedStates.NYSE),
    "NullCalendar": ql.NullCalendar,
}

DAY_COUNTERS = {
    "ActualActual.Bond": lambda: ql.ActualActual(ql.ActualActual.Bond),
    "Actual365Fixed": ql.Actual365Fixed,
    "Actual360": ql.Actual360,
    "Thirty360.BondBasis": lambda: ql.Thirty360(ql.Thirty360.BondBasis),
}

FREQUENCIES = {"Annual": ql.Annual, "Semiannual": ql.Semiannual, "Quarterly": ql.Quarterly}

CURRENCIES = {"USD": ql.USDCurrency, "KRW": ql.KRWCurrency, "EUR": ql.EURCurrency}

BDCS = {
    "Unadjusted": ql.Unadjusted,
    "Following": ql.Following,
    "ModifiedFollowing": ql.ModifiedFollowing,
}


def _check(table: dict, kind: str, name: str) -> str:
    if name not in table:
        raise ValueError(f"지원하지 않는 {kind} {name!r}: {sorted(table)}")
    return name


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ==== ② 관례 (conventions.yaml)
# 금리 커브(헬퍼)와 채권·스왑(조립)이 이름으로 함께 참조한다.


class Conventions(_Model):
    calendar: str
    day_count: str
    bill_day_count: str = "Actual365Fixed"
    settlement_days: int = Field(ge=0)
    frequency: str
    business_day_convention: str = "Unadjusted"
    payment_convention: str = "Following"

    @field_validator("calendar")
    @classmethod
    def _cal(cls, v):
        return _check(CALENDARS, "calendar", v)

    @field_validator("day_count", "bill_day_count")
    @classmethod
    def _dc(cls, v):
        return _check(DAY_COUNTERS, "day count", v)

    @field_validator("frequency")
    @classmethod
    def _freq(cls, v):
        return _check(FREQUENCIES, "frequency", v)

    @field_validator("business_day_convention", "payment_convention")
    @classmethod
    def _bdc(cls, v):
        return _check(BDCS, "business day convention", v)

    # QuantLib 객체
    def ql_calendar(self) -> ql.Calendar:
        return CALENDARS[self.calendar]()

    def ql_day_count(self) -> ql.DayCounter:
        return DAY_COUNTERS[self.day_count]()

    def ql_frequency(self) -> int:
        return FREQUENCIES[self.frequency]

    def ql_bdc(self) -> int:
        return BDCS[self.business_day_convention]

    def ql_payment(self) -> int:
        return BDCS[self.payment_convention]


# ==== ③ 시장 설정 (market.yaml): build_market이 시장 객체를 만드는 레시피
# 금리: 지수 → 헬퍼 구간 → 커브 (구간이 지수를, 커브가 관례·지수·할인 커브를 이름으로 참조)


class IndexConfig(_Model):
    """금리 지수. 예측 커브(curve)에 연결된 파생 객체로 만든다."""

    type: Literal["Overnight", "Ibor"]
    tenor: str = "1D"
    fixing_days: int = Field(ge=0)
    calendar: str
    day_count: str
    bdc: str = "ModifiedFollowing"
    currency: str
    curve: str  # 예측 커브 이름

    @field_validator("calendar")
    @classmethod
    def _cal(cls, v):
        return _check(CALENDARS, "calendar", v)

    @field_validator("day_count")
    @classmethod
    def _dc(cls, v):
        return _check(DAY_COUNTERS, "day count", v)

    @field_validator("currency")
    @classmethod
    def _ccy(cls, v):
        return _check(CURRENCIES, "currency", v)

    def make(self, name: str, handle: ql.YieldTermStructureHandle | None = None) -> ql.IborIndex:
        """QuantLib 지수. handle이 없으면 커브 미연결 (그 커브를 부트스트랩하는 헬퍼용)."""
        h = handle if handle is not None else ql.YieldTermStructureHandle()
        cal, dc, ccy = (
            CALENDARS[self.calendar](),
            DAY_COUNTERS[self.day_count](),
            CURRENCIES[self.currency](),
        )
        if self.type == "Overnight":
            return ql.OvernightIndex(name, self.fixing_days, ccy, cal, dc, h)
        return ql.IborIndex(
            name, ql.Period(self.tenor), self.fixing_days, ccy, cal, BDCS[self.bdc], False, dc, h
        )


class Segment(_Model):
    """헬퍼 구간. 종류마다 curves.HELPERS의 헬퍼 함수 하나:
    Bill(bill BEY → 할인채 가격), Bond(par yield 쿠폰·가격 100), Deposit(지수 예금 금리),
    OIS(익일물 지수 스왑), Swap(고정 vs Ibor 지수, 할인은 curve.discount_curve).
    """

    type: Literal["Bill", "Bond", "Deposit", "OIS", "Swap"]
    tenors: list[str] = Field(min_length=1)
    quote_key: str = ""  # 비우면 커브의 quote_key
    index: str = ""  # Deposit·OIS·Swap이 쓰는 지수 (market.yaml indices)


class CurveConfig(_Model):
    name: str
    quote_key: str = (
        ""  # 시세 키 틀, 예: "BOND/YIELD/USD/UST/PAR/{tenor}" (구간별로 덮어쓸 수 있다)
    )
    conventions: str
    discount_curve: str = ""  # Swap 헬퍼 할인에 쓸 다른 커브 (듀얼 커브). 비우면 자기 자신
    segments: list[Segment] = Field(min_length=1)
    interpolation: Literal["LogCubicDiscount", "LogLinearDiscount", "LinearZero"] = (
        "LogCubicDiscount"
    )
    factor_tenors: list[str] = Field(min_length=2)  # 시나리오로 흔드는 격자 (제로금리 이동)

    def key(self, seg: Segment, tenor: str) -> str:
        return (seg.quote_key or self.quote_key).format(tenor=tenor)

    def quote_keys(self) -> list[str]:
        return [self.key(s, t) for s in self.segments for t in s.tenors]

    def dependencies(self, indices: dict[str, IndexConfig]) -> set[str]:
        """먼저 만들어야 하는 다른 커브: 할인 커브 + 구간 지수의 예측 커브(자기 자신 제외)."""
        deps = {self.discount_curve} if self.discount_curve else set()
        deps |= {indices[s.index].curve for s in self.segments if s.index}
        return deps - {self.name}


# ==== ④ 상품·가격결정 설정 (products.yaml engines)
# templates는 클래스 없이 dict로 두고, portfolio.py의 명세 클래스(Bond …)가 검증한다.


class PricingConfig(_Model):
    """products.yaml engines: 상품 종류 → 기본 엔진, 엔진 → 인자 (FD 격자 크기 등)."""

    defaults: dict[str, str] = {}
    params: dict[str, dict[str, float | int | str]] = {}


# ==== ⑤ 분석 설정 (risk.yaml)


class Override(_Model):
    shift_size: float = Field(gt=0)
    scheme: Literal["Forward", "Central"] = "Forward"


class RiskConfig(_Model):
    shift_size: float = Field(1e-4, gt=0)  # 보고 단위 (1bp)
    scheme: Literal["Forward", "Central"] = "Forward"
    compute_gamma: bool = True
    shift_tenors: dict[str, list[str]] = {}  # 커브 → 이동 만기 (없으면 요인 격자)
    overrides: dict[str, Override] = {}  # 거래 id 또는 상품 종류 → 이동 크기·방식
    cross_gamma: list[tuple[str, str]] = []  # 요인 키 쌍, 예: ("UST/5Y", "UST/10Y")


# ==== ⑥ 최상위 설정: 위를 모두 묶고, 이름 참조를 교차 검사하고, 커브 의존 순서를 정한다


class Config(_Model):
    conventions: dict[str, Conventions]
    curves: dict[str, CurveConfig]
    indices: dict[str, IndexConfig] = {}
    pricing: PricingConfig = PricingConfig()
    products: dict[str, dict] = {}  # 상품 템플릿 이름 → {type, 기본 필드} (portfolio.expand)
    risk: RiskConfig = RiskConfig()

    def model_post_init(self, _ctx) -> None:
        for c in self.curves.values():
            if c.conventions not in self.conventions:
                raise ValueError(f"{c.name}: 관례 {c.conventions!r}가 없다")
            for s in c.segments:
                if s.type in ("Deposit", "OIS", "Swap") and s.index not in self.indices:
                    raise ValueError(f"{c.name}: {s.type} 구간의 지수 {s.index!r}가 없다")
                if not (s.quote_key or c.quote_key):
                    raise ValueError(f"{c.name}: {s.type} 구간의 시세 키가 없다")
            for d in c.dependencies(self.indices):
                if d not in self.curves:
                    raise ValueError(f"{c.name}: 의존 커브 {d!r}가 없다")
        for name, i in self.indices.items():
            if i.curve not in self.curves:
                raise ValueError(f"지수 {name}: 예측 커브 {i.curve!r}가 없다")

    def build_order(self) -> list[str]:
        """의존 먼저 순서 (위상 정렬). 순환이면 오류."""
        order: list[str] = []
        path: list[str] = []

        def visit(n: str) -> None:
            if n in order:
                return
            if n in path:
                raise ValueError("커브 의존 순환: " + " → ".join([*path[path.index(n) :], n]))
            path.append(n)
            for d in sorted(self.curves[n].dependencies(self.indices)):
                visit(d)
            path.pop()
            order.append(n)

        for n in self.curves:
            visit(n)
        return order


# ==== ⑦ 파일 읽기: configs/ → Config


def _read(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _named(section: dict, kind: str) -> dict:
    """{이름: 항목} → 항목마다 name 필드를 키로 채운다 (적었다면 키와 같아야 한다)."""
    out = {}
    for key, item in (section or {}).items():
        if item.get("name", key) != key:
            raise ValueError(f"{kind} {key!r}의 name이 키와 다르다: {item['name']!r}")
        out[key] = {**item, "name": key}
    return out


def load_config(root: str | Path = "configs") -> Config:
    root = Path(root)

    def optional(name):
        return _read(root / name) if (root / name).exists() else {}

    market = optional("market.yaml")
    products = optional("products.yaml")
    return Config.model_validate(
        {
            "conventions": _read(root / "conventions.yaml"),
            "indices": market.get("indices") or {},
            "curves": _named(market.get("curves"), "커브"),
            "pricing": products.get("engines") or {},
            "products": products.get("templates") or {},
            "risk": optional("risk.yaml"),
        }
    )
