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
> 시장 객체를 규칙에 따라 흔들거나 시간을 움직여 위험을 본다.**

QuantLib의 부품을 쓰고, ORE의 구조(QuantExt / OREData / OREAnalytics)와 정신을 파이썬 규모로 가볍게 구현한다.
- **정신**: (1) 시장과 계약을 설정·시세로부터 빌더가 객체로 만든다 (2) 하나의 시장 객체 위에서 모든 계약을 정합적으로 평가한다
  (3) 같은 규격의 시장을 규칙에 따라 흔들거나 시간을 움직여 위험을 본다 (4) 입력도 출력도 표다.
- **단순화**: XML, 깊은 상속, 등록용 클래스 계층, 결과 큐브는 YAML·pydantic, 딕셔너리 등록부, 조합, pandas로 바꾼다.
  노트북에서 객체를 직접 다루는 파이썬 API가 1차 사용 방식이다(ORE처럼 앱 하나가 아니라 객체를 바로 조립).

```
시장 데이터 DB (market-data 레포 docs/design.md) ──► [data: 객체화] TodaysMarket (커브·지수·변동성, 이름으로 조회)   ┐
포지션 YAML ───────────────────────────► [data: 객체화] Portfolio (Trade → QuantLib 상품 + 엔진)        ┘
                                                  │
                                                  ├─► 1) 가격평가      시장 × 계약 → NPV, 현금흐름              (data만으로)
                                                  ├─► 2) 위험          ScenarioSimMarket × 같은 계약 → 민감도, 시나리오 손익, theta  (analytics)
                                                  └─► 3) 그 밖의 파생  커브 표, P&L explain, 헷지 백테스트 …
                                                           │
                                                           ▼
                                                       결과 표 (QuantTool DB)
```

객체가 필요한 이유는 표에 있는 것이 **관측된 숫자 몇 개**(예: par yield 13개)인 반면 가격결정에는 **함수**(아무 날짜의 할인계수, 임의 구간의 선도금리)가
필요하기 때문이다. 그 함수를 시장 관례대로 부트스트랩해 만든 것이 시장 객체다.

### 1.2 층위 (QuantLib 층위처럼)

```
0. 기반                      qle/, data/utilities/
   - QuantLib 확장 : bill BEY↔가격, RiskFactorKey                                 ← QuantExt
   - 이름·파서    : 시세 키(ids), 문자열 → Calendar·DayCounter(parsers), 등록부(registry) ← ored/utilities
1. 레시피                    data/configuration/                                       ← ored/configuration
   - CurveConfig(어떤 시세로 어떤 헬퍼·보간), Conventions(관례), TodaysMarketParameters(만들 시장 객체 목록),
     EngineData(상품 → 모델·엔진), SimMarketParameters(격자), SensitivityScenarioData(흔드는 크기·방식)
2. 시장                      data/marketdata/                                          ← ored/marketdata
   - 입력 : Loader → MarketDatum(asof, 키, 값)
   - 조립 : CurveBuilder들 (YieldCurveBuilder, IndexBuilder, EquityCurveBuilder, EquityVolBuilder), DependencyGraph
   - 시장 : Market(규격) ← MarketImpl(보관소) ← TodaysMarket(구축, asof 고정)
3. 계약                      data/portfolio/                                           ← ored/portfolio
   - 데이터 : Trade(Bond, Swap, EquityOption …), LegData
   - 조립   : LegBuilder, EngineFactory, EngineBuilder(캐시)
   - 모음   : Portfolio
4. 모델                      data/model/                                               ← ored/model
   - ModelBuilder(LocalVol, Heston), 캘리브레이션 바스켓
5. 시뮬레이션 시장            analytics/scenario/                                       ← orea/scenario, simulation
   - 데이터 : RiskFactorKey, Scenario
   - 규칙   : ScenarioGenerator(Sensitivity, Stress, Historical, PCA), 의존 규칙(StickyStrike, SSR)
   - 시장   : SimMarket(update/reset) ← ScenarioSimMarket(격자 Quote)
6. 계산                      analytics/engine/                                         ← orea/engine
   - ValuationEngine(시나리오·날짜 반복 → NPV 표), SensitivityAnalysis, ParSensitivityAnalysis, StressTest, PnlExplain
7. 결과·활용                  analytics/app/                                            ← orea/app
   - 커브 표·모양 지표, 민감도 리포트, 요인 이력(→ risk_factors 표)
```

### 1.3 무엇을 하고, 무엇을 하지 않나

| 하고 싶은 것 | 하는 곳 |
|---|---|
| 시세·요인의 추이 보기 | 데이터 DB에 SQL (`market-data` 레포 `docs/design.md`). 툴 객체가 필요 없다 |
| PCA·SSR 같은 통계 추정 | `research/`. 검증된 값만 `configs/estimated/`에 출처와 함께 |
| 과거 어느 날의 시장을 재현 (그날의 커브·가격·그릭스, 백테스트) | 그 날짜로 `TodaysMarket(d)`, 결과는 표로 |
| 과거에 일어난 변화를 오늘 시장에 적용 (historical VaR) | 오늘 시장 + 과거 요인 변화 시나리오 → `ScenarioSimMarket` |
| 가정한 충격 (민감도, 스트레스, PCA 요인) | 오늘 시장 + 생성기 → `ScenarioSimMarket` |
| 시간 경과 (theta, P&L explain) | `ScenarioSimMarket.update(다음 날)` |
| 데이터 수집·정제·저장 | 별도 프로젝트 `market-data` |
| 신용(CDS, 해저드율, XVA, 담보) | 범위 밖 |

