# QuantTool 아키텍처

원본: 설계 인수인계서(2026-10-26). 레퍼런스 요약은 docs/references/ 참조.

## 1. 프로젝트 목표와 결정 사항

### 1.1 목표
- QuantLib을 엔진으로 쓰고, ORE의 시스템 설계를 참조한 **파이썬 가격결정·리스크 분석 툴**.
- 용도: (1) 시장 상태 모니터링(커브·서페이스·요인), (2) 포지션의 가격·민감도·시나리오 손익 분석, (3) 다른 프로젝트(팩터 모델 등)에 시장 요인 시계열 제공.
- 어필 포인트: "QuantLib의 가격결정 구조와 ORE의 리스크 시스템 구조를 이해하고, 필요한 만큼 가볍게 구현했으며, 통계적 추정은 외부 연구로 분리해 검증된 파라미터만 반영한다."

### 1.2 범위 결정
| 영역 | 선형 | 바닐라 | 이색 |
|---|---|---|---|
| 금리 | 구현 (국채·OIS 커브, 요인화, carry, term premium) | 개념 + 관찰 (MOVE, 국채선물옵션 bp vol) | 개념 |
| 주식 | 구현 (할인·배당·레포, implied forward) | 구현 (IV 서페이스, 그릭스, implied vs realized) | 구현 (LV 캘리브레이션, 오토콜 등) |

- 진행 순서: 금리 선형 → 주식 선형 → 주식 바닐라 → 주식 이색.
- 시간 배분 목표: 인프라 30%, 분석(시장 해석 노트북) 70%. 모듈 하나를 만들 때마다 그 모듈로 실제 시장을 읽는 노트북 하나를 붙인다.

### 1.3 데이터 제약
- 무료: 미 재무부 par yield, FRED, NY Fed SOFR, 한국은행 ECOS(국고채·CD·콜), 금투협 채권정보센터, KRX 정보데이터시스템, yfinance(현재 시점 옵션 체인), 증권사 API(KIS).
- 사실상 불가: 스왑 커브 호가, swaption·cap/floor vol.
- 대응: 금리는 국채 커브 + SOFR fixing·SOFR 선물 기반 OIS 근사. 옵션 체인은 지금부터 매일 스냅샷을 쌓는다.

### 1.4 연구와 툴의 분리
- 툴은 **정해진 규칙과 파라미터로 계산**한다. PCA 로딩, SSR 같은 **추정은 툴 밖(`research/`)**에서 하고, 검증을 통과한 값만 `configs/estimated/`에 출처 메타데이터와 함께 넣는다.
- 툴 안에서 하는 것은 추정이 아니라 적용이다(예: 저장된 로딩으로 오늘 요인 점수 계산).

---

## 2. 설계 원칙 (QuantLib·ORE에서 가져온 것)

1. **시장은 규격(인터페이스)이다.** 가격결정 코드는 `Market` 규격만 안다. 관측 시장(`Snapshot`)과 흔든 시장(`ScenarioMarket`)이 같은 규격을 구현한다. (ORE `Market` ← `TodaysMarket` / `ScenarioSimMarket`)
2. **모든 시장 입력은 id가 붙은 `SimpleQuote`이고, 구조물은 그 Quote에 연결된 채로 만든다.** 그래야 시나리오가 "Quote 값 변경 → Observer 전파 → Lazy 재계산"으로 끝난다.
3. **이름으로 참조한다.** 상품·모델은 커브를 객체가 아니라 이름으로 참조하고, 평가 시점에 시장에서 받는다.
4. **레시피(설정)와 제작자(빌더)를 분리한다.** 같은 군은 같은 빌더, 대상별 차이는 설정. (ORE `configuration/` vs `marketdata/` 빌더)
5. **구축 순서는 의존 그래프가 정한다.** 관계는 레시피의 참조에서 자동 추출. (ORE `DependencyGraph`)
6. **계약(무엇)과 평가 방법(어떻게)을 분리한다.** 계약서는 순수 데이터, 엔진 선택은 설정, 조립은 엔진 빌더, 창구는 팩토리. (QuantLib Instrument/PricingEngine, ORE Trade/EngineFactory/EngineBuilder)
7. **시나리오는 데이터이고, 생성·적용·평가는 분리한다.** 생성기 → Scenario(변경 목록) → ScenarioMarket.apply/reset → Runner. (ORE ScenarioGenerator / Scenario / ScenarioSimMarket / ValuationEngine)
7-1. **시나리오 시장은 ORE 방식의 격자 재표현을 쓴다.** 스냅샷의 커브·서페이스를 고정 격자점(제로금리, IV)에서 샘플링해 SimpleQuote로 보관하고, 그 Quote를 보간한 구조물로 시장을 구성한다. 시나리오는 격자점 Quote를 흔든다. 요인(PCA 등) 추정과 과거 재현도 같은 격자 좌표를 쓴다.
8. **의존 방향은 한쪽으로.** `config·core → market → derivatives → scenario → analytics`. 아래 층은 위 층을 import하지 않는다.
9. **파이썬 관례: 평평하게.** 최대 두 단계(패키지 → 파일). 비슷한 부류는 한 파일에 묶고, 커지면 쪼갠다.

