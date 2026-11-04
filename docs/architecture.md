# 소스 설계구조
기본 설정과 데이터 : 
1. config : 
  - configs/yaml : 문서화된 세팅
  - config.py : 
2. quoted data : 외부 데이터

시장 객체화 :
1. quotes.py : 시세DB를 {날짜: {키: 값}}으로 딕셔너리화
2. MarketObject : 시장 기본단위
  - 설계구조  :
    - `.handle`:
    - `.factors()`: `{이름: SimpleQuote}` (값은 기준 대비 이동, 기준 0)
    - `.refresh()`: 재갱신
    - `.roll(d)`: 시간 이동 > 그리고 이거 없애는거 어때? 왜냐면 roll도 시간을 옮기고 refresh 하는거아냐? 분리할 이유 있나? 
    - (선택) `.depends_on`: 기대는 시장 객체 이름 목록. 있으면 파생 객체? > 그리고 의존구조도 메소드나 이런거로 남겨둬야 파악가능해?  
 - curve :
- 구간 종류마다 헬퍼 함수 `HELPERS[type](key, quote, tenor, segment, ctx)`
  - `ctx`: 관례, 결제일, 할인 커브 Handle, 지수
- 커브 레시피(`CurveConfig`)
  - `discount_curve`: 헬퍼 할인. 듀얼 커브용
  - 구간별 `index`: OIS·Swap·Deposit 헬퍼의 지수. 지수의 예측 커브가 다른 커브면 그 커브가 먼저 만들어진다
- `build_curve(...) → BuiltCurve(.curve, .helpers, .quotes())`
- 진단: `helper_repricing(built, asof)`, `curve_table(handle, conventions)`, `curve_shape(table)`
- 도구: `bill_price`, `bill_yield`, `evaluation_date(d)`

3. Market : 시장 기본단위로 이뤄진 시장
  - 생성 함수: `build_market(asof, quotes[asof], cfg, linked=False)`
  - 속성
    - `.asof`, `.date`(지금 평가일)
    - `.objects`(이름 → 시장 객체), `.indices`(이름 → 지수) # > 여기서 왜 INDICIES는 또 따로보는거야 objects와 달리 ?
    - `.built`(부트스트랩 결과, 진단용), `.current`(적용 중인 시나리오) > built, current 활용 예시좀 알려줘 아직 이해가 안되는 개념이야  
  - 오브젝트 조회(그리고 이거 궁금한데 적절한 네이밍이 마켓오브젝트와 마켓인거야? 국룰 네이밍?)
    - `market["UST"]` → 상품이 연결되는 Handle (커브·vol: RelinkableHandle, 현물: QuoteHandle, Heston: 모델)
    - `market.index("CD91")` → 예측 커브(요인 포함)에 연결된 `ql.IborIndex`
- 요인: `.factors()` → `{"UST/5Y": SimpleQuote, "SPX/spot": …, "SPX_VOL/1Y/90": …, "SPX_HESTON/v0": …}`
- 시나리오: `.apply(s)`, `.reset()`, `with market.scenario(s): …`
  - 누적되지 않는다: 요인 = 기준 + 이동.
  - 바뀐 객체와 **그에 기대는 객체**(`depends_on`)를 의존 순서로 `refresh`한다.
- 시간: `.roll(d)`(평가일 d, ForwardForward, 의존 순서, 지난 fixing은 오늘 선도로), `.active()`(평가일을 시장 날짜로 두는 with 블록)
> 구현적인 궁금인데 왜 Market클래스의 생성자로 build market을 두는게 아니라 굳이 분리해서 함수를 정의한거야 ? 그리고 그냥 마켓 객체의 클래스 메소드나 변수들등등 설명하면서 설계의도와 기능 알려줘.



**`Portfolio`** (`portfolio.py`)
- 만들기
  - 파일: `Portfolio.from_file("positions/ust_book.yaml", …, products=cfg.products)`
  - 레코드: `Portfolio.from_records([{"id": …, "product": "KRW_IRS_CD91", …}], cfg.products)`
  - 코드: `Portfolio([trade(cfg, "SPX_EURO", id="c1", option_type="Call", strike=6000, expiry=…, quantity=10)])`
  - 템플릿 위에 거래 값을 덮는다. 템플릿 없이 모든 필드를 직접 써도 된다.
- `.build(market, cfg)`: 거래마다 `BUILDERS[type]`으로 상품을 만들고, 엔진을 고른다.
  - 엔진: 거래의 `engine` 필드 → 없으면 `pricing.yaml products[type]`
  - 엔진 공유: 같은 (엔진, 시장 객체들) 조합은 엔진 하나를 공유한다.
  - 다른 시장에 붙이려면 다시 부른다.
- `.npvs()`: 거래별 NPV × `multiplier()`(시장의 현재 날짜·시나리오), `.npv()`
- `.trades`, `.instruments`, `.engines`(`(엔진, 시장 객체…)` → 엔진)

| 상품 | 시장 객체 | 엔진 |
|---|---|---|
| `Bond` | `curve` | `DiscountingBond` |
| `IRSwap` (고정 vs Ibor) | `index`(예측), `discount` | `DiscountingSwap` |
| `EquityOption` (유럽형) | `underlying`, `curve`, `dividend`, `vol`, (`model`) | `AnalyticBS`, `FdBS`(격자는 `pricing.yaml engines`), `AnalyticHeston` |

**시나리오** (`analysis/scenarios.py`): 모두 `dict[요인 키, 이동]`을 돌려준다
- `parallel(market, "UST", 0.001)`
- `bucket(market, "UST", shift_tenors, j, size)`: 삼각 가중
- `from_loadings("UST", {만기: 로딩}, 크기)`, `combine(s1, s2, …)`
- `ssr(market, "SPX", "SPX_VOL", r, x)`: 현물 상대 이동 r과 격자 vol 이동
  Δσ(T,K) = σ(T, K·(1+r)^(x−1)) − σ(T,K)를 함께 담는다.
  x=1이면 sticky strike, x=0이면 sticky moneyness.

**리스크** (`analysis/risk.py`)
- `key_rate(book, market, cfg.risk, "UST") → {"delta": 만기 × 거래, "gamma": …}` (1bp당 손익)
  - 상품별 규칙: `risk.overrides[거래 id 또는 종류] = {shift_size, scheme}`. 그 크기·방식으로 계산한 뒤 1bp로 환산한다.
  - 이동 만기: `risk.shift_tenors[커브]` (없으면 요인 격자)
- `factor_delta(book, market, {이름: 요인 키 또는 h → 시나리오 함수}, size)`: 아무 요인·규칙의 중심 차분 delta·gamma
  - 예 `{"spot": "SPX/spot", "ssr=0": lambda r: ssr(market, "SPX", "SPX_VOL", r, 0.0)}`
- `cross_gamma(book, market, risk)`, `scenario_pnl(book, market, {이름: 시나리오})`, `theta(book, market, 다음 날)`