- 툴은 **정해진 규칙과 파라미터로 계산**한다. 추정은 툴 밖에서 하고, 툴 안에서는 적용만 한다.
- 툴의 쓸모: (1) 시장 상태 모니터링(커브·서페이스·요인), (2) 포지션의 가격·민감도·시나리오 손익, (3) 다른 프로젝트에 시장 요인 시계열 제공.

### 1.4 설계 원칙

1. **시장은 규격이고, 규격·보관소·구축·변경을 나눈다.** `Market` ← `MarketImpl` ← `TodaysMarket` / `SimMarket` ← `ScenarioSimMarket`.
   가격결정 코드는 `Market` 규격만 안다.
2. **모든 시장 입력은 id가 붙은 `SimpleQuote`이고, 구조물은 그 Quote에 연결된 채로 만든다.** 그래야 시나리오가 "Quote 값 변경 → Observer 전파 → Lazy 재계산"으로 끝난다.
3. **이름으로 참조한다.** 상품·모델은 커브를 객체가 아니라 이름으로 참조하고, 평가 시점에 시장에서 받는다.
4. **레시피(configuration)와 제작자(빌더)를 분리한다.** 같은 군은 같은 빌더, 대상별 차이는 설정.
5. **구축 순서는 의존 그래프가 정한다.** 관계는 레시피의 참조에서 자동 추출.
6. **계약(무엇)과 평가 방법(어떻게)을 분리한다.** Trade는 순수 데이터, 엔진 선택은 `EngineData`, 조립은 `EngineBuilder`, 창구는 `EngineFactory`.
7. **시나리오는 데이터이고, 생성·적용·평가는 분리한다.** `ScenarioGenerator` → `Scenario` → `ScenarioSimMarket` → `ValuationEngine`.
   - 7-1. **시뮬레이션 시장은 격자 재표현을 쓴다.** 기본은 spreaded(기준 대비 이동). 요인 추정과 과거 재현도 같은 격자 좌표를 쓴다.
   - 7-2. **시간 축은 SimMarket이 맡는다.** `update(date)`가 평가일을 옮기고 그 날의 시나리오를 적용한다. TodaysMarket은 asof 고정.
8. **의존 방향은 한쪽으로.** `qle`·`data.utilities`·`data.configuration` → `data.marketdata` → `data.portfolio`·`data.model` → `analytics.scenario` → `analytics.engine` → `analytics.app` (`tests/test_layering.py`).
9. **ORE 폴더 구조를 따른다.** 라이브러리 → 하위 영역 → 파일, 최대 세 단계. 비슷한 부류는 한 파일에 묶고, 커지면 쪼갠다.
10. **표 ↔ 객체 경계를 지킨다.** 들어올 때는 데이터 DB, 나갈 때는 결과 표. 객체는 짧게 쓰고 저장하지 않는다.

| ORE (C++) | QuantTool (파이썬) |
|---|---|
| XML + `fromXML`/`toXML` 데이터 클래스 | YAML + pydantic 모델 |
| 등록용 클래스 계층, `addDefaultBuilders` | 딕셔너리 등록부 + 데코레이터 |
| 깊은 상속 (평가 방법 × 자산군) | 규격만 상속, 나머지는 조합 |
| `CachingEngineBuilder` 템플릿 | dict 캐시 |
| 모든 조회에 configuration 인자 | 시장 구성 하나 |
| 전역 `InstrumentConventions` | 설정 객체로 전달 |
| NPV/Sensitivity cube | pandas |
| `OREApp` + `InputParameters` | 노트북에서 객체 직접 조립 (+ 필요하면 간단한 `run` 함수) |

### 1.5 프로젝트 구조

✓ = 구현됨, 나머지는 예정.