---

## 5. QuantTool 프로젝트 구조

```
quant-tool/
├── configs/                          [값]
│   ├── conventions/                  rates.yaml, equity.yaml
│   ├── market/
│   │   ├── todaysmarket.yaml         구축 대상
│   │   ├── curves/                   krw_ktb.yaml, ust.yaml, usd_sofr.yaml, spx_fwd.yaml
│   │   ├── indices/                  cd91.yaml, sofr.yaml
│   │   └── vols/                     spx.yaml
│   ├── pricing/                      engines.yaml, models.yaml
│   ├── scenario/                     grid.yaml(격자), factors.yaml, rules.yaml, sensitivity.yaml, stress.yaml
│   └── estimated/                    pca_krw.yaml, ssr_spx.yaml (값 + 출처, 격자 좌표 기준)
├── positions/                        평가할 포지션 파일
│
├── src/quanttool/
│   ├── qlext/                        QuantLib 확장 (svi.py …)
│   ├── config/                       설정 읽기·검증 (market.py, pricing.py, scenario.py)
│   ├── core/
│   │   ├── ids.py                    이름 규칙 (시세 id, 시장 객체 id, 리스크 요인 키, 단위)
│   │   ├── registry.py               유형 이름 → 클래스
│   │   └── dependency.py             DependencyGraph
│   │
│   ├── market/                       [1. 시장의 기본단위와 스냅샷]
│   │   ├── quotes.py                 Loader, QuoteStore
│   │   ├── rates.py                  YieldCurveBuilder(구간 유형), IndexBuilder
│   │   ├── equity.py                 EquityForwardBuilder, EquityVolBuilder
│   │   ├── market.py                 Market(규격), Snapshot(관측 시장)
│   │   ├── persist.py                스냅샷 결과 저장 (커브 격자, 서페이스 파라미터)
│   │   └── diagnostics.py            헬퍼 재가격 오차, 무차익 검사
│   │
│   ├── derivatives/                  [2. 파생상품과 포트폴리오]
│   │   ├── trades.py                 Trade, InstrumentWrapper, 레그
│   │   ├── rates.py                  FixedBond, IRSwap
│   │   ├── equity.py                 EquityForward, EquityVanilla, EquityDigital, Autocallable
│   │   ├── portfolio.py              Portfolio
│   │   ├── factory.py                EngineFactory (접수 창구)
│   │   ├── engines.py                엔진 빌더 (기술자)
│   │   └── models.py                 ModelBuilder, CalibrationBasket
│   │
│   ├── scenario/                     [3. 시나리오 분석]
│   │   ├── grid.py                   RiskFactorKey, ScenarioGrid (격자 정의, 스냅샷 샘플링)
│   │   ├── factors.py                KeyRateFactors, PCAFactors, VegaBuckets
│   │   ├── rules.py                  StickyStrike, SSRRule
│   │   ├── generators.py             Scenario, SensitivityGenerator, GridGenerator,
│   │   │                             StressGenerator, HistoricalGenerator
│   │   ├── scenario_market.py        ScenarioMarket (격자 Quote 보관, 보간 구조물, apply / reset)
│   │   ├── par.py                    격자 민감도 → par(시장 상품) 민감도 변환
│   │   └── runner.py                 ScenarioRunner, ScenarioResults
│   │
│   ├── analytics/                    market_monitor.py, sensitivity.py, pnl_explain.py, reports.py
│   └── app.py                        run(설정): 로드 → 스냅샷 → 포트폴리오 → 분석
│
├── pipeline/                         데이터 수집·정제·저장 (툴 밖)
├── data/                             (gitignore)
├── notebooks/                        시장 해석
├── research/                         PCA·SSR 추정 → 검증 후 configs/estimated/
├── tests/                            src와 같은 구조 + 기대 결과 비교
├── docs/                             architecture.md, references/
└── references/                       (gitignore) QuantLib-SWIG, ORE 클론
```

