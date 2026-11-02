# QuantTool

QuantLib으로 시세에서 커브를 만들고, 포지션을 그 커브에 붙여 가격을 내고, 시장을 흔들거나 시간을 움직여 민감도·시나리오 손익을 본다.
일간 분석용이다(그날 시세로 시장을 만들고, 결과는 표로 남긴다).

## 1. 핵심 아이디어 세 가지

1. **시장 객체: 기초 객체를 이름으로 한 번에 묶는다.**
   일드커브, (나중에) vol 서페이스 같은 기초 객체는 여러 상품의 가격결정 기반이다. 상품 A가 a·b·c, B가 b·c·d를 쓰더라도
   b는 한 번만 만들고 둘 다 `market["b"]`에 연결된다. 그래서 b를 흔들면 A와 B가 **같은 b로 함께** 움직인다(효율 + 정합성).
2. **시나리오: 요인을 정하고, 연동 규칙은 함수로.**
   시장 객체마다 "흔들 수 있는 값(요인)"을 스스로 정한다. 커브는 격자 만기별 제로 이동량,
   vol 서페이스는 격자 vol 또는 피팅 파라미터(SVI·SABR)다. 시나리오는 `{요인: 이동}` 사전이다.
   변수 사이 연동(PCA 로딩, spot과 vol을 SSR로 함께 …)은 그 사전을 만드는 **보통 파이썬 함수**로 쓴다.
3. **포트폴리오: 포지션을 시장에 붙여 가격.** 포지션은 YAML 한 줄, 커브는 이름으로 가리킨다. 엔진은 QuantLib 엔진 하나.

원칙: **QuantLib을 그대로 쓰고, 추상화는 두 번째 사용처가 생길 때만 만든다.**

## 2. 파일

```
src/quanttool/
  config.py      설정 읽기: 관례(Conventions), 커브 레시피(CurveConfig), 리스크(RiskConfig, Override)
  quotes.py      시세 파일 → {날짜: {키: 값}}
  curves.py      시세 → QuantLib 커브 (bill BEY·par bond 헬퍼, asof 고정, freeze), 진단·커브 표, evaluation_date
  factors.py     요인화된 시장 객체 규격(MarketObject)과 CurveFactors (기준 커브 + 격자 제로 이동량)
  market.py      Market (이름 → 객체, 요인, 시나리오 적용·해제, roll), build_market
  portfolio.py   Bond 명세 → ql.FixedRateBond + 엔진, Portfolio (build, npvs)
  scenarios.py   시나리오 규칙 함수: parallel, bucket(삼각 가중), from_loadings, combine
  risk.py        key_rate(delta·gamma, 상품별 규칙), cross_gamma, scenario_pnl, theta
configs/
  conventions/rates.yaml   관례
  curves/ust.yaml          커브 레시피 + 요인 격자
  risk.yaml                민감도 이동 크기·방식, 상품별 덮어쓰기, cross gamma 쌍
  estimated/               PCA 로딩 등 추정값 (출처와 함께)
positions/ust_book.yaml    포지션
tests/                     QuantLib 직접 계산과 비교
notebooks/                 tutorial/ 00~04, 01_ust_curve
```

## 3. 객체 가이드

**`Market`** (`market.py`) — 기초 객체 묶음
- 만들기: `build_market(asof, quotes[asof], cfg, linked=False)` (설정의 모든 커브를 만든다)
- 속성: `.asof`, `.date`(지금 평가일), `.objects`(이름 → 시장 객체), `.built`(부트스트랩 결과, 진단용), `.current`(적용 중인 시나리오)
- 조회: `market["UST"]` → 상품이 연결되는 `RelinkableYieldTermStructureHandle`
- 요인: `.factors()` → `{"UST/5Y": SimpleQuote, …}`
- 시나리오: `.apply(s)`, `.reset()`, `with market.scenario(s): …` (누적되지 않음: 요인 = 기준 + 이동)
- 시간: `.roll(d)` (평가일 d, ForwardForward), `.active()` (평가일을 시장 날짜로 두는 with 블록)

