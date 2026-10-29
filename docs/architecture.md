# QuantTool 아키텍처
---

## 0. 레퍼런스

### 0.1 QuantLib

QuantLib은 시장 상태, 계약, 프라이싱 모델을 표현하는 객체적 기반을 제공한다.

```
0. 기반
   - 시간 : Date, Period, Calendar, DayCounter, Schedule, Settings.evaluationDate(전역 평가일 하나)
   - 연결 : Observable/Observer, LazyObject, Handle/RelinkableHandle
1. 시장 정적 상태
   - 표현 : Quote(SimpleQuote), InterestRate, TermStructure(YieldTermStructure, BlackVolTermStructure …), Index
   - 도구 : RateHelper(BootstrapHelper 하위), 보간, 부트스트랩(PiecewiseYieldCurve)
2. 동학과 계산
   - StochasticProcess : SDE 기술 (BlackScholesMertonProcess, HestonProcess)
   - CalibratedModel   : Process + 파라미터 + calibrate() (HullWhite, HestonModel)
   - PricingEngine     : 특정 상품의 풀이법 (해석해, 트리, PDE, MC)
3. 계약과 분석
   - Instrument : Payoff + Exercise (옵션) / CashFlow·Leg (채권·스왑)
   - 상품 메소드 : NPV, 그릭스, cashflows (자기 상태 + 엔진만으로 답할 수 있는 것)
   - 패키지 함수 : CashFlows, BondFunctions (외부 가정이 필요하거나 여러 상품 공통)
```

