"""설정 읽기: 관례, 커브 레시피, 리스크 설정 (configs/의 YAML).

configs/
  conventions/rates.yaml   관례 이름 → 결제일·일수·쿠폰 주기 …
  curves/*.yaml            커브 하나의 레시피 (시세 키, 헬퍼 구간, 보간, 요인 격자)
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
    "NullCalendar": ql.NullCalendar,
}
DAY_COUNTERS = {
    "ActualActual.Bond": lambda: ql.ActualActual(ql.ActualActual.Bond),
    "Actual365Fixed": ql.Actual365Fixed,
    "Actual360": ql.Actual360,
    "Thirty360.BondBasis": lambda: ql.Thirty360(ql.Thirty360.BondBasis),
}
FREQUENCIES = {"Annual": ql.Annual, "Semiannual": ql.Semiannual, "Quarterly": ql.Quarterly}
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
    """헬퍼 구간: Bill = bill BEY → 할인채 가격, Bond = par yield 쿠폰·가격 100 채권."""

    type: Literal["Bill", "Bond"]
    tenors: list[str] = Field(min_length=1)


class CurveConfig(_Model):
    name: str
    quote_key: str  # 시세 키 틀, 예: "BOND/YIELD/USD/UST/PAR/{tenor}"
    conventions: str
    segments: list[Segment] = Field(min_length=1)
    interpolation: Literal["LogCubicDiscount", "LogLinearDiscount", "LinearZero"] = (
        "LogCubicDiscount"
    )
    factor_tenors: list[str] = Field(min_length=2)  # 시나리오로 흔드는 격자 (제로금리 이동)

    def quote_keys(self) -> list[str]:
        return [self.quote_key.format(tenor=t) for s in self.segments for t in s.tenors]


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


class Config(_Model):
    conventions: dict[str, Conventions]
    curves: dict[str, CurveConfig]
    risk: RiskConfig = RiskConfig()

    def model_post_init(self, _ctx) -> None:
        for c in self.curves.values():
            if c.conventions not in self.conventions:
                raise ValueError(f"{c.name}: 관례 {c.conventions!r}가 없다")


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
    risk = _read(root / "risk.yaml") if (root / "risk.yaml").exists() else {}
    return Config.model_validate(
        {"conventions": _read(root / "conventions" / "rates.yaml"), "curves": curves, "risk": risk}
    )
