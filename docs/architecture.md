# QuantTool 아키텍처

이 문서 하나가 설계의 기준이다. 0장은 참조한 두 라이브러리의 정신, 1장은 이 프로젝트가 무엇을 하려는지와 그동안 정한 것,
2장은 그것을 코드로 옮기는 원칙과 구조, 3장은 현재 진행 상황이다.

---

## 0. 레퍼런스의 정신

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

**학습 자료**
- A QuantLib Guide (https://www.quantlibguide.com/) — Library infrastructure 파트 정독, 나머지는 사전처럼.
- Implementing QuantLib (Ballabio) — 설계 이유.
- 직접 해 보기: `notebooks/tutorial/00_quantlib_basics.ipynb`

### 0.2 ORE: 데이터로부터 시장과 계약을 조립해, 포트폴리오를 정합적으로 평가하고 흔드는 시스템

ORE 설계 문서(`references/Engine/Docs/Design/ore_design.tex`, Introduction)의 요약:
- "QuantLib은 개별 상품과 그 평가·분석에 초점을 두고, ORE는 포트폴리오 분석을 목표로 한다."
- **OREData**는 외부 표현(XML 설정·시세 파일)을 메모리의 QuantLib 객체로 **번역**하고, 그 객체로 **Portfolio, Market, Model**을 **조립**한다.
  이것만으로 시장을 만들고 커브를 부트스트랩하고 포트폴리오를 읽어 현재가치와 현금흐름을 계산할 수 있다.
- **OREAnalytics**는 OREData가 조립한 Portfolio·Market·Model을 입력으로 받는다. 핵심은 Market 규격을 그대로 구현하면서
  시장 점을 바꿀 수 있는 **SimMarket**(`ScenarioSimMarket`)이다. 생성기가 만든 Scenario를 이 시장에 적용하면 QuantLib Observer 연쇄로
  "이 시장에 연결된 포트폴리오가 다시 평가될 때 시장 변화에 반응한다."

정리하면 ORE의 정신은 네 가지다.
1. **시장과 계약을 객체로 만든다.** 사람이 손으로 조립하지 않고, 레시피(설정)와 시세를 읽어 빌더가 만든다.
2. **하나의 시장 객체 위에서 모든 계약을 정합적으로 평가한다.** 같은 커브, 같은 관례, 같은 평가일. 표를 조회하는 것을 넘어
   "그 시점의 시장"이라는 일관된 함수 묶음으로 가격을 낸다.
3. **같은 규격의 시장을 규칙에 따라 흔든다.** 흔든 시장도 같은 Market 규격이라 평가 코드가 그대로 동작한다.
   그래서 민감도·스트레스·과거 재현·VaR·XVA가 모두 "시나리오 생성 → 적용 → 재평가"라는 한 방식으로 나온다.
4. **입력도 출력도 표다.** 시세·설정 파일을 받아 결과 리포트(NPV, 민감도, 큐브)를 낸다. 같은 입력이면 같은 결과가 나오고,
   `Examples/*/ExpectedOutput`으로 회귀 검사를 한다.

**층위와 폴더** (`references/Engine/` 기준)
```
QuantLib/                 고정 버전
QuantExt/qle/             QuantLib 확장 (termstructures, pricingengines, models, …)
OREData/ored/             [객체화] 시장·계약·모델
├── configuration/        레시피 (CurveConfig 계열, conventions)
├── marketdata/           Loader, MarketDatum, 커브·vol 빌더, DependencyGraph, Market, MarketImpl, TodaysMarket
├── model/                ModelBuilder 계열
└── portfolio/            Trade 계열, Portfolio, EngineFactory, builders/(상품별 엔진 빌더)
OREAnalytics/orea/        [활용] 위험 분석
├── scenario/             Scenario, ScenarioGenerator 계열, ScenarioSimMarket(+Parameters)
├── engine/               ValuationEngine, 민감도·스트레스·VaR·P&L explain
├── cube/, aggregation/   결과 큐브, XVA 집계
└── app/                  OREApp, analytics/(가격·민감도·VaR·P&L explain 플러그인)
Examples/                 예제 + ExpectedOutput (회귀 테스트)
Docs/                     UserGuide, Design(ore_design), 모델 문서
```
예제 입력 파일: `ore.xml`, `todaysmarket.xml`, `curveconfig.xml`, `conventions.xml`, `pricingengine.xml`, `portfolio.xml`,
`sensitivity.xml`, `stresstest.xml`, `simulation.xml`, `market.txt`(`날짜 키 값`), `fixings.txt`.

**학습 자료** (위에서부터 순서대로)
- `Docs/ore_design.pdf` Introduction과 Library Stack — 전체 그림. QuantLib Guide 같은 역할.
- `Examples/MinimalSetup` — 가격결정에 필요한 최소 설정(시세, todaysmarket, curveconfig, conventions).
- 파이썬으로 직접 해 보기: `pip install open-source-risk-engine`, `Examples/ORE-Python/ExampleScripts`(market.py, swap.py, portfolio.py),
  `Examples/ORE-Python/Notebooks`.
- `Examples/CurveBuilding`(부트스트랩 후 시장 상품 재가격 확인), `Examples/MarketRisk`(민감도, 스트레스, par 변환, VaR, P&L explain).
- `Docs/userguide.pdf` — 설정 파일 사전.
- Modern Derivatives Pricing and Sensitivity Analysis (Lichters, Stamm, Gallagher) — ORE 저자들의 책, 방법론.
- 헤더 다섯 개: `market.hpp`, `todaysmarket.hpp`, `trade.hpp`, `enginefactory.hpp`, `sensitivityscenariogenerator.hpp`.

### 0.3 QuantTool이 가져온 것

QuantLib의 부품을 쓰고, ORE의 정신 1~4를 파이썬 규모로 가볍게 구현한다. C++ 유산(XML, 깊은 상속, 등록용 클래스 계층,
결과 큐브)은 YAML·pydantic, 딕셔너리 등록부, 조합, pandas로 바꾼다(2.1). 노트북에서 객체를 직접 다루는 파이썬 API가 1차 사용 방식이다.

---

## 1. 프로젝트 목표와 결정 사항

### 1.1 핵심

> **QuantTool은 표준화된 시장 데이터로 "그 시점의 시장 객체"를 만들고, 계약을 그 시장에 붙여 정합적으로 평가하며,
> 시장 객체를 규칙에 따라 흔들어 위험을 본다.**

```
표준 시세 표 ──► [객체화] 시장 객체  Snapshot (커브·지수·변동성, 이름으로 조회)   ┐
계약 데이터 ───► [객체화] 계약 객체  Portfolio (Trade → QuantLib 상품 + 엔진)      ┘
                         │
                         ├─► 1) 가격평가     시장 × 계약 → NPV, 현금흐름
                         ├─► 2) 위험         흔든 시장(ScenarioMarket) × 같은 계약 → 민감도, 시나리오 손익
                         └─► 3) 그 밖의 파생 커브 표, P&L explain, 헷지 백테스트 …
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
| 과거 어느 날의 시장을 재현 (그날의 커브·가격·그릭스, 백테스트) | 그 날짜 표 행으로 `Snapshot.build(d)`, 결과는 표로 |
| 과거에 일어난 변화를 오늘 시장에 적용 (historical VaR) | 오늘 스냅샷 + 과거 요인 변화 시나리오 → `ScenarioMarket` |
| 가정한 충격 (민감도, 스트레스, PCA 요인) | 오늘 스냅샷 + 생성기 → `ScenarioMarket` |
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
  │ ② 정규화    pipeline: 공통 스키마로 변환 → data/store/quotes   (키는 core/ids.py 규칙으로 검증)
  │ ③ 검증·적재 pipeline: 단위·결측·휴일·이상치
  ▼
정규화 저장소 (DB 역할, 모든 분석·계산의 원천)
  │ ④ Loader.load(asof)    툴: 그 날짜 행만 조회, 출처를 모른다
  ▼
QuoteStore (메모리, 스냅샷 하나 동안만)  →  커브·상품 객체
```

- 출처마다 형식이 달라도 ② 이후로는 차이가 사라진다. ORE도 시세를 출처와 무관한 `날짜 키 값` 한 형식(`market.txt`)으로 받는다.
- 원본을 남겨 두면 정규화 규칙이 바뀌어도 다시 받지 않고 재처리할 수 있다.
- `QuoteStore`/`SimpleQuote`는 저장소가 아니라 실행용 객체다. 영속 데이터는 정규화 저장소에 있다.

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
| 시나리오 시장 방식 | 원래 시세 bump vs ORE식 격자 재표현 | **격자 재표현으로 결정** (PCA·과거 재현과 좌표 일치, 속도, vol 지역성) |
| 전역 평가일 | 날짜 다른 스냅샷 동시 평가 시 조용한 오류 | `Market.active()` 컨텍스트, 순차 평가 |
| 커브 기준일 | 평가일 따라 이동(현재, theta 시나리오용) vs asof 고정(ORE `TodaysMarket`, `yieldcurve.cpp`의 `asofDate_`) | **asof 고정을 기본으로 바꿀 예정**. 이동은 theta용 옵션. 지금은 다른 날짜 스냅샷을 반드시 `active()` 안에서 조회 |
| Index fixing 전역 공유 | 시나리오가 기준 스냅샷 fixing을 오염 | fixing은 구축 시 1회 로드, 시나리오에서 수정 금지 |
| IV 서페이스 흔들기 | 호가 bump 시 재피팅이 변화를 번지게 함, 느림 | 격자 재표현으로 해결 (재피팅 없음) |
| 격자 보간 오차 | 격자 커브가 원래 부트스트랩 커브와 다름 | `base_reconciliation`, 격자 20점. 합성 샘플 기준 최대 5.1e-4(30Y), 실데이터로 재검토 |
| 격자 바깥 | 외삽 형태가 결과에 영향 | 평탄 제로. QuantLib 1.44 `PiecewiseZeroSpreadedTermStructure`는 Quote 변경 시 외삽 설정이 풀려, 마지막 격자 Quote에 묶은 100Y 끝점으로 처리 |
| 민감도 단위 | 격자 민감도는 제로금리·격자 vol 기준 | `scenario/par.py`로 시장 상품 기준 변환 (ORE parsensitivity 대응) |
| UST par 헬퍼 관례 | par yield = 쿠폰인 가상 채권 가격이 정확히 100이어야 함 | 명목 만기 정규 일정 + Unadjusted 지급(수익률 관례). bill(≤1Y)은 BEY(Act/365, 반년 초과 시 반기복리 1회) → 할인채 가격. 쿠폰은 구축 시점 고정, 수익률 변화는 DerivedQuote로 가격에 전달 |
| 모델 재캘리브레이션 비용 | 시나리오마다 자동 재캘리브레이션 | "모델 고정" 선택지 |
| 단위·형식 | bp/소수, 수익률/가격 혼동 | 저장소는 항상 소수, `ids`에 유형·단위, `Scenario` 검증 |
| 듀얼 커브 (KRW) | CD 프로젝션 vs 할인 커브 | 구조는 지원, 데이터 확보 시 활성화 |

---

## 2. 설계 원칙과 프로젝트 구조

### 2.1 설계 원칙

1. **시장은 규격(인터페이스)이다.** 가격결정 코드는 `Market` 규격만 안다. 관측 시장(`Snapshot`)과 흔든 시장(`ScenarioMarket`)이 같은 규격을 구현한다. (ORE `Market` ← `TodaysMarket` / `ScenarioSimMarket`)
2. **모든 시장 입력은 id가 붙은 `SimpleQuote`이고, 구조물은 그 Quote에 연결된 채로 만든다.** 그래야 시나리오가 "Quote 값 변경 → Observer 전파 → Lazy 재계산"으로 끝난다.
3. **이름으로 참조한다.** 상품·모델은 커브를 객체가 아니라 이름으로 참조하고, 평가 시점에 시장에서 받는다.
4. **레시피(설정)와 제작자(빌더)를 분리한다.** 같은 군은 같은 빌더, 대상별 차이는 설정. (ORE `configuration/` vs `marketdata/` 빌더)
5. **구축 순서는 의존 그래프가 정한다.** 관계는 레시피의 참조에서 자동 추출. (ORE `DependencyGraph`)
6. **계약(무엇)과 평가 방법(어떻게)을 분리한다.** 계약서는 순수 데이터, 엔진 선택은 설정, 조립은 엔진 빌더, 창구는 팩토리. (QuantLib Instrument/PricingEngine, ORE Trade/EngineFactory/EngineBuilder)
7. **시나리오는 데이터이고, 생성·적용·평가는 분리한다.** 생성기 → Scenario(변경 목록) → ScenarioMarket.apply/reset → Runner. (ORE ScenarioGenerator / Scenario / ScenarioSimMarket / ValuationEngine)
   - 7-1. **시나리오 시장은 격자 재표현을 쓴다.** 스냅샷의 커브·서페이스를 고정 격자점(제로금리, IV)에서 샘플링해 SimpleQuote로 보관하고,
     그 Quote를 보간한 구조물로 시장을 구성한다. 시나리오는 격자점 Quote를 흔든다. 요인(PCA 등) 추정과 과거 재현도 같은 격자 좌표를 쓴다.
8. **의존 방향은 한쪽으로.** `config·core → market → derivatives → scenario → analytics`. 아래 층은 위 층을 import하지 않는다 (`tests/test_layering.py`).
9. **파이썬 관례: 평평하게.** 최대 두 단계(패키지 → 파일). 비슷한 부류는 한 파일에 묶고, 커지면 쪼갠다.
10. **표 ↔ 객체 경계를 지킨다.** 들어올 때는 정규화 저장소, 나갈 때는 결과 표. 객체는 짧게 쓰고 저장하지 않는다.

C++ 유산의 단순화:

| ORE | QuantTool |
|---|---|
| XML + 설정 클래스별 읽기·쓰기·검증 | YAML + pydantic |
| 등록용 클래스 계층 | 딕셔너리 등록부 + 데코레이터 (`core/registry.py`) |
| 깊은 상속 (평가 방법 × 자산군) | 규격만 상속, 나머지는 조합 |
| 캐싱 템플릿 | dict |
| 모든 질문에 configuration 인자 | 구성을 묶은 시장 객체 |
| 종류별 map 여러 개 | 이름 체계 하나 + 보관소 |
| 결과 큐브 | pandas |
| 클래스당 파일 하나 | 비슷한 부류는 한 모듈 |

### 2.2 프로젝트 구조

✓ = 구현됨, 나머지는 예정.

```
quant-tool/
├── configs/                          [값]
│   ├── conventions/rates.yaml ✓      (equity.yaml 예정)
│   ├── market/
│   │   ├── todaysmarket.yaml ✓       구축 대상
│   │   ├── curves/ust.yaml ✓         (krw_ktb, usd_sofr, krw_irs, spx_fwd 예정)
│   │   ├── indices/                  cd91.yaml, sofr.yaml
│   │   └── vols/                     spx.yaml
│   ├── pricing/engines.yaml ✓        (models.yaml 예정)
│   ├── scenario/grid.yaml ✓, sensitivity.yaml ✓   (factors, rules, stress 예정)
│   └── estimated/                    pca_krw.yaml, ssr_spx.yaml (값 + 출처, 격자 좌표 기준)
├── positions/ust_book.yaml ✓         평가할 포지션 (예시)
│
├── src/quanttool/
│   ├── config/ ✓                     설정 읽기·검증 (market, pricing, scenario, qlmap)
│   ├── core/ ✓                       ids(이름 규칙), registry(등록부), dependency(의존 그래프)
│   ├── qlext/                        QuantLib 확장 (svi.py …)
│   │
│   ├── market/                       [객체화: 시장]
│   │   ├── quotes.py ✓               Loader, QuoteStore (StoreLoader 예정)
│   │   ├── rates.py ✓                YieldCurveBuilder (스왑 구간·IndexBuilder 예정)
│   │   ├── equity.py                 EquityForwardBuilder, EquityVolBuilder
│   │   ├── market.py ✓               Market(규격), Snapshot(관측 시장)
│   │   ├── persist.py                요인 이력 생성 (날짜별 격자값 → risk_factors)
│   │   └── diagnostics.py ✓          헬퍼 재가격 오차 (무차익 검사 예정)
│   │
│   ├── derivatives/                  [객체화: 계약]
│   │   ├── trades.py ✓               Trade, InstrumentWrapper
│   │   ├── rates.py ✓                FixedBond (IRSwap 예정)
│   │   ├── equity.py                 EquityForward, EquityVanilla, EquityDigital, Autocallable
│   │   ├── portfolio.py ✓            Portfolio
│   │   ├── factory.py ✓              EngineFactory (접수 창구)
│   │   ├── engines.py ✓              엔진 빌더 (기술자)
│   │   └── models.py                 ModelBuilder, CalibrationBasket
│   │
│   ├── scenario/                     [활용: 흔들기]
│   │   ├── grid.py ✓                 ScenarioGrid (격자 정의, 스냅샷 샘플링)
│   │   ├── factors.py ✓              KeyRateFactors (PCAFactors, VegaBuckets 예정)
│   │   ├── rules.py                  StickyStrike, SSRRule
│   │   ├── generators.py ✓           Scenario, SensitivityGenerator (Grid·Stress·Historical 예정)
│   │   ├── scenario_market.py ✓      ScenarioMarket (격자 Quote, 보간 커브, apply / reset)
│   │   ├── par.py                    격자 민감도 → par(시장 상품) 민감도
│   │   └── runner.py ✓               ScenarioRunner, ScenarioResults
│   │
│   └── analytics/                    [활용: 결과 정리]
│       ├── market_monitor.py ✓       커브 표, 모양 지표
│       ├── sensitivity.py ✓          key rate·평행 DV01 표
│       └── pnl_explain.py, reports.py
│
├── pipeline/                         데이터 수집·정규화·적재 (툴 밖). ust_par.py ✓
├── data/                             (gitignore) raw/, store/
├── notebooks/                        tutorial/ ✓ (흐름 따라가기), 01_ust_curve ✓ (시장 해석)
├── research/                         PCA·SSR 추정 → 검증 후 configs/estimated/
├── tests/ ✓                          src와 같은 구조. QuantLib 직접 계산·해석해와 비교 (ORE ExpectedOutput 역할)
├── scripts/fetch_references.sh ✓     references/ 클론
├── docs/architecture.md              이 문서
└── references/                       (gitignore) QuantLib-SWIG, ORE 원본
```

이름 규칙: `configs/`는 값, `src/quanttool/config/`는 그 값을 읽는 코드.

### 2.3 클래스 설계

#### 상속
```
Market (규격)                                     ORE: Market
 ├ Snapshot ✓                                     ORE: MarketImpl + TodaysMarket
 └ ScenarioMarket ✓                               ORE: ScenarioSimMarket
Loader ← InMemoryLoader ✓, UstParCsvLoader ✓, StoreLoader     ORE: Loader ← CSVLoader, InMemoryLoader
MarketBuilder ← YieldCurveBuilder ✓, IndexBuilder, EquityForwardBuilder, EquityVolBuilder
Trade ← FixedBond ✓, IRSwap, EquityForward, EquityVanilla, EquityDigital, Autocallable
EngineBuilder ← DiscountingBondEngineBuilder ✓, DiscountingSwapEngineBuilder,
                AnalyticBSEngineBuilder, ReplicationDigitalEngineBuilder, LocalVolMCEngineBuilder
ModelBuilder ← LocalVolBuilder, HestonBuilder
RiskFactors ← KeyRateFactors ✓, PCAFactors, VegaBuckets
DependencyRule ← StickyStrike, SSRRule
ScenarioGenerator ← SensitivityGenerator ✓, GridGenerator, StressGenerator, HistoricalGenerator
```

#### 구성
```
Snapshot          QuoteStore, 이름 → RelinkableHandle 보관소, (구축 시) Loader, DependencyGraph, MarketBuilder들
EngineFactory     Market, Config(엔진 설정·관례), EngineBuilder 캐시
EngineBuilder     Market(팩토리가 건넴), 엔진 캐시, (필요 시) ModelBuilder
Trade             계약 데이터 / build 후 InstrumentWrapper(QuantLib Instrument, 승수)
Portfolio         Trade들
ScenarioGrid      격자 정의 (커브별 만기 격자, 서페이스별 만기 × moneyness 격자)
ScenarioMarket    기준 Market, ScenarioGrid, sim_data(RiskFactorKey → SimpleQuote), 격자 Quote를 보간한 커브 Handle
Scenario          label, RiskFactorKey → 이동량 (데이터)
ScenarioGenerator 격자, RiskFactors, (규칙), 이동 크기
ScenarioRunner    Portfolio, ScenarioMarket, Config
```

#### 핵심 시그니처 (구현 기준)
```python
class Market(ABC):                                    # 메뉴판
    asof: date
    def quote(self, quote_id: str) -> ql.QuoteHandle: ...
    def yield_curve(self, name: str) -> ql.YieldTermStructureHandle: ...
    def index(self, name: str) -> ql.Index: ...                       # 예정
    def equity_spot(self, name: str) -> ql.QuoteHandle: ...           # 예정
    def dividend_curve(self, name: str) -> ql.YieldTermStructureHandle: ...  # 예정
    def equity_vol(self, name: str) -> ql.BlackVolTermStructureHandle: ...   # 예정
    def active(self) -> ContextManager: ...           # evaluationDate = asof, 끝나면 복원

class Snapshot(Market):
    @classmethod
    def build(cls, asof: date, cfg: Config, loader: Loader) -> "Snapshot": ...

class MarketBuilder(ABC):
    kind: str                                         # registry 키 ("YieldCurve" …)
    def __init__(self, cfg: Config): ...
    def requires(self, recipe) -> list[Node]: ...     # 의존 그래프용 참조
    def build(self, recipe, quotes: QuoteStore, market: Market) -> BuiltCurve: ...

class Trade(BaseModel, ABC):                          # 계약 데이터 (pydantic)
    id: str
    type: str                                         # registry 키 = engines.yaml 키
    def build(self, factory: EngineFactory) -> None: ...
    def npv(self) -> float: ...

class EngineFactory:
    def __init__(self, market: Market, cfg: Config): ...
    def engine_for(self, trade: Trade) -> ql.PricingEngine: ...
    def conventions(self, name: str) -> RateConventions: ...

@dataclass(frozen=True)
class RiskFactorKey:                                  # ORE: QuantExt/qle/termstructures/scenario.hpp
    kind: str                                         # "zero", "equity_spot", "equity_vol" …
    name: str                                         # "UST", "SPX"
    point: tuple = ()                                 # ("5Y",) 또는 ("1Y", 1.00). ORE는 정수 인덱스

class ScenarioGrid:                                   # ORE: ScenarioSimMarketParameters
    def keys(self, name=None) -> list[RiskFactorKey]: ...
    def sample(self, market: Market) -> dict[RiskFactorKey, float]: ...

@dataclass(frozen=True)
class Scenario:
    label: tuple | str
    shifts: dict[RiskFactorKey, float]                # 소수 (금리 0.0001 = 1bp)

class ScenarioMarket(Market):                         # ORE: ScenarioSimMarket
    def __init__(self, base: Market, grid: ScenarioGrid): ...
    def apply(self, scenario: Scenario) -> None: ...  # 기준 + 이동량 (누적 아님)
    def reset(self) -> None: ...
    def base_reconciliation(self, portfolio, cfg) -> pd.DataFrame: ...

class ScenarioRunner:
    def __init__(self, portfolio: Portfolio, smkt: ScenarioMarket, cfg: Config): ...
    def run(self, scenarios: Iterable[Scenario]) -> ScenarioResults: ...   # .base, .npv, .pnl
```

#### 불변 조건
- 모든 시장 입력은 `QuoteStore`의 `SimpleQuote`이며 id는 `core/ids.py` 규칙을 따른다.
- 시나리오에서 흔드는 대상은 `ScenarioGrid`의 격자점이다. 흔들고 싶은 것은 격자에 정의되어 있어야 한다.
- 시나리오 시장의 기준 NPV는 스냅샷 기준 NPV와 허용 오차 이내로 일치해야 한다 (`base_reconciliation`).
- 요인 로딩·과거 시나리오는 격자 좌표(`RiskFactorKey`)로 정의한다.
- 가격결정·시나리오 코드는 `Market` 규격 메소드만 쓴다. `Snapshot` 내부를 직접 만지지 않는다.
- 계약서는 엔진·모델을 모른다. 엔진 선택은 `engines.yaml`.
- `ScenarioRunner`는 포트폴리오를 시나리오마다 재조립하지 않는다. 한 번 조립 후 apply → npv → reset.
- 날짜가 다른 시장은 `active()` 안에서 순차적으로만 평가한다.

### 2.4 사용 흐름

#### 커브 보기와 국채 평가 (구현됨, `notebooks/tutorial/02`, `03`)
```python
cfg  = load_config("configs")
snap = Snapshot.build(date(2026, 10, 23), cfg, loader)
curve_table(snap, "UST", cfg)                           # 할인계수, 제로, 1Y 선도, par
book = Portfolio.load("positions/ust_book.yaml")
with snap.active():
    book.build(EngineFactory(snap, cfg)); book.npvs()
```
```
Snapshot.build
  ├ evaluationDate = asof
  ├ loader.load(asof) → MarketQuote("UST/PAR/10Y", 0.0398), …
  ├ QuoteStore(quotes)                               id → SimpleQuote
  ├ DependencyGraph(builder.requires).order(targets) → [("YieldCurve", "UST")]
  └ YieldCurveBuilder.build(recipe, store, snap)
       수익률 Quote → DerivedQuote(가격) → BondHelper
       → PiecewiseLogCubicDiscount → RelinkableYieldTermStructureHandle → 보관소 등록
curve_table → snap.yield_curve("UST").zeroRate(…)    ← 여기서 첫 부트스트랩 (Lazy)
FixedBond.build(factory) → ql.FixedRateBond + factory.engine_for → DiscountingBondEngine(market.yield_curve("UST"))
```

#### key rate DV01 (구현됨, `notebooks/tutorial/04`)
```python
grid = ScenarioGrid(cfg.grid)
res  = ScenarioRunner(book, ScenarioMarket(snap, grid), cfg).run(
           SensitivityGenerator(grid, cfg.sensitivity).generate())
key_rate_dv01(res, cfg.sensitivity, "UST")
```
```
ScenarioMarket(snap, grid)
  ├ grid.sample(snap): UST 커브에서 1M…30Y 제로금리 읽기
  ├ sim_data[RiskFactorKey("zero", "UST", ("5Y",))] = SimpleQuote(…)
  └ 격자 Quote를 제로 선형 보간하는 커브 → Handle (원래 헬퍼·부트스트랩은 쓰지 않음)
ScenarioRunner.run
  ├ base_reconciliation: 스냅샷으로 조립한 NPV vs 격자 시장으로 조립한 NPV
  └ for s in scenarios: smkt.apply(s) → npvs() → smkt.reset()
```

#### 날짜별 커브 이력 (예정 패턴)
```python
rows = {}
for d in dates:
    snap = Snapshot.build(d, cfg, loader)
    with snap.active():
        rows[d] = curve_table(snap, "UST", cfg)["zero_cc"]
history = pd.DataFrame(rows).T            # 객체는 버리고 결과만 표로
```

#### IRS 포지션의 PCA 2×2 시나리오 (예정)
```yaml
# positions/book.yaml
- {id: IRS001, type: IRSwap, notional: 1.0e10, pay_receive: pay_fixed,
   fixed_rate: 0.0295, tenor: 5Y, index: CD91, discount: KRW_IRS}
# configs/estimated/pca_krw.yaml  (제로금리 격자 기준, 1 = 1bp)
grid: KRW_IRS
factors:
  PC1: {1Y: 0.92, 2Y: 0.97, 3Y: 1.00, 5Y: 0.98, 7Y: 0.96, 10Y: 0.93, 20Y: 0.88}
  PC2: {1Y: -0.60, 2Y: -0.45, 3Y: -0.30, 5Y: 0.00, 7Y: 0.20, 10Y: 0.40, 20Y: 0.60}
source: research/pca_krw.ipynb, window 2024-01 ~ 2026-09
```
```python
factors = PCAFactors.load("configs/estimated/pca_krw.yaml")
gen = GridGenerator(factors, {"PC1": [-25, 25], "PC2": [-10, 10]})   # shifts[key] = Σ 크기 × 로딩
res = ScenarioRunner(book, ScenarioMarket(snap, grid), cfg).run(gen.generate())
```
IRSwap.build는 `market.index("CD91")`로 변동 레그를 만들고, Index는 시나리오 시장의 격자 커브로 예측한다(fixing은 건드리지 않음).

#### 주식 디지털 옵션의 SSR 반영 델타 (예정)
- 시나리오 시장은 SPX 서페이스를 만기 × moneyness 격자 vol Quote로 재표현한다. 재피팅이 없어 vega 버킷이 지역적이다.
- 생성기가 spot 이동에 SSR 규칙으로 계산한 격자점별 vol 이동을 같은 Scenario에 담는다. 시장은 규칙을 모르고 적용만 한다.
- 분석적 BS는 행사가 vol 하나만 써서 skew 항을 놓친다:
  $D(K) = -\partial C/\partial K = D_{\text{BS}}(K) - \text{Vega}_{\text{BS}}(K)\,\partial\sigma/\partial K$.
  디지털은 `engines.yaml`에서 복제 방식이나 LV로 지정한다.

#### 사용성 비교
| | QuantLib | ORE | QuantTool |
|---|---|---|---|
| 시장 | Quote·커브·Process를 직접 조립 | 설정 파일 → TodaysMarket | 설정 파일 → `Snapshot.build` |
| 계약 | Instrument 직접 생성 | portfolio.xml → Trade | positions YAML → Trade |
| 엔진 | `setPricingEngine` 직접 | pricingengine.xml → EngineFactory | engines.yaml → EngineFactory |
| 시나리오 | Quote를 직접 setValue | simulation.xml(격자) + sensitivity.xml → 생성기 → ScenarioSimMarket | grid.yaml + scenario YAML + estimated → 생성기 → ScenarioMarket |
| 실행 | 스크립트 | ore.xml → OREApp | 노트북·파이썬 API |

### 2.5 설정 파일 예시
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

# configs/market/vols/spx.yaml (예정)
name: SPX_VOL
type: EquityVol
forward: SPX_FWD                 # 의존 그래프가 이 참조로 순서 결정
method: SSVI

# configs/pricing/engines.yaml
FixedBond:     {model: Discounting,  engine: DiscountingBond}       # 구현됨
IRSwap:        {model: Discounting,  engine: DiscountingSwap}
EquityVanilla: {model: BlackScholes, engine: AnalyticEuropean}
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
- 처음이면 `notebooks/tutorial/` 00~04를 순서대로 실행하며 코드 위치를 따라간다.
- `tests/fixtures/ust_par_sample.csv`는 재무부 CSV와 형식만 같은 합성 샘플이다. 실제 데이터는 아직 연결 전이다.

### 3.2 완료
- 첫 줄기 (UST 커브 → 국채 → key rate DV01): core, config, market, derivatives, scenario, analytics, 노트북 `01_ust_curve`.
- 튜토리얼 노트북 5개: QuantLib 기초 → 시세→커브 → Snapshot 내부 → 계약서→NPV → 시나리오.
- 테스트 81개. 완료 기준 (합성 샘플 기준):

| 기준 | 결과 |
|---|---|
| 헬퍼 재가격 오차 < 0.01bp | 약 1e-9bp |
| QuantLib 직접 조립 채권과 NPV 일치 | 상대오차 1e-12 이내 |
| Σ key rate DV01 = 평행 DV01 | −8,245.95 대 −8,246.30 (한쪽 차분의 2차 항만큼 차이) |
| 격자 시장 기준 NPV ≈ 스냅샷 NPV | 최대 상대오차 5.1e-4 (30Y) |
| 평행 DV01 vs QuantLib 직접 1bp 이동 | 1e-3 이내 |

### 3.3 다음 단계
1. 커브 기준일 asof 고정을 기본으로 (1.5), 튜토리얼 `05_curve_history`(날짜별 스냅샷 → 표).
2. 실제 데이터 연결 (1.4): 출처 결정 → `pipeline/sources/{fred,ecos,…}.py` 수집·정규화 → `StoreLoader` →
   KTB·KRW IRS·USD SOFR 커브 설정과 스왑 구간 헬퍼(`SwapRateHelper`/`OISRateHelper`), `IndexBuilder`.
3. `scenario/par.py`: 격자 민감도 → 국채·스왑 par 민감도(헷지 수량).
4. `market/persist.py`: 날짜별 격자값 → `risk_factors` 표. 옵션 체인 일별 적재 시작.
5. IRSwap, PCA 시나리오 → 주식 줄기 → P&L explain·과거 재현 → 오토콜·LV.
