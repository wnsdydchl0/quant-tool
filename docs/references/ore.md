# 레퍼런스: ORE (Open Source Risk Engine)

ORE 클래스·파일명은 2026-10 기준 OpenSourceRisk/Engine master에서 확인. 메소드 시그니처는 references/Engine 원본에서 재확인할 것.

QuantLib 위의 실무용 리스크 엔진. QuantLib 각 층 앞에 "설정을 읽어 그 층의 객체를 만들어 주는 층"을 붙인 구조.

### 4.1 층위와 폴더
```
Engine/
├── QuantLib/                 고정 버전
├── QuantExt/qle/             QuantLib 확장 (termstructures, pricingengines, models, …)
├── OREData/ored/             시장·계약·모델의 객체화
│   ├── configuration/        레시피 클래스 (CurveConfig 계열, conventions)
│   ├── marketdata/           로더, MarketDatum, 커브·vol 빌더, DependencyGraph,
│   │                         Market, MarketImpl, TodaysMarket, TodaysMarketParameters
│   ├── model/                ModelBuilder 계열, CalibrationBasket
│   ├── portfolio/            Trade 계열, Portfolio, EngineFactory, EngineData
│   │   └── builders/         상품 유형별 엔진 빌더
│   └── scripting/            스크립트 payoff
├── OREAnalytics/orea/        리스크
│   ├── scenario/             Scenario, ScenarioGenerator 계열, ScenarioSimMarket(+Parameters)
│   ├── simulation/           SimMarket, FixingManager
│   ├── engine/               ValuationEngine, ValuationCalculator, 민감도·스트레스·VaR·P&L explain
│   ├── cube/, aggregation/   결과 큐브, XVA 집계
│   └── app/                  OREApp, InputParameters, AnalyticsManager, analytics/(플러그인)
├── App/                      실행 파일
├── Examples/                 예제 + ExpectedOutput (회귀 테스트)
└── Docs/                     UserGuide, Design(ore_design), 모델 문서
```
예제 입력 파일: `ore.xml`, `todaysmarket.xml`, `curveconfig.xml`, `conventions.xml`, `pricingengine.xml`, `portfolio.xml`, `sensitivity.xml`, `stresstest.xml`, `simulation.xml`.

### 4.2 상속 구조 (확인됨)
```
Market ← MarketImpl ← TodaysMarket
                    ← SimMarket ← ScenarioSimMarket
Loader ← CSVLoader, InMemoryLoader
CurveConfig ← YieldCurveConfig (내부에 YieldCurveSegment 조합), EquityVolatilityCurveConfig, …
YieldCurveSegment ← Simple, AverageOIS, TenorBasis, CrossCcy, FittedBond, ZeroSpreaded, …
QuantLib::LazyObject ← ModelBuilder(QuantExt) ← IrModelBuilder ← HwBuilder
Trade ← Swap, Swaption, VanillaOptionTrade ← EquityOption, …
EngineBuilder ← CachingPricingEngineBuilder ← SwapEngineBuilderBase ← SwapEngineBuilder, …
                                            ← VanillaOptionEngineBuilder ← EuropeanOptionEngineBuilder ← EquityEuropeanOptionEngineBuilder
                                                                         ← AmericanOptionEngineBuilder ← FD/BAW 계열
ScenarioGenerator ← ShiftScenarioGenerator ← SensitivityScenarioGenerator, StressScenarioGenerator
                  ← HistoricalScenarioGenerator
ValuationCalculator ← NPVCalculator ← ExerciseCalculator, CashflowCalculator
Analytic ← PricingAnalytic, StressTestAnalytic, VarAnalytic, PnlExplainAnalytic, XvaAnalytic, …
```
엔진 빌더는 "평가 방법" 축과 "자산군" 축으로 두 번 갈라진다.