```
quant-tool/
├── configs/                               [값: ORE 입력 파일에 해당]
│   ├── conventions/rates.yaml ✓           Conventions (equity.yaml 예정)
│   ├── market/
│   │   ├── todaysmarket.yaml ✓            TodaysMarketParameters
│   │   ├── curves/ust.yaml ✓              CurveConfig (krw_ktb, usd_sofr, krw_irs, spx_fwd 예정)
│   │   ├── indices/                       cd91.yaml, sofr.yaml
│   │   └── vols/                          spx.yaml
│   ├── pricing/engines.yaml ✓             EngineData (models.yaml 예정)
│   ├── scenario/simmarket.yaml ✓          ScenarioSimMarketParameters
│   ├── scenario/sensitivity.yaml ✓        SensitivityScenarioData (stress.yaml 예정)
│   └── estimated/                         pca_krw.yaml, ssr_spx.yaml (값 + 출처, 격자 좌표 기준)
├── positions/ust_book.yaml ✓              포트폴리오 (ORE portfolio.xml)
│
├── src/quanttool/
│   ├── qle/                               [QuantExt]
│   │   ├── termstructures.py ✓            bill BEY↔가격
│   │   └── scenario.py ✓                  RiskFactorKey (ORE도 QuantExt에 둔다: 설정이 키를 만들 수 있게)
│   │
│   ├── data/                              [OREData] 번역과 조립
│   │   ├── utilities/                     ids.py ✓, registry.py ✓, parsers.py ✓
│   │   ├── configuration/                 curveconfig.py ✓, conventions.py ✓, todaysmarketparameters.py ✓,
│   │   │                                  enginedata.py ✓, simmarketparameters.py ✓(+ SensitivityScenarioData), load_config ✓
│   │   ├── marketdata/                    loader.py ✓(Loader, InMemoryLoader, UstParCsvLoader, MarketDatum, QuoteStore; DuckDBLoader 예정),
│   │   │                                  market.py ✓(Market, MarketImpl, MarketBuilder), todaysmarket.py ✓,
│   │   │                                  yieldcurve.py ✓(YieldCurveBuilder; 스왑 구간·IndexBuilder 예정),
│   │   │                                  equity.py(EquityCurveBuilder, EquityVolBuilder), dependencygraph.py ✓, diagnostics.py ✓
│   │   ├── portfolio/                     trade.py ✓(Trade, InstrumentWrapper), legdata.py(LegData, LegBuilder),
│   │   │                                  bond.py ✓, swap.py, equityoption.py, portfolio.py ✓,
│   │   │                                  enginefactory.py ✓(EngineFactory, EngineBuilder + 키별 캐시),
│   │   │                                  builders/bond.py ✓, builders/swap.py, builders/vanillaoption.py
│   │   └── model/                         modelbuilder.py(LocalVolBuilder, HestonBuilder)
│   │
│   └── analytics/                         [OREAnalytics] 활용
│       ├── scenario/                      scenario.py ✓(Scenario), simmarket.py ✓(SimMarket, ScenarioSimMarket),
│       │                                  sensitivityscenariogenerator.py ✓(ScenarioGenerator, SensitivityScenarioGenerator),
│       │                                  stressscenariogenerator.py, historicalscenariogenerator.py, pcascenariogenerator.py,
│       │                                  rules.py(StickyStrike, SSR)
│       ├── engine/                        valuationengine.py ✓(ValuationEngine, NPVCube), sensitivityanalysis.py ✓(SensitivityAnalysis,
│       │                                  SensitivityCube), parsensitivityanalysis.py, stresstest.py, pnlexplain.py
│       └── app/                           marketmonitor.py ✓, factorhistory.py
│
├── notebooks/                             tutorial/ ✓ 00~05 (흐름 따라가기), 01_ust_curve ✓ (시장 해석)
├── research/                              PCA·SSR 추정 → 검증 후 configs/estimated/
├── tests/ ✓                               src와 같은 구조. QuantLib 직접 계산·해석해와 비교 (ORE ExpectedOutput 역할)
├── scripts/fetch_references.sh ✓          references/ 클론
├── docs/                                  architecture.md
└── references/                            (gitignore) QuantLib-SWIG, ORE Engine, ORE-SWIG 원본
```

민감도 표(key rate·평행 DV01)는 ORE처럼 `SensitivityCube`의 메소드다. 별도 리포트 모듈은 두지 않는다.

이름 규칙: `configs/`는 값, `data/configuration/`은 그 값을 읽는 코드. 데이터 수집·적재는 별도 레포 `market-data`가 맡는다.

### 1.6 클래스 설계

#### 상속
```
Market (규격)                                         ored/marketdata/market.hpp
 └ MarketImpl (보관소)                                 marketimpl.hpp
    ├ TodaysMarket (구축, asof 고정)                   todaysmarket.hpp
    └ SimMarket (update, reset)                        orea/simulation/simmarket.hpp
       └ ScenarioSimMarket (격자 Quote, 생성기)        orea/scenario/scenariosimmarket.hpp
Loader ← InMemoryLoader ✓, UstParCsvLoader ✓, DuckDBLoader  ored/marketdata/loader.hpp
MarketBuilder ← YieldCurveBuilder ✓, IndexBuilder, EquityCurveBuilder, EquityVolBuilder
Trade ← Bond, Swap, EquityOption, EquityDigital, Autocallable                ored/portfolio/trade.hpp
LegBuilder ← FixedLegBuilder, FloatingLegBuilder                             ored/portfolio/legbuilders.hpp
EngineBuilder(키별 캐시 포함) ← DiscountingBondEngineBuilder ✓, DiscountingSwapEngineBuilder,
                AnalyticEuropeanEngineBuilder, ReplicationDigitalEngineBuilder, LocalVolMCEngineBuilder
ModelBuilder ← LocalVolBuilder, HestonBuilder
ScenarioGenerator ← SensitivityScenarioGenerator ✓, StressScenarioGenerator, HistoricalScenarioGenerator, PcaScenarioGenerator(자체)
```

