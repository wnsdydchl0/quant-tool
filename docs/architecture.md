# QuantTool

QuantLib으로 다음 흐름을 다룬다.
- 시세에서 커브·vol 서페이스·모델을 만든다.
- 포지션을 그 시장에 붙여 가격을 낸다.
- 시장을 흔들거나 시간을 움직여 민감도·시나리오 손익을 본다.

일간 분석용이다. 그날 시세로 시장을 만들고, 결과는 표로 남긴다.

## 1. 핵심 아이디어 세 가지

1. **시장 객체: 기초 객체를 이름으로 한 번에 묶는다.**
   - 일드커브, 배당 커브, vol 서페이스 같은 기초 객체는 여러 상품의 가격결정 기반이다.
   - 상품 A가 a·b·c, B가 b·c·d를 쓰더라도 b는 한 번만 만든다. 둘 다 `market["b"]`에 연결된다.
     그래서 b를 흔들면 A와 B가 **같은 b로 함께** 움직인다(효율 + 정합성).
   - 기초 객체에 기대는 **파생 객체**도 시장에 함께 있다.
     - 예측 커브에 연결된 금리 지수
     - 서페이스에 캘리브레이션한 Heston 모델
   - 기초 객체가 바뀌면 파생 객체가 의존 순서로 따라온다.
2. **시나리오: 요인을 정하고, 연동 규칙은 함수로.**
   - 시장 객체마다 "흔들 수 있는 값(요인)"을 스스로 정한다.
     - 커브: 격자 만기별 제로 이동
     - vol 서페이스: 격자 vol 이동
     - Heston: 파라미터 이동
   - 시나리오는 `{요인: 이동}` 사전이다.
   - 변수 사이 연동(PCA 로딩, spot과 vol을 SSR로 함께 …)은 그 사전을 만드는 **보통 파이썬 함수**로 쓴다.
3. **포트폴리오: 포지션을 시장에 붙여 가격.**
   - 포지션은 YAML 한 줄이고, 시장 객체는 이름으로 가리킨다.
   - 상품 조립과 가격결정 방법(엔진)은 따로다. 엔진은 설정으로 고른다.
     예: 같은 옵션을 BS 해석해 / FD / Heston으로.

원칙: **QuantLib을 그대로 쓰고, 추상화는 두 번째 사용처가 생길 때만 만든다.** 등록부·팩토리 대신 **사전과 함수**를 쓴다.

| 사전 | 키 → 값 | 넓히는 법 |
|---|---|---|
| `curves.HELPERS` | 구간 종류(Bill, Bond, Deposit, OIS, Swap) → 헬퍼 함수 | 함수 하나 + 한 줄 |
| `portfolio.TRADES`, `BUILDERS` | 상품 종류 → 명세 클래스, 조립 함수 | 클래스·함수 + 한 줄씩 |
| `portfolio.ENGINES` | 엔진 이름 → (거래, 시장, 인자) → QuantLib 엔진 | 람다 한 줄 + `pricing.yaml` |

## 2. 파일

```
src/quanttool/
  config.py          설정 읽기: 관례, 커브 레시피(구간·의존), 지수, 주식, 엔진 선택, 리스크. build_order(커브 의존 순서)
  market/            시장: 시세 → 시장 객체 → 이름으로 묶은 Market
    quotes.py        시세 파일 → {날짜: {키: 값}}
    curves.py        시세 → QuantLib 커브 (HELPERS: bill BEY·par bond·deposit·OIS·swap, 듀얼 커브 할인), 진단·커브 표,
                     CurveFactors (기준 커브 + 격자 제로 이동 = 흔들 수 있는 커브)
    equity.py        EquitySpot, VolSurface(격자 vol), HestonModelObject(캘리브레이션 파생 객체)
    market.py        MarketObject 규격, Market (이름 → 객체, 지수, 요인, 시나리오 적용·해제, 의존 순서 refresh, roll), build_market
  portfolio.py       Bond·IRSwap·EquityOption 명세 → QuantLib 상품, ENGINES, Portfolio (build, npvs)
  analysis/          시나리오 분석
    scenarios.py     시나리오 생성 함수: parallel, bucket(삼각 가중), from_loadings, combine, ssr
    risk.py          key_rate(delta·gamma, 상품별 규칙), factor_delta(아무 요인·규칙), cross_gamma, scenario_pnl, theta
configs/
  conventions/rates.yaml   관례 (UST, KRW_OIS, KRW_IRS)
  curves/*.yaml            커브 레시피: UST, KOFR(OIS), CD91(듀얼 커브: KOFR 할인)
  indices.yaml             지수 (KOFR 오버나이트, CD91 3M) → 예측 커브
  equity/spx.yaml          현물·배당·IV 격자 시세 키, Heston 설정(초기값, recalibrate_on, 최적화)
  pricing.yaml             상품 종류 → 엔진, 엔진 인자 (FD 격자)
  risk.yaml                민감도 이동 크기·방식, 상품별 덮어쓰기, cross gamma 쌍
  estimated/               PCA 로딩 등 추정값 (출처와 함께)
positions/                 ust_book.yaml, krw_swaps.yaml, spx_options.yaml
tests/                     QuantLib 직접 계산·해석해와 비교
notebooks/                 tutorial/ 00~06, 01_ust_curve
```