이름 규칙: `configs/`는 값, `src/quanttool/config/`는 그 값을 읽는 코드.

---

## 6. 클래스 설계

### 6.1 상속
```
Market (규격)                                     ORE: Market
 ├ Snapshot                                       ORE: MarketImpl + TodaysMarket
 └ ScenarioMarket                                 ORE: ScenarioSimMarket
Loader ← StoreLoader, InMemoryLoader              ORE: Loader
MarketBuilder ← YieldCurveBuilder, IndexBuilder, EquityForwardBuilder, EquityVolBuilder
Trade ← FixedBond, IRSwap, EquityForward, EquityVanilla, EquityDigital, Autocallable
EngineBuilder ← DiscountingBondEngineBuilder, DiscountingSwapEngineBuilder,
                AnalyticBSEngineBuilder, ReplicationDigitalEngineBuilder, LocalVolMCEngineBuilder
ModelBuilder ← LocalVolBuilder, HestonBuilder
RiskFactors ← KeyRateFactors, PCAFactors, VegaBuckets          (확장)
DependencyRule ← StickyStrike, SSRRule                          (확장)
ScenarioGenerator ← SensitivityGenerator, GridGenerator, StressGenerator, HistoricalGenerator
```

### 6.2 구성
```
Snapshot          QuoteStore, 이름 → Handle 보관소, 이름 → Index
                  (구축 시 사용) Loader, DependencyGraph, MarketBuilder들
EngineFactory     Market, 엔진 설정, EngineBuilder 등록부
EngineBuilder     Market(팩토리가 건넴), 엔진 캐시, (필요 시) ModelBuilder
ModelBuilder      Market, CalibrationBasket
Trade             계약 데이터 / build 후 InstrumentWrapper(QuantLib Instrument, 승수, 부속 항목)
Portfolio         Trade들
ScenarioGrid      격자 정의 (커브별 만기 격자, 서페이스별 만기 × moneyness 격자)
ScenarioMarket    기준 Snapshot, ScenarioGrid, sim_data(RiskFactorKey → SimpleQuote),
                  격자 Quote를 보간한 커브·서페이스 Handle
Scenario          RiskFactorKey → 이동량, 단위 (데이터)
ScenarioGenerator RiskFactors, DependencyRule들, 이동 크기
ScenarioRunner    Portfolio, ScenarioMarket, 엔진 설정
```