#### 구성
```
TodaysMarket            asof, TodaysMarketParameters, CurveConfigs, Conventions, Loader → (MarketImpl 보관소) 이름 → RelinkableHandle
EngineFactory           EngineData, Market, Conventions, 등록된 EngineBuilder (LegBuilder 예정)
EngineBuilder           (model, engine, trade_types), Market(팩토리가 건넴), 엔진 캐시
Trade                   계약 데이터 / build 후 InstrumentWrapper(QuantLib Instrument, 승수), legs
Portfolio               Trade들
ScenarioSimMarket       초기 Market, ScenarioSimMarketParameters, sim_data(RiskFactorKey → SimpleQuote), 격자 커브 Handle,
                        spreaded면 기준 커브 RelinkableHandle(날짜 이동 시 ImpliedTermStructure로 굴림), ScenarioGenerator
Scenario                label, RiskFactorKey → 이동량(shifts)
ValuationEngine         asof, 날짜 목록, SimMarket → NPVCube(기준 NPV, 시나리오[·날짜] × 거래 NPV)
SensitivityAnalysis     Portfolio, 초기 Market, Config(EngineData·ScenarioSimMarketParameters·SensitivityScenarioData) → SensitivityCube
```

#### 핵심 시그니처
구현된 것은 실제 코드 그대로, `# 예정`은 아직 없다.
```python
class Market(ABC):                                    # data/marketdata/market.py
    asof: date
    def quote(self, quote_id: str) -> ql.QuoteHandle: ...
    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def discount_curve(self, ccy: str) -> ql.YieldTermStructureHandle: ...   # 예정
    def index(self, name: str) -> ql.Index: ...                              # 예정 (지금은 NotImplementedError)
    def equity_spot(self, name: str) -> ql.QuoteHandle: ...                  # 예정
    def dividend_curve(self, name: str) -> ql.YieldTermStructureHandle: ...  # 예정
    def equity_vol(self, name: str) -> ql.BlackVolTermStructureHandle: ...   # 예정
    def active(self) -> ContextManager: ...           # evaluationDate = 이 시장의 날짜, 끝나면 복원

class MarketImpl(Market):                             # 보관소: 종류별 이름 → Handle
    def __init__(self, asof: date, quotes: QuoteStore | None = None): ...

class TodaysMarket(MarketImpl):                       # data/marketdata/todaysmarket.py
    def __init__(self, asof: date, params: TodaysMarketParameters, loader: Loader,
                 curve_configs: Mapping[str, YieldCurveConfig], conventions: Mapping[str, RateConventions],
                 preserve_quote_linkage: bool = False): ...    # False면 구축 직후 커브를 freeze (ORE 기본)
    @classmethod
    def from_config(cls, asof: date, cfg: Config, loader: Loader, preserve_quote_linkage: bool = False): ...
    def curve_helpers(self, name: str) -> list[HelperInfo]: ...

class SimMarket(MarketImpl):                          # analytics/scenario/simmarket.py
    date: date                                        # 현재 시뮬레이션 날짜 (active()가 이 날짜를 씀)
    scenario_generator: ScenarioGenerator | None
    scenario: Scenario | None                         # 지금 적용된 시나리오 (None = 기준)
    def update(self, d: date) -> None: ...            # 평가일 = d, 기준 커브 roll, 생성기의 다음 시나리오 적용
    def reset(self) -> None: ...                      # 날짜 asof, 기준 시나리오

class ScenarioSimMarket(SimMarket):
    def __init__(self, init_market: Market, params: ScenarioSimMarketParameters, spreaded: bool | None = None): ...
    #   spreaded=None이면 simmarket.yaml의 커브별 spreaded 값
    base_zero: dict[RiskFactorKey, float]             # 초기 커브의 격자점 제로금리
    base_values: dict[RiskFactorKey, float]           # 격자 Quote 기준값 (spreaded 0, 절대는 제로금리)
    def apply_scenario(self, s: Scenario) -> None: ...  # 기준값 + 이동량, 누적되지 않음
    def base_reconciliation(self, portfolio: Portfolio, cfg: Config) -> pd.DataFrame: ...

class Trade(BaseModel, ABC):                          # 계약 데이터 (pydantic), data/portfolio/trade.py
    id: str
    trade_type: str
    def build(self, factory: EngineFactory) -> None: ...
    def npv(self) -> float: ...

class EngineFactory:                                  # data/portfolio/enginefactory.py
    def __init__(self, engine_data: EngineData, market: Market, conventions: Mapping[str, RateConventions]): ...
    @classmethod
    def from_config(cls, cfg: Config, market: Market) -> EngineFactory: ...
    def builder(self, trade_type: str) -> EngineBuilder: ...   # (model, engine)이 engines.yaml과 다르면 KeyError
    def conventions(self, name: str) -> RateConventions: ...
    def leg_builder(self, leg_type: str) -> LegBuilder: ...    # 예정

class EngineBuilder(ABC):
    model: ClassVar[str]; engine_name: ClassVar[str]; trade_types: ClassVar[frozenset[str]]
    def engine(self, *keys) -> ql.PricingEngine: ...  # 같은 키면 캐시 (ORE CachingEngineBuilder)

@dataclass(frozen=True)
class RiskFactorKey:                                  # qle/scenario.py
    kind: str                                         # "zero", "equity_spot", "dividend_yield", "equity_vol"
    name: str                                         # "UST", "SPX"
    point: tuple = ()                                 # ("5Y",), ("1Y", 1.00). ORE는 정수 인덱스

@dataclass(frozen=True)
class Scenario:                                       # analytics/scenario/scenario.py
    label: tuple | str
    shifts: dict[RiskFactorKey, float]                # 기준 대비 이동량

class ScenarioGenerator(ABC):                         # analytics/scenario/sensitivityscenariogenerator.py
    def next(self, d: date) -> Scenario: ...          # d가 이전 날짜 이하이면 다음 표본(경로)으로
    def reset(self) -> None: ...
    def samples(self) -> int: ...

class ValuationEngine:                                # analytics/engine/valuationengine.py
    def __init__(self, asof: date, dates: Sequence[date], sim_market: SimMarket): ...
    def build_cube(self, portfolio: Portfolio) -> NPVCube: ...   # NPVCube.base, .npv, .pnl, .total_pnl()

class SensitivityAnalysis:                            # analytics/engine/sensitivityanalysis.py
    def __init__(self, portfolio: Portfolio, market: Market, cfg: Config,
                 sim_params: ScenarioSimMarketParameters | None = None,
                 sensi_data: SensitivityScenarioData | None = None): ...
    def generate_sensitivities(self) -> None: ...
    def sensi_cube(self) -> SensitivityCube: ...      # .key_rate_dv01(curve), .parallel_dv01(curve)
```

