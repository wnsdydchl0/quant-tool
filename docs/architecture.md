# QuantTool 아키텍처

이 문서 하나가 설계의 기준이다.
- **0장 레퍼런스**: QuantLib과 ORE의 구조, ORE를 실제로 쓰는 모습.
- **1장 패키지의 구조**: QuantTool이 무엇이고 어떤 층으로 되어 있는지, 폴더·클래스 설계, 실제 사용 흐름.
- **2장 진행**: 결정 사항, 현황, 다음 단계.
- 데이터 수집·저장은 별도 프로젝트로 분리한다: `docs/data_platform.md`.

> **상태(2026-10-28)**: 1장의 구조와 클래스 이름은 ORE를 따르도록 고친 **제안**이다(피드백 대기).
> 현재 코드는 아직 이전 이름(`Snapshot`, `ScenarioMarket` 등)이며, 대응은 1.8 표를 본다.
> 범위에서 신용(CDS, 해저드율, XVA, 담보) 기능은 제외한다.

---

## 0. 레퍼런스

### 0.1 QuantLib: 한 상품을 정확히 평가하는 부품 상자

QuantLib은 **시장 상태를 표현하는 객체와 계약을 표현하는 객체를 만들고, 둘을 엔진으로 이어 가격을 내는 부품**을 층별로 제공한다.
조립은 사용자가 직접 한다.

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

층을 잇는 장치 세 가지가 QuantLib 설계의 핵심이다.
- **Handle**: 객체가 아니라 객체가 놓인 "자리"를 가리킨다. `RelinkableHandle.linkTo`로 자리의 내용을 통째로 바꾸면,
  그 자리를 쓰는 모든 상품에 한 번에 적용된다.
- **Observer**: Quote → 커브 → 엔진 → 상품으로 변경 알림이 이어진다. 바뀐 것에 의존하는 것만 "낡음" 표시가 된다.
- **LazyObject**: 실제로 값을 물을 때만 다시 계산한다.

그래서 시장 입력을 `SimpleQuote`로 두고 구조물을 그 Quote에 연결해 만들면, "Quote 값 변경 → 재평가 → 원복"만으로 민감도와 시나리오가 끝난다.
엔진은 **생성될 때 시장 재료**(커브·Process 핸들)를 쥐고, **계산할 때 계약 조건**(arguments)을 받는다.

주의할 전역 상태: `Settings.evaluationDate`는 하나뿐이라 날짜가 다른 시장을 동시에 평가할 수 없다. Index fixing도 지수 이름으로 전역 공유된다.