### 6.3 인터페이스 명세 (핵심 시그니처)
```python
class Market(ABC):                                    # 메뉴판
    asof: date
    def quote(self, quote_id: str) -> ql.QuoteHandle: ...
    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def index(self, name: str) -> ql.Index: ...
    def equity_spot(self, name: str) -> ql.QuoteHandle: ...
    def dividend_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def equity_vol(self, name: str) -> ql.BlackVolTermStructureHandle: ...
    def active(self) -> ContextManager: ...           # evaluationDate 설정 보장

class Snapshot(Market):
    @classmethod
    def build(cls, asof: date, cfg: Config, loader: Loader | None = None) -> "Snapshot": ...

class MarketBuilder(ABC):
    kind: str                                         # registry 키 ("YieldCurve" …)
    def requires(self, recipe) -> list[str]: ...      # 의존 그래프용 참조 추출
    def build(self, recipe, quotes: QuoteStore, market: Market) -> object: ...

class Trade(ABC):
    id: str
    trade_type: str                                   # registry 키 = 엔진 설정 키
    def build(self, factory: "EngineFactory") -> None: ...
    def npv(self) -> float: ...

class EngineFactory:
    def __init__(self, market: Market, engine_cfg): ...
    def engine_for(self, trade: Trade) -> ql.PricingEngine: ...

@dataclass(frozen=True)
class RiskFactorKey:                                  # ORE RiskFactorKey 대응
    kind: str                                         # "zero", "equity_spot", "equity_vol" …
    name: str                                         # "KRW_KTB", "SPX"
    point: tuple = ()                                 # ("5Y",) 또는 ("1Y", 1.00)

class ScenarioGrid:                                   # ORE ScenarioSimMarketParameters 대응
    def keys(self) -> list[RiskFactorKey]: ...
    def sample(self, market: Market) -> dict[RiskFactorKey, float]: ...   # 스냅샷에서 격자값 읽기

class Scenario:
    label: tuple | str
    shifts: dict[RiskFactorKey, float]                # 이동량 (단위: 금리 소수, vol 소수)

class ScenarioMarket(Market):                         # ORE ScenarioSimMarket 대응
    def __init__(self, base: Snapshot, grid: ScenarioGrid): ...
    def apply(self, scenario: Scenario) -> None: ...
    def reset(self) -> None: ...
    def base_reconciliation(self, portfolio) -> pd.DataFrame: ...   # 기준 NPV 대사

class ScenarioGenerator(ABC):
    def generate(self) -> Iterable[Scenario]: ...

class ScenarioRunner:
    def __init__(self, portfolio: Portfolio, smkt: ScenarioMarket, engine_cfg): ...
    def run(self, scenarios: Iterable[Scenario]) -> "ScenarioResults": ...
```

### 6.4 불변 조건
- 모든 시장 입력은 `QuoteStore`의 `SimpleQuote`이며 id는 `core/ids.py` 규칙을 따른다.
- 시나리오에서 흔드는 대상은 `ScenarioGrid`의 격자점이다. 흔들고 싶은 것은 격자에 정의되어 있어야 한다.
- 시나리오 시장의 기준 NPV는 스냅샷 기준 NPV와 허용 오차 이내로 일치해야 한다 (`base_reconciliation`).
- 요인 로딩·과거 시나리오는 격자 좌표(`RiskFactorKey`)로 정의한다.
- 가격결정·시나리오 코드는 `Market` 규격 메소드만 쓴다. `Snapshot` 내부를 직접 만지지 않는다.
- 계약서는 엔진·모델을 모른다. 엔진 선택은 `engines.yaml`.
- `ScenarioRunner`는 포트폴리오를 시나리오마다 재조립하지 않는다. 한 번 조립 후 apply → npv → reset.
- 날짜가 다른 시장은 `active()` 안에서 순차적으로만 평가한다.

---

## 7. 사용 예시와 호출 흐름

### 7.1 한국 국채 커브 보기
```python
cfg  = load_config("configs/")
snap = Snapshot.build(date(2026, 10, 23), cfg)
table = market_monitor.curve_table(snap, "KRW_KTB")
```
```
Snapshot.build
  ├ evaluationDate 설정
  ├ StoreLoader.load(asof) → MarketQuote("KTB/YLD/3Y", 0.0281), …
  ├ QuoteStore(quotes)                               id → SimpleQuote
  ├ DependencyGraph(builders.requires).order(targets) → ["KRW_KTB"]
  └ YieldCurveBuilder.build(recipe, store, snap)
       수익률 Quote → DerivedQuote(가격) → FixedRateBondHelper
       → PiecewiseLogCubicDiscount → RelinkableYieldTermStructureHandle → 보관소 등록
market_monitor.curve_table
  └ snap.yield_curve("KRW_KTB").zeroRate(…)        ← 여기서 첫 부트스트랩 (Lazy)
```