#### 불변 조건
- 모든 시장 입력은 시장의 `SimpleQuote`이며 키는 `data/utilities/ids.py` 규칙(= 데이터 플랫폼의 `series_id`)을 따른다.
- 시나리오에서 흔드는 대상은 `ScenarioSimMarketParameters`의 격자점이다.
- 시뮬레이션 시장의 기준 NPV는 초기 시장 NPV와 허용 오차 이내로 일치해야 한다 (spreaded는 사실상 0).
- 요인 로딩·과거 시나리오는 격자 좌표(`RiskFactorKey`)로 정의한다.
- 가격결정·시나리오 코드는 `Market` 규격 메소드만 쓴다.
- Trade는 엔진·모델을 모른다. 엔진 선택은 `EngineData`(`engines.yaml`).
- `ValuationEngine`은 포트폴리오를 시나리오마다 재조립하지 않는다.
- `TodaysMarket`은 만들어진 뒤 바뀌지 않는다. 바꾸는 것은 `SimMarket`만.
- 날짜가 다른 시장은 각자의 `active()` 안에서 순차적으로만 평가한다.

### 1.7 사용 흐름

예시 상황: **미 국채 포트폴리오의 오늘 가격, key rate DV01, 다음 날 theta.** 0.2 호출 흐름과 같은 순서다.
아래 코드는 `DuckDBLoader`(예정)만 빼고 지금 그대로 돌아간다. 합성 샘플로 같은 흐름을 실행하는 것이 `notebooks/tutorial/` 01~05다.

**① 입력: 무엇이 어디에 있나**

| 위치 | 읽는 클래스 | 내용 |
|---|---|---|
| `market.duckdb` 뷰 `v_quote` (데이터 플랫폼) | `DuckDBLoader` → `MarketDatum` | `2026-10-23 BOND/YIELD/USD/UST/PAR/10Y 0.0398` |
| `configs/conventions/rates.yaml` | `Conventions` | `UST: {calendar: UnitedStates.GovernmentBond, day_count: ActualActual.Bond, settlement_days: 1, frequency: Semiannual, …}` |
| `configs/market/curves/ust.yaml` | `YieldCurveConfig` | 세그먼트: bill(1M~1Y) `ZeroCouponBill`, 쿠폰채(2Y~30Y) `FixedRateBond`; 시세 키 접두어; 보간 `LogCubic(Discount)` |
| `configs/market/todaysmarket.yaml` | `TodaysMarketParameters` | `yield_curves: [UST]` (만들 시장 객체; `discount_curves: {USD: UST}` 예정) |
| `configs/pricing/engines.yaml` | `EngineData` | `Bond: {model: DiscountedCashflows, engine: DiscountingBondEngine}` |
| `positions/ust_book.yaml` | `Portfolio` → `Bond` | `{id: UST_10Y, trade_type: Bond, notional: 1e7, coupon: 0.04125, issue: 2026-08-15, maturity: 2036-08-15, conventions: UST, discount: UST}` |
| `configs/scenario/simmarket.yaml` | `ScenarioSimMarketParameters` | `UST: {tenors: [1M, …, 30Y], interpolation: Linear(Zero), spreaded: true, roll_down: ForwardForward}` |
| `configs/scenario/sensitivity.yaml` | `SensitivityScenarioData` | `key_rate_bp: 1.0, parallel_bp: 1.0` (par 변환 상품은 `ParSensitivityAnalysis`와 함께 예정) |

**② 코드**

