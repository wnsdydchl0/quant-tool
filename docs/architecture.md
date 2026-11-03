**시장 객체 규격 `MarketObject`** (`market/market.py`) — 새 객체는 이것만 맞추면 시장·시나리오·리스크가 그대로 동작한다
- `.handle`: 상품·엔진이 연결되는 자리
- `.factors()`: `{이름: SimpleQuote}` (값은 기준 대비 이동, 기준 0)
- `.refresh()`: 요인이 바뀐 뒤 다시 만들 일이 있으면 여기서 한다. 커브는 Observer로 따라와서 할 일 없음
- `.roll(d)`: 시간 이동
- (선택) `.depends_on`: 기대는 시장 객체 이름 목록. 있으면 파생 객체
>코멘트 : 원본 코드보니까 Protocol 상속받아서 정의하던데 그 클래스는 무엇이고, 의도와 기능이 뭐야? 왜 필요한거야 Marketobject라는 클래스가? 

**`Market`** (`market/market.py`) — 시장 객체 묶음
- 객체생성 함수: `build_market(asof, quotes[asof], cfg, linked=False)`
  - 커브는 의존 먼저 순서(`cfg.build_order()`)로 만든다.
  - 그다음 지수, 주식 객체, 파생 모델을 만든다.
- 속성
  - `.asof`, `.date`(지금 평가일)
  - `.objects`(이름 → 시장 객체), `.indices`(이름 → 지수)
  - `.built`(부트스트랩 결과, 진단용), `.current`(적용 중인 시나리오)
- 조회
  - `market["UST"]` → 상품이 연결되는 Handle (커브·vol: RelinkableHandle, 현물: QuoteHandle, Heston: 모델)
  - `market.index("CD91")` → 예측 커브(요인 포함)에 연결된 `ql.IborIndex`
- 요인: `.factors()` → `{"UST/5Y": SimpleQuote, "SPX/spot": …, "SPX_VOL/1Y/90": …, "SPX_HESTON/v0": …}`
- 시나리오: `.apply(s)`, `.reset()`, `with market.scenario(s): …`
  - 누적되지 않는다: 요인 = 기준 + 이동.
  - 바뀐 객체와 **그에 기대는 객체**(`depends_on`)를 의존 순서로 `refresh`한다.
- 시간: `.roll(d)`(평가일 d, ForwardForward, 의존 순서, 지난 fixing은 오늘 선도로), `.active()`(평가일을 시장 날짜로 두는 with 블록)
> 구현적인 궁금인데 왜 Market클래스의 생성자로 build market을 두는게 아니라 굳이 분리해서 함수를 정의한거야 ? 그리고 그냥 마켓 객체의 클래스 메소드나 변수들등등 설명하면서 설계의도와 기능 알려줘.

**커브** (`market/curves.py`)
- 구간 종류마다 헬퍼 함수 `HELPERS[type](key, quote, tenor, segment, ctx)`
  - `ctx`: 관례, 결제일, 할인 커브 Handle, 지수
- 커브 레시피(`CurveConfig`)
  - `discount_curve`: 헬퍼 할인. 듀얼 커브용
  - 구간별 `index`: OIS·Swap·Deposit 헬퍼의 지수. 지수의 예측 커브가 다른 커브면 그 커브가 먼저 만들어진다
- `build_curve(...) → BuiltCurve(.curve, .helpers, .quotes())`
- 진단: `helper_repricing(built, asof)`, `curve_table(handle, conventions)`, `curve_shape(table)`
- 도구: `bill_price`, `bill_yield`, `evaluation_date(d)`

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

## 4. 사용 예

```python
from datetime import date
from quanttool.config import load_config
from quanttool.market.quotes import read_quotes
from quanttool.market import build_market
from quanttool.portfolio import Portfolio, trade
from quanttool.analysis.scenarios import parallel, from_loadings, ssr
from quanttool.analysis.risk import key_rate, factor_delta, scenario_pnl, theta

cfg = load_config("configs")
quotes = read_quotes("tests/fixtures/market_sample.txt")
asof = date(2026, 10, 23)

market = build_market(asof, quotes[asof], cfg)                  # 커브·지수·주식·모델을 한 번, 이름으로
book = Portfolio.from_file("positions/ust_book.yaml", "positions/krw_swaps.yaml",   # 예시 북
                           "positions/spx_options.yaml", products=cfg.products)
book = Portfolio([*book.trades.values(),                                          # 코드로 한 건 추가
                  trade(cfg, "SPX_EURO", id="SPX_3M_C105", option_type="Call", strike=6300,
                        expiry=date(2027, 1, 22), quantity=5)]).build(market, cfg)
book.npvs()

kr = key_rate(book, market, cfg.risk, "CD91")                   # 예측 커브 delta·gamma (만기 × 거래)
pnl = scenario_pnl(book, market, {
    "parallel +10bp": parallel(market, "UST", 0.0010),
    "steepener": from_loadings("UST", {"2Y": -1.0, "10Y": 1.0}, 0.0005),
    "SPX -5% (ssr 0.5)": ssr(market, "SPX", "SPX_VOL", -0.05, 0.5),
})
deltas = factor_delta(book, market, {
    "sticky strike": "SPX/spot",
    "sticky moneyness": lambda r: ssr(market, "SPX", "SPX_VOL", r, 0.0),
}, 0.01)
th = theta(book, market, date(2026, 10, 26))
```