### 7.2 IRS 포지션의 PCA 2×2 시나리오
```yaml
# positions/book.yaml
- {id: IRS001, type: IRSwap, notional: 1.0e10, pay_receive: pay_fixed,
   fixed_rate: 0.0295, tenor: 5Y, index: CD91, discount: KRW_KTB}
# configs/scenario/grid.yaml
KRW_KTB: {kind: zero, tenors: [1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y], interpolation: LogLinear(Discount)}
SPX:     {kind: equity_vol, expiries: [1M, 3M, 6M, 1Y, 2Y], moneyness: [0.8, 0.9, 1.0, 1.1, 1.2]}

# configs/estimated/pca_krw.yaml  (제로금리 격자 기준, 1 = 1bp)
grid: KRW_KTB
factors:
  PC1: {1Y: 0.92, 2Y: 0.97, 3Y: 1.00, 5Y: 0.98, 7Y: 0.96, 10Y: 0.93, 20Y: 0.88, 30Y: 0.85}
  PC2: {1Y: -0.60, 2Y: -0.45, 3Y: -0.30, 5Y: 0.00, 7Y: 0.20, 10Y: 0.40, 20Y: 0.60, 30Y: 0.70}
source: research/pca_krw.ipynb, 저장된 일별 스냅샷 격자, window 2024-01 ~ 2026-09
```
(예시 단순화: 실무에서는 CD91 기반 IRS 커브를 별도로 둔다.)
```python
portfolio = Portfolio.load("positions/book.yaml")
grid    = ScenarioGrid.load("configs/scenario/grid.yaml")
factors = PCAFactors.load("configs/estimated/pca_krw.yaml")
gen  = GridGenerator(factors, {"PC1": [-25, 25], "PC2": [-10, 10]})
smkt = ScenarioMarket(snap, grid)
res  = ScenarioRunner(portfolio, smkt, cfg.pricing).run(gen.generate())
res.pivot("PC1", "PC2")
```
```
Portfolio.load → TRADES["IRSwap"](데이터) → 계약서
ScenarioMarket(snap, grid)
  ├ grid.sample(snap): KRW_KTB 커브에서 1Y…30Y 제로금리 읽기
  ├ sim_data[RiskFactorKey("zero","KRW_KTB",("5Y",))] = SimpleQuote(0.0298) …
  ├ 격자 Quote를 보간하는 ql.ZeroCurve 계열 → Handle 등록 (원래 헬퍼·부트스트랩은 쓰지 않음)
  └ Index("CD91")는 이 Handle로 예측하도록 재구성 (fixing은 건드리지 않음)
ScenarioRunner.run
  ├ portfolio.build(EngineFactory(smkt, …))
  │    IRSwap.build: index = market.index("CD91"); ql.VanillaSwap(…)
  │                  engine = factory.engine_for(self)
  │                    engines.yaml: IRSwap → DiscountingSwap
  │                    DiscountingSwapEngineBuilder (캐시) → ql.DiscountingSwapEngine(market.yield_curve("KRW_KTB"))
  ├ smkt.base_reconciliation(portfolio)       격자 커브 기준 NPV vs 스냅샷 기준 NPV
  ├ base = portfolio.npv()
  └ for s in GridGenerator.generate():          4개, shifts[key] = Σ 크기 × 로딩[key.point]
       smkt.apply(s)    → 격자점 SimpleQuote.setValue → 보간 커브 → Index·엔진 → 스왑 "낡음"
       pnl = portfolio.npv() - base             → 보간만 다시, 재평가
       smkt.reset()
res.pivot → 2×2 손익 표 (PC1 델타, PC1·PC2 교차 감마를 차분으로 읽음)
헷지용으로는 par.py로 격자 민감도 → 국채·스왑 par 민감도 변환
```