```python
from datetime import date
from quanttool.data.configuration import load_config                       # data/configuration/__init__.py
from quanttool.data.marketdata import DuckDBLoader, TodaysMarket            # data/marketdata/loader.py(DuckDBLoader 예정), todaysmarket.py
from quanttool.data.portfolio import EngineFactory, Portfolio                # data/portfolio/enginefactory.py, portfolio.py
from quanttool.analytics.scenario import ScenarioSimMarket                  # analytics/scenario/simmarket.py
from quanttool.analytics.engine import SensitivityAnalysis                  # analytics/engine/sensitivityanalysis.py
from quanttool.analytics.app import curve_table                             # analytics/app/marketmonitor.py

asof = date(2026, 10, 23)

# 1) 레시피 읽기: configs/ YAML → pydantic 객체 (ORE fromFile 대응)
cfg = load_config("configs")
#    cfg.conventions["UST"]      : Conventions 항목 (calendar, day_count, …)
#    cfg.curve_configs["UST"]    : YieldCurveConfig (segments, interpolation)
#    cfg.todaysmarket            : TodaysMarketParameters
#    cfg.engine_data["Bond"]     : EngineData 항목 (model, engine)
#    cfg.simmarket, cfg.sensitivity

# 2) 시세 읽기: DB → MarketDatum 목록 (ORE CSVLoader 대응)
loader = DuckDBLoader("~/data/market.duckdb")
#    loader.load(asof) → [MarketDatum(asof, "BOND/YIELD/USD/UST/PAR/1M", 0.0402), …]

# 3) 시장 조립: 레시피 + 시세 → TodaysMarket (asof 고정, 이후 불변)
market = TodaysMarket.from_config(asof, cfg, loader)
#    = TodaysMarket(asof, cfg.todaysmarket, loader, cfg.curve_configs, cfg.conventions)
#    내부 (data/marketdata/todaysmarket.py):
#      DependencyGraph로 순서 결정 (스왑 커브가 할인 커브에 의존하면 할인 커브 먼저)
#      BUILDERS["YieldCurve"] = YieldCurveBuilder (data/marketdata/yieldcurve.py), 평가일 = asof로 두고 실행
#        시세 키 → SimpleQuote → 세그먼트별 헬퍼 (bill: BondHelper(ZeroCouponBond, 가격=qle.bill_price(y)),
#                                            쿠폰채: BondHelper(FixedRateBond, 가격=DerivedQuote(y)))
#        → ql.PiecewiseLogCubicDiscount(asof, helpers, Act365) → freeze() → RelinkableHandle
#      MarketImpl 보관소에 등록: yield_curve("UST")
curve_table(market, "UST", cfg)               # 할인계수, 제로, 1Y 선도, par (analytics/app/marketmonitor.py)

# 4) 포트폴리오 조립: 계약 데이터 → QuantLib 상품 + 엔진
book = Portfolio.load("positions/ust_book.yaml")          # Trade 데이터 (pydantic), 아직 QuantLib 객체 없음
factory = EngineFactory.from_config(cfg, market)          # = EngineFactory(cfg.engine_data, market, cfg.conventions)
with market.active():                                     # evaluationDate = asof
    book.build(factory)
    #  Bond.build (data/portfolio/bond.py):
    #    ql.Schedule(issue, maturity, 6M, …) → ql.FixedRateBond(…)
    #    builder = factory.builder("Bond")              → DiscountingBondEngineBuilder (data/portfolio/builders/bond.py)
    #    bond.setPricingEngine(builder.engine("UST"))   → ql.DiscountingBondEngine(market.yield_curve("UST")), 캐시
    #    self.instrument = InstrumentWrapper(bond, multiplier=notional/100)
    book.npvs()                                           # 거래별 NPV (pandas)

# 5) 민감도: 시뮬레이션 시장에서 흔들고 반복 평가 (ORE SensitivityAnalysis와 같은 순서)
sa = SensitivityAnalysis(book, market, cfg)               # sim_params·sensi_data 기본값 = cfg.simmarket, cfg.sensitivity
sa.generate_sensitivities()
#  내부 (analytics/engine/sensitivityanalysis.py):
#    a) sim = ScenarioSimMarket(market, cfg.simmarket)          # spreaded (simmarket.yaml)
#         market.yield_curve("UST")를 1M…30Y에서 샘플 → 격자 SimpleQuote(이동량 0)
#         커브 = PiecewiseZeroSpreadedTermStructure(원래 커브, 격자 Quote) → 기준 상태에서 원래 커브와 같음
#    b) gen = SensitivityScenarioGenerator(cfg.simmarket, cfg.sensitivity)
#         [기준, UST 1M +1bp, …, UST 30Y +1bp, UST 평행 +1bp]
#    c) sim.scenario_generator = gen
#    d) book.build(EngineFactory.from_config(cfg, sim))     # 같은 계약을 시뮬레이션 시장에 다시 연결
#    e) ValuationEngine(asof, [asof], sim).build_cube(book) # 시나리오마다 sim.update(asof) → npvs() → 표 한 행
#    f) SensitivityCube(cube, sensi_data): (흔든 NPV − 기준 NPV) / shift → 델타
sa.sensi_cube().key_rate_dv01("UST")                       # 만기 × 거래 표
sa.sensi_cube().parallel_dv01("UST")

# 6) 시간 경과: 시장 그대로, 평가일만 하루 이동 → theta
sim = ScenarioSimMarket(market, cfg.simmarket)
with sim.active():
    book.build(EngineFactory.from_config(cfg, sim))
    base = book.npvs()
sim.update(date(2026, 10, 26))                              # 다음 영업일, 생성기 없음 → 기준 시나리오, 평가일 이동
with sim.active():                                          # 기준 커브는 ForwardForward로 굴러 있음
    theta = book.npvs() - base
sim.reset()

# 7) 날짜별 커브 이력: 날짜마다 TodaysMarket을 만들고 결과만 표로 (객체는 버림)
history = {d: curve_table(TodaysMarket.from_config(d, cfg, loader), "UST", cfg)["zero_cc"]
           for d in loader.dates()}
```

