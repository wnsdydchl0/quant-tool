"""설정 읽기: 관례, 커브 레시피, 리스크 설정 (configs/의 YAML).

configs/
  conventions/rates.yaml   관례 이름 → 결제일·일수·쿠폰 주기 …
  curves/*.yaml            커브 하나의 레시피 (시세 키, 헬퍼 구간, 보간, 요인 격자)
  equity/*.yaml            주식 하나: 현물·배당·IV 격자 시세 키, Heston 모델 설정
  products.yaml            상품 템플릿: 거래마다 같은 특성(관례·지수·할인·기초자산 …)
  pricing.yaml             상품 종류 → 엔진, 엔진 인자
  risk.yaml                민감도 이동 크기·방식, 상품별 덮어쓰기, cross gamma 쌍
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import QuantLib as ql
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- 문자열 → QuantLib (지원 목록을 명시해 오타를 막는다)
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


class Segment(_Model):
    """헬퍼 구간. 종류마다 curves.HELPERS의 헬퍼 함수 하나:
    Bill(bill BEY → 할인채 가격), Bond(par yield 쿠폰·가격 100), Deposit(지수 예금 금리),
    OIS(익일물 지수 스왑), Swap(고정 vs Ibor 지수, 할인은 curve.discount_curve).
    """

    type: Literal["Bill", "Bond", "Deposit", "OIS", "Swap"]
    tenors: list[str] = Field(min_length=1)
    quote_key: str = ""  # 비우면 커브의 quote_key
    index: str = ""  # Deposit·OIS·Swap이 쓰는 지수 (configs/indices.yaml)


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


class PricingConfig(_Model):
    """상품 종류 → 엔진 이름, 엔진 이름 → 엔진 인자 (FD 격자 크기 등)."""

    products: dict[str, str] = {}
    engines: dict[str, dict[str, float | int | str]] = {}


class VolGrid(_Model):
    """IV 격자 시세. strikes는 asof 현물 대비 % (100 = ATM)."""

    quote_key: str  # 예: EQ/VOL/SPX/{expiry}/{strike}
    expiries: list[str]
    strikes: list[int]


class HestonConfig(_Model):
    """서페이스에 캘리브레이션하는 Heston 모델 (파생 시장 객체)."""

    name: str
    init: dict[str, float]  # v0, kappa, theta, sigma, rho 초기값
    # 이 시장 객체가 바뀌면 다시 캘리브레이션 (비우면 파라미터 고정). 예: [SPX, SPX_VOL]
    recalibrate_on: list[str] = []
    expiries: list[str] = []  # 비우면 vol 격자 전체
    strikes: list[int] = []
    optimizer: dict[str, float | int] = {}  # max_iterations, root/function/gradient epsilon …


class EquityConfig(_Model):
    name: str  # 현물 객체 이름. 배당 커브 {name}_DIV, vol {name}_VOL
    calendar: str
    day_count: str = "Actual365Fixed"
    discount_curve: str
    spot_key: str
    dividend_key: str  # 연속복리 배당률 (평탄)
    dividend_tenors: list[str]
    vol: VolGrid
    heston: HestonConfig | None = None

    @field_validator("calendar")
    @classmethod
    def _cal(cls, v):
        return _check(CALENDARS, "달력", v)

    @field_validator("day_count")
    @classmethod
    def _dc(cls, v):
        return _check(DAY_COUNTERS, "일수 계산", v)

    def ql_calendar(self) -> ql.Calendar:
        return CALENDARS[self.calendar]()

    def ql_day_count(self) -> ql.DayCounter:
        return DAY_COUNTERS[self.day_count]()


class Config(_Model):
    conventions: dict[str, Conventions]
    curves: dict[str, CurveConfig]
    indices: dict[str, IndexConfig] = {}
    pricing: PricingConfig = PricingConfig()
    equities: dict[str, EquityConfig] = {}
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
        for e in self.equities.values():
            if e.discount_curve not in self.curves:
                raise ValueError(f"{e.name}: 할인 커브 {e.discount_curve!r}가 없다")
            deps = {e.name, e.discount_curve, f"{e.name}_DIV", f"{e.name}_VOL"}
            if e.heston and not set(e.heston.recalibrate_on) <= deps:
                raise ValueError(f"{e.heston.name}: recalibrate_on은 {sorted(deps)} 중에서")

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


def _read(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(root: str | Path = "configs") -> Config:
    root = Path(root)
    curves = {}
    for p in sorted((root / "curves").glob("*.yaml")):
        data = _read(p)
        if data["name"] in curves:
            raise ValueError(f"커브 이름 중복: {data['name']} ({p})")
        curves[data["name"]] = data

    equities = {}
    for p in sorted((root / "equity").glob("*.yaml")):
        data = _read(p)
        equities[data["name"]] = data

    def optional(name):
        return _read(root / name) if (root / name).exists() else {}

    return Config.model_validate(
        {
            "conventions": _read(root / "conventions" / "rates.yaml"),
            "curves": curves,
            "indices": optional("indices.yaml"),
            "pricing": optional("pricing.yaml"),
            "equities": equities,
            "products": optional("products.yaml"),
            "risk": optional("risk.yaml"),
        }
    )
