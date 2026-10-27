# QuantTool 아키텍처

이 문서 하나가 설계의 기준이다. 0장은 참조한 두 라이브러리(QuantLib, ORE)의 구조와 정신,
1장은 이 프로젝트가 무엇을 하려는지와 그동안 정한 것, 2장은 그것을 코드로 옮기는 원칙과 구조, 3장은 진행 현황이다.

> **상태(2026-10-27)**: 2.2~2.3의 구조와 클래스 이름은 ORE를 그대로 따르도록 고친 **제안**이다(피드백 대기).
> 현재 코드는 아직 이전 이름(`Snapshot`, `ScenarioMarket` 등)이며, 대응은 2.4 표를 본다.

---

## 0. 레퍼런스의 구조와 정신

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

### 0.2 ORE 개요: QuantLib 위의 세 라이브러리

근거: ORE 설계 문서 `references/Engine/Docs/Design/ore_design.tex`(= https://rkapl123.github.io/ore_design.pdf), Introduction과 Library Stack.

> "QuantLib은 개별 상품과 그 평가·분석에 초점을 두고, ORE는 (단순 합산이 아닌) 포트폴리오 분석을 목표로 한다."

| 라이브러리 | 역할 | QuantLib과의 관계 |
|---|---|---|
| **QuantExt** | QuantLib 확장: 상품, 엔진, 커브, 모델. QuantLib과 **같은 폴더·클래스 구조** | QuantLib에 없는 부품을 같은 규격으로 보탠다. QuantLib 버그는 원본을 고치지 않고 해당 클래스를 복사해 고친다. 일부는 나중에 QuantLib으로 기여 |
| **OREData** | **번역과 조립.** 외부 표현(XML 설정, 시세 파일)을 QuantLib 객체로 번역하고, 그것으로 **Market, Portfolio, Model** 세 객체를 조립 | 이것만으로 시장 구축, 커브 부트스트랩, 포트폴리오 로드, 현재가치·현금흐름 계산까지 가능 |
| **OREAnalytics** | **활용.** OREData의 세 객체를 입력으로 받아 시나리오·시뮬레이션 기반 위험 분석 | 핵심은 Market 규격을 그대로 가지면서 바꿀 수 있는 `SimMarket` |

QuantLib의 층위(기반 → 시장 정적 상태 → 동학과 계산 → 계약과 분석)에 맞춰 ORE를 보면, ORE는 그 위에 **"조립 → 활용"** 두 단을 얹은 구조다.

```
[QuantLib + QuantExt]   부품: Date·Quote·커브·헬퍼·Instrument·PricingEngine·Model
        │
[OREData: 번역·조립]    입력(XML·시세) ─► configuration(레시피) ─► 빌더 ─► 세 객체
   ├ configuration/     레시피: CurveConfig 계열, Conventions, TodaysMarketParameters, EngineData
   ├ marketdata/        Loader → TodaysMarket (Market ← MarketImpl ← TodaysMarket)   "그 시점의 시장"
   ├ portfolio/         Trade 데이터 → build(EngineFactory) → QuantLib Instrument + PricingEngine
   ├ model/             ModelBuilder → 캘리브레이션된 모델 (LGM, CrossAssetModel)
   └ utilities/         문자열 → QuantLib 객체 파서(Calendar, Period, …)
        │   여기까지로 t0 가격평가·현금흐름 가능
[OREAnalytics: 활용]
   ├ simulation/        SimMarket (MarketImpl + update/reset), FixingManager
   ├ scenario/          Scenario(데이터) · ScenarioGenerator(규칙) · ScenarioSimMarket(+Parameters)
   ├ engine/            ValuationEngine(날짜 × 시나리오 × 거래 → NPV cube),
   │                    SensitivityAnalysis, StressTest, ParSensitivityAnalysis, VaR
   ├ cube/, aggregation/ NPVCube, PostProcess(노출·XVA 집계)
   └ app/               OREApp + Analytic 플러그인(Pricing, Sensitivity, Stress, VaR, XVA, …), InputParameters
```

**OREApp 정보 흐름** (설계 문서 Figure 2):

| 단계 | 처리 | 입력 → 출력 |
|---|---|---|
| 1 | 포트폴리오 로드, 커브 구축, 모델 캘리브레이션 (OREData) | 거래 데이터, 시장 데이터, 설정 |
| 2 | t0 가격평가, 시장 시뮬레이션, 미래 시점 평가 (OREAnalytics) | → NPV·현금흐름 리포트, NPV cube |
| 3 | 집계, 담보 모델링, 노출 분석 | → 노출·XVA 리포트, 넷팅 NPV cube |

모든 Analytic은 공통으로 "초기 시장 구축 → 엔진 팩토리 구축 → 포트폴리오 로드·조립(엔진과 시장 커브 연결)"을 하고, 그 위에서 자기 분석을 한다.

### 0.3 OREData: 세 객체 (Market, Portfolio, Model)

| 객체 | 추상화하는 것 | 내용 |
|---|---|---|
| **Market** | 한 시점의 시장 상태 | 커브·지수·변동성·스팟을 이름(키)으로 조회 |
| **Portfolio** | 계약들 | Trade 데이터 → QuantLib Instrument + PricingEngine |
| **Model** | 시장의 동학 | SDE 모델과 캘리브레이션 (`LgmBuilder`, `CrossAssetModelBuilder`) |

"Data"라는 이름은 데이터를 저장한다는 뜻이 아니라 **데이터를 객체로 바꾸는 층**이라는 뜻이다.

#### Market 계층: 왜 네 단계로 나누나

| 클래스 | 역할 | 비유 | 원본 |
|---|---|---|---|
| `Market` | 가격결정 코드가 아는 **규격**. `discountCurve(ccy)`, `iborIndex(name)`, `equitySpot(name)`… 순수 가상 함수 | 메뉴판 | `ored/marketdata/market.hpp` |
| `MarketImpl` | 이름 → Handle **보관소**(map들)와 조회 구현 | 창고 | `ored/marketdata/marketimpl.hpp` |
| `TodaysMarket` | 레시피·시세로 창고를 **채우는 구축 로직**. 커브 기준일은 asof 고정 | 오늘 장 본 것 | `ored/marketdata/todaysmarket.hpp` |
| `SimMarket` | 창고 내용을 **바꿀 수 있는** 시장. `update(date)`, `reset()`, numeraire, FixingManager 추가 | 실험용 창고 | `orea/simulation/simmarket.hpp` |
| `ScenarioSimMarket` | `update`를 "생성기에서 시나리오를 받아 격자 Quote에 적용"으로 구현 | | `orea/scenario/scenariosimmarket.hpp` |

- `TodaysMarket`과 `SimMarket`이 모두 `MarketImpl`을 상속하는 이유: **창고는 같고 채우는 방식만 다르다.**
- 가격결정 코드는 `Market`만 알기 때문에 어느 쪽에 연결되든 그대로 동작한다. 엔진 빌더 원본도 `market_->equityVol(name)`처럼 규격 메소드만 부른다.
- `TodaysMarket`의 커브는 asof를 기준일로 고정해 만든다(`ored/marketdata/yieldcurve.cpp`가 `asofDate_`를 넘김). 그래서 스냅샷 커브는 전역 평가일과 무관한 함수가 된다.

#### Portfolio: 데이터 → build → 상품 + 엔진

- Trade는 먼저 **순수 데이터**(문자열, 숫자, 리스트)로 로드되고, `build(engineFactory)`를 불러야 QuantLib 상품으로 번역되어
  엔진과 시장 커브에 연결된다(`ored/portfolio/trade.hpp`, `portfolio.hpp`).
- **데이터 클래스 ↔ XML**: `LegData`(통화, 일정, 지급/수취)가 레그 종류별 내용(`FixedLegData`, `FloatingLegData`, …)을 담고,
  모두 `fromXML`/`toXML`로 XML과 서로 변환된다. XML은 데이터 클래스를 파일로 적은 형태일 뿐이다.
  파이썬 바인딩에서는 XML 없이 데이터 클래스를 바로 만든다(`Examples/ORE-Python/ExampleScripts/portfolio.py`):
  ```python
  fixedLeg = ql.LegData(ql.FixedLegData(rates), isPayer, ccy, fixedSchedule, fixedDC, notionals)
  trade = ql.ORESwap(env, floatingLeg, fixedLeg)
  ```
  QuantTool에서는 YAML + pydantic 모델이 이 자리를 맡는다.
- **LegBuilder**: `FixedLegBuilder.buildLeg(legData)` → QuantLib `Leg`(현금흐름 목록). 레그 종류별 빌더가 EngineFactory에 등록된다.
- **EngineBuilder / EngineFactory** (설계 문서 그림 "Collaboration Diagram of Instrument/Leg Builder and Factory Classes"):
  엔진 빌더는 (model, engine, trade types)로 팩토리에 등록되고, `CachingEngineBuilder`를 상속해 **같은 키면 같은 엔진**을 돌려준다.
  목적은 엔진 수와 메모리를 줄이는 것과, 계약서가 평가 방법을 모르게 하는 것이다.

```python
# 팩토리 없이 (QuantLib 직접): 상품마다 사람이 엔진과 커브를 고른다
for bond in bonds:                                            # 1000개
    bond.setPricingEngine(ql.DiscountingBondEngine(curve))    # 엔진 1000개

# ORE 방식
factory = EngineFactory(market, engine_data)                  # engine_data: "Bond → Discounting/DiscountingBondEngine"
factory.register(DiscountingBondEngineBuilder())              # (model, engine, trade_types)

class Bond(Trade):
    def build(self, factory):
        ql_bond = ql.FixedRateBond(...)                       # 계약 데이터 → QuantLib 상품
        builder = factory.builder("Bond")                     # 설정에서 고른 빌더
        ql_bond.setPricingEngine(builder.engine(self.discount_curve))   # 자기 키로 요청

class DiscountingBondEngineBuilder(CachingEngineBuilder):
    def engine(self, curve_name):                             # 같은 키면 캐시 반환
        return self.cache.get_or_make(curve_name,
            lambda: ql.DiscountingBondEngine(self.market.yield_curve(curve_name)))
```
원본 `ored/portfolio/swap.cpp`의 `Swap::build`가 이 순서다: `engineFactory->builder("Swap")` → 레그마다 `legBuilder->buildLeg` →
`swapBuilder->engine(ccy, …)` → `setPricingEngine`.
팩토리를 `TodaysMarket`으로 만들면 오늘 가격, `ScenarioSimMarket`으로 만들면 시나리오 가격이 나온다. 계약서 코드는 같다.

### 0.4 OREAnalytics: SimMarket 위의 분석

설계 문서(Simulation Market 절): "시장이 가정한 시나리오로 움직일 때(**고정 기준일**) 또는 **시간에 따라** 변할 때 가치가 어떻게 바뀌는지는,
포트폴리오를 그렇게 변하는 시장에 '그냥' 연결하고 재평가를 일으키면 된다."

```
SimMarket.update(d):                          # orea/simulation/simmarket.cpp
    scenario = generator.next(d)              # 그 날짜의 시나리오
    evaluationDate = scenario.asof            # 날짜를 움직이고        (scenariosimmarket.cpp updateDate)
    apply(scenario)                           # 격자 Quote를 바꾼다 → Observer → 연결된 포트폴리오 "낡음"
```

| 쓰임 | 날짜 | 시나리오 |
|---|---|---|
| 민감도·스트레스 | asof 고정 | 격자점 이동 |
| 노출·XVA 시뮬레이션 | t1, t2, … 날짜 격자를 따라 이동 | 모델이 만든 시장 경로 |
| theta (우리 쓰임) | 하루 이동 | 시장 그대로 |
| P&L explain (우리 쓰임) | 다음 날 | 다음 날 실제 요인 변화 |

- **Scenario**: asof, label, `RiskFactorKey → 값`. `RiskFactorKey`는 (종류, 이름, 정수 인덱스). 경로는 시나리오의 벡터.
- **ScenarioGenerator**: 몬테카를로(LGM, CrossAsset), 민감도, 스트레스, 과거(HistoricalScenarioGenerator: 과거 t → t+h 변화를 오늘에 적용).
- **ScenarioSimMarketParameters**: 시뮬레이션 시장의 구성(커브별 격자 만기, 보간, 외삽).
- **ScenarioSimMarket의 커브**(`scenariosimmarket.cpp` `makeYieldCurve`):
  - 절대 모드: 격자 Quote = 할인계수, `InterpolatedDiscountCurve`(settlementDays 0, 평가일을 따라 이동).
  - **spreaded 모드**: 격자 Quote = 기준 커브 대비 이동(0에서 시작), `SpreadedDiscountCurve(초기 시장 커브, …)`.
    기준 상태에서 시뮬레이션 커브가 원래 커브와 **정확히 같다**(보간 오차가 이동량에만 생김).
- **ValuationEngine**: 날짜 × 시나리오마다 `update` → 계산기들(NPV 등) → NPV cube.
- **SensitivityAnalysis**(설계 문서 Engine 절): ① 시뮬레이션 시장 구축 ② 포트폴리오를 그 시장에 연결해 조립 ③ 민감도 시나리오 생성
  ④ 시나리오 엔진 실행 ⑤ 1·2차 민감도 정리 ⑥ 결과 구조 채우기. StressTest도 같은 순서.
- **ParSensitivityAnalysis**: 제로·해저드율 등 "raw" 민감도를 시장 상품(예금, 스왑, CDS) 기준 par 민감도로 야코비안(연쇄법칙) 변환.
  raw 영역에서 계산하는 이유: 시장 점을 바꿀 때마다 재부트스트랩하지 않아 빠르다.

### 0.5 학습 자료

QuantLib
- A QuantLib Guide (https://www.quantlibguide.com/) — Library infrastructure 파트 정독, 나머지는 사전처럼.
- Implementing QuantLib (Ballabio) — 설계 이유.
- Context7: `/lballabio/quantlib`, `/lballabio/quantlib-swig`(파이썬 예제가 더 많음) 등록되어 있다.
- 직접 해 보기: `notebooks/tutorial/00_quantlib_basics.ipynb`

ORE (Context7에는 미등록 — `references/Engine` 원본을 본다)
- `Docs/ore_design.pdf` — Introduction, Library Stack(OREData·OREAnalytics) 순서로. QuantLib Guide 같은 역할.
- `Examples/MinimalSetup` — 가격결정에 필요한 최소 설정(시세, todaysmarket, curveconfig, conventions).
- 파이썬으로 직접: `pip install open-source-risk-engine`, `Examples/ORE-Python/ExampleScripts`(market.py, swap.py, portfolio.py), `Examples/ORE-Python/Notebooks`.
- `Examples/CurveBuilding`(부트스트랩 후 재가격 확인), `Examples/MarketRisk`(민감도, 스트레스, par 변환, VaR, P&L explain).
- `Docs/userguide.pdf` — 설정 파일 사전.
- Modern Derivatives Pricing and Sensitivity Analysis (Lichters, Stamm, Gallagher) — ORE 저자들의 방법론.
- 헤더: `market.hpp`, `marketimpl.hpp`, `todaysmarket.hpp`, `trade.hpp`, `enginefactory.hpp`, `simmarket.hpp`, `scenariosimmarket.hpp`, `sensitivityscenariogenerator.hpp`.

### 0.6 QuantTool이 가져오는 것

- **구조**: ORE의 세 라이브러리 경계(QuantExt / OREData / OREAnalytics)와 폴더·클래스 이름을 그대로 쓴다(2.2, 2.3).
- **정신**: (1) 시장과 계약을 설정·시세로부터 빌더가 객체로 만든다 (2) 하나의 시장 객체 위에서 모든 계약을 정합적으로 평가한다
  (3) 같은 규격의 시장을 규칙에 따라 흔들거나 시간을 움직여 위험을 본다 (4) 입력도 출력도 표다.
- **단순화**: C++ 유산(XML, 깊은 상속, 등록용 클래스 계층, 결과 큐브)은 YAML·pydantic, 딕셔너리 등록부, 조합, pandas로 바꾼다(2.1).
  노트북에서 객체를 직접 다루는 파이썬 API가 1차 사용 방식이다.

---

## 1. 프로젝트 목표와 결정 사항

### 1.1 핵심

> **QuantTool은 표준화된 시장 데이터로 "그 시점의 시장 객체"를 만들고, 계약을 그 시장에 붙여 정합적으로 평가하며,
> 시장 객체를 규칙에 따라 흔들거나 시간을 움직여 위험을 본다.**

```
표준 시세 표 ──► [data: 객체화] TodaysMarket (커브·지수·변동성, 이름으로 조회)   ┐
계약 데이터 ───► [data: 객체화] Portfolio (Trade → QuantLib 상품 + 엔진)        ┘
                         │
                         ├─► 1) 가격평가      시장 × 계약 → NPV, 현금흐름              (data만으로)
                         ├─► 2) 위험          ScenarioSimMarket × 같은 계약 → 민감도, 시나리오 손익, theta  (analytics)
                         └─► 3) 그 밖의 파생  커브 표, P&L explain, 헷지 백테스트 …
                                  │
                                  ▼
                              결과 표
```

객체화가 근본이고, 가격평가와 위험 분석은 그 객체를 활용하는 방식이다. 객체가 필요한 이유는 표에 있는 것이
**관측된 숫자 몇 개**(예: par yield 13개)인 반면 가격결정에는 **함수**(아무 날짜의 할인계수, 임의 구간의 선도금리)가 필요하기 때문이다.
그 함수를 시장 관례대로 부트스트랩해 만든 것이 시장 객체다.

### 1.2 무엇을 하고, 무엇을 하지 않나

| 하고 싶은 것 | 하는 곳 |
|---|---|
| 시세·요인의 추이 보기 | 표 연산 (`data/store/quotes`, `risk_factors`). 툴 객체가 필요 없다 |
| PCA·SSR 같은 통계 추정 | `research/`. 검증된 값만 `configs/estimated/`에 출처와 함께 |
| 과거 어느 날의 시장을 재현 (그날의 커브·가격·그릭스, 백테스트) | 그 날짜 표 행으로 `TodaysMarket(d)`, 결과는 표로 |
| 과거에 일어난 변화를 오늘 시장에 적용 (historical VaR) | 오늘 시장 + 과거 요인 변화 시나리오 → `ScenarioSimMarket` |
| 가정한 충격 (민감도, 스트레스, PCA 요인) | 오늘 시장 + 생성기 → `ScenarioSimMarket` |
| 시간 경과 (theta, P&L explain) | `ScenarioSimMarket.update(다음 날)` |
| 데이터 수집·정제 | `pipeline/` (툴 밖) |

- 툴은 **정해진 규칙과 파라미터로 계산**한다. 추정은 툴 밖에서 하고, 툴 안에서는 적용만 한다(예: 저장된 로딩으로 오늘 요인 점수 계산).
- 툴의 쓸모: (1) 시장 상태 모니터링(커브·서페이스·요인), (2) 포지션의 가격·민감도·시나리오 손익, (3) 다른 프로젝트(팩터 모델 등)에 시장 요인 시계열 제공.

### 1.3 범위

| 영역 | 선형 | 바닐라 | 이색 |
|---|---|---|---|
| 금리 | 구현 (국채·스왑 커브, 요인화, carry, term premium) | 개념 + 관찰 (MOVE, 국채선물옵션 bp vol) | 개념 |
| 주식 | 구현 (할인·배당·레포, implied forward) | 구현 (IV 서페이스, 그릭스, implied vs realized) | 구현 (LV 캘리브레이션, 오토콜 등) |

- 진행 순서: 금리 선형 → 주식 선형 → 주식 바닐라 → 주식 이색.
- 시간 배분 목표: 인프라 30%, 분석(시장 해석 노트북) 70%. 모듈 하나를 만들 때마다 그 모듈로 실제 시장을 읽는 노트북 하나를 붙인다.

### 1.4 데이터

#### 흐름: 원본 → 정규화 → 저장소 → 시장 객체

```
출처(FRED, ECOS, …)
  │ ① 수집      pipeline: 받은 그대로        → data/raw/{source}/...
  │ ② 정규화    pipeline: 공통 스키마로 변환 → data/store/quotes   (키는 data/utilities/ids.py 규칙으로 검증)
  │ ③ 검증·적재 pipeline: 단위·결측·휴일·이상치
  ▼
정규화 저장소 (DB 역할, 모든 분석·계산의 원천)
  │ ④ Loader.load(asof)    툴: 그 날짜 행만 조회, 출처를 모른다   (ORE Loader → MarketDatum)
  ▼
TodaysMarket (메모리, 분석 하나 동안만)  →  커브·상품 객체
```

- 출처마다 형식이 달라도 ② 이후로는 차이가 사라진다. ORE도 시세를 출처와 무관한 `날짜 키 값` 한 형식(`market.txt`)으로 받는다.
- 원본을 남겨 두면 정규화 규칙이 바뀌어도 다시 받지 않고 재처리할 수 있다.
- 시장 객체 안의 `SimpleQuote`는 저장소가 아니라 실행용 객체다. 영속 데이터는 정규화 저장소에 있다.

#### 저장소 (parquet + DuckDB, 서버 없음)

| 표 | 내용 | 성격 | ORE 대응 |
|---|---|---|---|
| `quotes` | `date, quote_id, value(소수), source, ingested_at` 긴 형식 | 관측값. 바뀌지 않음 | `market.txt`, `fixings.txt` |
| `quote_meta` | `quote_id → 상품 유형, 통화, 관례, 만기, 단위, 출처` | 키 사전 | — |
| `risk_factors` | 날짜별 격자점 값 (제로금리 1M…30Y, IV 격자) | 모델 산출. 커브 방법·격자가 바뀌면 재생성 | historical scenario file |
| `results` | 날짜 × 거래별 NPV, 그릭스, 손익 분해 | 계산 결과. 포지션·모델이 바뀌면 재생성 | NPV cube, 리포트 |

- 분석용 넓은 형식(행=날짜, 열=만기)은 `quotes`를 피벗해 만든다.
- 관측값과 계산 결과는 분리한다. 관측값은 사실이고, 계산 결과는 모델이 바뀌면 다시 만들어야 한다.
- 시세 키는 ORE처럼 스스로를 설명하게 넓힌다(현재 `UST/PAR/2Y` → 예정):
  `BOND/YIELD/USD/UST/PAR/10Y`, `BOND/YIELD/KRW/KTB/MKT/3Y`, `IR_SWAP/RATE/KRW/1D/3M/5Y`(CD91), `OIS/RATE/USD/2D/1D/10Y`(SOFR), `FIXING/SOFR`, `FIXING/CD91`.

#### 금리 종류

| | 무엇 | 변동 레그 | 예 |
|---|---|---|---|
| 국채 금리 | 정부 채권 수익률 | — | UST 10Y, 국고채 3Y |
| IRS | 고정 ↔ 기간물 지표금리 | 3M CD, (과거) 3M LIBOR, Term SOFR | KRW IRS = 고정 vs CD91, 분기 지급 |
| OIS | 고정 ↔ 익일물 금리의 기간 복리 | SOFR, KOFR, €STR | USD SOFR 스왑 |

- OIS는 변동 레그가 익일물 복리인 IRS다. 미국은 LIBOR 종료(2023-06) 후 표준 스왑이 SOFR OIS라, "SOFR 스왑/IRS/OIS"는 보통 같은 상품이다.
- 한국 표준 IRS는 여전히 CD91 기준이고, KOFR OIS는 도입 단계라 유동성이 작다.
- USD는 SOFR OIS 하나로 예측과 할인을 같이 한다. KRW는 CD91 IRS로 예측 커브를 만들고, 할인 커브는 담보 조건에 따라 확인이 필요하다.

#### 출처 (조사 2026-10-27, 미연결)

| 대상 | 출처 | 이력 | 비고 |
|---|---|---|---|
| 미 국채 par yield | FRED `DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2, DGS3, DGS5, DGS7, DGS10, DGS20, DGS30` (`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10`), 재무부 원본(`pipeline/ust_par.py`) | 수십 년 (10Y 1962~, 1M 2001~). 30Y는 2002-02~2006-02 공백 | 공식 (H.15 = 재무부 CMT). 키 없이 받는지 확인 |
| SOFR 고시 | NY Fed `https://markets.newyorkfed.org/api/rates/secured/sofr/...`, FRED `SOFR` | 2018-04-02~ | 공식 |
| 국고채 | 한국은행 ECOS 시장금리(일별) `817Y002` — `https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/1/{N}/817Y002/D/{시작}/{끝}/{항목}` | 수십 년 (만기별 시작일 확인) | 공식 (원천: 금투협 최종호가수익률). 무료 인증키 `ECOS_API_KEY`. 국고채 10년 = `010210000` |
| CD91 | ECOS `817Y002` (항목코드 확인) | 수십 년 (확인) | 공식 |
| USD SOFR OIS | **무료 공식 커브 없음** (FRED ICE 스왑은 2016년 중단) | — | 아래 결정 |
| KRW IRS (CD91) | 서울외국환중개 `http://smbs.biz/Exchange/IRS.jsp`, 한국자금중개 `https://www.kmbco.com/kor/rate/deri_rate.do` | SMBS는 한 번에 최대 36개월. 최대 과거 범위 확인 | 중개사 공시, HTML |
| 그 밖의 무료 | 금투협 채권정보센터, KRX 정보데이터시스템, yfinance(현재 옵션 체인), 증권사 API(KIS) | | 옵션 체인은 이력이 없으니 일찍 적재 시작 |

결정할 것:
- **USD SOFR OIS**: ① DTCC SDR 공개 체결(`https://pddata.dtcc.com/ppd/cftcdashboard`, CFTC 의무 공시, 1차 출처). 만기별 당일 시작 거래의 중앙값을
  par 금리로 쓴다. 공개 파일은 약 1년치만 보관하므로 몇 년치는 지금부터 매일 쌓아야 한다. ② checkmyswap 무료 API(제3자, 미검증).
  ③ SOFR + 국채 스프레드 근사(실제 시세 아님). ④ Bloomberg·Refinitiv를 쓸 수 있으면 몇 년치를 한 번에 받는 유일한 경로.
  어떤 출처든 SOFR 스왑 시장이 2021~2022년에 본격화돼 이력은 길어야 4~5년이다.
- **KRW IRS**: 중개사 두 곳 조회 페이지를 서로 대조하며 수집, 또는 단말기 CSV 공급.
- 사실상 불가: swaption·cap/floor vol.

### 1.5 결정 사항과 미결정

| 항목 | 내용 | 현재 방향 |
|---|---|---|
| 구조·이름 | 자체 이름(Snapshot, ScenarioMarket …) vs ORE 이름 | **ORE 구조·이름을 따른다** (2.2, 2.3, 제안) |
| 시나리오 시장 방식 | 원래 시세 bump vs ORE식 격자 재표현 | **격자 재표현으로 결정** (PCA·과거 재현과 좌표 일치, 속도, vol 지역성) |
| 격자 커브 모드 | 절대(격자 Quote = 제로금리, 현재 구현) vs spreaded(격자 Quote = 기준 대비 이동, ORE `SpreadedDiscountCurve`) | **spreaded를 기본으로**. 기준 상태 대사 오차가 0이 된다(현재 절대 모드는 합성 샘플 기준 최대 5.1e-4, 30Y). 절대 모드는 옵션 |
| 커브 기준일 | TodaysMarket: 평가일 따라 이동(현재) vs asof 고정(ORE) | **TodaysMarket은 asof 고정**. 시간 이동은 SimMarket이 맡는다(시뮬레이션 커브는 평가일을 따라 이동) |
| 시간 축 | 고정 기준일 시나리오만(현재) | `SimMarket.update(date)`로 theta·P&L explain 지원 |
| 전역 평가일 | 날짜 다른 시장 동시 평가 시 조용한 오류 | 시장마다 `active()` 컨텍스트, 순차 평가 |
| 엔진 요청 방식 | `factory.engine_for(trade)`(현재) vs `factory.builder(type).engine(키)`(ORE) | ORE 방식. Trade가 자기 키로 빌더에 요청 |
| Index fixing 전역 공유 | 시나리오가 기준 시장 fixing을 오염 | fixing은 구축 시 1회 로드, 시나리오에서 수정 금지 (ORE FixingManager 대응은 시간 축 도입 때) |
| IV 서페이스 흔들기 | 호가 bump 시 재피팅이 변화를 번지게 함, 느림 | 격자 재표현으로 해결 (재피팅 없음) |
| 격자 바깥 | 외삽 형태가 결과에 영향 | 평탄 제로. QuantLib 1.44 `PiecewiseZeroSpreadedTermStructure`는 Quote 변경 시 외삽 설정이 풀려, 마지막 격자 Quote에 묶은 100Y 끝점으로 처리 |
| 민감도 단위 | 격자 민감도는 제로금리·격자 vol 기준 | `ParSensitivityAnalysis`로 시장 상품 기준 변환 |
| UST par 헬퍼 관례 | par yield = 쿠폰인 가상 채권 가격이 정확히 100이어야 함 | 명목 만기 정규 일정 + Unadjusted 지급(수익률 관례). bill(≤1Y)은 BEY(Act/365, 반년 초과 시 반기복리 1회) → 할인채 가격. 쿠폰은 구축 시점 고정, 수익률 변화는 DerivedQuote로 가격에 전달 |
| 모델 재캘리브레이션 비용 | 시나리오마다 자동 재캘리브레이션 | "모델 고정" 선택지 |
| 단위·형식 | bp/소수, 수익률/가격 혼동 | 저장소는 항상 소수, `ids`에 유형·단위, `Scenario` 검증 |
| 듀얼 커브 (KRW) | CD 프로젝션 vs 할인 커브 | 구조는 지원, 데이터 확보 시 활성화 |

---

## 2. 설계 원칙과 프로젝트 구조

### 2.1 설계 원칙

1. **시장은 규격(인터페이스)이고, 규격·보관소·구축·변경을 나눈다.** `Market`(규격) ← `MarketImpl`(보관소) ← `TodaysMarket`(구축) / `SimMarket`(변경) ← `ScenarioSimMarket`.
   가격결정 코드는 `Market` 규격만 안다.
2. **모든 시장 입력은 id가 붙은 `SimpleQuote`이고, 구조물은 그 Quote에 연결된 채로 만든다.** 그래야 시나리오가 "Quote 값 변경 → Observer 전파 → Lazy 재계산"으로 끝난다.
3. **이름으로 참조한다.** 상품·모델은 커브를 객체가 아니라 이름으로 참조하고, 평가 시점에 시장에서 받는다.
4. **레시피(configuration)와 제작자(빌더)를 분리한다.** 같은 군은 같은 빌더, 대상별 차이는 설정.
5. **구축 순서는 의존 그래프가 정한다.** 관계는 레시피의 참조에서 자동 추출. (ORE `DependencyGraph`)
6. **계약(무엇)과 평가 방법(어떻게)을 분리한다.** Trade는 순수 데이터, 엔진 선택은 `EngineData`, 조립은 `EngineBuilder`, 창구는 `EngineFactory`.
7. **시나리오는 데이터이고, 생성·적용·평가는 분리한다.** `ScenarioGenerator` → `Scenario` → `ScenarioSimMarket.update/apply/reset` → `ValuationEngine`.
   - 7-1. **시뮬레이션 시장은 격자 재표현을 쓴다.** 커브·서페이스를 고정 격자점에서 표현한 SimpleQuote로 보관하고 그 Quote를 보간해 시장을 구성한다.
     기본은 spreaded(기준 대비 이동). 요인(PCA 등) 추정과 과거 재현도 같은 격자 좌표를 쓴다.
   - 7-2. **시간 축은 SimMarket이 맡는다.** `update(date)`가 평가일을 옮기고 그 날의 시나리오를 적용한다. TodaysMarket은 asof 고정.
8. **의존 방향은 한쪽으로.** `data.utilities·configuration → data.marketdata → data.portfolio → analytics.scenario → analytics.engine → analytics.app`. `qle`는 QuantLib만 의존 (`tests/test_layering.py`).
9. **ORE 폴더 구조를 따른다.** 라이브러리 → 하위 영역 → 파일, 최대 세 단계. 비슷한 부류는 한 파일에 묶고, 커지면 쪼갠다.
10. **표 ↔ 객체 경계를 지킨다.** 들어올 때는 정규화 저장소, 나갈 때는 결과 표. 객체는 짧게 쓰고 저장하지 않는다.

C++ 유산의 단순화:

| ORE | QuantTool |
|---|---|
| XML + `fromXML`/`toXML` 데이터 클래스 | YAML + pydantic 모델 |
| 등록용 클래스 계층, `addDefaultBuilders` | 딕셔너리 등록부 + 데코레이터 |
| 깊은 상속 (평가 방법 × 자산군) | 규격만 상속, 나머지는 조합 |
| `CachingEngineBuilder` 템플릿 | dict 캐시 |
| 모든 질문에 configuration 인자 | 구성을 묶은 시장 객체 (시장 구성 하나) |
| 종류별 map 여러 개 | 이름 체계 하나 + 보관소 |
| NPV cube | pandas (날짜 × 시나리오 × 거래) |
| 클래스당 파일 하나 | 비슷한 부류는 한 모듈 |

### 2.2 프로젝트 구조 (제안, ORE 대응)

✓ = 현재 코드에 같은 기능이 있음(이름·위치는 2.4 표대로 옮길 예정), 나머지는 예정.

```
quant-tool/
├── configs/                               [값]
│   ├── conventions/rates.yaml ✓           (equity.yaml 예정)
│   ├── market/
│   │   ├── todaysmarket.yaml ✓            TodaysMarketParameters: 구축 대상
│   │   ├── curves/ust.yaml ✓              CurveConfig (krw_ktb, usd_sofr, krw_irs, spx_fwd 예정)
│   │   ├── indices/                       cd91.yaml, sofr.yaml
│   │   └── vols/                          spx.yaml
│   ├── pricing/engines.yaml ✓             EngineData (models.yaml 예정)
│   ├── scenario/simmarket.yaml ✓          ScenarioSimMarketParameters (← grid.yaml)
│   ├── scenario/sensitivity.yaml ✓        SensitivityScenarioData (stress.yaml 예정)
│   └── estimated/                         pca_krw.yaml, ssr_spx.yaml (값 + 출처, 격자 좌표 기준)
├── positions/ust_book.yaml ✓              포트폴리오 (예시)
│
├── src/quanttool/
│   ├── qle/                               [QuantExt] QuantLib 확장
│   │   └── termstructures.py              bill BEY↔가격 ✓, 격자 커브 구성(절대 ✓ / spreaded)
│   │
│   ├── data/                              [OREData] 번역과 조립: Market, Portfolio, Model
│   │   ├── utilities/                     ids.py ✓(시세 id, RiskFactorKey는 analytics로), registry.py ✓, parsers.py ✓
│   │   ├── configuration/                 curveconfig.py ✓, conventions.py ✓, todaysmarketparameters.py ✓,
│   │   │                                  enginedata.py ✓, simmarketparameters 읽기 ✓, load_config ✓
│   │   ├── marketdata/                    loader.py ✓(Loader, InMemoryLoader, CsvLoader, MarketDatum),
│   │   │                                  market.py(Market ✓, MarketImpl), todaysmarket.py ✓,
│   │   │                                  yieldcurve.py ✓(YieldCurveBuilder; 스왑 구간·IndexBuilder 예정),
│   │   │                                  equity.py(EquityCurveBuilder, EquityVolBuilder), dependencygraph.py ✓, diagnostics.py ✓
│   │   ├── portfolio/                     trade.py ✓(Trade, InstrumentWrapper), legdata.py(LegData, LegBuilder),
│   │   │                                  bond.py ✓, swap.py, equityoption.py, portfolio.py ✓,
│   │   │                                  enginefactory.py ✓(EngineFactory, EngineBuilder, CachingEngineBuilder),
│   │   │                                  builders/bond.py ✓, builders/swap.py, builders/vanillaoption.py
│   │   └── model/                         modelbuilder.py(LocalVolBuilder, HestonBuilder), calibrationbasket.py
│   │
│   └── analytics/                         [OREAnalytics] 활용
│       ├── scenario/                      scenario.py ✓(RiskFactorKey, Scenario), simmarketparameters.py ✓,
│       │                                  simmarket.py ✓(SimMarket, ScenarioSimMarket),
│       │                                  sensitivityscenariogenerator.py ✓, stressscenariogenerator.py,
│       │                                  historicalscenariogenerator.py, pcascenariogenerator.py, rules.py(StickyStrike, SSR)
│       ├── engine/                        valuationengine.py ✓(ValuationEngine, NPVCube), sensitivityanalysis.py,
│       │                                  parsensitivityanalysis.py, stresstest.py, pnlexplain.py
│       └── app/                           marketmonitor.py ✓, sensitivityreport.py ✓, factorhistory.py(→ risk_factors)
│
├── pipeline/                              데이터 수집·정규화·적재 (툴 밖). ust_par.py ✓
├── data/                                  (gitignore) raw/, store/
├── notebooks/                             tutorial/ ✓ (흐름 따라가기), 01_ust_curve ✓ (시장 해석)
├── research/                              PCA·SSR 추정 → 검증 후 configs/estimated/
├── tests/ ✓                               src와 같은 구조. QuantLib 직접 계산·해석해와 비교 (ORE ExpectedOutput 역할)
├── scripts/fetch_references.sh ✓          references/ 클론
├── docs/architecture.md                   이 문서
└── references/                            (gitignore) QuantLib-SWIG, ORE 원본
```

이름 규칙: `configs/`는 값, `data/configuration/`은 그 값을 읽는 코드.

### 2.3 클래스 설계 (제안, ORE 이름)

#### 상속
```
Market (규격)                                         ored/marketdata/market.hpp
 └ MarketImpl (보관소)                                 ored/marketdata/marketimpl.hpp
    ├ TodaysMarket (구축, asof 고정)                   ored/marketdata/todaysmarket.hpp
    └ SimMarket (update, reset)                        orea/simulation/simmarket.hpp
       └ ScenarioSimMarket (격자 Quote, 생성기)        orea/scenario/scenariosimmarket.hpp
Loader ← InMemoryLoader, CsvLoader                     ored/marketdata/loader.hpp
CurveBuilder ← YieldCurveBuilder, IndexBuilder, EquityCurveBuilder, EquityVolBuilder   ored/marketdata/yieldcurve.hpp 등
Trade ← Bond, Swap, EquityOption, EquityDigital, Autocallable                          ored/portfolio/trade.hpp
LegBuilder ← FixedLegBuilder, FloatingLegBuilder                                       ored/portfolio/legbuilders.hpp
EngineBuilder ← CachingEngineBuilder ← DiscountingBondEngineBuilder, DiscountingSwapEngineBuilder,
                AnalyticEuropeanEngineBuilder, ReplicationDigitalEngineBuilder, LocalVolMCEngineBuilder
                                                                                       ored/portfolio/enginefactory.hpp
ModelBuilder ← LocalVolBuilder, HestonBuilder                                          ored/model/
ScenarioGenerator ← SensitivityScenarioGenerator, StressScenarioGenerator,
                    HistoricalScenarioGenerator, PcaScenarioGenerator(자체)             orea/scenario/
```

#### 구성
```
TodaysMarket            asof, TodaysMarketParameters, CurveConfigs, Conventions, Loader
                        → (MarketImpl 보관소) 이름 → RelinkableHandle, QuoteStore
EngineFactory           Market, EngineData, 등록된 EngineBuilder·LegBuilder
EngineBuilder           (model, engine, trade_types), Market(팩토리가 건넴), 엔진 캐시
Trade                   계약 데이터 / build 후 InstrumentWrapper(QuantLib Instrument, 승수), legs
Portfolio               Trade들
ScenarioSimMarket       초기 Market, ScenarioSimMarketParameters,
                        sim_data(RiskFactorKey → SimpleQuote), 격자 Quote를 보간한 커브 Handle, ScenarioGenerator
Scenario                asof, label, RiskFactorKey → 값 (데이터)
ValuationEngine         asof, 날짜 격자, SimMarket, 계산기(NPV) → NPVCube
SensitivityAnalysis     Portfolio 데이터, 초기 Market, ScenarioSimMarketParameters, SensitivityScenarioData, EngineData
```

#### 핵심 시그니처
```python
class Market(ABC):                                    # 규격 (메뉴판)
    asof: date
    def quote(self, quote_id: str) -> ql.QuoteHandle: ...
    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def index(self, name: str) -> ql.Index: ...
    def equity_spot(self, name: str) -> ql.QuoteHandle: ...
    def dividend_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def equity_vol(self, name: str) -> ql.BlackVolTermStructureHandle: ...
    def active(self) -> ContextManager: ...           # evaluationDate = 이 시장의 날짜, 끝나면 복원

class MarketImpl(Market):                             # 보관소: 종류별 이름 → Handle, 조회 구현
    def _set_yield_curve(self, name, handle): ...

class TodaysMarket(MarketImpl):                       # 구축: 커브 기준일 = asof 고정
    def __init__(self, asof: date, params: TodaysMarketParameters, loader: Loader,
                 curve_configs, conventions): ...      # DependencyGraph 순서로 CurveBuilder 실행

class SimMarket(MarketImpl):                          # 변경 가능한 시장
    def update(self, d: date) -> None: ...            # 평가일 = d, 생성기에서 다음 시나리오, 적용
    def reset(self) -> None: ...

class ScenarioSimMarket(SimMarket):
    def __init__(self, init_market: Market, params: ScenarioSimMarketParameters,
                 spreaded: bool = True): ...
    scenario_generator: ScenarioGenerator | None
    def apply_scenario(self, s: Scenario) -> None: ...   # 날짜 이동 없이 적용

class Trade(BaseModel, ABC):                          # 계약 데이터 (pydantic, ORE fromXML 대응)
    id: str
    trade_type: str                                   # EngineData 키
    def build(self, factory: EngineFactory) -> None: ...
    def npv(self) -> float: ...

class EngineFactory:
    def __init__(self, market: Market, engine_data: EngineData): ...
    def builder(self, trade_type: str) -> EngineBuilder: ...
    def leg_builder(self, leg_type: str) -> LegBuilder: ...

class EngineBuilder(ABC):                             # (model, engine, trade_types)로 등록
    def engine(self, *keys) -> ql.PricingEngine: ...  # 같은 키면 캐시 반환

@dataclass(frozen=True)
class RiskFactorKey:                                  # QuantExt/qle/termstructures/scenario.hpp
    key_type: str                                     # "DiscountCurve", "YieldCurve", "EquitySpot", "EquityVolatility" …
    name: str                                         # "UST", "SPX"
    point: tuple = ()                                 # ("5Y",) 또는 ("1Y", 1.00). ORE는 정수 인덱스

@dataclass(frozen=True)
class Scenario:
    asof: date
    label: tuple | str
    values: dict[RiskFactorKey, float]                # spreaded: 이동량, 절대: 값

class ScenarioGenerator(ABC):
    def next(self, d: date) -> Scenario: ...          # ORE와 같은 방식 (반복자처럼)

class ValuationEngine:
    def __init__(self, asof: date, dates: list[date], sim_market: SimMarket): ...
    def build_cube(self, portfolio: Portfolio, n_samples: int) -> NPVCube: ...

class SensitivityAnalysis:                            # orea/engine/sensitivityanalysis.hpp 순서
    def run(self) -> SensitivityResults: ...          # sim market → 포트폴리오 연결 → 시나리오 → 엔진 → 민감도 정리
```

#### 불변 조건
- 모든 시장 입력은 시장의 `SimpleQuote`이며 id는 `data/utilities/ids.py` 규칙을 따른다.
- 시나리오에서 흔드는 대상은 `ScenarioSimMarketParameters`의 격자점이다. 흔들고 싶은 것은 격자에 정의되어 있어야 한다.
- 시뮬레이션 시장의 기준 NPV는 초기 시장 NPV와 허용 오차 이내로 일치해야 한다 (spreaded는 사실상 0).
- 요인 로딩·과거 시나리오는 격자 좌표(`RiskFactorKey`)로 정의한다.
- 가격결정·시나리오 코드는 `Market` 규격 메소드만 쓴다. `MarketImpl` 보관소를 직접 만지지 않는다.
- Trade는 엔진·모델을 모른다. 엔진 선택은 `EngineData`(`engines.yaml`).
- `ValuationEngine`은 포트폴리오를 시나리오마다 재조립하지 않는다. 한 번 조립 후 update → npv → reset.
- `TodaysMarket`은 만들어진 뒤 바뀌지 않는다(asof 고정). 바꾸는 것은 `SimMarket`만.
- 날짜가 다른 시장은 각자의 `active()` 안에서 순차적으로만 평가한다.

### 2.4 현재 코드와 제안 이름의 대응

| 현재 (`src/quanttool/`) | 제안 | ORE |
|---|---|---|
| `core/ids.py`, `registry.py` | `data/utilities/` | `ored/utilities/` |
| `config/qlmap.py` | `data/utilities/parsers.py` | `ored/utilities/parsers.hpp` |
| `config/` (`YieldCurveConfig`, `TodaysMarketConfig`, `PricingConfig`) | `data/configuration/` (`YieldCurveConfig`, `TodaysMarketParameters`, `EngineData`) | `ored/configuration/` |
| `core/dependency.py` | `data/marketdata/dependencygraph.py` | `ored/marketdata/dependencygraph.hpp` |
| `market/quotes.py` (`Loader`, `QuoteStore`, `UstParCsvLoader`) | `data/marketdata/loader.py` (`Loader`, `CsvLoader`; 재무부 형식 해석은 pipeline으로) | `ored/marketdata/loader.hpp`, `csvloader.hpp` |
| `market/market.py` `Market`, `Snapshot` | `Market`, `MarketImpl`, `TodaysMarket` | `market.hpp`, `marketimpl.hpp`, `todaysmarket.hpp` |
| `market/rates.py` `YieldCurveBuilder`, `bill_price` | `data/marketdata/yieldcurve.py`, `qle/termstructures.py` | `ored/marketdata/yieldcurve.hpp`, QuantExt |
| `derivatives/trades.py`, `rates.py` `FixedBond`, `portfolio.py` | `data/portfolio/trade.py`, `bond.py` `Bond`, `portfolio.py` | `ored/portfolio/` |
| `derivatives/factory.py`, `engines.py` | `data/portfolio/enginefactory.py`, `builders/bond.py` | `enginefactory.hpp`, `builders/bond.hpp` |
| `scenario/grid.py` `ScenarioGrid` | `analytics/scenario/simmarketparameters.py` `ScenarioSimMarketParameters` | `scenariosimmarketparameters.hpp` |
| `scenario/scenario_market.py` `ScenarioMarket` | `analytics/scenario/simmarket.py` `SimMarket`, `ScenarioSimMarket` | `simmarket.hpp`, `scenariosimmarket.hpp` |
| `scenario/generators.py` `Scenario`, `SensitivityGenerator` + `factors.py` | `scenario.py` `Scenario`, `sensitivityscenariogenerator.py` | `scenario.hpp`, `sensitivityscenariogenerator.hpp` |
| `scenario/runner.py` `ScenarioRunner`, `ScenarioResults` | `analytics/engine/valuationengine.py` `ValuationEngine`, `NPVCube` + `sensitivityanalysis.py` | `valuationengine.hpp`, `sensitivityanalysis.hpp` |
| `analytics/market_monitor.py`, `sensitivity.py` | `analytics/app/marketmonitor.py`, `sensitivityreport.py` | `orea/app/analytics/` |

### 2.5 사용 흐름 (제안 이름)

#### 커브 보기와 국채 평가 (OREData만)
```python
cfg    = load_config("configs")
market = TodaysMarket(date(2026, 10, 23), cfg.todaysmarket, loader, cfg.curves, cfg.conventions)
curve_table(market, "UST", cfg)                          # 할인계수, 제로, 1Y 선도, par
book = Portfolio.load("positions/ust_book.yaml")
with market.active():
    book.build(EngineFactory(market, cfg.engine_data)); book.npvs()
```
```
TodaysMarket(asof, …)
  ├ loader.load(asof) → MarketDatum("UST/PAR/10Y", 0.0398), …  → SimpleQuote들
  ├ DependencyGraph(CurveBuilder.requires).order(대상) → [("YieldCurve", "UST")]
  └ YieldCurveBuilder.build(config): 수익률 Quote → DerivedQuote(가격) → BondHelper
       → PiecewiseLogCubicDiscount(asof, …) → RelinkableHandle → MarketImpl 보관소
Bond.build(factory)
  ├ ql.FixedRateBond(일정, 쿠폰)
  └ factory.builder("Bond").engine("UST") → DiscountingBondEngine(market.yield_curve("UST"))  (캐시)
```

#### key rate DV01 (OREData + OREAnalytics)
```python
sa = SensitivityAnalysis(book, market, cfg.simmarket, cfg.sensitivity, cfg.engine_data)
res = sa.run()
res.key_rate_dv01("UST"); res.parallel_dv01("UST")
```
```
SensitivityAnalysis.run
  ├ ScenarioSimMarket(market, simmarket_params, spreaded=True)   격자 Quote = 0 (기준 대비 이동)
  ├ book.build(EngineFactory(sim_market, engine_data))           포트폴리오를 시뮬레이션 시장에 연결
  ├ SensitivityScenarioGenerator → [기준, kr 1M, …, kr 30Y, parallel]
  ├ ValuationEngine: 시나리오마다 apply_scenario → npvs → reset → NPVCube
  └ 기준 대비 차이 → 민감도 표
```

#### 시간 경과와 날짜별 이력
```python
sim = ScenarioSimMarket(market, params)
sim.update(asof + 1)          # 시장 그대로, 평가일 하루 이동 → theta
# 날짜별 커브 이력: 날짜마다 TodaysMarket을 만들고 결과만 표로
rows = {d: curve_table(TodaysMarket(d, …), "UST", cfg)["zero_cc"] for d in dates}
```

#### IRS 포지션의 PCA 2×2 시나리오 (예정)
```yaml
# positions/book.yaml
- {id: IRS001, trade_type: Swap, notional: 1.0e10, pay_fixed: true,
   fixed_rate: 0.0295, tenor: 5Y, index: CD91, discount: KRW_IRS}
# configs/estimated/pca_krw.yaml  (제로금리 격자 기준, 1 = 1bp)
grid: KRW_IRS
factors:
  PC1: {1Y: 0.92, 2Y: 0.97, 3Y: 1.00, 5Y: 0.98, 7Y: 0.96, 10Y: 0.93, 20Y: 0.88}
  PC2: {1Y: -0.60, 2Y: -0.45, 3Y: -0.30, 5Y: 0.00, 7Y: 0.20, 10Y: 0.40, 20Y: 0.60}
source: research/pca_krw.ipynb, window 2024-01 ~ 2026-09
```
`PcaScenarioGenerator`가 `values[key] = Σ 요인 크기 × 로딩`으로 2×2 시나리오를 만들고, 나머지는 민감도와 같은 경로다.
`Swap.build`는 `LegBuilder`로 레그를 만들고 변동 레그는 `market.index("CD91")`을 쓴다. 지수는 시뮬레이션 시장 커브로 예측한다(fixing은 건드리지 않음).

#### 주식 디지털 옵션의 SSR 반영 델타 (예정)
- 시뮬레이션 시장은 SPX 서페이스를 만기 × moneyness 격자 vol Quote로 재표현한다. 재피팅이 없어 vega 버킷이 지역적이다.
- 생성기가 spot 이동에 SSR 규칙으로 계산한 격자점별 vol 이동을 같은 Scenario에 담는다. 시장은 규칙을 모르고 적용만 한다.
- 분석적 BS는 행사가 vol 하나만 써서 skew 항을 놓친다:
  $D(K) = -\partial C/\partial K = D_{\text{BS}}(K) - \text{Vega}_{\text{BS}}(K)\,\partial\sigma/\partial K$.
  디지털은 `engines.yaml`에서 복제 방식이나 LV로 지정한다.

#### 사용성 비교
| | QuantLib | ORE | QuantTool |
|---|---|---|---|
| 시장 | Quote·커브·Process를 직접 조립 | 설정 파일 → TodaysMarket | YAML → `TodaysMarket` |
| 계약 | Instrument 직접 생성 | portfolio.xml → Trade | positions YAML → Trade |
| 엔진 | `setPricingEngine` 직접 | pricingengine.xml → EngineFactory | engines.yaml → EngineFactory |
| 시나리오 | Quote를 직접 setValue | simulation.xml + sensitivity.xml → 생성기 → ScenarioSimMarket | simmarket.yaml + sensitivity.yaml (+ estimated) → 생성기 → ScenarioSimMarket |
| 실행 | 스크립트 | ore.xml → OREApp | 노트북·파이썬 API (`SensitivityAnalysis` 등) |

### 2.6 설정 파일 예시
```yaml
# configs/market/curves/ust.yaml (구현됨)
name: UST
type: YieldCurve
currency: USD
conventions: UST                 # configs/conventions/rates.yaml의 이름
segments:
  - {type: ZeroCouponBill, quote_family: UST, quote_field: PAR, tenors: [1M, 2M, 3M, 4M, 6M, 1Y]}
  - {type: FixedRateBond,  quote_family: UST, quote_field: PAR, tenors: [2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y]}
interpolation: LogCubic(Discount)

# configs/scenario/simmarket.yaml (← grid.yaml)
yield_curves:
  UST: {tenors: [1M, 3M, 6M, 9M, 1Y, 18M, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 12Y, 15Y, 20Y, 25Y, 30Y],
        interpolation: LinearZero, extrapolation: FlatZero, spreaded: true}

# configs/pricing/engines.yaml (EngineData)
Bond:          {model: DiscountedCashflows, engine: DiscountingBondEngine}   # 구현됨(FixedBond)
Swap:          {model: DiscountedCashflows, engine: DiscountingSwapEngine}
EquityOption:  {model: BlackScholes, engine: AnalyticEuropeanEngine}
EquityDigital: {model: BlackScholes, engine: CallSpreadReplication}
Autocallable:  {model: LocalVol,     engine: MonteCarlo, params: {paths: 100000}}
```

---

## 3. 진행 현황과 다음 단계

최종 갱신 2026-10-27. 브랜치 `claude/confident-hamilton-ui198k`, PR https://github.com/wnsdydchl0/quant-tool/pull/1

### 3.1 시작하기
```bash
git clone https://github.com/wnsdydchl0/quant-tool.git && cd quant-tool
git checkout claude/confident-hamilton-ui198k
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,notebook]"
scripts/fetch_references.sh                              # QuantLib-SWIG, ORE 원본 (선택)
python -m pytest -q && ruff check . && ruff format --check .
```
- `pytest`는 `python -m pytest`로 돌린다. PATH의 `pytest`가 QuantLib 없는 다른 환경을 가리킬 수 있다.
- 처음이면 `notebooks/tutorial/` 00~04를 순서대로 실행하며 코드 위치를 따라간다(현재 이름 기준).
- `tests/fixtures/ust_par_sample.csv`는 재무부 CSV와 형식만 같은 합성 샘플이다. 실제 데이터는 아직 연결 전이다.

### 3.2 완료 (현재 이름 기준)
- 첫 줄기 (UST 커브 → 국채 → key rate DV01): core, config, market, derivatives, scenario, analytics, 노트북 `01_ust_curve`.
- 튜토리얼 노트북 5개: QuantLib 기초 → 시세→커브 → Snapshot 내부 → 계약서→NPV → 시나리오.
- 테스트 81개. 완료 기준 (합성 샘플 기준):

| 기준 | 결과 |
|---|---|
| 헬퍼 재가격 오차 < 0.01bp | 약 1e-9bp |
| QuantLib 직접 조립 채권과 NPV 일치 | 상대오차 1e-12 이내 |
| Σ key rate DV01 = 평행 DV01 | −8,245.95 대 −8,246.30 (한쪽 차분의 2차 항만큼 차이) |
| 격자 시장 기준 NPV ≈ 스냅샷 NPV (절대 모드) | 최대 상대오차 5.1e-4 (30Y) |
| 평행 DV01 vs QuantLib 직접 1bp 이동 | 1e-3 이내 |

### 3.3 다음 단계
1. **ORE 구조로 재구성** (이 문서 승인 후, 커밋 단위)
   1. 패키지 이동·이름 변경(동작 불변, 테스트 그대로 통과).
   2. `MarketImpl` 분리 + `TodaysMarket` asof 고정.
   3. `SimMarket`/`ScenarioSimMarket`: `update(date)`, spreaded 모드(기준 대사 오차 0).
   4. `EngineFactory.builder` 방식, `ValuationEngine`/`NPVCube`, `SensitivityAnalysis`.
   5. 튜토리얼 노트북 새 이름으로 재생성, 튜토리얼 `05_curve_history`(날짜별 시장 → 표, theta).
2. 실제 데이터 연결 (1.4): 출처 결정 → `pipeline/sources/{fred,ecos,…}.py` 수집·정규화 → `CsvLoader` →
   KTB·KRW IRS·USD SOFR 커브 설정과 스왑 구간 헬퍼(`SwapRateHelper`/`OISRateHelper`), `IndexBuilder`, `Swap`·`LegBuilder`.
3. `ParSensitivityAnalysis`: 격자 민감도 → 국채·스왑 par 민감도(헷지 수량).
4. `analytics/app/factorhistory.py`: 날짜별 격자값 → `risk_factors` 표. 옵션 체인 일별 적재 시작.
5. PCA 시나리오 → 주식 줄기 → P&L explain·과거 재현 → 오토콜·LV.