참고자료
- A QuantLib Guide (https://www.quantlibguide.com/)
- Implementing QuantLib (Ballabio)
- Context7: `/lballabio/quantlib`, `/lballabio/quantlib-swig`(파이썬 예제가 더 많음).

### 0.2 ORE: 데이터로부터 시장과 계약을 조립해, 포트폴리오를 정합적으로 평가하고 흔드는 시스템

ORE는 시장상태를 표현할 수 있는 기본 단위와 이들을 포괄하는 객체적 기반과 이를 활용한 민감도/시나리오 분석 기능을 제공한다.
시장을 객체화하고 민감도/시나리오 분석을 할 수 있는 구조를 참고한다.

```
[QuantLib + QuantExt]   부품: Date·Quote·커브·헬퍼·Instrument·PricingEngine·Model
        │
[OREData: 번역·조립]    입력(XML·시세) ─► configuration(레시피) ─► 빌더 ─► 세 객체
   ├ configuration/     레시피: CurveConfigurations, Conventions, TodaysMarketParameters
   ├ marketdata/        Loader(MarketDatum) → TodaysMarket (Market ← MarketImpl ← TodaysMarket)
   ├ portfolio/         Trade 데이터(LegData…) → build(EngineFactory) → Instrument + PricingEngine; EngineData
   ├ model/             ModelBuilder → 캘리브레이션된 모델
   └ utilities/         문자열 → QuantLib 객체 파서(Calendar, Period, …)
        │   여기까지로 t0 가격평가·현금흐름 가능
[OREAnalytics: 활용]
   ├ simulation/        SimMarket (MarketImpl + update/reset), FixingManager
   ├ scenario/          Scenario · ScenarioGenerator · ScenarioSimMarket(+Parameters) · SensitivityScenarioData
   ├ engine/            ValuationEngine(날짜 × 시나리오 × 거래 → cube), SensitivityAnalysis, StressTest, ParSensitivityAnalysis, VaR
   ├ cube/              NPVCube, SensitivityCube
   └ app/               OREApp + Analytic(Pricing, Sensitivity, Stress, VaR, …), InputParameters
```

#### 클래스가 맞물리는 방식

표의 "W n.m"은 `docs/ore_walkthrough.md`의 절이다. 거기에 입력 예시, 파이썬으로 옮긴 클래스, 쓰는 코드가 있다.
원본 경로는 `references/Engine/` 기준이고, 이름은 원본 그대로다(C++ 표기 읽는 법은 워크스루 맨 앞).

**시장 (OREData `ored/marketdata/`, `ored/configuration/`)**

| 클래스 | 상속 | 만들 때 받는 것 | 핵심 메소드 | 누가 쓰나 | W |
|---|---|---|---|---|---|
| `MarketDatum` | ← `SwapQuote`, `MoneyMarketQuote`, … | asof, 키 문자열, 값 | `name()`, `quote()` | Loader가 만들고, 커브 빌더가 Quote를 헬퍼에 붙임 | 1.1 |
| `Loader` | ← `CSVLoader`, `InMemoryLoader` | 시세·fixing 파일 또는 목록 | `loadQuotes(asof)`, `get(키)`, `get(와일드카드)`, `loadFixings()` | TodaysMarket | 1.1 |
| `Conventions` | 항목 ← `IRSwapConvention`, `DepositConvention`, … | conventions.xml | `get(id)` | 커브 헬퍼, 상품 빌더 (전역 `InstrumentConventions`) | 1.2 |
| `CurveConfigurations` | 항목 `YieldCurveConfig` ← `CurveConfig` | curveconfig.xml | `yieldCurveConfig(id)`, `requiredCurveIds()` | TodaysMarket(구축, 의존 그래프) | 1.3 |
| `TodaysMarketParameters` | — | todaysmarket.xml | `configurations()`, `mapping(객체 종류, configuration)` → {이름: CurveSpec} | TodaysMarket | 1.4 |
| `Market` | 추상 규격 | — | `discountCurve(ccy)`, `yieldCurve(name)`, `iborIndex(name)`, `equitySpot`, `equityVol`, … | 엔진 빌더, 레그 빌더 (이것만 안다) | 1.6 |
| `MarketImpl` | ← `Market` | asof | 종류별 dict `(configuration, 이름) → Handle` + 조회 구현 | 하위 클래스가 채움 | 1.5 |
| `TodaysMarket` | ← `MarketImpl` | asof, TodaysMarketParameters, Loader, CurveConfigurations, `preserveQuoteLinkage=False` | 생성자에서 의존 순서대로 전부 구축 | 사용자, SensitivityAnalysis(초기 시장) | 1.5 |

**계약 (OREData `ored/portfolio/`)**

| 클래스 | 상속 | 만들 때 받는 것 | 핵심 메소드 | 누가 쓰나 | W |
|---|---|---|---|---|---|
| `Trade` | ← `Swap`, `Bond`, `FxForward`, … | id, tradeType, `Envelope` + 상품 데이터(`LegData` 목록 등) | `build(engineFactory)`, `instrument()`, `legs()` | Portfolio | 2.1 |
| `LegData` | 내용 ← `FixedLegData`, `FloatingLegData`, … | 통화, 지급/수취, 원금, 일정(`ScheduleData`), 종류별 내용 | `legType()`, `concreteLegData()` | LegBuilder | 2.1 |
| `Portfolio` | — | portfolio.xml 또는 `add(trade)` | `build(factory)`, `trades()` | 사용자, SensitivityAnalysis | 2.1 |
| `EngineData` | — | pricingengine.xml | `model(상품)`, `engine(상품)`, `engineParameters(상품)` | EngineFactory | 2.2 |
| `EngineBuilder` | ← `CachingPricingEngineBuilder` ← `SwapEngineBuilder`, … | (model, engine, tradeTypes) 고정. 시장·설정은 팩토리가 `init`으로 넣음 | `engine(키…)` → 같은 키면 캐시된 엔진 | Trade.build | 2.3 |
| `LegBuilder` | ← `FixedLegBuilder`, `FloatingLegBuilder`, … | legType | `buildLeg(legData, factory, …)` → QuantLib Leg | Trade.build | 2.4 |
| `EngineFactory` | — | EngineData, **Market**, configurations | `builder(tradeType)`, `legBuilder(legType)`, `market()` | Trade.build | 2.5 |
| `InstrumentWrapper` | ← `VanillaInstrument`, … | QuantLib Instrument, 승수 | `NPV()`, `qlInstrument()` | Trade가 build 결과로 보관 | 2.6 |

**분석 (OREAnalytics `orea/scenario/`, `orea/simulation/`, `orea/engine/`, `orea/cube/`)**

| 클래스 | 상속 | 만들 때 받는 것 | 핵심 메소드 | 누가 쓰나 | W |
|---|---|---|---|---|---|
| `RiskFactorKey` | — | (종류, 이름, 격자 인덱스) | — | 모든 시나리오 객체의 키 | 3.1 |
| `Scenario` | ← `SimpleScenario` | asof, label | `add(키, 값)`, `get(키)`, `isAbsolute()` | 생성기가 만들고 SimMarket이 적용 | 3.1 |
| `ScenarioSimMarketParameters` | — | simulation.xml | `yieldCurveTenors(name)`, `indices()`, `equityVolSmileDynamics(name)` | ScenarioSimMarket | 3.2 |
| `SimMarket` | ← `MarketImpl` | asof | `update(d)`, `reset()`, `scenarioGenerator` | ValuationEngine | 3.3 |
| `ScenarioSimMarket` | ← `SimMarket` | 초기 Market, ScenarioSimMarketParameters, `useSpreadedTermStructures` | `applyScenario(s)`, `baseScenario()` | SensitivityAnalysis, EngineFactory(시장 자리에) | 3.3 |
| `SensitivityScenarioData` | — | sensitivity.xml | 커브·spot·vol별 `ShiftData`(크기, Absolute/Relative, Forward/Central), par 상품, gamma 여부 | 생성기, ParSensitivityAnalysis | 3.4 |
| `ScenarioGenerator` | ← `ShiftScenarioGenerator` ← `SensitivityScenarioGenerator` | SensitivityScenarioData, 기준 Scenario, 격자 설정, sim 시장, 민감도 템플릿 | `next(d)`, `samples()`, `scenarioDescriptions()` | SimMarket.update | 3.5 |
| `ValuationCalculator` | ← `NPVCalculator`, `CashflowCalculator` | 기준 통화 등 | `calculate(trade, …, cube, 날짜, 표본)` | ValuationEngine | 3.6 |
| `ValuationEngine` | — | asof, DateGrid, SimMarket, 모델 빌더 | `buildCube(portfolio, cube, calculators)` | SensitivityAnalysis | 3.6 |
| `NPVCube` | ← `NPVSensiCube` ← `SensiCube` | 거래 id, asof, 표본 수 | `setT0`, `set`, `getT0`, `get` | ValuationEngine이 채움 | 3.6 |
| `SensitivityCube` | — | NPVSensiCube, 시나리오 설명, 이동 크기·방식 | `delta(거래, 키)`, `gamma`, `crossGamma` | 사용자, 리포트 | 3.7 |
| `SensitivityAnalysis` | — | Portfolio, 초기 Market, configuration, EngineData, ScenarioSimMarketParameters, SensitivityScenarioData, recalibrateModels | `generateSensitivities()`, `sensiCubes()` | 사용자, OREApp | 3.8 |
| `ParSensitivityAnalysis` | — | asof, ScenarioSimMarketParameters, SensitivityScenarioData | `computeParInstrumentSensitivities(sim)` → 야코비안, `ParSensitivityConverter` | 사용자 (raw → par 변환) | 3.9 |

#### 호출 흐름

```python
# ① 시장: 레시피 + 시세 → TodaysMarket                                                  (W 1.1~1.5)
loader = CSVLoader("market.txt", "fixings.txt")
curve_configs = CurveConfigurations.fromFile("curveconfig.xml")
tm_params = TodaysMarketParameters.fromFile("todaysmarket.xml")
market = TodaysMarket(asof, tm_params, loader, curve_configs)        # 의존 순서대로 커브 구축, asof 고정

# ② 계약: 데이터 → build(팩토리) → QuantLib 상품 + 엔진                                  (W 2.1~2.6)
factory = EngineFactory(EngineData.fromFile("pricingengine.xml"), market)
portfolio = Portfolio.fromFile("portfolio.xml")
portfolio.build(factory)
#   Swap.build(factory): builder = factory.builder("Swap")
#                        legs = [factory.legBuilder(ld.legType()).buildLeg(ld, factory) for ld in legData]
#                        swap = ql.Swap(legs, payers); swap.setPricingEngine(builder.engine("EUR"))
portfolio.trades()["Swap_20y"].instrument().NPV()

# ③ 민감도: 같은 계약을 흔들 수 있는 시장에 다시 연결해 반복 평가                         (W 3.1~3.8)
sa = SensitivityAnalysis(portfolio, market, "default", engine_data, sim_params, sensi_data, recalibrateModels=True)
sa.generateSensitivities()
#   a) sim = ScenarioSimMarket(market, sim_params, useSpreadedTermStructures=…)   # 초기 시장 → 격자 Quote
#   b) gen = SensitivityScenarioGenerator(sensi_data, sim.baseScenario(), sim_params, sim, …)
#   c) sim.scenarioGenerator = gen
#   d) portfolio.build(EngineFactory(engine_data, sim))                            # 시장 자리만 바뀜
#   e) ValuationEngine(asof, DateGrid("1,0W"), sim).buildCube(portfolio, cube, [NPVCalculator(ccy)])
#        for 시나리오: sim.update(asof) → 격자 Quote 변경 → 모든 거래 NPV → cube
#   f) SensitivityCube(cube, gen.scenarioDescriptions(), …).delta("Swap_20y", key)
# ④ (선택) ParSensitivityAnalysis: zero 격자 민감도 → 헷지 상품(par) 민감도             (W 3.9)
```

핵심은 ②와 ③-d가 **같은 `build` 코드**라는 점이다. 바뀌는 것은 팩토리에 넘긴 시장 하나다.
`TodaysMarket`과 `ScenarioSimMarket`이 모두 `Market` 규격을 따르기 때문이다.

#### 참고자료
- ORE 원본: `references/Engine`(GitHub `OpenSourceRisk/Engine`). Context7에는 ORE가 없어 원본을 직접 읽는다.
- 파이썬 바인딩: `references/ORE-SWIG`, 예제 `Examples/ORE-Python/ExampleScripts`(market.py, swap.py, portfolio.py), `Examples/ORE-Python/Notebooks`.
- 설계 문서: `Docs/Design/ore_design.tex`(= https://rkapl123.github.io/ore_design.pdf) — Introduction, Library Stack.
- 사용자 가이드: `Docs/userguide.pdf` — 설정 파일 사전.
- 예제 입력: `Examples/MinimalSetup`(최소 설정), `Examples/CurveBuilding`, `Examples/MarketRisk`(민감도, 스트레스, par 변환, P&L explain).
- Modern Derivatives Pricing and Sensitivity Analysis (Lichters, Stamm, Gallagher) — ORE 저자들의 방법론.
- 학습용 워크스루: `docs/ore_walkthrough.md`

---

## 1. 패키지의 구조

### 1.1 핵심

> **QuantTool은 표준화된 시장 데이터로 "그 시점의 시장 객체"를 만들고, 계약을 그 시장에 붙여 정합적으로 평가하며,
> 시장 객체를 규칙에 따라 흔들거나 시간을 움직여 민감도·시나리오 손익을 본다.**

QuantLib의 부품을 쓰고, ORE의 구조(QuantExt / OREData / OREAnalytics)를 **클래스 이름·인자·호출 순서까지** 따른다.
파이썬에 맞춰 바꾼 것은 표기(snake_case, XML 대신 YAML + pydantic, 결과 보기용 pandas)와 1.4 표에 적은 몇 가지뿐이다.

```
시세 (market-data 레포 → CSVLoader/DuckDBLoader) ─► [data] TodaysMarket (커브를 이름으로 조회)   ┐
포지션 YAML ─────────────────────────────────► [data] Portfolio (Trade → QuantLib 상품 + 엔진) ┘
                                                        │
                                                        ├─► 가격평가   시장 × 계약 → NPV, 현금흐름                    (data만으로)
                                                        ├─► 민감도     ScenarioSimMarket × 같은 계약 → delta, gamma, 템플릿별 규칙 (analytics)
                                                        ├─► 시나리오   손으로·스트레스·PCA 요인 → DeltaScenario → 손익
                                                        └─► 시간       SimMarket.update(다음 날) → theta
```

객체가 필요한 이유: 표에 있는 것은 **관측된 숫자 몇 개**(par yield 13개)지만 가격결정에는 **함수**(아무 날짜의 할인계수,
임의 구간의 선도금리)가 필요하다. 그 함수를 시장 관례대로 부트스트랩해 만든 것이 시장 객체다.

### 1.2 층위

```
0. 기반              qle/                  QuantLib 확장: bill BEY↔가격, 격자 커브, RiskFactorKey·Scenario     ← QuantExt
                     data/utilities/       파서(문자열 → Calendar…), 등록부, DateGrid                        ← ored/utilities
1. 레시피            data/configuration/   Conventions, YieldCurveConfig, TodaysMarketParameters, CurveSpec,
                                           EngineData, ScenarioSimMarketParameters, SensitivityScenarioData  ← ored/configuration, orea/scenario
2. 시장              data/marketdata/      MarketDatum, Loader, YieldCurveBuilder, DependencyGraph,
                                           Market ← MarketImpl ← TodaysMarket                                ← ored/marketdata
3. 계약              data/portfolio/       Trade(Bond …), BondData, LegData, LegBuilder, EngineBuilder, EngineFactory, Portfolio ← ored/portfolio
   모델              data/model/           ModelBuilder (예정)                                               ← ored/model
4. 시뮬레이션 시장   analytics/scenario/   SimMarket ← ScenarioSimMarket, ScenarioGenerator ← ShiftScenarioGenerator
                                           ← SensitivityScenarioGenerator, ScenarioDescription               ← orea/scenario, orea/simulation
5. 큐브              analytics/cube/       NPVCube, SensitivityCube                                          ← orea/cube
6. 계산              analytics/engine/     ValuationCalculator, ValuationEngine, SensitivityAnalysis         ← orea/engine
7. 보기              analytics/app/        커브 표·모양 지표                                                  ← orea/app
```
아래 층은 위 층을 import하지 않는다 (`tests/test_layering.py`).

### 1.3 무엇을 하고, 무엇을 하지 않나

| 하고 싶은 것 | 하는 곳 |
|---|---|
| 그 날의 커브·가격 (과거 어느 날 재현 포함) | `TodaysMarket(d)` + `Portfolio.build` |
| 격자점 민감도 (delta, gamma, cross gamma) | `SensitivityAnalysis` |
| 상품별로 다른 민감도 계산 규칙 (이동 크기·방식) | 엔진 파라미터 `SensitivityTemplate` + `keyed_shift_size/scheme` |
| 요인 사이 연동 규칙 (spot 이동 시 vol 서페이스 반응: sticky strike, SSR) | 시뮬레이션 시장의 스마일 동학 자리 (ORE `SmileDynamics`, 주식 줄기에서 구현 예정) |
| 가정한 충격 (스트레스, PCA 요인, 손으로 만든 이동) | `zero_rate_shift_scenario` → `DeltaScenario` → `ScenarioSimMarket.apply_scenario` |
| 시간 경과 (theta) | `ScenarioSimMarket.update(다음 날)` |
| 각 시점의 (수정) 그릭으로 헷지하고 성과 측정 | 날짜별 `TodaysMarket` + 민감도 + 다음 날 재평가 (`hedgebacktest`, 예정) |
| PCA·SSR 같은 통계 추정 | `research/`. 검증된 값만 `configs/estimated/`에 출처와 함께 |
| 데이터 수집·정제·저장 | 별도 레포 `market-data` |
| 범위 밖 | 신용(CDS, XVA, 담보), 통계적 리스크(VaR, 노출 시뮬레이션). 몬테카를로는 상품 가격결정 엔진 안에만 둔다 |

### 1.4 설계 원칙과 ORE와 다른 점

1. **시장은 규격이고, 규격·보관소·구축·변경을 나눈다.** `Market` ← `MarketImpl` ← `TodaysMarket` / `SimMarket` ← `ScenarioSimMarket`.
   가격결정 코드는 `Market` 규격만 안다.
2. **시장 입력은 시세 Quote이고, 구조물은 그 Quote에 연결된 채로 만든다.** 시세는 `MarketDatum.quote`(SimpleQuote), 시뮬레이션 시장은 격자 Quote(`sim_data`).
   그래서 시나리오가 "Quote 값 변경 → Observer 전파 → Lazy 재계산"으로 끝난다.
3. **이름으로 참조한다.** 계약은 커브를 객체가 아니라 이름(`reference_curve_id: UST`)으로 가리키고, 엔진 빌더가 시장에서 받는다.
   이름 → 레시피 매핑은 `todaysmarket.yaml`이 정한다.
4. **레시피(configuration)와 제작자(빌더)를 분리한다.** 같은 군은 같은 빌더, 대상별 차이는 설정.
5. **구축 순서는 의존 그래프가 정한다.** 관계는 레시피의 참조(`required_curve_ids`)에서 자동 추출.
6. **계약(무엇)과 평가 방법(어떻게)을 분리한다.** Trade는 순수 데이터, 엔진 선택은 `EngineData`, 조립은 `EngineBuilder`, 창구는 `EngineFactory`.
7. **시나리오는 데이터이고, 생성·적용·평가는 분리한다.** `ScenarioGenerator` → `Scenario` → `ScenarioSimMarket` → `ValuationEngine` → 큐브.
   - 7-1. **시뮬레이션 시장은 격자 재표현을 쓴다.** 민감도는 spreaded(기준 대비 비율). 요인 추정과 시나리오도 같은 격자 좌표(`RiskFactorKey`)를 쓴다.
   - 7-2. **시간 축은 SimMarket이 맡는다.** `update(date)`가 평가일을 옮기고 그 날의 시나리오를 적용한다. TodaysMarket은 asof 고정.
8. **의존 방향은 한쪽으로** (1.2, `tests/test_layering.py`).
9. **ORE 폴더·파일·클래스 이름을 따른다.** 파일 하나 = ORE 헤더 하나가 기본이고, 머리 주석에 원본 경로를 적는다.
10. **표 ↔ 객체 경계를 지킨다.** 들어올 때는 시세 파일·DB, 나갈 때는 결과 표. 객체는 짧게 쓰고 저장하지 않는다.

**ORE와 다른 점 (전부)**. 새로 다르게 하면 여기에 한 줄 추가한다(CLAUDE.md 규칙).

| ORE (원본 경로) | QuantTool | 이유 | 포기한 것 |
|---|---|---|---|
| XML + `fromXML`/`toXML` | YAML + pydantic (필드 이름 snake_case) | 파이썬에서 읽기·검증이 쉽다 | 없음 (구조 같음) |
| 클래스 등록 계층 (`addDefaultBuilders`) | 딕셔너리 등록부 + 데코레이터 (`data/utilities/registry.py`) | 파이썬 관용 | 없음 |
| `EngineBuilder::engine()`(이름) / `engine(args…)`(생성) 오버로드 | 이름은 `engine_name`, 생성은 `engine(…)` | 파이썬에 오버로드가 없다 | 없음 |
| 국채 커브는 개별 채권 가격(`BOND/PRICE`, FittedBond) | par yield 곡선 시세 `BOND/YIELD/…/PAR/{만기}` + 세그먼트 `ZeroCouponBill`·`FixedRateBond` (확장) | 재무부가 par yield를 고시한다 | 개별 채권 가격 커브는 아직 없음 |
| `DiscountingRiskyBondEngine` (신용 커브·증권 스프레드) | 이름은 같게, 신용 없이 무위험 할인 | 신용 범위 밖 | 위험 할인 |
| `SpreadedDiscountCurve` logLinear / logCubic 보간 | `LinearZero`만 (`qle/termstructures.py`) | QuantLib-Python에 같은 구조물이 없다 | 격자점 사이 로그 할인계수 보간 |
| spreaded 커브 노드가 시간 기준(만기까지 시간 고정) | 노드가 날짜 기준 | QuantLib 클래스가 날짜를 받는다 | 시나리오 + 날짜 이동을 함께 할 때 이동량이 붙는 위치가 미세하게 다름 |
| `NPVCube` 구현 여러 개 (메모리·파일·정밀도) | numpy 배열 하나 + pandas 보기 | 규모가 작다 | 대형 포트폴리오 성능 |
| FX 환산(`NPVCalculator` 기준 통화) | 기준 통화 거래만 | 아직 다통화 상품 없음 | 다통화 |
| 멀티스레드 `SensitivityAnalysis`, `FixingManager`, 모델 재캘리브레이션 | 단일 스레드, fixing 없음, 재캘리브레이션 자리만 | 지금 필요 없음 | 성능, 변동 레그 과거 fixing |
| `OREApp` + `InputParameters` | 노트북에서 객체를 직접 조립 | 탐색·실험이 주 용도 | 일괄 실행 앱 |

### 1.5 프로젝트 구조

✓ = 구현됨, 나머지는 예정.

```
quant-tool/
├── configs/                               [값: ORE 입력 파일에 해당]
│   ├── conventions/rates.yaml ✓           conventions.xml
│   ├── market/todaysmarket.yaml ✓         todaysmarket.xml (configuration → 이름 → 커브 지정)
│   ├── market/curves/ust.yaml ✓           curveconfig.xml의 YieldCurve 항목 하나
│   ├── pricing/engines.yaml ✓             pricingengine.xml
│   ├── scenario/simmarket.yaml ✓          simulation.xml (Market 블록)
│   ├── scenario/sensitivity.yaml ✓        sensitivity.xml
│   └── estimated/                         PCA 로딩, SSR 등 (값 + 출처, 격자 좌표 기준)
├── positions/ust_book.yaml ✓              portfolio.xml
├── src/quanttool/
│   ├── qle/                               [QuantExt] termstructures.py ✓, scenario.py ✓
│   ├── data/                              [OREData]
│   │   ├── utilities/                     parsers.py ✓, registry.py ✓, dategrid.py ✓
│   │   ├── configuration/                 conventions.py ✓, curveconfig.py ✓, curvespec.py ✓, todaysmarketparameters.py ✓,
│   │   │                                  enginedata.py ✓, scenariosimmarketparameters.py ✓, sensitivityscenariodata.py ✓
│   │   ├── marketdata/                    marketdatum.py ✓, loader.py ✓(CSVLoader, InMemoryLoader; DuckDBLoader 예정),
│   │   │                                  market.py ✓, todaysmarket.py ✓, yieldcurve.py ✓, dependencygraph.py ✓, diagnostics.py ✓
│   │   ├── portfolio/                     trade.py ✓, bond.py ✓, legdata.py ✓, legbuilders.py ✓, enginefactory.py ✓,
│   │   │                                  portfolio.py ✓, builders/bond.py ✓, swap.py, equityoption.py
│   │   └── model/                         modelbuilder.py
│   └── analytics/                         [OREAnalytics]
│       ├── scenario/                      scenario.py ✓, simmarket.py ✓, scenariogenerator.py ✓, shiftscenariogenerator.py ✓,
│       │                                  sensitivityscenariogenerator.py ✓, stressscenariogenerator.py, pcascenariogenerator.py
│       ├── cube/                          npvcube.py ✓, sensitivitycube.py ✓
│       ├── engine/                        valuationcalculator.py ✓, valuationengine.py ✓, sensitivityanalysis.py ✓,
│       │                                  parsensitivityanalysis.py, stresstest.py, hedgebacktest.py, pnlexplain.py
│       └── app/                           marketmonitor.py ✓
├── notebooks/                             tutorial/ ✓ 00~05 (흐름 따라가기), 01_ust_curve ✓ (시장 해석)
├── research/                              PCA·SSR 추정 → 검증 후 configs/estimated/
├── tests/ ✓                               src와 같은 구조. QuantLib 직접 계산·해석해와 비교
├── scripts/fetch_references.sh ✓          references/ 클론
├── docs/                                  architecture.md, ore_walkthrough.md (학습용)
└── references/                            (gitignore) QuantLib-SWIG, ORE Engine, ORE-SWIG 원본
```

### 1.6 객체 가이드

numpy·pandas 정리처럼 **객체마다 구조 · 속성 · 초기화 · 메소드**를 적는다. 원본 경로는 `references/Engine/` 기준.
QuantLib 객체(`ql.…`)를 감싸거나 만드는 것이 대부분이라, "무엇을 들고 있고 무엇을 돌려주는가"를 중심으로 본다.

#### 상속 한눈에

```
Market (규격) ← MarketImpl (보관소) ← TodaysMarket (구축, asof 고정)
                                  └ SimMarket (update/reset) ← ScenarioSimMarket (격자 Quote)
Loader ← InMemoryLoader ← CSVLoader                         MarketDatum ← BondYieldQuote, ZeroQuote, SwapQuote, MoneyMarketQuote
MarketBuilder ← YieldCurveBuilder
Trade ← Bond                                                InstrumentWrapper ← VanillaInstrument
EngineBuilder ← CachingPricingEngineBuilder ← BondEngineBuilder ← BondDiscountingEngineBuilder
LegBuilder ← FixedLegBuilder
Scenario ← SimpleScenario, DeltaScenario
ScenarioGenerator ← ListScenarioGenerator ← ShiftScenarioGenerator ← SensitivityScenarioGenerator
ValuationCalculator ← NPVCalculator
```

#### (1) 설정 — `quanttool.data.configuration`

- **`load_config(root) → Config`**: `configs/`의 YAML을 읽어 검증된 설정 묶음을 만든다. 관례를 전역 `InstrumentConventions`에 등록한다(ORE `InputParameters`).
  - 속성: `.conventions`(dict), `.curve_configs`(dict: 레시피 id → `YieldCurveConfig`), `.todaysmarket`, `.engine_data`, `.simmarket`, `.sensitivity`
- **`TodaysMarketParameters`** (todaysmarket.xml)
  - 구조: configuration id → 객체 종류별 묶음 id → {시장 이름: 커브 지정 `Yield/USD/UST`}
  - 메소드: `.mapping(MarketObject.DiscountCurve, "default") → {"USD": "Yield/USD/UST"}`, `.curve_specs(configuration) → ["Yield/USD/UST"]`
- **`parse_curve_spec("Yield/USD/UST") → YieldCurveSpec(curve_config_id="UST", ccy="USD")`**
- **`YieldCurveConfig`** (curveconfig.xml의 YieldCurve 하나)
  - 속성: `.curve_id`, `.currency`, `.segments`(각각 `.type`, `.quotes`, `.conventions`), `.interpolation_variable`, `.interpolation_method`, `.discount_curve`
  - 메소드: `.quotes()`(모든 시세 키), `.required_curve_ids()`(의존 레시피)
- **`InstrumentConventions.instance().conventions().get("UST") → RateConventions`** (전역 관례 등록부)
- **`EngineData`** (pricingengine.xml): `.model(상품)`, `.engine(상품)`, `.model_parameters(상품)`, `.engine_parameters(상품)`, `.global_parameters`
- **`ScenarioSimMarketParameters`** (simulation.xml): `.base_currency`, `.curves() → [(KeyType, 이름)]`, `.yield_curve_tenors(이름)`, `.keys(KeyType, 이름) → [RiskFactorKey]`, `.interpolation`
- **`SensitivityScenarioData`** (sensitivity.xml): `.yield_curves[이름] → CurveShiftData(.shift_type, .shift_size, .shift_scheme, .shift_tenors, .keyed_shift_size, .keyed_shift_scheme)`,
  `.compute_gamma`, `.cross_gamma_filter`, `.use_spreaded_term_structures`, `.templates()`

#### (2) 시세 — `quanttool.data.marketdata` (marketdatum.py, loader.py)

- **`MarketDatum`**: 시세 한 줄
  - 구조: 키가 스스로를 설명한다 `종류/시세유형/…` → 파서가 하위 클래스로
  - 속성: `.name`(키), `.value`, `.asof_date`, `.instrument_type`, `.quote_type`, `.quote`(SimpleQuote: 커브 헬퍼가 연결되는 곳), 하위 클래스별 `.ccy`, `.tenor` …
  - 초기화: `parse_market_datum(asof, "BOND/YIELD/USD/UST/PAR/10Y", 0.0398) → BondYieldQuote`
- **`Loader`**: 시세 창구 (출처를 감춘다)
  - 초기화: `CSVLoader(시세 파일들, fixing 파일들)` (ORE market.txt 형식), `InMemoryLoader()` + `.add(날짜, 키, 값)`
  - 메소드: `.load_quotes(d)`, `.get(키, d)`, `.get_wildcard("BOND/YIELD/USD/UST/PAR/*", d)`, `.has(키, d)`, `.asof_dates()`, `.load_fixings()`

#### (3) 시장 — `quanttool.data.marketdata` (market.py, todaysmarket.py)

- **`Market`** (규격): 가격결정 코드가 아는 유일한 것
  - 속성: `.asof`
  - 메소드: `.discount_curve(통화, configuration="default")`, `.yield_curve(이름, configuration="default")` → `ql.YieldTermStructureHandle`,
    `.active()`(평가일을 이 시장 날짜로 두는 with 블록). `index`·`equity_spot`·`equity_vol` 등은 자리만 있다
  - 없는 configuration이면 `default`에서 찾는다
- **`TodaysMarket`** (구축된 오늘 시장)
  - 초기화: `TodaysMarket(asof, todaysmarket_params, loader, curve_configs, preserve_quote_linkage=False)`, 또는 `TodaysMarket.from_config(asof, cfg, loader)`
  - 하는 일: configuration마다 필요한 레시피를 의존 순서대로 한 번씩 구축 → asof 기준일로 부트스트랩 → 얼림(freeze) → 이름마다 Handle 등록
  - 속성: `.asof`, `.loader`, `.params`
  - 메소드: `Market` 규격 + `.yield_curve_names()`, `.curve_helpers(레시피 id)`(진단용 헬퍼 목록)
- 진단: `helper_repricing(market, "UST")` (헬퍼 재가격 오차 표), `curve_table(market, "UST", cfg)`, `curve_shape(table)`

#### (4) 계약 — `quanttool.data.portfolio`

- **`Trade`** (계약서, 순수 데이터 → build 후 상품)
  - 속성(데이터): `.id`, `.trade_type`, `.envelope`(상대방 등)
  - 메소드(build 후): `.build(factory)`, `.instrument() → InstrumentWrapper`, `.npv()`, `.legs()`, `.npv_currency()`, `.notional()`, `.maturity()`,
    `.sensitivity_template()`, `.reset()`, `.is_built()`
- **`Bond(Trade)`**: `.bond_data: BondData(issuer_id, security_id, reference_curve_id, settlement_days, calendar, issue_date, bond_notional, coupons: [LegData])`
  - build 순서: `factory.builder("Bond")` → 레그마다 `factory.leg_builder(leg_type).build_leg(...)` → `ql.Bond(…)` → `builder.engine(통화, 신용, 증권, 기준 커브, income)` → `VanillaInstrument(상품, 승수)`
- **`LegData`**: `.leg_type`, `.payer`, `.currency`, `.notionals`, `.day_counter`, `.payment_convention`, `.schedule_data`(`ScheduleRules`), `.fixed_leg_data`(`.rates`)
- **`InstrumentWrapper`**: `.ql_instrument()`, `.multiplier`, `.npv()`
- **`EngineFactory`** (접수 창구)
  - 초기화: `EngineFactory(engine_data, market, configurations=None)`, `EngineFactory.from_config(cfg, market)`
  - 메소드: `.builder(trade_type) → EngineBuilder`(상품 유형당 하나), `.leg_builder(leg_type)`, `.market()`
  - 같은 계약을 다른 시장에 붙이려면 다른 시장으로 팩토리를 만들어 `portfolio.build(factory)`를 다시 부른다
- **`EngineBuilder`** (기술자): `.model`, `.engine_name`, `.trade_types`, `.engine(키…)`(같은 키면 캐시), `.configuration(MarketContext.pricing)`, `.engine_parameter(이름)`
  - 새 빌더: `CachingPricingEngineBuilder`를 상속해 `key_impl`, `engine_impl`을 쓰고 `@register_engine_builder`
- **`Portfolio`**: `Portfolio.from_file(yaml)`, `.add(trade)`, `.trades()`(id → Trade), `.get(id)`, `.ids()`, `.build(factory)`, `.reset()`, `.npvs()`(pandas), `.npv()`

#### (5) 리스크 요인과 시나리오 — `quanttool.qle.scenario`, `quanttool.analytics.scenario`

- **`RiskFactorKey(key_type, name, index)`**: 격자점 하나. 예: `RiskFactorKey(KeyType.YieldCurve, "UST", 9)` = UST 커브 격자 10번째 점(5Y). `str()` → `"YieldCurve/UST/9"`
- **`Scenario`**: 격자점 → 값
  - 속성·메소드: `.asof()`, `.label()`, `.keys()`, `.get(key)`, `.has(key)`, `.is_absolute()`(False면 기준 대비 비율), `.values()`
  - 초기화: `SimpleScenario(asof, label, {key: 값}, absolute)`, `DeltaScenario(기준, {바뀐 key: 값}, label)`(나머지는 기준 값)
  - 도우미: `zero_rate_shift_scenario(sim, {key: 제로금리 이동}, label) → DeltaScenario` (스트레스·PCA·손으로 만든 시나리오)
- **`ScenarioSimMarket`** (흔들 수 있는 시장)
  - 초기화: `ScenarioSimMarket(init_market, sim_params, configuration="default", use_spreaded_term_structures=False)`
  - 구조: 초기 시장 커브를 격자 Quote(`sim_data`)로 다시 표현. spreaded면 Quote = 할인계수 비율(기준 1), 아니면 할인계수
  - 속성: `.sim_data`(key → SimpleQuote), `.sim_data_times`(key → 시간), `.date`, `.scenario`(지금 적용된 것), `.scenario_generator`
  - 메소드: `Market` 규격 + `.base_scenario()`, `.base_scenario_absolute()`, `.apply_scenario(s)`, `.update(d)`(다음 시나리오 + 날짜 이동), `.reset()`,
    `.base_reconciliation(portfolio, cfg)`(초기 시장과 NPV 대사)
- **`ScenarioGenerator`**: `.next(d)`, `.reset()`, `.samples()`
  - `ListScenarioGenerator([시나리오…])`: 정해진 목록
  - `SensitivityScenarioGenerator(sensitivity_data, base_scenario, sim_params, sim, template="")`: 기준 + shift tenor마다 Up(+Down) + Cross.
    `.scenario_descriptions()`(`"Up:YieldCurve/UST/9/5Y"`), `.shift_sizes()`, `.shift_schemes()`

#### (6) 큐브와 계산 — `quanttool.analytics.cube`, `quanttool.analytics.engine`

- **`NPVCube(ids, asof, dates, samples, depth=1)`**: 거래 × 날짜 × 표본 × 깊이
  - 메소드: `.set_t0/.get_t0(거래)`, `.set/.get(거래, 날짜 번호, 표본 번호)`, `.ids()`, `.samples()`, `.t0()`·`.to_frame(labels=…)`(pandas 보기)
- **`ValuationCalculator`**: 시장을 갱신한 뒤 거래마다 무엇을 남길지. `NPVCalculator(기준 통화)`
- **`ValuationEngine(today, dates, sim_market)`**: `.build_cube(portfolio, cube, [calculators])` — 표본마다·날짜마다 `sim.update(d)` → 계산기 → 큐브. 끝나면 reset
- **`SensitivityCube(cube, descriptions, target_sizes, actual_sizes, schemes)`**
  - 메소드: `.delta(거래, key)`, `.gamma(거래, key)`, `.cross_gamma(거래, (k1, k2))`, `.factors()`, `.report()`(ORE 리포트 열), `.delta_table(KeyType, 이름, measure)`(만기 × 거래)
  - 값은 "설정한 이동 1회당 NPV 변화"(1bp 이동이면 1bp당 손익)
- **`SensitivityAnalysis(portfolio, market, configuration, engine_data, sim_params, sensitivity_data)`**, `SensitivityAnalysis.from_config(portfolio, market, cfg)`
  - `.generate_sensitivities()`: 템플릿별로 시뮬레이션 시장·생성기·재조립·ValuationEngine → `.sensi_cubes()`
  - `.report()`, `.delta_table(KeyType.YieldCurve, "UST", measure="Delta"|"Gamma")`, `.sim_market`

#### 불변 조건
- 시장 입력은 loader의 시세 Quote이고, 커브는 그 Quote에 연결된 헬퍼로 만든다.
- 시나리오에서 흔드는 대상은 `ScenarioSimMarketParameters`의 격자점(`sim_data`)이다. 시나리오는 격자점 전부의 값을 준다(`DeltaScenario`로 기준을 채움).
- spreaded 시뮬레이션 시장의 기준 NPV는 초기 시장 NPV와 같다(상대오차 < 1e-12).
- 가격결정·시나리오 코드는 `Market` 규격 메소드만 쓴다.
- Trade는 엔진·모델을 모른다. 엔진 선택은 `EngineData`, 민감도 규칙은 엔진 파라미터 `SensitivityTemplate` + `SensitivityScenarioData`.
- `ValuationEngine`은 포트폴리오를 시나리오마다 재조립하지 않는다. 끝나면 시장을 reset한다.
- `TodaysMarket`은 만들어진 뒤 바뀌지 않는다. 바꾸는 것은 `SimMarket`만.
- 날짜가 다른 시장은 각자의 `active()` 안에서 순차적으로만 평가한다.

### 1.7 사용 흐름

예시 상황: **미 국채 포트폴리오의 오늘 가격, key rate delta·gamma, 다음 날 theta.** 0.2 호출 흐름과 같은 순서이고,
합성 샘플로 같은 흐름을 실행하는 것이 `notebooks/tutorial/` 01~05다.

```python
from datetime import date
from quanttool.data.configuration import load_config
from quanttool.data.marketdata import CSVLoader, TodaysMarket
from quanttool.data.portfolio import EngineFactory, Portfolio
from quanttool.analytics.scenario import KeyType, ScenarioSimMarket, zero_rate_shift_scenario
from quanttool.analytics.engine import SensitivityAnalysis
from quanttool.analytics.app import curve_table

asof = date(2026, 10, 23)
cfg = load_config("configs")                                  # 1) 레시피 (+ 관례 전역 등록)
loader = CSVLoader("tests/fixtures/market_ust_sample.txt")    # 2) 시세 (market-data 연결 후 DuckDBLoader)
market = TodaysMarket.from_config(asof, cfg, loader)          # 3) 오늘 시장: Yield/USD/UST 한 번 구축, USD·UST 이름으로 공유

book = Portfolio.from_file("positions/ust_book.yaml")         # 4) 계약 데이터 (BondData + LegData)
with market.active():
    book.build(EngineFactory.from_config(cfg, market))        #    Bond.build: builder("Bond") → leg_builder("Fixed") → ql.Bond → engine(…)
    npv = book.npvs()

sa = SensitivityAnalysis.from_config(book, market, cfg)       # 5) 민감도 (ORE generateSensitivities 순서)
sa.generate_sensitivities()
delta = sa.delta_table(KeyType.YieldCurve, "UST")             #    만기 × 거래, 1bp당 손익
gamma = sa.delta_table(KeyType.YieldCurve, "UST", measure="Gamma")
report = sa.report()                                          #    ORE sensitivity 리포트 열

sim = ScenarioSimMarket(market, cfg.simmarket, use_spreaded_term_structures=True)
with sim.active():                                            # 6) 손으로 만든 시나리오 (스트레스·PCA도 같은 방식)
    book.build(EngineFactory.from_config(cfg, sim))
    base = book.npvs()
    keys = cfg.simmarket.keys(KeyType.YieldCurve, "UST")
    sim.apply_scenario(zero_rate_shift_scenario(sim, {k: 0.0010 for k in keys}, "parallel +10bp"))
    pnl = book.npvs() - base
    sim.reset()
sim.update(date(2026, 10, 26))                                # 7) theta: 시장 그대로, 날짜만 (ForwardForward)
with sim.active():
    theta = book.npvs() - base
sim.reset()

history = {d: curve_table(TodaysMarket.from_config(d, cfg, loader), "UST", cfg)["zero_cc"]
           for d in loader.asof_dates()}                      # 8) 날짜별 이력: 결과만 표로
```

### 1.8 확장하는 법

새 기능은 **ORE에서 그 관심사가 어디에 사는지** 원본으로 확인하고 같은 자리에 넣는다. 다르게 하면 1.4 표에 적는다.

| 하고 싶은 것 | 추가하는 곳 | ORE 원본 |
|---|---|---|
| 커브 추가 (KRW 국채, SOFR) | `configs/market/curves/*.yaml` + `todaysmarket.yaml` 매핑. 새 헬퍼 종류면 `yieldcurve.py` 세그먼트 + `curveconfig.py` | `ored/marketdata/yieldcurve.cpp`, `configuration/yieldcurveconfig.hpp` |
| 지수 (CD91, SOFR) | `Market.index` + `todaysmarket.yaml`의 IndexForwardingCurves + 지수 빌더 | `marketdata/todaysmarket.cpp` (IndexCurve 노드) |
| 상품 추가 (Swap, EquityOption) | `data/portfolio/<상품>.py` (`@TRADES.register`) + 레그 종류면 `legdata.py`·`legbuilders.py` + `builders/<상품>.py` + `engines.yaml` | `ored/portfolio/swap.cpp`, `legbuilders.hpp`, `builders/swap.hpp` |
| 엔진 교체 (예: 디지털을 복제 방식으로) | `builders/`에 새 빌더(`CachingPricingEngineBuilder`), `engines.yaml`의 model/engine만 바꿈 | `ored/portfolio/builders/` |
| 상품별 민감도 규칙 (이동 크기·방식) | 엔진 파라미터 `SensitivityTemplate` + `sensitivity.yaml`의 `keyed_shift_size/scheme` | `orea/engine/sensitivityanalysis.cpp`, `ored/portfolio/trade.cpp` |
| 요인 연동 규칙 (sticky strike, SSR) | vol 격자를 `ScenarioSimMarket`에 추가하고 스마일 동학을 `simmarket.yaml`에 (`SmileDynamics`) | `orea/scenario/scenariosimmarket.cpp`, `QuantExt/qle/termstructures/dynamicstype.hpp` |
| 엔진 그릭의 사후 보정 (예: Δ + Vega·∂σ/∂S) | 새 `ValuationCalculator`(깊이에 그릭 기록) 또는 SensitivityCube 위 계산 | `orea/engine/valuationcalculator.hpp` |
| 스트레스·PCA 시나리오 | `ListScenarioGenerator` + `zero_rate_shift_scenario`, 규칙이 커지면 `stressscenariogenerator.py` | `orea/scenario/stressscenariogenerator.hpp` |
| par 민감도 (헷지 수량) | `analytics/engine/parsensitivityanalysis.py` | `orea/engine/parsensitivityanalysis.hpp` |
| 헷지 백테스트·P&L 귀속 | `analytics/engine/hedgebacktest.py`, `pnlexplain.py` (날짜별 `TodaysMarket` + 민감도 + 다음 날 재평가) | `orea/engine/pnlexplainreport.cpp`, `marketriskbacktest.cpp` |

### 1.9 설정 파일 예시

```yaml
# configs/market/todaysmarket.yaml
configurations:
  default: {discounting_curves_id: default, yield_curves_id: default}
discounting_curves:
  default: {USD: Yield/USD/UST}
yield_curves:
  default: {UST: Yield/USD/UST}

# configs/market/curves/ust.yaml (발췌)
curve_id: UST
currency: USD
segments:
  - type: ZeroCouponBill
    conventions: UST
    quotes: [BOND/YIELD/USD/UST/PAR/1M, …, BOND/YIELD/USD/UST/PAR/1Y]
  - type: FixedRateBond
    conventions: UST
    quotes: [BOND/YIELD/USD/UST/PAR/2Y, …, BOND/YIELD/USD/UST/PAR/30Y]
interpolation_variable: Discount
interpolation_method: LogCubic

# configs/pricing/engines.yaml
products:
  Bond: {model: DiscountedCashflows, engine: DiscountingRiskyBondEngine, engine_parameters: {}}

# configs/scenario/simmarket.yaml
base_currency: USD
yield_curves:
  names: [UST]
  tenors: {"": [1M, 3M, 6M, …, 30Y]}
  interpolation: LinearZero

# configs/scenario/sensitivity.yaml
use_spreaded_term_structures: true
compute_gamma: true
yield_curves:
  UST: {shift_type: Absolute, shift_size: 0.0001, shift_scheme: Forward, shift_tenors: [1M, …, 30Y]}

# positions/ust_book.yaml (한 거래)
- id: UST_10Y
  trade_type: Bond
  bond_data:
    security_id: UST_10Y
    reference_curve_id: UST
    settlement_days: 1
    calendar: UnitedStates.GovernmentBond
    issue_date: 2026-08-15
    coupons:
      - {leg_type: Fixed, payer: false, currency: USD, notionals: [1.0e7], day_counter: ActualActual.Bond,
         payment_convention: Unadjusted, fixed_leg_data: {rates: [0.04125]},
         schedule_data: {rules: [{start_date: 2026-08-15, end_date: 2036-08-15, tenor: 6M,
                                  calendar: UnitedStates.GovernmentBond, rule: Backward}]}}
```

---

## 2. 진행

### 2.1 결정 사항과 미결정

ORE와 다르게 한 것은 1.4 표에 있다. 여기는 그 밖의 결정이다.

| 항목 | 내용 | 현재 방향 |
|---|---|---|
| 구조·이름 | 자체 이름 vs ORE | **ORE 구조·클래스·인자·호출 순서를 따른다** (구현됨). 다른 점은 1.4 표 |
| 데이터 | 이 레포에서 수집 vs 별도 프로젝트 | **별도 레포 `market-data`** (`../market-data` `docs/design.md`, `docs/data_catalog.md`) |
| 범위 | 신용, 통계적 리스크 | **제외**: CDS·XVA·담보, VaR·노출 시뮬레이션. 몬테카를로는 상품 엔진 안에만 |
| 분석의 주 목적 | — | 시장 요인화(격자·PCA) 위의 민감도, 그릭 계산 규칙 수정과 검증, (이후) 각 시점의 수정 그릭으로 헷지한 성과 측정 |
| 시나리오 시장 방식 | 원래 시세 bump vs ORE식 격자 재표현 | **격자 재표현** (PCA·과거 재현과 좌표 일치, 속도, vol 지역성) |
| 격자 Quote | — | ORE와 같이 spreaded = 할인계수 비율(기준 1), 절대 = 할인계수. 민감도는 spreaded (`sensitivity.yaml`) |
| 커브 기준일 | — | **asof 고정 + freeze** (`preserve_quote_linkage=True`면 시세 연결 유지). 시간 이동은 SimMarket |
| 시간 축 | — | `SimMarket.update(date)` (ForwardForward roll)로 theta. P&L explain은 예정 |
| 전역 평가일 | 날짜 다른 시장 동시 평가 시 조용한 오류 | 시장마다 `active()`, 순차 평가 |
| 격자 바깥 | 외삽 형태가 결과에 영향 | 평탄 제로. QuantLib 1.44 `PiecewiseZeroSpreadedTermStructure`는 Quote 변경 시 외삽 설정이 풀려, 마지막 격자 Quote에 묶은 100Y 끝점으로 처리 |
| 민감도 단위 | 격자 민감도는 제로금리 기준 | ORE와 같이 "설정한 이동 1회당 NPV 변화". par 기준은 `ParSensitivityAnalysis`(예정) |
| UST par 헬퍼 관례 | par yield = 쿠폰인 가상 채권 가격이 정확히 100이어야 함 | 명목 만기 정규 일정 + Unadjusted 지급. bill(≤1Y)은 BEY → 할인채 가격. 쿠폰은 구축 시점 고정, 수익률 변화는 DerivedQuote로 가격에 전달 |
| Index fixing 전역 공유 | 시나리오가 기준 시장 fixing을 오염 | fixing은 구축 시 1회 로드, 시나리오에서 수정 금지 (변동 레그 때) |
| 모델 재캘리브레이션 | 시나리오마다 자동 재캘리브레이션 비용 | ORE와 같이 `recalibrate_models` 선택지 |
| 듀얼 커브 (KRW) | CD 프로젝션 vs 할인 커브 | 구조는 지원(`discount_curve` 의존), 데이터 확보 시 활성화 |

### 2.2 현황

최종 갱신 2026-10-29. 브랜치 `claude/confident-hamilton-ui198k`, PR https://github.com/wnsdydchl0/quant-tool/pull/1

시작하기
```bash
git clone https://github.com/wnsdydchl0/quant-tool.git && cd quant-tool
git checkout claude/confident-hamilton-ui198k
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,notebook]"
scripts/fetch_references.sh                              # QuantLib-SWIG, ORE Engine, ORE-SWIG 원본 (선택)
python -m pytest -q && ruff check . && ruff format --check .
```
- `pytest`는 `python -m pytest`로 돌린다. PATH의 `pytest`가 QuantLib 없는 다른 환경을 가리킬 수 있다.
- 처음이면 `notebooks/tutorial/` 00~05를 순서대로 실행하며 코드 위치를 따라간다. 객체 정리는 1.6.
- `tests/fixtures/market_ust_sample.txt`는 ORE market.txt 형식의 합성 샘플이다. 실제 데이터는 `market-data` 레포 연결 전이다.

완료
- 첫 줄기 (UST 커브 → 국채 → key rate delta·gamma), 노트북 `01_ust_curve`.
- ORE 정렬 (2026-10-29): 시장(configuration·CurveSpec·전역 관례), 시세(MarketDatum 키·CSVLoader), 계약(BondData·LegData·LegBuilder·
  EngineFactory configurations·캐싱 빌더 키), 시나리오(RiskFactorKey 정수 인덱스·Scenario 값·DeltaScenario·할인계수 비율 격자),
  민감도(ShiftData·Up/Down·gamma·cross gamma·민감도 템플릿·NPVCube·ValuationCalculator·SensitivityCube 리포트).
- 튜토리얼 노트북 6개(00~05).
- 테스트 116개. 완료 기준 (합성 샘플 기준):

| 기준 | 결과 |
|---|---|
| 헬퍼 재가격 오차 < 0.01bp | 약 1e-9bp |
| QuantLib 직접 조립 채권(FixedRateBond)과 NPV 일치 | 상대오차 1e-12 이내 (매도 포지션 부호 포함) |
| spreaded 시뮬레이션 커브 = 초기 커브 (격자 사이·바깥 포함) | 할인계수 차이 < 1e-14, 거래 NPV 상대오차 < 1e-12 |
| 모든 격자점 +1bp 시나리오 vs QuantLib `ZeroSpreadedTermStructure` 1bp | 상대오차 < 1e-10 |
| Σ key rate delta vs 평행 1bp | −8,252.07 대 −8,252.41 (차이 = 2차 항) |
| 10bp 중심 차분(템플릿) → 1bp 환산 vs 1bp 전진 차분 | 상대오차 < 2e-3 |
| cross gamma vs 두 점 동시 이동 직접 계산 | 1e-6 이내 |
| `update(d)` 후 커브 vs `ImpliedTermStructure(초기 커브, d)` | 1e-12 이내 (theta 경로) |
| `TodaysMarket`은 다른 날짜 시장·평가일·시세 변경과 무관 | 기준일·할인계수 불변 (테스트) |

### 2.3 다음 단계
1. **데이터 연결**: `market-data` 레포가 만든 DuckDB를 읽는 `DuckDBLoader` (키는 MarketDatum 규칙).
2. `ParSensitivityAnalysis`: 격자 민감도 → 국채 par 민감도(헷지 수량).
3. 주식 줄기: `EquitySpot`·`DividendYield`·`EquityVolatility` 격자, 스마일 동학(sticky strike/moneyness, SSR), `EquityOption`.
   여기서 그릭 수정 규칙(템플릿, 동학, 사후 보정 계산기)을 실험한다.
4. KRW 국채·IRS, USD SOFR 커브와 `Swap`·변동 레그(`FloatingLegBuilder`), `Market.index`.
5. PCA 시나리오(`configs/estimated/`) → 헷지 백테스트·P&L 귀속 → 오토콜·LV.