**시장 객체 규격 `MarketObject`** (`factors.py`) — 새 객체(vol 서페이스 등)는 이것만 맞추면 시장·시나리오·리스크가 그대로 동작한다
- `.handle`: 상품이 연결되는 자리
- `.factors()`: `{이름: SimpleQuote}`
- `.refresh()`: 요인이 바뀐 뒤 다시 만들 일이 있으면 (피팅 파라미터 방식). 커브는 Observer로 따라와서 할 일 없음
- `.roll(d)`: 시간 이동

**`CurveFactors`** (`factors.py`): 커브 = `PiecewiseZeroSpreadedTermStructure(부트스트랩 커브, 격자 이동량)`. 이동량 0이면 부트스트랩 커브와 정확히 같다. 속성 `.tenors`, `.times`, `.base`.

**커브** (`curves.py`)
- `build_curve(curve_cfg, conventions, quotes, asof, linked) → BuiltCurve(.curve, .helpers, .quotes())`
- `helper_repricing(built, asof)`: 헬퍼 재가격 오차 표
- `curve_table(handle, conventions)`: 할인계수·제로·1Y 선도·par
- `curve_shape(table)`: 2s10s, 5s30s, 나비
- `bill_price`, `bill_yield`, `evaluation_date(d)`

**`Portfolio`** (`portfolio.py`)
- 만들기: `Portfolio.from_file("positions/ust_book.yaml")`
- `.build(market, cfg)`: 거래마다 QuantLib 상품을 만들어 `market[curve]`에 연결. 다른 시장에 붙이려면 다시 부른다
- `.npvs()`: 거래별 NPV(포지션 크기 반영, 시장의 현재 날짜·시나리오), `.npv()`
- `.trades`(id → 명세), `.instruments`(id → QuantLib 상품), `.engines`(커브 → 엔진)
- 상품 추가: 명세 클래스와 조립 함수를 `TRADES`, `BUILDERS` 사전에 한 줄씩

**시나리오** (`scenarios.py`): 모두 `dict[요인 키, 이동]`을 돌려준다
- `parallel(market, "UST", 0.001)`, `bucket(market, "UST", shift_tenors, j, size)`(삼각 가중), `from_loadings("UST", {만기: 로딩}, 크기)`, `combine(s1, s2, …)`

**리스크** (`risk.py`)
- `key_rate(book, market, cfg.risk, "UST") → {"delta": 만기 × 거래, "gamma": …}` (1bp당 손익)
  - 상품별 규칙: `risk.overrides[거래 id 또는 종류] = {shift_size, scheme}` → 그 크기·방식으로 계산해 1bp로 환산
  - 이동 만기: `risk.shift_tenors[커브]` (없으면 요인 격자)
- `cross_gamma(book, market, risk)`, `scenario_pnl(book, market, {이름: 시나리오})`, `theta(book, market, 다음 날)`

## 4. 사용 예

```python
from datetime import date
from quanttool.config import load_config
from quanttool.quotes import read_quotes
from quanttool.market import build_market
from quanttool.portfolio import Portfolio
from quanttool.scenarios import parallel, from_loadings
from quanttool.risk import key_rate, scenario_pnl, theta

cfg = load_config("configs")
quotes = read_quotes("tests/fixtures/market_ust_sample.txt")
asof = date(2026, 10, 23)

market = build_market(asof, quotes[asof], cfg)                  # 커브는 한 번, 이름으로
book = Portfolio.from_file("positions/ust_book.yaml").build(market, cfg)
book.npvs()

kr = key_rate(book, market, cfg.risk, "UST")                    # delta·gamma (만기 × 거래)
pnl = scenario_pnl(book, market, {
    "parallel +10bp": parallel(market, "UST", 0.0010),
    "steepener": from_loadings("UST", {"2Y": -1.0, "10Y": 1.0}, 0.0005),
})
th = theta(book, market, date(2026, 10, 26))
```