**③ 정리**: 사용자가 만지는 것은 `configs/`, `positions/`, 데이터 DB뿐이다. ①~④는 `data`, ⑤~⑥은 `analytics`다.
같은 `Bond.build`가 ④에서는 `TodaysMarket`에, ⑤-d·⑥에서는 `ScenarioSimMarket`에 연결된다.

#### 이후 예정 흐름

- **IRS 포지션의 PCA 2×2 시나리오**: `configs/estimated/pca_krw.yaml`(격자 기준 로딩 + 출처) → `PcaScenarioGenerator`가
  `values[key] = Σ 요인 크기 × 로딩`으로 시나리오를 만들고, 나머지는 민감도와 같은 경로. `Swap.build`는 `LegBuilder`로 레그를 만들고
  변동 레그는 `market.index("CD91")`을 쓴다(지수는 시뮬레이션 시장 커브로 예측, fixing은 건드리지 않음).
- **주식 디지털 옵션의 SSR 반영 델타**: 시뮬레이션 시장이 SPX 서페이스를 만기 × moneyness 격자 vol Quote로 재표현하고(재피팅 없음),
  생성기가 spot 이동에 SSR 규칙으로 계산한 격자 vol 이동을 같은 Scenario에 담는다. 분석적 BS는 skew 항을 놓치므로
  ($D(K) = D_{\text{BS}}(K) - \text{Vega}_{\text{BS}}(K)\,\partial\sigma/\partial K$) 디지털은 `engines.yaml`에서 복제 방식이나 LV로 지정한다.

#### 사용성 비교
| | QuantLib | ORE | QuantTool |
|---|---|---|---|
| 시장 | Quote·커브·Process를 직접 조립 | todaysmarket.xml + curveconfig.xml → TodaysMarket | YAML → `TodaysMarket` |
| 계약 | Instrument 직접 생성 | portfolio.xml → Trade | positions YAML → Trade |
| 엔진 | `setPricingEngine` 직접 | pricingengine.xml → EngineFactory | engines.yaml → EngineFactory |
| 시나리오 | Quote를 직접 setValue | simulation.xml + sensitivity.xml → ScenarioSimMarket | simmarket.yaml + sensitivity.yaml → ScenarioSimMarket |
| 실행 | 스크립트 | InputParameters → OREApp.run | 노트북에서 객체 조립 |

### 1.8 설정 파일 예시
```yaml
# configs/market/curves/ust.yaml (구현됨)
name: UST
type: YieldCurve
currency: USD
conventions: UST
segments:
  - {type: ZeroCouponBill, quote_family: UST, quote_field: PAR, tenors: [1M, 2M, 3M, 4M, 6M, 1Y]}
  - {type: FixedRateBond,  quote_family: UST, quote_field: PAR, tenors: [2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y]}
interpolation: LogCubic(Discount)

# configs/scenario/simmarket.yaml (구현됨)
UST:
  kind: zero
  tenors: [1M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 12Y, 15Y, 20Y, 25Y, 30Y]
  interpolation: Linear(Zero)
  extrapolation: flat_zero
  spreaded: true
  roll_down: ForwardForward

# configs/pricing/engines.yaml (EngineData; Bond만 구현됨)
Bond:          {model: DiscountedCashflows, engine: DiscountingBondEngine}
Swap:          {model: DiscountedCashflows, engine: DiscountingSwapEngine}
EquityOption:  {model: BlackScholes, engine: AnalyticEuropeanEngine}
EquityDigital: {model: BlackScholes, engine: CallSpreadReplication}
Autocallable:  {model: LocalVol,     engine: MonteCarlo, params: {paths: 100000}}
```

---

## 2. 진행

### 2.1 결정 사항과 미결정