## 5. 확장

| 하고 싶은 것 | 어디에 |
|---|---|
| 커브 추가 (KRW 국채, SOFR) | `configs/curves/*.yaml`(+ 지수면 `indices.yaml`). 새 헬퍼 종류면 `curves.HELPERS`에 함수 하나 |
| 다른 주식·지수 | `configs/equity/*.yaml` 하나 (시세 키, 격자, Heston 설정) |
| 피팅 vol 서페이스 (SVI·SABR) | `market/equity.py`에 `MarketObject`를 맞춘 클래스. 요인 = 파라미터 Quote, `refresh()`에서 서페이스를 다시 만들어 handle에 연결 |
| 다른 모델 (local vol, SABR 모델) | `HestonModelObject`처럼 `depends_on` + `refresh`(캘리브레이션 정책). 시장이 의존 순서로 부른다 |
| 상품 추가 | `portfolio.py`의 `TRADES`·`BUILDERS`에 명세·조립 함수(`market_names()`, `multiplier()`), 자주 쓰면 `products.yaml`에 템플릿 |
| 엔진 추가·교체 | `ENGINES`에 람다 한 줄, `pricing.yaml products`에서 기본으로 고르거나 거래의 `engine` 필드. 인자는 `pricing.yaml engines` |
| 연동 규칙 (SSR, PCA, 상관 충격) | `analysis/scenarios.py`에 시나리오 함수. 여러 객체의 요인을 한 사전에 함께 |
| 그릭 계산 규칙 수정 | `risk.yaml`의 `overrides`, `factor_delta`에 규칙 함수, 또는 `analysis/risk.py`에 계산 함수 |
| par 민감도 (헷지 수량) | `analysis/risk.py`에 함수 |
| 헷지 백테스트 | `analysis/backtest.py`: 날짜마다 `build_market` → 북 + 헷지 거래(`trade`) → 수정 그릭으로 헷지 수량 → 다음 날 시장에서 재평가 → 손익 |
| roll-down theta | `CurveFactors.roll`에 "만기별 제로 그대로" 방식 |
| 실시간 포지션 | 바깥 OMS 어댑터 `read_positions()` → 같은 레코드 모양 → `Portfolio.from_records(…, cfg.products)` |
| 실제 데이터 | `market/quotes.py`에 DB 읽기 함수 (같은 `{날짜: {키: 값}}` 모양). 데이터는 `../market-data` 레포 |

## 6. 결정 사항

**ORE에서 가져온 아이디어** (클래스 구조는 따르지 않고, 사전과 함수로 옮겼다)

| ORE | 여기 | ORE 파일 |
|---|---|---|
| TodaysMarket: 시장을 이름으로 묶고, 커브 의존 그래프 순서로 만든다 | `Market`, `build_market`, `Config.build_order` | `OREData/ored/marketdata/todaysmarket.hpp`, `dependencygraph.hpp` |
| 커브 빌더: 구간(segment) 종류별 헬퍼, 할인 커브 지정 | `curves.HELPERS`, `CurveConfig.discount_curve`, 구간 `index` | `OREData/ored/marketdata/yieldcurve.hpp` |
| EngineFactory + pricingengine.xml: 상품 종류별 엔진을 설정으로 | `ENGINES` + `pricing.yaml`, 엔진 공유 | `OREData/ored/portfolio/enginefactory.hpp` |
| recalibrateModels: 시나리오에서 모델을 다시 캘리브레이션할지 | `HestonModelObject` `recalibrate_on` | `OREAnalytics/orea/engine/sensitivityanalysis.cpp` |
| 지수·모델이 기초 커브·서페이스 Handle에 연결 | `Market.index`, 파생 객체 `depends_on` | `todaysmarket.hpp` |
| spreaded 시뮬레이션 커브, ForwardForward 시간 이동 | `CurveFactors`, `VolSurface.roll` | `OREAnalytics/orea/scenario/scenariosimmarket.hpp` |