학습 자료
- A QuantLib Guide (https://www.quantlibguide.com/) — Library infrastructure 파트 정독, 나머지는 사전처럼.
- Implementing QuantLib (Ballabio) — 설계 이유.
- Context7: `/lballabio/quantlib`, `/lballabio/quantlib-swig`(파이썬 예제가 더 많음).
- 직접 해 보기: `notebooks/tutorial/00_quantlib_basics.ipynb`

### 0.2 ORE: 데이터로부터 시장과 계약을 조립해, 포트폴리오를 정합적으로 평가하고 흔드는 시스템

근거: ORE 원본 `references/Engine`(GitHub `OpenSourceRisk/Engine`), 설계 문서 `Docs/Design/ore_design.tex`
(= https://rkapl123.github.io/ore_design.pdf), 파이썬 바인딩 `references/ORE-SWIG`. Context7에는 ORE가 없어서 원본을 직접 읽는다.

#### (1) 세 라이브러리

> "QuantLib은 개별 상품과 그 평가·분석에 초점을 두고, ORE는 (단순 합산이 아닌) 포트폴리오 분석을 목표로 한다." — 설계 문서 Introduction

| 라이브러리 | 역할 | QuantLib과의 관계 |
|---|---|---|
| **QuantExt** | QuantLib 확장: 상품, 엔진, 커브, 모델. QuantLib과 **같은 폴더·클래스 구조** | QuantLib에 없는 부품을 같은 규격으로 보탠다. QuantLib 버그는 원본을 고치지 않고 해당 클래스를 복사해 고친다 |
| **OREData** | **번역과 조립.** 외부 표현(XML 설정, 시세 파일)을 QuantLib 객체로 번역하고, 그것으로 **Market, Portfolio, Model**을 조립 | 이것만으로 시장 구축, 커브 부트스트랩, 포트폴리오 로드, 현재가치·현금흐름 계산까지 가능 |
| **OREAnalytics** | **활용.** OREData의 세 객체를 입력으로 받아 시나리오·시뮬레이션 기반 위험 분석 | 핵심은 Market 규격을 그대로 가지면서 바꿀 수 있는 `SimMarket` |

QuantLib 층위 위에 **"조립 → 활용"** 두 단을 얹은 구조다. "Data"는 데이터를 저장한다는 뜻이 아니라 **데이터를 객체로 바꾸는 층**이라는 뜻이다.

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

#### (2) OREData의 세 객체와 Market 계층

| 객체 | 추상화하는 것 | 내용 |
|---|---|---|
| **Market** | 한 시점의 시장 상태 | 커브·지수·변동성·스팟을 이름(키)으로 조회 |
| **Portfolio** | 계약들 | Trade 데이터 → QuantLib Instrument + PricingEngine |
| **Model** | 시장의 동학 | SDE 모델과 캘리브레이션 |

| 클래스 | 역할 | 비유 | 원본 |
|---|---|---|---|
| `Market` | 가격결정 코드가 아는 **규격**. `discountCurve(ccy)`, `iborIndex(name)`, `equitySpot(name)`… 순수 가상 함수 | 메뉴판 | `OREData/ored/marketdata/market.hpp` |
| `MarketImpl` | 이름 → Handle **보관소**(map들)와 조회 구현 | 창고 | `marketimpl.hpp` |
| `TodaysMarket` | 레시피·시세로 창고를 **채우는 구축 로직**. 커브 기준일 asof 고정 | 오늘 장 본 것 | `todaysmarket.hpp` |
| `SimMarket` | 창고 내용을 **바꿀 수 있는** 시장. `update(date)`, `reset()` | 실험용 창고 | `OREAnalytics/orea/simulation/simmarket.hpp` |
| `ScenarioSimMarket` | `update`를 "생성기에서 시나리오를 받아 격자 Quote에 적용"으로 구현 | | `orea/scenario/scenariosimmarket.hpp` |

- `TodaysMarket`과 `SimMarket`이 모두 `MarketImpl`을 상속하는 이유: **창고는 같고 채우는 방식만 다르다.**
- 가격결정 코드는 `Market`만 알아서 어느 쪽에 연결되든 그대로 동작한다. 엔진 빌더도 `market_->equityVol(name)`처럼 규격 메소드만 부른다.
- `TodaysMarket`은 만들어진 뒤 바뀌지 않는 시장이다.
  - 커브 기준일이 asof로 고정된다(`ored/marketdata/yieldcurve.cpp`가 `asofDate_`를 넘김).
  - 생성자 인자 `preserveQuoteLinkage`의 기본값이 `false`라 구축 후 시세 Quote와의 연결도 끊는다(`todaysmarket.hpp`).
  - 흔드는 일은 `SimMarket`의 몫이다.

#### (3) Portfolio: 데이터 → build → 상품 + 엔진

- Trade는 먼저 **순수 데이터**로 로드되고, `build(engineFactory)`를 불러야 QuantLib 상품으로 번역되어 엔진과 시장 커브에 연결된다.
- **데이터 클래스 ↔ XML**
  - `LegData`(통화, 일정, 지급/수취)가 레그 종류별 내용(`FixedLegData`, `FloatingLegData`, …)을 담는다.
  - 모두 `fromXML`/`toXML`로 XML과 서로 변환된다. XML은 데이터 클래스를 파일로 적은 형태일 뿐이다.
  - 파이썬에서는 XML 없이 데이터 클래스를 바로 만들 수 있다(`Examples/ORE-Python/ExampleScripts/portfolio.py`).
- **LegBuilder**: `FixedLegBuilder.buildLeg(legData)` → QuantLib `Leg`(현금흐름 목록). 레그 종류별로 EngineFactory에 등록된다.
- **EngineBuilder / EngineFactory**
  - 엔진 빌더는 (model, engine, trade types)로 팩토리에 등록되고, `CachingEngineBuilder`를 상속해 **같은 키면 같은 엔진**을 돌려준다.
  - 목적은 엔진 수와 메모리를 줄이고, 계약서가 평가 방법을 모르게 하는 것이다(`ored/portfolio/enginefactory.hpp` 주석).
  - `Swap::build`(`ored/portfolio/swap.cpp`)의 순서: `engineFactory->builder("Swap")` → 레그마다 `legBuilder->buildLeg` →
    `swapBuilder->engine(ccy, …)` → `setPricingEngine` → `instrument_` 저장.

```python
# 엔진 팩토리가 없을 때 (QuantLib 직접): 상품마다 사람이 엔진과 커브를 고른다
for bond in bonds:                                            # 1000개
    bond.setPricingEngine(ql.DiscountingBondEngine(curve))    # 엔진 1000개

# ORE 방식
factory = EngineFactory(engine_data, market)                  # engine_data: "Bond → DiscountedCashflows/DiscountingBondEngine"
class Bond(Trade):
    def build(self, factory):
        ql_bond = ql.FixedRateBond(...)                       # 계약 데이터 → QuantLib 상품
        builder = factory.builder("Bond")                     # 설정에서 고른 빌더
        ql_bond.setPricingEngine(builder.engine(self.ccy, self.curve_id))  # 자기 키로 요청 → 같은 키면 캐시
```

#### (4) OREAnalytics: SimMarket 위의 분석

설계 문서(Simulation Market 절): "시장이 가정한 시나리오로 움직일 때(**고정 기준일**) 또는 **시간에 따라** 변할 때 가치가 어떻게 바뀌는지는,
포트폴리오를 그렇게 변하는 시장에 '그냥' 연결하고 재평가를 일으키면 된다."

```
SimMarket.update(d):                          # orea/simulation/simmarket.cpp
    scenario = generator.next(d)              # loadNextScenario: 그 날짜의 시나리오
    evaluationDate = scenario.asof            # updateDate (scenariosimmarket.cpp)
    apply(scenario)                           # applyScenario: 격자 Quote 변경 → Observer → 연결된 포트폴리오 "낡음"
```

| 쓰임 | 날짜 | 시나리오 |
|---|---|---|
| 민감도·스트레스 | asof 고정 | 격자점 이동 |
| 시장 시뮬레이션 | t1, t2, … 날짜 격자를 따라 이동 | 모델이 만든 시장 경로 |
| theta (우리 쓰임) | 하루 이동 | 시장 그대로 |
| P&L explain (우리 쓰임) | 다음 날 | 다음 날 실제 요인 변화 |

- **Scenario**: asof, label, `RiskFactorKey → 값`. `RiskFactorKey`는 (종류, 이름, 정수 인덱스). 경로는 시나리오의 벡터.
- **ScenarioGenerator**: 몬테카를로, 민감도(`SensitivityScenarioGenerator`), 스트레스, 과거(`HistoricalScenarioGenerator`: 과거 t → t+h 변화를 오늘에 적용).
- **ScenarioSimMarketParameters**(`simulation.xml`): 시뮬레이션 시장 구성(커브별 격자 만기, 보간, 외삽, 대상 지수).
- **SensitivityScenarioData**(`sensitivity.xml`): 어떤 커브를 어떤 만기에서 얼마나(1bp, Absolute) 어떤 방식(Forward/Central)으로 흔들지,
  그리고 par 변환에 쓸 시장 상품(OIS, IRS, …)과 관례.
- **ScenarioSimMarket의 커브**(`scenariosimmarket.cpp` `makeYieldCurve`)
  - 절대 모드: 격자 Quote = 할인계수, `InterpolatedDiscountCurve`(settlementDays 0, 평가일을 따라 이동).
  - **spreaded 모드**: 격자 Quote = 기준 커브 대비 이동, `SpreadedDiscountCurve(초기 시장 커브, …)`.
    기준 상태에서 시뮬레이션 커브가 원래 커브와 **정확히 같다**.
- **ValuationEngine::buildCube**: 표본(시나리오)마다 → 날짜마다 → `populateCube`(시장 갱신, 계산기 실행) → cube에 기록 → 끝나면 `reset`.
- **ParSensitivityAnalysis**: 제로금리 등 "raw" 민감도를 시장 상품 기준 par 민감도로 야코비안(연쇄법칙) 변환.
  raw 영역에서 계산하는 이유는 시장 점을 바꿀 때마다 재부트스트랩하지 않아 빠르기 때문이다.

#### (5) ORE를 실제로 쓰는 모습

예시 상황: **EUR 20년 스왑 하나의 오늘 가격과 금리 민감도.** 입력 파일은 `references/Engine/Examples/MinimalSetup/Input`, `Examples/MarketRisk/Input`.

**① 입력 파일: 무엇이 들어 있나**

| 파일 | 데이터 클래스 | 내용 (실제 발췌) |
|---|---|---|
| `market_20160205.txt` | `CSVLoader` → `MarketDatum` | `2016-02-05 IR_SWAP/RATE/EUR/2D/6M/10Y 0.0123` — 날짜, 스스로를 설명하는 키, 값 |
| `fixings_20160205.txt` | `Fixing` | `2016-02-02 EUR-EURIBOR-6M -0.0013` |
| `conventions.xml` | `Conventions` | `EUR-6M-SWAP-CONVENTIONS`: 고정 레그 주기·일수, 변동 지수 |
| `curveconfig.xml` | `CurveConfigurations` → `YieldCurveConfig` | `CurveId=EUR6M`, `Segments/Simple`: 어떤 시세 키(`IR_SWAP/RATE/EUR/2D/6M/*`)를 어떤 관례로, 보간 `LogLinear(Discount)` |
| `todaysmarket.xml` | `TodaysMarketParameters` | "만들 시장 객체 → 레시피": `<DiscountingCurve currency="EUR">Yield/EUR/EUR1D</DiscountingCurve>`, `<Index name="EUR-EURIBOR-6M">Yield/EUR/EUR6M</Index>` |
| `pricingengine.xml` | `EngineData` | `<Product type="Swap"><Model>DiscountedCashflows</Model><Engine>DiscountingSwapEngine</Engine>` |
| `portfolio_swap.xml` | `Portfolio` → `Swap`(`SwapData` → `LegData`×2) | `TradeType=Swap`, 고정 레그(`FixedLegData/Rates 0.021`, `ScheduleData`), 변동 레그(`FloatingLegData/Index EUR-EURIBOR-6M`) |
| `simulation.xml` | `ScenarioSimMarketParameters` | `YieldCurves/Tenors 2W,1M,…,30Y`, `Interpolation LogLinear`, 대상 `Indices` |
| `sensitivity.xml` | `SensitivityScenarioData` | `DiscountCurve ccy="EUR"`: `ShiftType Absolute`, `ShiftSize 0.0001`, `ShiftTenors …`, `ParConversion Instruments OIS,…` |
| `ore.xml` | `Parameters` | asof, 위 파일 경로들, 돌릴 분석(`npv`, `sensitivity`) |

**② 파이썬에서 실제로 쓰는 방식: 앱에 입력을 넘기고 결과를 꺼낸다** (`Examples/ORE-Python`, 바인딩 `ORE-SWIG/OREAnalytics-SWIG/SWIG/orea_app.i`)

```python
import ORE as ore                                       # pip install open-source-risk-engine

inputs = ore.InputParameters()                          # orea/app/inputparameters.hpp: 모든 입력을 담는 상자
inputs.setAsOfDate("2016-02-05")
inputs.setCurveConfigsFromFile("Input/curveconfig.xml")         # → CurveConfigurations
inputs.setConventionsFromFile("Input/conventions.xml")          # → Conventions (전역 InstrumentConventions에 등록)
inputs.setTodaysMarketParamsFromFile("Input/todaysmarket.xml")  # → TodaysMarketParameters
inputs.setPricingEngineFromFile("Input/pricingengine.xml")      # → EngineData
inputs.setPortfolioFromFile("Input/portfolio_swap.xml")         # → Portfolio (아직 데이터 상태)
inputs.insertAnalytic("NPV")
inputs.insertAnalytic("SENSITIVITY")
inputs.setSensiSimMarketParamsFromFile("Input/simulation.xml")  # → ScenarioSimMarketParameters
inputs.setSensiScenarioDataFromFile("Input/sensitivity.xml")    # → SensitivityScenarioData

app = ore.OREApp(inputs, "log.txt", 31)                 # orea/app/oreapp.hpp
app.run(market_data, fixings_data)                      # 시세·fixing 문자열 목록 (market.txt 줄들)

app.getReport("npv")                                    # 거래별 NPV 표
app.getReport("sensitivity")                            # 거래 × 리스크 요인 민감도 표
market = app.getAnalytic("NPV").getMarket()             # 조립된 TodaysMarket을 꺼내 직접 조회도 가능
market.discountCurve("EUR").discount(ore.Date(5, 2, 2026))
```

**③ `app.run()` 안에서 일어나는 일: 객체 단위로 풀면** (C++ 시그니처를 파이썬처럼 옮김)

```python
# 1) 시세 읽기 — ored/marketdata/csvloader.hpp
loader = CSVLoader()
loader.fromFiles("market_20160205.txt", "fixings_20160205.txt")
#    loader.get("IR_SWAP/RATE/EUR/2D/6M/10Y", asof) → MarketDatum
#    MarketDatum: name, asofDate, quote(Handle<Quote>), instrumentType=IR_SWAP, quoteType=RATE (키를 파싱해 앎)

# 2) 레시피 읽기 — ored/configuration/
curve_configs = CurveConfigurations(); curve_configs.fromFile("curveconfig.xml")
conventions = Conventions(); conventions.fromFile("conventions.xml")
InstrumentConventions.instance().setConventions(conventions)       # 관례는 전역 등록부
tm_params = TodaysMarketParameters(); tm_params.fromFile("todaysmarket.xml")

# 3) 시장 조립 — ored/marketdata/todaysmarket.hpp
market = TodaysMarket(asof, tm_params, loader, curve_configs)
#    내부: DependencyGraph로 순서 결정 (EUR6M 커브는 EUR1D 할인 커브에 의존 → EUR1D 먼저)
#          노드마다 YieldCurve(asof, spec, curve_configs, loader) → 세그먼트별 RateHelper → PiecewiseYieldCurve(asof, …)
#          결과 Handle을 MarketImpl의 map에 등록: discountCurve("EUR"), iborIndex("EUR-EURIBOR-6M") (지수는 그 커브로 예측)

# 4) 엔진 팩토리 — ored/portfolio/enginefactory.hpp
engine_data = EngineData(); engine_data.fromFile("pricingengine.xml")
factory = EngineFactory(engine_data, market)          # 기본 엔진·레그 빌더가 등록된 상태

# 5) 포트폴리오 조립 — ored/portfolio/portfolio.hpp, swap.cpp
portfolio = Portfolio(); portfolio.fromFile("portfolio_swap.xml")    # Trade 데이터 (SwapData, LegData)
portfolio.build(factory)
#    Swap.build: builder = factory.builder("Swap")
#                legs = [factory.legBuilder(ld.legType()).buildLeg(ld, factory, …) for ld in legData]
#                       (FloatingLegBuilder는 market.iborIndex("EUR-EURIBOR-6M")을 씀)
#                swap = QuantLib Swap(legs, payer flags)
#                swap.setPricingEngine(builder.engine(ccy="EUR"))  → DiscountingSwapEngine(market.discountCurve("EUR")), 캐시
#                instrument_ = VanillaInstrument(swap)

# 6) t0 가격 — PricingAnalytic
portfolio.get("Swap_20y").instrument().NPV()

# 7) 민감도 — orea/engine/sensitivityanalysis.cpp generateSensitivities()
sa = SensitivityAnalysis(portfolio, market, "default", engine_data,
                         sim_params,      # ScenarioSimMarketParameters (simulation.xml)
                         sensi_data,      # SensitivityScenarioData (sensitivity.xml)
                         recalibrateModels=True)
sa.generateSensitivities()
#    내부 순서 (원본 그대로):
#    a) sim_market = ScenarioSimMarket(market, sim_params, …, useSpreadedTermStructures)
#         초기 시장 커브를 격자 만기에서 샘플링해 SimpleQuote(simData)로 보관, 그 Quote로 커브 재구성
#    b) gen = SensitivityScenarioGenerator(sensi_data, sim_market.baseScenario(), sim_params, …)
#         시나리오: 기준, EUR 할인 커브 2W +1bp, 1M +1bp, …, 30Y +1bp, (지수 커브도)
#    c) sim_market.scenarioGenerator = gen
#    d) factory2 = EngineFactory(engine_data, sim_market);  portfolio.build(factory2)   ← 같은 계약을 시뮬레이션 시장에 다시 연결
#    e) engine = ValuationEngine(asof, DateGrid("1,0W"), sim_market, …)
#       engine.buildCube(portfolio, cube, [NPVCalculator])
#         for 시나리오 in gen: sim_market.update(asof) → 모든 거래 NPV → cube[거래, 시나리오]
#    f) SensitivityCube(cube, 시나리오 설명, shift 크기) → (흔든 NPV − 기준 NPV)/shift = 델타, 감마
sa.sensiCube()                                        # → 리포트 "sensitivity"
# 8) (선택) par 변환 — ParSensitivityAnalysis: sensitivity.xml의 ParConversion 상품(OIS 등) 기준으로 야코비안 변환
```

**④ 정리**: 사용자가 만지는 것은 **입력 파일(데이터)**뿐이다. 객체 조립(①~⑤)은 OREData, 흔들고 반복 평가하는 것(⑦)은 OREAnalytics가 한다.
같은 `Swap.build` 코드가 ⑤에서는 `TodaysMarket`에, ⑦-d에서는 `ScenarioSimMarket`에 연결된다. 이것이 Market 규격의 힘이다.

학습 자료 (순서대로)
- `Docs/ore_design.pdf` — Introduction, Library Stack(OREData·OREAnalytics). QuantLib Guide 같은 역할.
- `Examples/MinimalSetup` — 가격결정에 필요한 최소 설정. 위 ①의 파일들.
- 파이썬으로 직접: `Examples/ORE-Python/ExampleScripts`(market.py, swap.py, portfolio.py, loader.py), `Examples/ORE-Python/Notebooks`(Example_8: InputParameters로 분석 돌리기).
- `Examples/CurveBuilding`(부트스트랩 후 재가격 확인), `Examples/MarketRisk`(민감도, 스트레스, par 변환, VaR, P&L explain).
- `Docs/userguide.pdf` — 설정 파일 사전.
- Modern Derivatives Pricing and Sensitivity Analysis (Lichters, Stamm, Gallagher) — ORE 저자들의 방법론.
- 헤더: `market.hpp`, `marketimpl.hpp`, `todaysmarket.hpp`, `trade.hpp`, `enginefactory.hpp`, `simmarket.hpp`, `scenariosimmarket.hpp`,
  `sensitivityscenariogenerator.hpp`, `sensitivityanalysis.hpp`, `valuationengine.hpp`.

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
시장 데이터 DB (docs/data_platform.md) ──► [data: 객체화] TodaysMarket (커브·지수·변동성, 이름으로 조회)   ┐
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
   - QuantLib 확장 : bill BEY↔가격, 격자 커브(절대·spreaded)                       ← QuantExt
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
| 시세·요인의 추이 보기 | 데이터 DB에 SQL (`docs/data_platform.md`). 툴 객체가 필요 없다 |
| PCA·SSR 같은 통계 추정 | `research/`. 검증된 값만 `configs/estimated/`에 출처와 함께 |
| 과거 어느 날의 시장을 재현 (그날의 커브·가격·그릭스, 백테스트) | 그 날짜로 `TodaysMarket(d)`, 결과는 표로 |
| 과거에 일어난 변화를 오늘 시장에 적용 (historical VaR) | 오늘 시장 + 과거 요인 변화 시나리오 → `ScenarioSimMarket` |
| 가정한 충격 (민감도, 스트레스, PCA 요인) | 오늘 시장 + 생성기 → `ScenarioSimMarket` |
| 시간 경과 (theta, P&L explain) | `ScenarioSimMarket.update(다음 날)` |
| 데이터 수집·정제·저장 | 별도 프로젝트 `market-data` |
| 신용(CDS, 해저드율, XVA, 담보) | 범위 밖 |

- 툴은 **정해진 규칙과 파라미터로 계산**한다. 추정은 툴 밖에서 하고, 툴 안에서는 적용만 한다.
- 툴의 쓸모: (1) 시장 상태 모니터링(커브·서페이스·요인), (2) 포지션의 가격·민감도·시나리오 손익, (3) 다른 프로젝트에 시장 요인 시계열 제공.

### 1.4 범위

| 영역 | 선형 | 바닐라 | 이색 |
|---|---|---|---|
| 금리 | 구현 (국채·스왑 커브, 요인화, carry, term premium) | 개념 + 관찰 (MOVE, 국채선물옵션 bp vol) | 개념 |
| 주식 | 구현 (할인·배당·레포, implied forward) | 구현 (IV 서페이스, 그릭스, implied vs realized) | 구현 (LV 캘리브레이션, 오토콜 등) |

- 진행 순서: 금리 선형 → 주식 선형 → 주식 바닐라 → 주식 이색.
- 시간 배분 목표: 인프라 30%, 분석(시장 해석 노트북) 70%. 모듈 하나를 만들 때마다 그 모듈로 실제 시장을 읽는 노트북 하나를 붙인다.

### 1.5 설계 원칙

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

### 1.6 프로젝트 구조 (제안)

✓ = 현재 코드에 같은 기능이 있음(이름·위치는 1.8 표대로 옮길 예정), 나머지는 예정.

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
│   ├── scenario/simmarket.yaml ✓          ScenarioSimMarketParameters (← grid.yaml)
│   ├── scenario/sensitivity.yaml ✓        SensitivityScenarioData (stress.yaml 예정)
│   └── estimated/                         pca_krw.yaml, ssr_spx.yaml (값 + 출처, 격자 좌표 기준)
├── positions/ust_book.yaml ✓              포트폴리오 (ORE portfolio.xml)
│
├── src/quanttool/
│   ├── qle/                               [QuantExt]
│   │   └── termstructures.py              bill BEY↔가격 ✓, 격자 커브 구성(절대 ✓ / spreaded)
│   │
│   ├── data/                              [OREData] 번역과 조립
│   │   ├── utilities/                     ids.py ✓, registry.py ✓, parsers.py ✓
│   │   ├── configuration/                 curveconfig.py ✓, conventions.py ✓, todaysmarketparameters.py ✓,
│   │   │                                  enginedata.py ✓, simmarketparameters.py ✓, sensitivitydata.py ✓, load_config ✓
│   │   ├── marketdata/                    loader.py ✓(Loader, InMemoryLoader, CsvLoader, DuckDBLoader, MarketDatum),
│   │   │                                  market.py(Market ✓, MarketImpl), todaysmarket.py ✓,
│   │   │                                  yieldcurve.py ✓(YieldCurveBuilder; 스왑 구간·IndexBuilder 예정),
│   │   │                                  equity.py(EquityCurveBuilder, EquityVolBuilder), dependencygraph.py ✓, diagnostics.py ✓
│   │   ├── portfolio/                     trade.py ✓(Trade, InstrumentWrapper), legdata.py(LegData, LegBuilder),
│   │   │                                  bond.py ✓, swap.py, equityoption.py, portfolio.py ✓,
│   │   │                                  enginefactory.py ✓(EngineFactory, EngineBuilder, CachingEngineBuilder),
│   │   │                                  builders/bond.py ✓, builders/swap.py, builders/vanillaoption.py
│   │   └── model/                         modelbuilder.py(LocalVolBuilder, HestonBuilder)
│   │
│   └── analytics/                         [OREAnalytics] 활용
│       ├── scenario/                      scenario.py ✓(RiskFactorKey, Scenario), simmarket.py ✓(SimMarket, ScenarioSimMarket),
│       │                                  sensitivityscenariogenerator.py ✓, stressscenariogenerator.py,
│       │                                  historicalscenariogenerator.py, pcascenariogenerator.py, rules.py(StickyStrike, SSR)
│       ├── engine/                        valuationengine.py ✓(ValuationEngine, NPV 표), sensitivityanalysis.py,
│       │                                  parsensitivityanalysis.py, stresstest.py, pnlexplain.py
│       └── app/                           marketmonitor.py ✓, sensitivityreport.py ✓, factorhistory.py
│
├── notebooks/                             tutorial/ ✓ (흐름 따라가기), 01_ust_curve ✓ (시장 해석)
├── research/                              PCA·SSR 추정 → 검증 후 configs/estimated/
├── tests/ ✓                               src와 같은 구조. QuantLib 직접 계산·해석해와 비교 (ORE ExpectedOutput 역할)
├── scripts/fetch_references.sh ✓          references/ 클론
├── docs/                                  architecture.md, data_platform.md
└── references/                            (gitignore) QuantLib-SWIG, ORE Engine, ORE-SWIG 원본
```

이름 규칙: `configs/`는 값, `data/configuration/`은 그 값을 읽는 코드. 데이터 수집(`pipeline/`)은 `market-data` 프로젝트로 옮긴다.

### 1.7 클래스 설계 (제안)

#### 상속
```
Market (규격)                                         ored/marketdata/market.hpp
 └ MarketImpl (보관소)                                 marketimpl.hpp
    ├ TodaysMarket (구축, asof 고정)                   todaysmarket.hpp
    └ SimMarket (update, reset)                        orea/simulation/simmarket.hpp
       └ ScenarioSimMarket (격자 Quote, 생성기)        orea/scenario/scenariosimmarket.hpp
Loader ← InMemoryLoader, CsvLoader, DuckDBLoader       ored/marketdata/loader.hpp
CurveBuilder ← YieldCurveBuilder, IndexBuilder, EquityCurveBuilder, EquityVolBuilder
Trade ← Bond, Swap, EquityOption, EquityDigital, Autocallable                ored/portfolio/trade.hpp
LegBuilder ← FixedLegBuilder, FloatingLegBuilder                             ored/portfolio/legbuilders.hpp
EngineBuilder ← CachingEngineBuilder ← DiscountingBondEngineBuilder, DiscountingSwapEngineBuilder,
                AnalyticEuropeanEngineBuilder, ReplicationDigitalEngineBuilder, LocalVolMCEngineBuilder
ModelBuilder ← LocalVolBuilder, HestonBuilder
ScenarioGenerator ← SensitivityScenarioGenerator, StressScenarioGenerator, HistoricalScenarioGenerator, PcaScenarioGenerator(자체)
```

#### 구성
```
TodaysMarket            asof, TodaysMarketParameters, CurveConfigs, Conventions, Loader → (MarketImpl 보관소) 이름 → RelinkableHandle
EngineFactory           Market, EngineData, 등록된 EngineBuilder·LegBuilder
EngineBuilder           (model, engine, trade_types), Market(팩토리가 건넴), 엔진 캐시
Trade                   계약 데이터 / build 후 InstrumentWrapper(QuantLib Instrument, 승수), legs
Portfolio               Trade들
ScenarioSimMarket       초기 Market, ScenarioSimMarketParameters, sim_data(RiskFactorKey → SimpleQuote), 격자 커브 Handle, ScenarioGenerator
Scenario                asof, label, RiskFactorKey → 값
ValuationEngine         asof, 날짜 격자, SimMarket → NPV 표
SensitivityAnalysis     Portfolio, 초기 Market, EngineData, ScenarioSimMarketParameters, SensitivityScenarioData
```

#### 핵심 시그니처
```python
class Market(ABC):                                    # 규격
    asof: date
    def quote(self, key: str) -> ql.QuoteHandle: ...
    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def discount_curve(self, ccy: str) -> ql.YieldTermStructureHandle: ...
    def index(self, name: str) -> ql.Index: ...
    def equity_spot(self, name: str) -> ql.QuoteHandle: ...
    def dividend_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def equity_vol(self, name: str) -> ql.BlackVolTermStructureHandle: ...
    def active(self) -> ContextManager: ...           # evaluationDate = 이 시장의 날짜, 끝나면 복원

class MarketImpl(Market): ...                         # 보관소: 종류별 이름 → Handle

class TodaysMarket(MarketImpl):
    def __init__(self, asof: date, params: TodaysMarketParameters, loader: Loader,
                 curve_configs: CurveConfigurations, conventions: Conventions): ...

class SimMarket(MarketImpl):
    def update(self, d: date) -> None: ...            # 평가일 = d, 생성기에서 다음 시나리오, 적용
    def reset(self) -> None: ...

class ScenarioSimMarket(SimMarket):
    def __init__(self, init_market: Market, params: ScenarioSimMarketParameters, spreaded: bool = True): ...
    scenario_generator: ScenarioGenerator | None
    def base_scenario(self) -> Scenario: ...
    def apply_scenario(self, s: Scenario) -> None: ...

class Trade(BaseModel, ABC):                          # 계약 데이터 (pydantic)
    id: str
    trade_type: str
    def build(self, factory: EngineFactory) -> None: ...
    def npv(self) -> float: ...

class EngineFactory:
    def __init__(self, engine_data: EngineData, market: Market): ...
    def builder(self, trade_type: str) -> EngineBuilder: ...
    def leg_builder(self, leg_type: str) -> LegBuilder: ...

class EngineBuilder(ABC):
    def engine(self, *keys) -> ql.PricingEngine: ...  # 같은 키면 캐시

@dataclass(frozen=True)
class RiskFactorKey:
    key_type: str                                     # "DiscountCurve", "YieldCurve", "EquitySpot", "EquityVolatility" …
    name: str                                         # "USD", "UST", "SPX"
    point: tuple = ()                                 # ("5Y",), ("1Y", 1.00). ORE는 정수 인덱스

@dataclass(frozen=True)
class Scenario:
    asof: date
    label: tuple | str
    values: dict[RiskFactorKey, float]

class ScenarioGenerator(ABC):
    def next(self, d: date) -> Scenario: ...
    def samples(self) -> int: ...

class ValuationEngine:
    def __init__(self, asof: date, dates: list[date], sim_market: SimMarket): ...
    def build_cube(self, portfolio: Portfolio) -> pd.DataFrame: ...   # (시나리오, 날짜) × 거래

class SensitivityAnalysis:
    def __init__(self, portfolio, market, engine_data, sim_params, sensi_data): ...
    def generate_sensitivities(self) -> None: ...
    def sensi_cube(self) -> SensitivityCube: ...
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

### 1.8 현재 코드와 제안 이름의 대응

| 현재 (`src/quanttool/`) | 제안 | ORE |
|---|---|---|
| `core/ids.py`, `registry.py` | `data/utilities/` | `ored/utilities/` |
| `config/qlmap.py` | `data/utilities/parsers.py` | `ored/utilities/parsers.hpp` |
| `config/` (`YieldCurveConfig`, `TodaysMarketConfig`, `PricingConfig`, `GridConfig`, `SensitivityConfig`) | `data/configuration/` (`YieldCurveConfig`, `TodaysMarketParameters`, `EngineData`, `ScenarioSimMarketParameters`, `SensitivityScenarioData`) | `ored/configuration/`, `orea/scenario/` |
| `core/dependency.py` | `data/marketdata/dependencygraph.py` | `ored/marketdata/dependencygraph.hpp` |
| `market/quotes.py` (`Loader`, `QuoteStore`, `UstParCsvLoader`) | `data/marketdata/loader.py` (`Loader`, `CsvLoader`, `DuckDBLoader`, `MarketDatum`) | `ored/marketdata/loader.hpp`, `csvloader.hpp`, `marketdatum.hpp` |
| `market/market.py` `Market`, `Snapshot` | `Market`, `MarketImpl`, `TodaysMarket` | `market.hpp`, `marketimpl.hpp`, `todaysmarket.hpp` |
| `market/rates.py` `YieldCurveBuilder`, `bill_price` | `data/marketdata/yieldcurve.py`, `qle/termstructures.py` | `ored/marketdata/yieldcurve.hpp`, QuantExt |
| `derivatives/trades.py`, `rates.py` `FixedBond`, `portfolio.py` | `data/portfolio/trade.py`, `bond.py` `Bond`, `portfolio.py` | `ored/portfolio/` |
| `derivatives/factory.py`, `engines.py` | `data/portfolio/enginefactory.py`, `builders/bond.py` | `enginefactory.hpp`, `builders/bond.hpp` |
| `scenario/grid.py` `ScenarioGrid` | `analytics/scenario/simmarket.py`가 쓰는 `ScenarioSimMarketParameters` | `scenariosimmarketparameters.hpp` |
| `scenario/scenario_market.py` `ScenarioMarket` | `analytics/scenario/simmarket.py` `SimMarket`, `ScenarioSimMarket` | `simmarket.hpp`, `scenariosimmarket.hpp` |
| `scenario/generators.py` `Scenario`, `SensitivityGenerator` + `factors.py` | `scenario.py` `Scenario`, `sensitivityscenariogenerator.py` | `scenario.hpp`, `sensitivityscenariogenerator.hpp` |
| `scenario/runner.py` `ScenarioRunner`, `ScenarioResults` | `analytics/engine/valuationengine.py`, `sensitivityanalysis.py` | `valuationengine.hpp`, `sensitivityanalysis.hpp` |
| `analytics/market_monitor.py`, `sensitivity.py` | `analytics/app/marketmonitor.py`, `sensitivityreport.py` | `orea/app/analytics/` |

### 1.9 사용 흐름 (구현되면 이렇게 쓴다)

예시 상황: **미 국채 포트폴리오의 오늘 가격, key rate DV01, 다음 날 theta.** ORE 0.2(5)와 같은 순서다.

**① 입력: 무엇이 어디에 있나**

| 위치 | 읽는 클래스 | 내용 |
|---|---|---|
| `market.duckdb` 뷰 `v_quote` (데이터 플랫폼) | `DuckDBLoader` → `MarketDatum` | `2026-10-23 BOND/YIELD/USD/UST/PAR/10Y 0.0398` |
| `configs/conventions/rates.yaml` | `Conventions` | `UST: {calendar: UnitedStates.GovernmentBond, day_count: ActualActual.Bond, settlement_days: 1, frequency: Semiannual, …}` |
| `configs/market/curves/ust.yaml` | `YieldCurveConfig` | 세그먼트: bill(1M~1Y) `ZeroCouponBill`, 쿠폰채(2Y~30Y) `FixedRateBond`; 시세 키 접두어; 보간 `LogCubic(Discount)` |
| `configs/market/todaysmarket.yaml` | `TodaysMarketParameters` | `yield_curves: {UST: UST}`, `discount_curves: {USD: UST}` (만들 시장 객체 → 레시피) |
| `configs/pricing/engines.yaml` | `EngineData` | `Bond: {model: DiscountedCashflows, engine: DiscountingBondEngine}` |
| `positions/ust_book.yaml` | `Portfolio` → `Bond` | `{id: UST_10Y, trade_type: Bond, notional: 1e7, coupon: 0.04125, issue: 2026-08-15, maturity: 2036-08-15, conventions: UST, discount: UST}` |
| `configs/scenario/simmarket.yaml` | `ScenarioSimMarketParameters` | `UST: {tenors: [1M, …, 30Y], interpolation: LinearZero, spreaded: true}` |
| `configs/scenario/sensitivity.yaml` | `SensitivityScenarioData` | `UST: {shift_type: absolute, shift_size: 0.0001, scheme: forward, par_instruments: [Bill…, Bond…]}` |

**② 코드**

```python
from datetime import date
from quanttool.data.configuration import load_config                       # data/configuration/__init__.py
from quanttool.data.marketdata import DuckDBLoader, TodaysMarket            # data/marketdata/loader.py, todaysmarket.py
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
market = TodaysMarket(asof, cfg.todaysmarket, loader, cfg.curve_configs, cfg.conventions)
#    내부 (data/marketdata/todaysmarket.py):
#      DependencyGraph로 순서 결정 (스왑 커브가 할인 커브에 의존하면 할인 커브 먼저)
#      CURVE_BUILDERS["YieldCurve"] = YieldCurveBuilder (data/marketdata/yieldcurve.py)
#        시세 키 → SimpleQuote → 세그먼트별 헬퍼 (bill: BondHelper(ZeroCouponBond, 가격=qle.bill_price(y)),
#                                            쿠폰채: BondHelper(FixedRateBond, 가격=DerivedQuote(y)))
#        → ql.PiecewiseLogCubicDiscount(asof, helpers, Act365) → RelinkableHandle
#      MarketImpl 보관소에 등록: yield_curve("UST"), discount_curve("USD")
curve_table(market, "UST", cfg)               # 할인계수, 제로, 1Y 선도, par (analytics/app/marketmonitor.py)

# 4) 포트폴리오 조립: 계약 데이터 → QuantLib 상품 + 엔진
book = Portfolio.load("positions/ust_book.yaml")          # Trade 데이터 (pydantic), 아직 QuantLib 객체 없음
factory = EngineFactory(cfg.engine_data, market)          # data/portfolio/enginefactory.py
with market.active():                                     # evaluationDate = asof
    book.build(factory)
    #  Bond.build (data/portfolio/bond.py):
    #    ql.Schedule(issue, maturity, 6M, …) → ql.FixedRateBond(…)
    #    builder = factory.builder("Bond")              → DiscountingBondEngineBuilder (data/portfolio/builders/bond.py)
    #    bond.setPricingEngine(builder.engine("UST"))   → ql.DiscountingBondEngine(market.yield_curve("UST")), 캐시
    #    self.instrument = InstrumentWrapper(bond, multiplier=notional/100)
    book.npvs()                                           # 거래별 NPV (pandas)

# 5) 민감도: 시뮬레이션 시장에서 흔들고 반복 평가 (ORE SensitivityAnalysis와 같은 순서)
sa = SensitivityAnalysis(book, market, cfg.engine_data, cfg.simmarket, cfg.sensitivity)
sa.generate_sensitivities()
#  내부 (analytics/engine/sensitivityanalysis.py):
#    a) sim = ScenarioSimMarket(market, cfg.simmarket, spreaded=True)
#         market.yield_curve("UST")를 1M…30Y에서 샘플 → 격자 SimpleQuote(이동량 0)
#         커브 = 원래 커브 + 보간된 이동량 (qle/termstructures.py) → 기준 상태에서 원래 커브와 같음
#    b) gen = SensitivityScenarioGenerator(cfg.sensitivity, sim.base_scenario())
#         [기준, UST 1M +1bp, …, UST 30Y +1bp, UST 평행 +1bp]
#    c) sim.scenario_generator = gen
#    d) book.build(EngineFactory(cfg.engine_data, sim))     # 같은 계약을 시뮬레이션 시장에 다시 연결
#    e) ValuationEngine(asof, [asof], sim).build_cube(book) # 시나리오마다 sim.update(asof) → npvs() → 표 한 행
#    f) (흔든 NPV − 기준 NPV) / shift → 델타
sa.sensi_cube().key_rate_dv01("UST")                       # 만기 × 거래 표
sa.sensi_cube().parallel_dv01("UST")

# 6) 시간 경과: 시장 그대로, 평가일만 하루 이동 → theta
sim = ScenarioSimMarket(market, cfg.simmarket)
book.build(EngineFactory(cfg.engine_data, sim))
with sim.active():
    base = book.npvs()
    sim.update(date(2026, 10, 26))                          # 다음 영업일, 시나리오 없음(기준) → 평가일 이동
    theta = book.npvs() - base

# 7) 날짜별 커브 이력: 날짜마다 TodaysMarket을 만들고 결과만 표로 (객체는 버림)
history = {d: curve_table(TodaysMarket(d, cfg.todaysmarket, loader, cfg.curve_configs, cfg.conventions),
                          "UST", cfg)["zero_cc"]
           for d in dates}
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

### 1.10 설정 파일 예시
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

# configs/scenario/simmarket.yaml (← grid.yaml)
yield_curves:
  UST: {tenors: [1M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 12Y, 15Y, 20Y, 25Y, 30Y],
        interpolation: LinearZero, extrapolation: FlatZero, spreaded: true}

# configs/pricing/engines.yaml (EngineData)
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
| 구조·이름 | 자체 이름(Snapshot, ScenarioMarket …) vs ORE 이름 | **ORE 구조·이름을 따른다** (1.6, 1.7, 제안) |
| 데이터 | 이 레포 `pipeline/` vs 별도 프로젝트 | **별도 프로젝트 `market-data` + DuckDB** (`docs/data_platform.md`) |
| 범위 | 신용 포함 여부 | **신용(CDS, 해저드율, XVA, 담보) 제외** |
| 시나리오 시장 방식 | 원래 시세 bump vs ORE식 격자 재표현 | **격자 재표현** (PCA·과거 재현과 좌표 일치, 속도, vol 지역성) |
| 격자 커브 모드 | 절대(현재 구현) vs spreaded(ORE `SpreadedDiscountCurve`) | **spreaded 기본**. 기준 대사 오차 0(현재 절대 모드는 합성 샘플 기준 최대 5.1e-4, 30Y). 절대는 옵션 |
| 커브 기준일 | TodaysMarket: 평가일 따라 이동(현재) vs asof 고정(ORE) | **asof 고정**. 시간 이동은 SimMarket이 맡는다 |
| 시간 축 | 고정 기준일 시나리오만(현재) | `SimMarket.update(date)`로 theta·P&L explain |
| 전역 평가일 | 날짜 다른 시장 동시 평가 시 조용한 오류 | 시장마다 `active()`, 순차 평가 |
| 엔진 요청 방식 | `factory.engine_for(trade)`(현재) vs `factory.builder(type).engine(키)`(ORE) | ORE 방식 |
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

최종 갱신 2026-10-28. 브랜치 `claude/confident-hamilton-ui198k`, PR https://github.com/wnsdydchl0/quant-tool/pull/1

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
- 처음이면 `notebooks/tutorial/` 00~04를 순서대로 실행하며 코드 위치를 따라간다(현재 이름 기준).
- `tests/fixtures/ust_par_sample.csv`는 재무부 CSV와 형식만 같은 합성 샘플이다. 실제 데이터는 아직 연결 전이다.

완료 (현재 이름 기준)
- 첫 줄기 (UST 커브 → 국채 → key rate DV01): core, config, market, derivatives, scenario, analytics, 노트북 `01_ust_curve`.
- 튜토리얼 노트북 5개.
- 테스트 81개. 완료 기준 (합성 샘플 기준):

| 기준 | 결과 |
|---|---|
| 헬퍼 재가격 오차 < 0.01bp | 약 1e-9bp |
| QuantLib 직접 조립 채권과 NPV 일치 | 상대오차 1e-12 이내 |
| Σ key rate DV01 = 평행 DV01 | −8,245.95 대 −8,246.30 (한쪽 차분의 2차 항만큼 차이) |
| 격자 시장 기준 NPV ≈ 스냅샷 NPV (절대 모드) | 최대 상대오차 5.1e-4 (30Y) |
| 평행 DV01 vs QuantLib 직접 1bp 이동 | 1e-3 이내 |

### 2.3 다음 단계
1. **ORE 구조로 재구성** (이 문서 승인 후, 커밋 단위)
   1. 패키지 이동·이름 변경(동작 불변, 테스트 그대로 통과).
   2. `MarketImpl` 분리 + `TodaysMarket` asof 고정.
   3. `SimMarket`/`ScenarioSimMarket`: `update(date)`, spreaded 모드.
   4. `EngineFactory.builder` 방식, `ValuationEngine`, `SensitivityAnalysis`.
   5. 튜토리얼 노트북 새 이름으로 재생성, `05_curve_history`(날짜별 시장 → 표, theta).
2. **데이터 플랫폼** (`docs/data_platform.md` 9장): `market-data` 레포, DuckDB 스키마, FRED 수집기 → QuantTool `DuckDBLoader`.
3. `ParSensitivityAnalysis`: 격자 민감도 → 국채·스왑 par 민감도(헷지 수량).
4. KRW 국채·IRS, USD SOFR 커브와 `Swap`·`LegBuilder`.
5. `factorhistory`: 날짜별 격자값 → `risk_factors` 표. 옵션 체인 일별 적재 시작.
6. PCA 시나리오 → 주식 줄기 → P&L explain·과거 재현 → 오토콜·LV.