### 7.3 주식 디지털 옵션의 SSR 반영 델타
```python
book = Portfolio.load("positions/equity.yaml")       # EquityDigital, SPX, K=6000
gen  = SensitivityGenerator(cfg.scenario, rules=[SSRRule.load("configs/estimated/ssr_spx.yaml")])
res  = ScenarioRunner(book, ScenarioMarket(snap, grid), cfg.pricing).run(gen.generate())
```
- 시나리오 시장은 SPX 서페이스를 만기 × moneyness 격자 vol Quote로 재표현한다. 재피팅이 없어 vega 버킷이 지역적이다.
- 생성기가 spot 이동에 SSR 규칙으로 계산한 격자점별 vol 이동을 같은 Scenario에 담는다.
- 시장은 규칙을 모르고 적용만 한다.
- 엔진 선택 주의: 분석적 BS는 행사가 vol 하나만 써서 skew 항을 놓친다
  $D(K) = -\partial C/\partial K = D_{\text{BS}}(K) - \text{Vega}_{\text{BS}}(K)\,\partial\sigma/\partial K$.
  디지털은 `engines.yaml`에서 복제 방식이나 LV로 지정한다.

### 7.4 사용성 비교
| | QuantLib | ORE | QuantTool |
|---|---|---|---|
| 시장 | 사용자가 Quote·커브·Process를 직접 조립 | 설정 파일 → TodaysMarket | 설정 파일 → `Snapshot.build` |
| 계약 | Instrument 직접 생성 | portfolio.xml → Trade | positions YAML → Trade |
| 엔진 | `setPricingEngine` 직접 | pricingengine.xml → EngineFactory | engines.yaml → EngineFactory |
| 시나리오 | Quote를 직접 setValue | simulation.xml(격자) + sensitivity.xml → 생성기 → ScenarioSimMarket | grid.yaml + scenario YAML + estimated → 생성기 → ScenarioMarket |
| 실행 | 스크립트 | ore.xml → OREApp | 노트북·파이썬 API, 또는 app.run |
QuantTool은 ORE의 "설정 기반 조립"을 따르되, 노트북에서 객체를 직접 다룰 수 있는 파이썬 API를 1차 사용 방식으로 둔다.

---

## 8. 설정 파일 예시
```yaml
# configs/market/curves/krw_ktb.yaml
name: KRW_KTB
type: YieldCurve
currency: KRW
calendar: SouthKorea.Settlement
day_count: ActualActual.ISMA
reference: settlement_days       # 평가일을 따라 이동 (theta 시나리오용)
segments:
  - {type: FixedRateBond, quote_type: YLD, frequency: Semiannual,
     tenors: [1Y, 3Y, 5Y, 10Y, 20Y, 30Y]}
interpolation: LogCubic(Discount)

# configs/market/vols/spx.yaml
name: SPX_VOL
type: EquityVol
forward: SPX_FWD                 # 의존 그래프가 이 참조로 순서 결정
method: SSVI                     # 시나리오에서는 grid.yaml의 격자 vol로 재표현되어 흔들림

# configs/pricing/engines.yaml
IRSwap:        {model: Discounting,  engine: DiscountingSwap}
FixedBond:     {model: Discounting,  engine: DiscountingBond}
EquityVanilla: {model: BlackScholes, engine: AnalyticEuropean}
EquityDigital: {model: BlackScholes, engine: CallSpreadReplication}
Autocallable:  {model: LocalVol,     engine: MonteCarlo, params: {paths: 100000}}
```

---

## 9. 위험 요소와 미결정 사항