### 4.3 구성 구조
```
TodaysMarket      생성자: asof, TodaysMarketParameters, Loader, CurveConfigurations, …
                  보관소(MarketImpl): yieldCurves_, iborIndices_, swaptionCurves_, fxVols_,
                  defaultCurves_, capFloorCurves_, … (이름·구성 → Handle)
TodaysMarketParameters  MarketConfiguration(MarketObject → 레시피 id)을 이름별로 여러 벌
MarketObject (market.hpp)  DiscountCurve, YieldCurve, IndexCurve, SwapIndexCurve, FXSpot, FXVol,
                  SwaptionVol, CapFloorVol, DefaultCurve, EquityCurve, EquityVol, … 
DependencyGraph   노드(MarketObject, 이름, curveSpec), DFS로 순서와 순환 감지
EngineFactory     EngineData(pricingengine.xml) + Market 보유, 유형별 EngineBuilder 등록
Trade             build(EngineFactory) 순수가상, instrument_(InstrumentWrapper), legs_
ScenarioSimMarket 초기화: 기준 Market + ScenarioSimMarketParameters(격자)
                  simData_: RiskFactorKey → SimpleQuote, applyScenario(), reset()
ValuationEngine   SimMarket, Portfolio, Calculator들 → 날짜 × 샘플 × 거래 큐브
```
엔진 빌더가 시장에서 재료를 꺼내는 실제 코드 (vanillaoption 빌더 발췌):
```cpp
Handle<BlackVolTermStructure> vol = market_->equityVol(assetName, config);
return make_shared<GeneralizedBlackScholesProcess>(
    market_->equitySpot(assetName, config), market_->equityDividendCurve(assetName, config),
    market_->equityForecastCurve(assetName, config), vol);
```
`market_`이 TodaysMarket이든 ScenarioSimMarket이든 같은 코드가 동작한다. 이것이 핵심.

### 4.4 사용 흐름 (주식 옵션 NPV와 민감도)
```
Loader로 시세 읽기 → TodaysMarket(DependencyGraph 순서로 빌더 실행)
EngineFactory(EngineData, TodaysMarket) → Portfolio.build(factory)
  EquityOption::build → QuantLib VanillaOption 생성 → 팩토리에서 엔진 빌더 → Process·엔진 조립(캐시)
PricingAnalytic → NPV
ScenarioSimMarket(TodaysMarket, 격자) → EngineFactory(…, ScenarioSimMarket)로 재조립
SensitivityScenarioGenerator → Scenario 목록
ValuationEngine: applyScenario → NPV 재요청 → reset 반복 → 결과 큐브 → 민감도(→ par 변환)
```
ORE 시나리오 시장은 원래 상품으로 재부트스트랩하지 않고, 격자점 Quote로 **재표현**해서 흔든다(빠름, 통일된 요인 격자, MC 겸용). 대신 par 민감도 변환이 필요하다.

### 4.5 파이썬에서 단순화할 C++ 유산
| ORE | QuantTool |
|---|---|
| XML + 설정 클래스별 읽기·쓰기·검증 | YAML + pydantic/dataclass |
| 등록용 클래스 계층 | 딕셔너리 등록부 + 데코레이터 |
| 깊은 상속 (평가 방법 × 자산군) | 규격만 상속, 나머지는 조합 |
| 캐싱 템플릿 | dict / lru_cache |
| 모든 질문에 configuration 인자 | 구성을 묶은 시장 객체 |
| 종류별 map 여러 개 | 이름 체계 하나 + 보관소 |
| 결과 큐브 | pandas / xarray |
| 클래스당 파일 하나 | 비슷한 부류는 한 모듈 |

그대로 가져갈 것: 원칙 1~7 (2장).

### 4.6 학습 자료
- Docs/Design/ore_design, Docs/UserGuide, Examples(MinimalSetup, CurveBuilding, MarketRisk).
- 헤더 다섯 개: market.hpp, todaysmarket.hpp, trade.hpp, enginefactory.hpp, sensitivityscenariogenerator.hpp.