| 항목 | 결정 |
|---|---|
| 범위 | 신용(CDS, XVA)과 통계적 리스크(VaR, 노출 시뮬레이션)는 제외한다. 몬테카를로는 상품 엔진 안에만 둔다 |
| UST par 헬퍼 | 명목 만기 정규 일정 + Unadjusted 지급이면 par 채권 가격이 정확히 100이다. bill은 BEY → 할인채 가격 |
| 격자 바깥 | 평탄 제로로 둔다. QuantLib 1.44 `PiecewiseZeroSpreadedTermStructure`는 Quote가 바뀌면 외삽 설정이 풀린다. 그래서 마지막 격자 Quote에 묶은 100Y 끝점으로 처리한다 |
| 의존 커브와 얼림 | 듀얼 커브의 CD91 헬퍼는 KOFR **요인 Handle**로 할인한다. 커브는 오늘 시세로 얼린다. KOFR를 흔들면 CD91 할인은 움직이지만 CD91은 다시 부트스트랩하지 않는다(`linked=True`에서만 다시 푼다) |
| vol 서페이스 | 격자 IV → `BlackVarianceSurface`(분산 쌍선형), 행사가 바깥은 평탄. 행사가는 asof 현물 기준 절대값이고, 기본 연동은 sticky strike다 |
| Heston 캘리브레이션 | 서페이스 격자점마다 `HestonModelHelper`(가격 상대오차), LevenbergMarquardt. 헬퍼 만기는 격자 날짜와 맞추려고 일수 + NullCalendar를 쓴다. 기본 정책은 현물·vol에 재캘리브레이션, 금리·배당에는 고정 |
| 시간 이동과 fixing | `roll(d)`는 [asof, d) 사이 지수 fixing을 오늘의 예측 선도로 채운다(ForwardForward 실현). asof로 돌아오면 원래 이력으로 되돌린다 |
| 전역 평가일 | 상품 값은 그 시장의 `active()` 안에서 낸다 (`Portfolio.npvs`, 캘리브레이션이 알아서) |
| 민감도 단위 | key rate는 격자 제로금리 1bp당 손익, `factor_delta`는 넘긴 size 이동당 손익. par 기준은 예정 |

## 7. 현황과 다음 단계

- 시작: `pip install -e ".[dev,notebook]"`
- 검사: `python -m pytest -q && ruff check . && ruff format --check .` (pytest는 `python -m`으로)
- 데이터: 합성 샘플 `tests/fixtures/market_sample.txt`
  - 시세: UST, KRW KOFR OIS·CD91 IRS, SPX
  - SPX IV는 알려진 Heston 파라미터 가격에서 역산했다.
  - 실제 데이터는 `../market-data` 연결 전이다.
- 검증 (합성 샘플, 66개 테스트)
  - 금리
    - 헬퍼 재가격 < 0.01bp, QuantLib 직접 커브·채권과 일치(1e-12)
    - 요인 0 = 부트스트랩 커브(1e-14)
    - 평행 시나리오 vs `ZeroSpreadedTermStructure`(1e-10)
    - Σ key rate −8,252.07 vs 평행 −8,252.41(2차 항)
    - cross gamma = 직접 계산, theta = `ImpliedTermStructure`(1e-9)
  - 듀얼 커브: KOFR·CD91 = 직접 `OISRateHelper`/`SwapRateHelper(discountingCurve)`(1e-12), par IRS fairRate = 시세
  - 주식
    - 서페이스·옵션 = 직접 `BlackVarianceSurface`/`AnalyticEuropeanEngine`
    - FD ≈ 해석해(1e-3)
    - 현물 delta = QuantLib `delta()`(1e-5), vol 평행 ≈ `vega()`(1e-2)
    - Heston: 생성 파라미터 복원(κ 1.80, θ 0.045, σ 0.60, ρ −0.70, v0 0.033), 직접 `AnalyticHestonEngine`과 일치
    - 재캘리브레이션 정책·캐시, SSR: sticky moneyness 항등식, ssr=0 − ssr=1 delta ≈ vega × (−skew)

다음 단계
1. 실제 데이터 읽기 (`quotes.py`에 market-data DB 함수).
2. par 민감도: 격자 delta → 국채·스왑 par 수량.
3. 피팅 vol 서페이스(SVI) 객체, PCA 로딩(`configs/estimated/`), 헷지 PnL 백테스트(수정 그릭 기준).