## 5. 확장

| 하고 싶은 것 | 어디에 |
|---|---|
| 커브 추가 (KRW 국채, SOFR) | `configs/curves/*.yaml`. 새 헬퍼 종류면 `curves.py`의 구간 종류 하나 |
| vol 서페이스 | `factors.py`에 `MarketObject`를 맞춘 클래스. 격자 vol 방식이면 요인 = 격자 vol Quote, 피팅 방식이면 요인 = 파라미터 Quote + `refresh()`에서 다시 만들어 handle에 연결 |
| 연동 규칙 (SSR, sticky strike, PCA) | `scenarios.py`에 시나리오 함수. spot과 vol 요인을 한 사전에 함께 |
| 상품 추가 (옵션, 스왑) | `portfolio.py`의 `TRADES`·`BUILDERS`에 명세·조립 함수 |
| 그릭 계산 규칙 수정 | `risk.yaml`의 `overrides`, 또는 `risk.py`에 계산 함수 |
| par 민감도 (헷지 수량), 헷지 백테스트 | `risk.py`에 함수 (날짜별 `build_market` + 민감도 + 다음 날 재평가) |
| 실제 데이터 | `quotes.py`에 DB 읽기 함수 (같은 `{날짜: {키: 값}}` 모양). 데이터는 `../market-data` 레포 |

## 6. 결정 사항

| 항목 | 결정 |
|---|---|
| 참고한 ORE 아이디어 | 시장을 이름으로 묶기, 오늘 커브는 asof 고정·얼림, 흔들기는 기준 커브 위 이동량(기준 상태 정확히 같음), 시간 이동은 ForwardForward. 클래스 구조는 따르지 않는다 |
| 범위 | 신용(CDS, XVA), 통계적 리스크(VaR, 노출 시뮬레이션) 제외. 몬테카를로는 상품 엔진 안에만 |
| UST par 헬퍼 | 명목 만기 정규 일정 + Unadjusted 지급 → par 채권 가격이 정확히 100. bill은 BEY → 할인채 가격 |
| 격자 바깥 | 평탄 제로. QuantLib 1.44 `PiecewiseZeroSpreadedTermStructure`는 Quote 변경 시 외삽 설정이 풀려, 마지막 격자 Quote에 묶은 100Y 끝점으로 처리 |
| 전역 평가일 | 상품 값은 그 시장의 `active()` 안에서 (`Portfolio.npvs`가 알아서) |
| 민감도 단위 | 격자 제로금리 1bp당 손익. par 기준은 예정 |

## 7. 현황과 다음 단계

- 시작: `pip install -e ".[dev,notebook]"`, 검사 `python -m pytest -q && ruff check . && ruff format --check .` (pytest는 `python -m`으로).
- 데이터는 합성 샘플 `tests/fixtures/market_ust_sample.txt`. 실제 데이터는 `../market-data` 연결 전.
- 검증 (합성 샘플): 헬퍼 재가격 < 0.01bp, QuantLib 직접 커브·채권과 일치(1e-12), 요인 0 = 부트스트랩 커브(1e-14),
  평행 시나리오 vs `ZeroSpreadedTermStructure` 직접 계산(1e-10), Σ key rate −8,252.07 vs 평행 −8,252.41(2차 항),
  10bp 중심 차분 → 1bp vs 1bp 전진(2e-3), cross gamma = 직접 계산, theta = `ImpliedTermStructure`(1e-9).

다음 단계
1. 실제 데이터 읽기 (`quotes.py`에 market-data DB 함수).
2. par 민감도: 격자 delta → 국채 par 수량.
3. 주식 줄기: 현물·배당 커브, vol 서페이스(격자/피팅 파라미터 두 방식), 옵션, 연동 규칙(SSR).
4. KRW·SOFR 커브와 스왑, PCA 로딩(`configs/estimated/`), 헷지 백테스트.
