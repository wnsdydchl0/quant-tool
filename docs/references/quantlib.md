# 레퍼런스: QuantLib

### 1 층위
```
0. 기반
   - 시간 : Date, Period, Calendar, DayCounter, Schedule, Settings.evaluationDate
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

### 2 연결 장치
| 장치 | 의미 | 쓰임 |
|---|---|---|
| Handle | 객체가 아니라 "자리"를 가리킴. `RelinkableHandle.linkTo`로 교체 | 커브·vol 공유와 교체 |
| Observer | 의존 관계 구독, 변경 시 알림 연쇄 전파 | Quote → 커브 → 엔진 → 상품 |
| LazyObject | 알림 시 "낡음" 표시만, 요청 시 계산 | 커브 부트스트랩, 상품 NPV |

넘기는 방식 세 단계: 숫자(연동 없음) / `Handle(obj)`(내용 변화 전파) / `RelinkableHandle`(객체 교체까지).

### 3 Instrument와 PricingEngine의 대화
```
option.NPV()
  → 낡지 않았으면 캐시 반환 (LazyObject)
  → 상품이 엔진의 arguments(주문서)에 계약 조건 기입   setupArguments
  → 엔진이 자기가 쥔 시장 데이터로 계산, results 작성   calculate
  → 상품이 results를 읽어 저장                         fetchResults
```
엔진은 **생성 시 시장 갈래**(Process, 커브 핸들)를 쥐고, **계산 시 계약 갈래**(arguments)를 받는다.

### 4 대표 사용 흐름
```python
spot, r, vol = ql.SimpleQuote(100), ql.SimpleQuote(0.03), ql.SimpleQuote(0.2)
rf  = ql.FlatForward(0, cal, ql.QuoteHandle(r), ql.Actual365Fixed())
bv  = ql.BlackConstantVol(0, cal, ql.QuoteHandle(vol), ql.Actual365Fixed())
proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(spot), div_h,
                                    ql.YieldTermStructureHandle(rf),
                                    ql.BlackVolTermStructureHandle(bv))
opt = ql.EuropeanOption(ql.PlainVanillaPayoff(ql.Option.Call, 100), ql.EuropeanExercise(T))
opt.setPricingEngine(ql.AnalyticEuropeanEngine(proc))
opt.NPV(); vol.setValue(0.21); opt.NPV()      # 시세 변경 → 자동 재평가
```
QuantTool은 이 조립을 **빌더와 팩토리 뒤로 숨긴다.** 사용자는 `Snapshot`, 계약서, `Portfolio`만 다룬다.

### 5 주의할 전역 상태
- `Settings.evaluationDate`: 전역 하나. 날짜가 다른 시장을 동시에 평가할 수 없다.
- Index fixing: 지수 이름 기준 전역 저장. 같은 이름의 Index는 fixing을 공유한다.

### 6 학습 자료
- A QuantLib Guide (quantlibguide.com) — Library infrastructure 파트 정독, 나머지는 사전처럼.
- Implementing QuantLib (Ballabio) — 설계 이유.

---