| 항목 | 내용 | 현재 방향 |
|---|---|---|
| 구조·이름 | 자체 이름 vs ORE 이름 | **ORE 구조·이름을 따른다** (1.5, 1.6, 구현됨) |
| 데이터 | 이 레포에서 수집 vs 별도 프로젝트 | **별도 프로젝트 `market-data` + DuckDB** (`market-data` 레포 `docs/design.md`) |
| 범위 | 신용 포함 여부 | **신용(CDS, 해저드율, XVA, 담보) 제외** |
| 시나리오 시장 방식 | 원래 시세 bump vs ORE식 격자 재표현 | **격자 재표현** (PCA·과거 재현과 좌표 일치, 속도, vol 지역성) |
| 격자 커브 모드 | 절대 vs spreaded(ORE `SpreadedDiscountCurve`) | **spreaded 기본**(구현됨). 기준 대사 오차 ≈1e-16(절대 모드는 합성 샘플 기준 최대 5.1e-4, 30Y). 절대는 `spreaded=False` |
| 커브 기준일 | TodaysMarket: 평가일 따라 이동 vs asof 고정(ORE) | **asof 고정 + freeze**(구현됨, `preserve_quote_linkage=True`면 시세 연결 유지). 시간 이동은 SimMarket이 맡는다 |
| 시간 축 | 고정 기준일 시나리오만 vs 날짜 이동 | `SimMarket.update(date)`(구현됨, ForwardForward roll)로 theta. P&L explain은 예정 |
| 전역 평가일 | 날짜 다른 시장 동시 평가 시 조용한 오류 | 시장마다 `active()`, 순차 평가 |
| 엔진 요청 방식 | `factory.engine_for(trade)` vs `factory.builder(type).engine(키)`(ORE) | ORE 방식(구현됨) |
| 관례 보관 | ORE 전역 `InstrumentConventions` vs 설정 객체 전달 | 설정 객체 전달 (전역 상태를 늘리지 않음) |
| Index fixing 전역 공유 | 시나리오가 기준 시장 fixing을 오염 | fixing은 구축 시 1회 로드, 시나리오에서 수정 금지 |
| IV 서페이스 흔들기 | 호가 bump 시 재피팅이 변화를 번지게 함, 느림 | 격자 재표현으로 해결 |
| 격자 바깥 | 외삽 형태가 결과에 영향 | 평탄 제로. QuantLib 1.44 `PiecewiseZeroSpreadedTermStructure`는 Quote 변경 시 외삽 설정이 풀려, 마지막 격자 Quote에 묶은 100Y 끝점으로 처리 |
| 민감도 단위 | 격자 민감도는 제로금리·격자 vol 기준 | `ParSensitivityAnalysis`로 시장 상품 기준 변환 |
| UST par 헬퍼 관례 | par yield = 쿠폰인 가상 채권 가격이 정확히 100이어야 함 | 명목 만기 정규 일정 + Unadjusted 지급. bill(≤1Y)은 BEY → 할인채 가격. 쿠폰은 구축 시점 고정, 수익률 변화는 DerivedQuote로 가격에 전달 |
| 모델 재캘리브레이션 비용 | 시나리오마다 자동 재캘리브레이션 | "모델 고정" 선택지 |
| 단위·형식 | bp/소수, 수익률/가격 혼동 | 데이터 DB는 항상 소수, 키에 유형·단위 |
| 듀얼 커브 (KRW) | CD 프로젝션 vs 할인 커브 | 구조는 지원, 데이터 확보 시 활성화 |

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
- 처음이면 `notebooks/tutorial/` 00~05를 순서대로 실행하며 코드 위치를 따라간다.
- `tests/fixtures/ust_par_sample.csv`는 재무부 CSV와 형식만 같은 합성 샘플이다. 실제 데이터는 아직 연결 전이다.

완료
- 첫 줄기 (UST 커브 → 국채 → key rate DV01), 노트북 `01_ust_curve`.
- ORE 구조로 재구성: `qle` / `data`(utilities, configuration, marketdata, portfolio) / `analytics`(scenario, engine, app).
  `Market`/`MarketImpl`/`TodaysMarket`(asof 고정, freeze), `SimMarket`/`ScenarioSimMarket`(`update`, spreaded),
  `EngineFactory.builder`, `ValuationEngine`/`NPVCube`, `SensitivityAnalysis`/`SensitivityCube`.
- 튜토리얼 노트북 6개(00~05).
- 테스트 94개. 완료 기준 (합성 샘플 기준):

| 기준 | 결과 |
|---|---|
| 헬퍼 재가격 오차 < 0.01bp | 약 1e-9bp |
| QuantLib 직접 조립 채권과 NPV 일치 | 상대오차 1e-12 이내 |
| 시뮬레이션 시장 기준 NPV ≈ 초기 시장 NPV (spreaded) | 상대오차 < 1e-12 (실측 ≈4e-16). 절대 모드는 최대 5.1e-4 (30Y) |
| Σ key rate DV01 = 평행 DV01 | −8,252.07 대 −8,252.41 (한쪽 차분의 2차 항만큼 차이) |
| 평행 DV01 vs QuantLib 직접 1bp 이동 (`ZeroSpreadedTermStructure`) | 1e-10 이내 |
| `update(d)` 후 커브 vs `ImpliedTermStructure(초기 커브, d)` | 1e-12 이내 (theta 경로) |
| `TodaysMarket`은 다른 날짜 시장·평가일 변경과 무관 | 기준일·할인계수 불변 (테스트) |

### 2.3 다음 단계
1. **데이터 플랫폼** (`market-data` 레포 `docs/design.md` 9장): `market-data` 레포, DuckDB 스키마, FRED 수집기 → QuantTool `DuckDBLoader`.
2. `ParSensitivityAnalysis`: 격자 민감도 → 국채·스왑 par 민감도(헷지 수량).
3. KRW 국채·IRS, USD SOFR 커브와 `Swap`·`LegBuilder`, `Market.discount_curve`·`index`.
4. `factorhistory`: 날짜별 격자값 → `risk_factors` 표. 옵션 체인 일별 적재 시작.
5. PCA 시나리오 → 주식 줄기 → P&L explain·과거 재현 → 오토콜·LV.