| 항목 | 내용 | 현재 방향 |
|---|---|---|
| 전역 평가일 | 날짜 다른 스냅샷 동시 평가 시 조용한 오류 | `Market.active()` 컨텍스트, 순차 평가 |
| Index fixing 전역 공유 | 시나리오가 기준 스냅샷 fixing을 오염 | fixing은 구축 시 1회 로드, 시나리오에서 수정 금지 |
| IV 서페이스 흔들기 | 호가 bump 시 재피팅이 변화를 번지게 함, 느림 | 격자 재표현으로 해결 (재피팅 없음) |
| 격자 보간 오차 | 격자 커브가 원래 부트스트랩 커브와 미세하게 다름 | `base_reconciliation`, 격자 촘촘히, 허용 오차 테스트 |
| 민감도 단위 | 격자 민감도는 제로금리·격자 vol 기준 | `scenario/par.py`로 시장 상품 기준 변환 (ORE parsensitivity 대응) |
| 격자 밖 구조 | 격자 사이·바깥에서 보간·외삽 형태가 결과에 영향 | 보간법을 grid.yaml에 명시, 외삽 정책 결정 필요 |
| 시간 경과 | 커브 기준일 고정 vs 이동 | 빌더 설정 `reference` |
| 모델 재캘리브레이션 비용 | 시나리오마다 자동 재캘리브레이션 | "모델 고정" 선택지 |
| 스냅샷 이력 | 연구·과거 재현에 구축 결과 필요 | `market/persist.py` |
| 단위·형식 | bp/소수, 수익률/가격 혼동 | `ids`에 유형·단위, `Scenario` 검증 |
| 시나리오 시장 방식 | 원래 시세 bump vs ORE식 격자 재표현 | **격자 재표현으로 결정** (PCA·과거 재현과 좌표 일치, 속도, vol 지역성) |
| 금리 데이터 | 스왑 커브 무료 데이터 없음 | 국채 + SOFR 선물 OIS 근사, 한계를 docs에 명시 |
| 듀얼 커브 (KRW) | CD 프로젝션 vs 할인 커브 | 구조는 지원, 데이터 확보 시 활성화 |

---

## 10. 다음 단계

### 10.1 첫 줄기 (미국 국채 커브 → 국채 → key rate DV01)
필요 파일:
```
configs/market/curves/ust.yaml, configs/market/todaysmarket.yaml,
configs/pricing/engines.yaml, configs/scenario/grid.yaml, configs/scenario/sensitivity.yaml
config/market.py, config/pricing.py, config/scenario.py
core/ids.py, core/registry.py, core/dependency.py
market/quotes.py, market/rates.py, market/market.py, market/diagnostics.py
derivatives/trades.py, derivatives/rates.py, derivatives/portfolio.py,
derivatives/factory.py, derivatives/engines.py
scenario/grid.py, scenario/factors.py, scenario/generators.py, scenario/scenario_market.py, scenario/runner.py
analytics/market_monitor.py, analytics/sensitivity.py
notebooks/01_ust_curve.ipynb
```
완료 기준: 헬퍼 재가격 오차가 허용 범위 이내, 격자 시장 기준 NPV가 스냅샷 NPV와 허용 오차 이내(`base_reconciliation`), 격자 key rate DV01 합이 평행 이동 DV01과 일치, QuantLib 직접 계산과 NPV 일치. par 변환(`scenario/par.py`)은 첫 줄기 직후에 추가.

### 10.2 이후
1. 주식 줄기: `market/equity.py`, `derivatives/equity.py`, `scenario/rules.py`, 디지털·바닐라 엔진.
2. `market/persist.py`와 일별 스냅샷 적재.
3. PCA·SSR 연구 → `configs/estimated/`.
4. P&L explain, 과거 재현 시나리오.
5. 오토콜 + LV 모델 빌더.

### 10.3 CLAUDE.md 초안
```
# QuantTool
- 구조와 원칙은 docs/architecture.md를 따른다. 새 모듈은 2장 원칙과 6.4 불변 조건을 지킨다.
- 의존 방향: config·core → market → derivatives → scenario → analytics. 역방향 import 금지.
- QuantLib API는 추측하지 말고 references/QuantLib-SWIG 또는 dir()/help()로 확인 후 사용.
- ORE 설계를 참조할 때는 references/Engine 원본을 확인하고 파일 경로를 남긴다.
- 모든 기능은 tests/에 QuantLib 직접 계산 또는 해석해와 비교하는 테스트를 함께 작성한다.
- 작업 단위는 작게: 모듈 하나, 테스트 통과, diff 리뷰 후 커밋.
- 설정 값은 configs/, 추정값은 configs/estimated/(출처 필수). 코드에 상수로 넣지 않는다.
```

---

## 참고 자료
- A QuantLib Guide: https://www.quantlibguide.com/
- QuantLib: https://github.com/lballabio/QuantLib , QuantLib-SWIG: https://github.com/lballabio/QuantLib-SWIG
- ORE: https://github.com/OpenSourceRisk/Engine
- Implementing QuantLib (Ballabio), Modern Derivatives Pricing and Sensitivity Analysis (Lichters, Stamm, Gallagher)