## 3. 객체 가이드

**`Market`** (`market/market.py`) — 시장 객체 묶음
- 만들기: `build_market(asof, quotes[asof], cfg, linked=False)`
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

**시장 객체 규격 `MarketObject`** (`market/market.py`) — 새 객체는 이것만 맞추면 시장·시나리오·리스크가 그대로 동작한다
- `.handle`: 상품·엔진이 연결되는 자리
- `.factors()`: `{이름: SimpleQuote}` (값은 기준 대비 이동, 기준 0)
- `.refresh()`: 요인이 바뀐 뒤 다시 만들 일이 있으면 여기서 한다. 커브는 Observer로 따라와서 할 일 없음
- `.roll(d)`: 시간 이동
- (선택) `.depends_on`: 기대는 시장 객체 이름 목록. 있으면 파생 객체

| 객체 | 요인 | refresh | roll |
|---|---|---|---|
| `CurveFactors` (금리·배당 커브) | `UST/5Y`: 격자 제로 이동 | 없음 (`PiecewiseZeroSpreadedTermStructure`) | `ImpliedTermStructure` |
| `EquitySpot` | `SPX/spot`: 상대 이동 | 현물 = 기준 × (1 + 이동) | 그대로 |
| `VolSurface` | `SPX_VOL/1Y/90`: 격자 vol 이동 (만기/현물 대비 % 행사가) | `BlackVarianceSurface` 재조립 | 선도 분산 실현 |
| `HestonModelObject` (파생) | `SPX_HESTON/v0` 등: 캘리브레이션 위 파라미터 이동 | `recalibrate_on` 객체가 바뀌었으면 재캘리브레이션 (입력별 캐시) + 이동 | 굴린 시장에 재캘리브레이션 |

- `CurveFactors`: `PiecewiseZeroSpreadedTermStructure(부트스트랩 커브, 격자 이동)`. 이동 0이면 부트스트랩 커브와 정확히 같다.
  속성 `.tenors`, `.times`, `.base`.
- `VolSurface`: 행사가는 asof 현물 기준 **절대값**이다. 그래서 현물만 흔들면 sticky strike다.
  속성 `.expiries`, `.strike_pcts`, `.strikes`, `.dates`, `.base`(이동 없는 서페이스), `.vol(날짜, 행사가)`.
- `HestonModelObject`
  - `.params()`, `.calibrated`, `.calibration_errors()`(헬퍼 가격 오차), `.helpers()`, `.depends_on`
  - `recalibrate_on`(설정): 이 객체들이 바뀌면 다시 캘리브레이션한다. 목록 밖(예: 금리)이 바뀌면 파라미터를 고정하고 프로세스 Handle로만 따라온다.

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
- 만들기: `Portfolio.from_file("positions/ust_book.yaml", …)`
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
from quanttool.portfolio import Portfolio
from quanttool.analysis.scenarios import parallel, from_loadings, ssr
from quanttool.analysis.risk import key_rate, factor_delta, scenario_pnl, theta

cfg = load_config("configs")
quotes = read_quotes("tests/fixtures/market_sample.txt")
asof = date(2026, 10, 23)

market = build_market(asof, quotes[asof], cfg)                  # 커브·지수·주식·모델을 한 번, 이름으로
book = Portfolio.from_file("positions/ust_book.yaml", "positions/krw_swaps.yaml",
                           "positions/spx_options.yaml").build(market, cfg)
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
| 피팅 vol 서페이스 (SVI·SABR) | `equity.py`에 `MarketObject`를 맞춘 클래스. 요인 = 파라미터 Quote, `refresh()`에서 서페이스를 다시 만들어 handle에 연결 |
| 다른 모델 (local vol, SABR 모델) | `HestonModelObject`처럼 `depends_on` + `refresh`(캘리브레이션 정책). 시장이 의존 순서로 부른다 |
| 상품 추가 | `portfolio.py`의 `TRADES`·`BUILDERS`에 명세·조립 함수. `market_names()`, `multiplier()` |
| 엔진 추가·교체 | `ENGINES`에 람다 한 줄, `pricing.yaml products`에서 기본으로 고르거나 거래의 `engine` 필드. 인자는 `pricing.yaml engines` |
| 연동 규칙 (SSR, PCA, 상관 충격) | `scenarios.py`에 시나리오 함수. 여러 객체의 요인을 한 사전에 함께 |
| 그릭 계산 규칙 수정 | `risk.yaml`의 `overrides`, `factor_delta`에 규칙 함수, 또는 `risk.py`에 계산 함수 |
| par 민감도 (헷지 수량), 헷지 백테스트 | `risk.py`에 함수 (날짜별 `build_market` + 민감도 + 다음 날 재평가) |
| 실제 데이터 | `quotes.py`에 DB 읽기 함수 (같은 `{날짜: {키: 값}}` 모양). 데이터는 `../market-data` 레포 |

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
- 검증 (합성 샘플, 63개 테스트)
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
