# ORE 워크스루: 예시 하나로 OREData → OREAnalytics 따라가기

학습용 문서다. 스킴이 잡히면 이 파일은 지워도 된다(설계 기준은 `docs/architecture.md`).

- 예시: **EUR 20년 스왑(고정 2.1% 수취, EURIBOR 6M 지급) 하나의 오늘 가격과 금리 민감도.**
- 입력 파일: `references/Engine/Examples/MinimalSetup/Input`, `Examples/Input/curveconfig.xml`, `Examples/MarketRisk/Input`.
- 코드는 C++ 원본을 **의사 파이썬**으로 옮긴 것이다. 이름·순서는 원본 그대로이고, 각 블록 위에 원본 경로를 단다(경로는 `references/Engine/` 기준).
- 각 단계는 같은 순서로 쓴다: **입력 → 받는 클래스 → 쓰는 코드 → 왜 이렇게 나눴나 → QuantTool 대응**.

---

## 0. 전체 그림

```
 입력 파일 (데이터)                      OREData: 번역 + 조립                              OREAnalytics: 흔들고 반복 평가
 ─────────────────                      ─────────────────────                              ─────────────────────────────
 market.txt, fixings.txt ──► Loader ─────────┐
 conventions.xml ─────────► Conventions ─────┤
 curveconfig.xml ─────────► CurveConfigurations ┤
 todaysmarket.xml ────────► TodaysMarketParameters ┴──► TodaysMarket ═══════╗ (Market 규격)
                                                        (MarketImpl 창고)  ║
                                                                           ║  ┌──────────────────────────────────────────┐
 pricingengine.xml ───────► EngineData ──────► EngineFactory(data, market) ║  │ ScenarioSimMarket(초기 Market, 격자)     │
                                                ├ builder("Swap")          ╚═►│   격자 Quote(simData) → 격자 커브         │
                                                └ legBuilder("Floating")      │   update(d): 생성기.next(d) → 적용        │
 portfolio.xml ───────────► Portfolio(Trade 데이터)                            └──────▲───────────────────┬─────────────────┘
                              │ build(factory)                                        │ scenarioGenerator  │ (Market 규격)
                              ▼                                                       │                    ▼
                           Trade.instrument = QuantLib Swap + 엔진  ──NPV (t0)      SensitivityScenarioGenerator   EngineFactory(data, simMarket)
                                                                                     ▲ (기준, 1M+1bp, …)            │ portfolio.build(다시)
 simulation.xml ──────────► ScenarioSimMarketParameters ─────────────────────────────┘                              ▼
 sensitivity.xml ─────────► SensitivityScenarioData ──────────────────────────────► ValuationEngine.buildCube(portfolio, cube, [NPVCalculator])
                                                                                       시나리오마다 simMarket.update → NPV → NPVCube
                                                                                                    ▼
                                                                                    SensitivityCube: delta·gamma·crossGamma
                                                                                                    ▼ (선택)
                                                                                    ParSensitivityAnalysis: zero 민감도 → par(헷지 상품) 민감도
```

핵심 세 줄:
1. **입력은 전부 데이터**다. XML은 데이터 클래스를 파일로 적은 것일 뿐이다(`fromXML`/`toXML`).
2. OREData는 데이터를 **QuantLib 객체 그래프**로 조립한다. 시장 객체는 `Market`, 계약 객체는 `Portfolio`, 동학 객체는 `Model`이다.
3. OREAnalytics는 **같은 계약**을 **흔들 수 있는 시장**(`ScenarioSimMarket`)에 다시 연결하고, 시나리오마다 다시 평가한다.
   두 시장이 모두 `Market` 규격을 따르므로 계약·엔진 코드는 한 줄도 바뀌지 않는다.

---

## 1. OREData: Market 만들기

### 1.1 MarketDatum과 Loader: 시세 한 줄 = 스스로를 설명하는 키 + 값

입력 (`MinimalSetup/Input/market_20160205_flat.txt`, `Examples/Input/market_20160205.txt`)
```
2016-02-05  MM/RATE/EUR/2D/6M            -0.0013
2016-02-05  IR_SWAP/RATE/EUR/2D/6M/10Y    0.0049
2016-02-05  ZERO/RATE/EUR/EUR6M/A360/1Y   0.0010
```

받는 클래스 (`OREData/ored/marketdata/marketdatum.hpp`, `marketdatumparser.cpp`, `loader.hpp`)
```python
class MarketDatum:                      # 시세 하나
    asof_date: Date
    name: str                           # "IR_SWAP/RATE/EUR/2D/6M/10Y"
    quote: Handle[Quote]                # SimpleQuote(0.0049) — 커브 헬퍼가 여기에 붙는다
    instrument_type: InstrumentType     # ZERO, DISCOUNT, MM, FRA, IR_SWAP, BASIS_SWAP, FX_SPOT, EQUITY_SPOT, EQUITY_OPTION, …
    quote_type: QuoteType               # RATE, PRICE, RATE_LNVOL, …

class SwapQuote(MarketDatum):           # 키를 파싱해 의미를 아는 하위 클래스
    ccy = "EUR"; fwd_start = Period("2D"); tenor = Period("6M"); term = Period("10Y")

def parseMarketDatum(asof, name, value) -> MarketDatum:   # marketdatumparser.cpp
    tokens = name.split("/")            # ["IR_SWAP","RATE","EUR","2D","6M","10Y"]
    if tokens[0] == "IR_SWAP":          # 6~7개 토큰: 통화, (지수), 시작, 변동 주기, 만기
        return SwapQuote(value, asof, name, RATE, ccy=tokens[2], fwd_start=..., tenor=..., term=...)
    ...

class Loader(ABC):                      # 시세 창구
    def loadQuotes(self, d: Date) -> list[MarketDatum]: ...    # 그 날짜 전부
    def get(self, name: str, d: Date) -> MarketDatum: ...      # 이름 하나
    def get(self, wildcard: Wildcard, d: Date) -> set[MarketDatum]: ...   # "IR_SWAP/RATE/EUR/2D/6M/*"
    def has(self, name, d) -> bool: ...
    def asofDates(self) -> set[Date]: ...
    def loadFixings(self) -> set[Fixing]: ...                  # 과거 지수 고시값 (변동 레그 확정 쿠폰용)

class CSVLoader(Loader): ...            # 파일에서 읽음 (csvloader.hpp)
class InMemoryLoader(Loader): ...       # 파이썬에서 직접 넣음
```

쓰는 코드
```python
loader = CSVLoader("market_20160205.txt", "fixings_20160205.txt", implyTodaysFixings=False)
q = loader.get("IR_SWAP/RATE/EUR/2D/6M/10Y", Date(5, 2, 2016))
q.quote.value()                                        # 0.0049
loader.get(Wildcard("IR_SWAP/RATE/EUR/2D/6M/*"), asof) # 커브 설정이 이 패턴으로 시세를 모은다
```

**왜 이렇게 나눴나**
- **키에 의미가 들어 있다.** 그래서 시세 파일에는 별도 스키마가 필요 없다. 커브 설정은 "어떤 키를 쓸지"만 적는다.
- **시세는 Quote(Handle)로 들어온다.** 커브 헬퍼가 이 Quote를 관찰하므로, 값을 바꾸면 커브가 따라온다(QuantLib Observer).
- **Loader는 출처를 모르게 감싼다.** CSV든 DB든 메모리든 `loadQuotes(asof)` 하나로 같다.

**QuantTool**: `data/marketdata/loader.py`의 `MarketDatum`, `Loader`, `InMemoryLoader`, `UstParCsvLoader`, `QuoteStore`. 키 규칙은 `data/utilities/ids.py`(`BOND/YIELD/USD/UST/PAR/10Y`)에 있다.

### 1.2 Conventions: 상품 관례 사전

입력 (`MinimalSetup/Input/conventions.xml`)
```xml
<Swap>
  <Id>EUR-6M-SWAP-CONVENTIONS</Id>
  <FixedCalendar>TARGET</FixedCalendar>
  <FixedFrequency>Annual</FixedFrequency>
  <FixedConvention>MF</FixedConvention>
  <FixedDayCounter>A365</FixedDayCounter>
  <Index>EUR-EURIBOR-6M</Index>
</Swap>
<Deposit><Id>EUR-DEPOSIT</Id><IndexBased>true</IndexBased><Index>EUR-EURIBOR</Index></Deposit>
```

받는 클래스 (`OREData/ored/configuration/conventions.hpp`)
```python
class Convention(ABC):  id: str; type: Type      # Deposit, FRA, Swap, OIS, IRSwap, FX, …
class IRSwapConvention(Convention):
    fixed_calendar: Calendar; fixed_frequency: Frequency; fixed_convention: BusinessDayConvention
    fixed_day_counter: DayCounter; index: IborIndex   # "EUR-EURIBOR-6M" → QuantLib Euribor6M
class Conventions:
    def fromFile(self, path): ...
    def get(self, id: str) -> Convention: ...

InstrumentConventions.instance().setConventions(conventions)   # 전역 등록부. 커브·상품 빌더가 여기서 꺼낸다
```

**왜**: 같은 숫자 2%도 결제일·일수·주기가 다르면 다른 숫자다. 관례를 이름 하나로 묶어 두면 커브 설정과 계약서가 `EUR-6M-SWAP-CONVENTIONS`라는 이름만 가리키면 된다.

**QuantTool**: `configs/conventions/rates.yaml` → `data/configuration/conventions.py`의 `RateConventions`. 전역 등록부 대신 `cfg.conventions`를 넘긴다(architecture.md 2.1).

### 1.3 CurveConfigurations: 커브 하나를 만드는 레시피

입력 (`Examples/Input/curveconfig.xml`의 EUR6M, 발췌)
```xml
<YieldCurve>
  <CurveId>EUR6M</CurveId>
  <Currency>EUR</Currency>
  <DiscountCurve>EUR1D</DiscountCurve>              <!-- 스왑 헬퍼의 할인은 EUR1D(OIS) 커브로: 의존 관계 -->
  <Segments>
    <Simple>
      <Type>Deposit</Type>
      <Quotes><Quote>MM/RATE/EUR/2D/6M</Quote></Quotes>
      <Conventions>EUR-EURIBOR-CONVENTIONS</Conventions>
      <ProjectionCurve>EUR6M</ProjectionCurve>
    </Simple>
    <Simple>
      <Type>Swap</Type>
      <Quotes>
        <Quote>IR_SWAP/RATE/EUR/2D/6M/2Y</Quote> … <Quote>IR_SWAP/RATE/EUR/2D/6M/50Y</Quote>
      </Quotes>
      <Conventions>EUR-6M-SWAP-CONVENTIONS</Conventions>
    </Simple>
  </Segments>
  <InterpolationVariable>Discount</InterpolationVariable>
  <InterpolationMethod>LogLinear</InterpolationMethod>
  <YieldCurveDayCounter>A365</YieldCurveDayCounter>
</YieldCurve>
```

받는 클래스 (`OREData/ored/configuration/curveconfigurations.hpp`, `yieldcurveconfig.hpp`, `curveconfig.hpp`)
```python
class YieldCurveSegment:                 # 세그먼트 = "이 시세들을 이 관례의 이 헬퍼로"
    type: str                            # Deposit, FRA, Future, Swap, OIS, Zero, …
    quotes: list[str]                    # 시세 키
    conventions_id: str
class SimpleYieldCurveSegment(YieldCurveSegment):
    projection_curve_id: str             # 이 세그먼트가 예측에 쓰는 커브 (자기 자신이면 단일 커브)
class DirectYieldCurveSegment(YieldCurveSegment): ...   # 제로금리·할인계수를 그대로 쓰는 경우

class YieldCurveConfig:
    curve_id: str                        # "EUR6M"
    currency: str
    discount_curve_id: str               # "EUR1D" → 의존 그래프의 간선
    segments: list[YieldCurveSegment]
    interpolation_variable: str          # Discount, Zero, Forward
    interpolation_method: str            # Linear, LogLinear, Cubic, …
    def requiredCurveIds(self) -> dict: ...   # 이 커브가 먼저 필요로 하는 커브들 (CurveConfig 공통)

class CurveConfigurations:
    def fromFile(self, path): ...
    def yieldCurveConfig(self, id: str) -> YieldCurveConfig: ...
```

**왜**: 커브는 "시세 목록 + 헬퍼 종류 + 관례 + 보간 + 의존 커브"로 완전히 정해진다. 이것을 설정으로 두면 새 커브를 추가할 때 코드를 바꾸지 않는다.

**QuantTool**: `configs/market/curves/ust.yaml` → `data/configuration/curveconfig.py`의 `YieldCurveConfig`(segments: `ZeroCouponBill`, `FixedRateBond`).

### 1.4 TodaysMarketParameters: 오늘 시장에 무엇을 둘지

입력 (`MinimalSetup/Input/todaysmarket.xml`, 발췌)
```xml
<Configuration id="default">
  <DiscountingCurvesId>default</DiscountingCurvesId>
  <YieldCurvesId>default</YieldCurvesId>
</Configuration>
<DiscountingCurves id="default">
  <DiscountingCurve currency="EUR">Yield/EUR/EUR1D</DiscountingCurve>
</DiscountingCurves>
<IndexForwardingCurves id="default">
  <Index name="EUR-EURIBOR-6M">Yield/EUR/EUR6M</Index>
  <Index name="EUR-EONIA">Yield/EUR/EUR1D</Index>
</IndexForwardingCurves>
```

받는 클래스 (`OREData/ored/marketdata/todaysmarketparameters.hpp`, `curvespec.hpp`, `market.hpp`)
```python
class MarketObject(Enum):                # 시장에 둘 수 있는 객체 종류
    DiscountCurve, YieldCurve, IndexCurve, SwapIndexCurve, FXSpot, FXVol, SwaptionVol,
    CapFloorVol, EquityCurve, EquityVol, ...

class MarketConfiguration:               # configuration id 하나 = MarketObject별 "묶음 id"
    market_object_ids: dict[MarketObject, str]      # {DiscountCurve: "default", YieldCurve: "default", …}

class TodaysMarketParameters:
    def configurations(self) -> list[tuple[str, MarketConfiguration]]: ...   # "default", "collateral_inCcy", …
    def mapping(self, o: MarketObject, configuration: str) -> dict[str, str]: ...
        # mapping(DiscountCurve, "default") == {"EUR": "Yield/EUR/EUR1D"}
        # mapping(IndexCurve,    "default") == {"EUR-EURIBOR-6M": "Yield/EUR/EUR6M", "EUR-EONIA": "Yield/EUR/EUR1D"}

class YieldCurveSpec(CurveSpec):         # "Yield/EUR/EUR6M" 파싱 결과
    ccy = "EUR"; curve_config_id = "EUR6M"
```

**왜**
- **"시장에서 부르는 이름"과 "만드는 레시피"를 나눈다.** 가격결정 코드는 `discountCurve("EUR")`만 부르고, 그 이름이 어떤 레시피(`EUR1D`)로 만들어지는지는 설정이 정한다. 레시피를 바꿔도 가격결정 코드는 그대로다.
- **한 레시피를 여러 이름이 공유한다.** `EUR-EONIA` 지수와 EUR 할인 커브가 같은 `EUR1D` 커브 객체 하나를 쓴다.
- **configuration**: 같은 이름 `discountCurve("EUR")`이 용도에 따라 다른 커브를 가리키게 할 수 있다. 예를 들어 가격결정용과 모델 캘리브레이션용(담보 통화별 할인)을 구분한다. 대부분 `"default"` 하나만 쓴다.

**QuantTool**: `configs/market/todaysmarket.yaml`(`yield_curves: [UST]`) → `data/configuration/todaysmarketparameters.py`. configuration 구분과 이름 → 레시피 매핑은 아직 없다. 지금은 이름과 레시피가 같다.

### 1.5 TodaysMarket: 레시피 + 시세 → 시장 객체 (구축 한 줄씩)

받는 클래스 (`OREData/ored/marketdata/todaysmarket.hpp/.cpp`, `marketimpl.hpp`, `yieldcurve.cpp`, `dependencygraph.hpp`)
```python
class TodaysMarket(MarketImpl):
    def __init__(self, asof, params: TodaysMarketParameters, loader: Loader,
                 curveConfigs: CurveConfigurations,
                 continueOnError=False, loadFixings=True, lazyBuild=False,
                 referenceData=None, preserveQuoteLinkage=False, ...):
        self.asof_ = asof
        self.initialise(asof)

    def initialise(self, asof):
        if loadFixings: applyFixings(loader.loadFixings())        # 전역 IndexManager에 과거 고시값 등록
        for configuration, _ in params.configurations():
            graph = DependencyGraph(...)                           # 노드 = (MarketObject, 이름, CurveSpec)
            graph.buildDependencyGraph(configuration)              # 간선 = curveConfig.requiredCurveIds()
            for node in graph.topological_order():                 # EUR1D → EUR6M 순
                self.buildNode(configuration, node)

    def buildNode(self, configuration, node):
        if node.curveSpec.baseType() == CurveType.Yield:
            spec = node.curveSpec                                  # YieldCurveSpec("EUR", "EUR6M")
            if spec.name() not in self.requiredYieldCurves_:       # 같은 레시피는 한 번만 만든다
                yc = YieldCurve(asof_, [spec], curveConfigs, loader, self.requiredYieldCurves_, ...)
                #   yieldcurve.cpp: 세그먼트마다 시세 키 → loader.get(...).quote → RateHelper
                #   Deposit → DepositRateHelper, Swap → SwapRateHelper(quote, 관례, 할인=requiredYieldCurves_["EUR1D"])
                #   → PiecewiseYieldCurve[Discount, LogLinear](asofDate_, helpers, dayCounter)  ← 기준일 asof 고정
                self.requiredYieldCurves_[spec.name()] = yc
            h = self.requiredYieldCurves_[spec.name()].handle()
            if node.obj == MarketObject.DiscountCurve:
                self.yieldCurves_[(configuration, YieldCurveType.Discount, node.name)] = h   # ("default", Discount, "EUR")
            elif node.obj == MarketObject.YieldCurve:
                self.yieldCurves_[(configuration, YieldCurveType.Yield, node.name)] = h
            elif node.obj == MarketObject.IndexCurve:
                index = parseIborIndex(node.name, h)               # "EUR-EURIBOR-6M" → Euribor6M(예측 커브 = h)
                self.iborIndices_[(configuration, node.name)] = Handle(index)
        elif ...: # FXSpot, SwaptionVol, EquityCurve, EquityVol 도 같은 틀
        # preserveQuoteLinkage=False(기본)면 구축 후 시세 Quote와의 연결을 끊는다 → 이후 시세가 바뀌어도 시장 불변

class MarketImpl(Market):                # 창고: 종류별 map (marketimpl.hpp)
    yieldCurves_: dict[tuple[str, YieldCurveType, str], Handle[YieldTermStructure]]
    iborIndices_: dict[tuple[str, str], Handle[IborIndex]]
    swaptionCurves_: dict[tuple[str, str], Handle[SwaptionVolatilityStructure]]
    fxVols_, equitySpots_, equityVols_, ...                  # 모두 (configuration, 이름) → Handle
    def discountCurveImpl(self, ccy, configuration="default"):
        return self.lookup(self.yieldCurves_, (configuration, Discount, ccy))   # 없으면 "default"로 대체
```

쓰는 코드
```python
market = TodaysMarket(asof, tm_params, loader, curve_configs)
```

**왜 이렇게 나눴나**
- **의존 그래프**: EUR6M 스왑 헬퍼는 EUR1D로 할인하므로 EUR1D가 먼저다. 순서를 사람이 정하지 않는다.
- **창고(MarketImpl)와 구축(TodaysMarket)의 분리**: 창고는 "이름 → Handle"만 안다. 그래서 같은 창고를 다른 방식으로 채우는 시장(SimMarket, 3장)이 같은 규격을 그대로 갖는다.
- **asof 고정 + 연결 끊기**: 오늘 시장은 한 번 만들면 변하지 않는다. 흔드는 일은 SimMarket이 한다.
- **Handle로 보관**: 바깥에서 받은 Handle이 나중에 다른 커브로 다시 연결될 수 있다(RelinkableHandle).

**QuantTool**: `data/marketdata/todaysmarket.py` `TodaysMarket`(asof 고정, `freeze`, `preserve_quote_linkage`), `market.py` `MarketImpl`, `dependencygraph.py`, `yieldcurve.py` `YieldCurveBuilder`.

### 1.6 Market 규격: 가격결정 코드가 아는 유일한 것

(`OREData/ored/marketdata/market.hpp`)
```python
class Market(ABC):
    defaultConfiguration = "default"
    def asofDate(self) -> Date: ...
    def discountCurve(self, ccy, configuration="default") -> Handle[YieldTermStructure]: ...
    def yieldCurve(self, name, configuration="default") -> Handle[YieldTermStructure]: ...
    def iborIndex(self, name, configuration="default") -> Handle[IborIndex]: ...
    def swapIndex(self, name, configuration="default") -> Handle[SwapIndex]: ...
    def swaptionVol(self, key, configuration="default") -> Handle[SwaptionVolatilityStructure]: ...
    def fxSpot(self, ccypair, configuration="default") -> Handle[Quote]: ...
    def equitySpot(self, name, configuration="default") -> Handle[Quote]: ...
    def equityDividendCurve(self, name, configuration="default") -> Handle[YieldTermStructure]: ...
    def equityVol(self, name, configuration="default") -> Handle[BlackVolTermStructure]: ...
```

쓰는 코드
```python
df = market.discountCurve("EUR").discount(Date(5, 2, 2026))
euribor = market.iborIndex("EUR-EURIBOR-6M").currentLink()
euribor.fixing(Date(5, 8, 2016))                      # 미래 날짜 → 예측 커브(EUR6M)로 계산한 선도
vol = market.equityVol("SPX").blackVol(1.0, 4500.0)
```

**QuantTool**: `data/marketdata/market.py`의 `Market`. `yield_curve`, `quote`는 있고 `index`, `equity_spot`, `dividend_curve`, `equity_vol`은 자리만 있다(`NotImplementedError`). `discount_curve`는 아직 없다.

---

## 2. OREData: Portfolio 만들기

### 2.1 계약 데이터: Trade → SwapData → LegData

입력 (`MinimalSetup/Input/portfolio_swap.xml`, 발췌)
```xml
<Trade id="Swap_20y">
  <TradeType>Swap</TradeType>
  <Envelope><CounterParty>CPTY_A</CounterParty><NettingSetId>CPTY_A</NettingSetId></Envelope>
  <SwapData>
    <LegData>
      <LegType>Fixed</LegType>  <Payer>false</Payer>  <Currency>EUR</Currency>
      <Notionals><Notional>10000000</Notional></Notionals>
      <DayCounter>A360</DayCounter>  <PaymentConvention>MF</PaymentConvention>
      <FixedLegData><Rates><Rate>0.021</Rate></Rates></FixedLegData>
      <ScheduleData><Rules><StartDate>20160301</StartDate><EndDate>20360301</EndDate><Tenor>1Y</Tenor>
        <Calendar>TARGET</Calendar><Convention>MF</Convention><Rule>Forward</Rule></Rules></ScheduleData>
    </LegData>
    <LegData>
      <LegType>Floating</LegType>  <Payer>true</Payer>  <Currency>EUR</Currency>
      …
      <FloatingLegData><Index>EUR-EURIBOR-6M</Index><Spreads><Spread>0</Spread></Spreads><FixingDays>2</FixingDays></FloatingLegData>
      <ScheduleData>… <Tenor>6M</Tenor> …</ScheduleData>
    </LegData>
  </SwapData>
</Trade>
```

받는 클래스 (`OREData/ored/portfolio/trade.hpp`, `envelope.hpp`, `swap.hpp`, `legdata.hpp`, `schedule.hpp`)
```python
class Envelope:                          # 계약 바깥 정보: 상대방, 네팅셋, 추가 필드
    counterparty: str; netting_set_id: str; additional_fields: dict

class Trade(ABC):                        # 계약서. build 전에는 순수 데이터
    id: str
    tradeType_: str                      # "Swap" — EngineData에서 엔진을 고르는 열쇠
    envelope_: Envelope
    # build 후에 채워지는 것
    instrument_: InstrumentWrapper | None    # QuantLib Instrument + 승수
    legs_: list[Leg]                         # 레그별 현금흐름
    npvCurrency_: str; notional_: float; maturity_: Date
    sensitivityTemplate_: str                # 3.5에서 다시 나온다
    @abstractmethod
    def build(self, engineFactory: EngineFactory) -> None: ...
    def fromXML(self, node) / toXML(self): ...

class ScheduleData:  rules: list[ScheduleRules]      # 시작·끝·주기·달력·관례·Rule → QuantLib Schedule
class LegData:                           # 레그 공통 필드
    legType: str                         # "Fixed", "Floating", "Equity", "CPI", …
    payer: bool; currency: str; notionals: list[float]
    dayCounter: str; paymentConvention: str; schedule: ScheduleData
    concreteLegData: LegAdditionalData   # 레그 종류별 내용
class FixedLegData(LegAdditionalData):    rates: list[float]
class FloatingLegData(LegAdditionalData): index: str; spreads: list[float]; fixingDays: int; isInArrears: bool

class Swap(Trade):
    legData_: list[LegData]              # SwapData = LegData 목록

class Portfolio:
    def fromFile(self, path): ...        # XML → Trade 객체들 (아직 build 안 함)
    def add(self, trade): ...
    def build(self, factory, context="unspecified", ...): ...   # 모든 trade.build(factory)
    def trades(self) -> dict[str, Trade]: ...
```

쓰는 코드: XML 없이 파이썬에서 직접 만들 수도 있다(`Examples/ORE-Python/ExampleScripts/portfolio.py`).
```python
fixed = LegData(FixedLegData([0.021]), isPayer=False, currency="EUR", schedule=ScheduleData(rules_1y),
                dayCounter="A360", notionals=[1e7], paymentConvention="MF")
floating = LegData(FloatingLegData("EUR-EURIBOR-6M", fixingDays=2, isInArrears=False, spreads=[0.0]),
                   isPayer=True, currency="EUR", schedule=ScheduleData(rules_6m), ...)
swap = Swap(Envelope("CPTY_A"), [fixed, floating]); swap.setId("Swap_20y")
portfolio = Portfolio(); portfolio.add(swap)
```

**왜**
- **계약서에는 엔진·모델·커브 객체가 없다.** 이름만 있다(`EUR-EURIBOR-6M`, 통화 EUR). 같은 계약서를 어느 시장에든 연결할 수 있는 이유다.
- **레그를 공통 필드 + 종류별 내용으로 나눈다.** 새 레그 종류(CMS, CPI, Equity 등)를 추가해도 Swap 코드는 그대로다.

**QuantTool**: `positions/ust_book.yaml` → `data/portfolio/bond.py` `Bond`(pydantic), `trade.py` `Trade`, `portfolio.py` `Portfolio`. LegData와 LegBuilder는 Swap을 만들 때 추가할 예정이다.

### 2.2 EngineData: 상품 유형 → 평가 방법

입력 (`MinimalSetup/Input/pricingengine.xml`, 발췌)
```xml
<Product type="Swap">
  <Model>DiscountedCashflows</Model>   <ModelParameters/>
  <Engine>DiscountingSwapEngine</Engine>   <EngineParameters/>
</Product>
<Product type="BermudanSwaption">
  <Model>LGM</Model>
  <ModelParameters><Parameter name="Calibration">Bootstrap</Parameter><Parameter name="Reversion">0.03</Parameter>…</ModelParameters>
  <Engine>Grid</Engine> …
</Product>
```

받는 클래스 (`OREData/ored/portfolio/enginedata.hpp`)
```python
class EngineData:
    def model(self, productName) -> str: ...                    # "DiscountedCashflows"
    def engine(self, productName) -> str: ...                   # "DiscountingSwapEngine"
    def modelParameters(self, productName) -> dict: ...
    def engineParameters(self, productName) -> dict: ...         # 예: {"SensitivityTemplate": "IR_FD"}
    def globalParameters(self) -> dict: ...                      # 예: {"RunType": "SensitivityDelta"}
```

**왜**: 평가 방법은 계약이 아니라 **기관의 선택**이다. 같은 버뮤단을 LGM 격자로 할지 몬테카를로로 할지는 이 파일 한 줄로 바꾼다. 계약서는 그대로 둔다.

**QuantTool**: `configs/pricing/engines.yaml`(`Bond: {model: DiscountedCashflows, engine: DiscountingBondEngine}`) → `data/configuration/enginedata.py`.

### 2.3 EngineBuilder: (model, engine) 하나를 맡는 기술자

받는 클래스 (`OREData/ored/portfolio/enginefactory.hpp`, `builders/swap.hpp`)
```python
class EngineBuilder(ABC):
    def __init__(self, model: str, engine: str, tradeTypes: set[str]):
        self.model, self.engine, self.tradeTypes = model, engine, tradeTypes
    # 팩토리가 init()으로 넣어 준다
    market_: Market
    configurations_: dict[MarketContext, str]
    modelParameters_: dict; engineParameters_: dict
    def configuration(self, ctx: MarketContext) -> str: ...      # pricing → "default"
    def engineParameter(self, name, ...) -> str: ...

class CachingPricingEngineBuilder(EngineBuilder, Generic[Key, *Args]):
    engines_: dict[Key, PricingEngine] = {}
    def engine(self, *args) -> PricingEngine:
        key = self.keyImpl(*args)
        if key not in self.engines_:
            self.engines_[key] = self.engineImpl(*args)          # 같은 키면 같은 엔진
        return self.engines_[key]
    @abstractmethod
    def keyImpl(self, *args) -> Key: ...
    @abstractmethod
    def engineImpl(self, *args) -> PricingEngine: ...

class SwapEngineBuilderBase(CachingPricingEngineBuilder):          # builders/swap.hpp
    def __init__(self, model, engine):
        super().__init__(model, engine, {"Swap", "CapFloor_as_Swap"})
    def keyImpl(self, ccy, discountCurve, securitySpread, eqNames):
        return ccy.code() + "_" + discountCurve + "_" + securitySpread + "_" + "_".join(eqNames)

class SwapEngineBuilder(SwapEngineBuilderBase):
    def __init__(self): super().__init__("DiscountedCashflows", "DiscountingSwapEngine")
    def engineImpl(self, ccy, discountCurve, securitySpread, eqNames):
        cfg = self.configuration(MarketContext.pricing)
        yts = (self.market_.discountCurve(ccy.code(), cfg) if not discountCurve
               else indexOrYieldCurve(self.market_, discountCurve, cfg))
        if securitySpread:
            yts = Handle(ZeroSpreadedTermStructure(yts, self.market_.securitySpread(securitySpread, cfg)))
        return DiscountingSwapEngine(yts)                         # QuantLib 엔진
```

**왜**
- 엔진 빌더만 **시장에 접근해 커브를 고른다**. 계약서는 "EUR로 할인해 달라"라는 키만 넘긴다.
- **같은 키면 같은 엔진**을 재사용한다(EUR 스왑 1000개 → 엔진 1개). 메모리가 줄고, 커브가 바뀌면 그 엔진 하나만 통지받는다.
- **(model, engine)으로 등록**한다. engines.yaml의 선택과 빌더가 1:1로 맞는다.

**QuantTool**: `data/portfolio/enginefactory.py` `EngineBuilder`(키별 캐시 내장, `make(*keys)`가 engineImpl 역할), `builders/bond.py` `DiscountingBondEngineBuilder`.

### 2.4 LegBuilder: LegData → QuantLib Leg(현금흐름 목록)

(`OREData/ored/portfolio/legbuilders.hpp/.cpp`, `legdata.cpp`)
```python
class LegBuilder(ABC):
    legType: str
    @abstractmethod
    def buildLeg(self, data: LegData, engineFactory, requiredFixings, configuration, ...) -> Leg: ...

class FixedLegBuilder(LegBuilder):           # legType "Fixed"
    def buildLeg(self, data, engineFactory, requiredFixings, configuration, ...):
        schedule = makeSchedule(data.schedule)
        return makeFixedLeg(data)                # FixedRateLeg(schedule).withNotionals(...).withCouponRates(0.021, A360)

class FloatingLegBuilder(LegBuilder):        # legType "Floating"
    def buildLeg(self, data, engineFactory, requiredFixings, configuration, ...):
        fl = data.concreteLegData                                             # FloatingLegData
        index = engineFactory.market().iborIndex(fl.index, configuration).currentLink()   # ← 시장 사용 지점
        leg = makeIborLeg(data, index, engineFactory)                         # IborLeg(schedule, index).withSpreads(...)
        requiredFixings.add(...)                                              # 과거 fixing이 필요한 날짜 기록
        return leg
```

**왜**: 레그 만드는 법을 상품마다 반복하지 않는다. Swap, Swaption의 기초 스왑, 캡의 레그가 모두 같은 LegBuilder를 쓴다.

**QuantTool**: 아직 없다(`legdata.py` 예정). `Bond.build`가 일정을 직접 만든다.

### 2.5 EngineFactory: 기술자 사무실의 접수 창구

(`OREData/ored/portfolio/enginefactory.hpp/.cpp`)
```python
class MarketContext(Enum): irCalibration, fxCalibration, eqCalibration, pricing

class EngineFactory:
    def __init__(self, data: EngineData, market: Market,
                 configurations: dict[MarketContext, str] = {},     # {pricing: "default"}
                 referenceData=None, iborFallbackConfig=..., extraEngineBuilders=[]):
        self.data_, self.market_, self.configurations_ = data, market, configurations
        self.builders_ = 등록부의 모든 EngineBuilder        # (model, engine, tradeTypes)별
        self.legBuilders_ = 등록부의 모든 LegBuilder         # legType별

    def builder(self, tradeType: str) -> EngineBuilder:
        model, engine = self.data_.model(tradeType), self.data_.engine(tradeType)   # pricingengine.xml
        b = 등록부에서 (model, engine)이 맞고 tradeType을 지원하는 빌더   # 없으면 오류
        b.init(self.market_, self.configurations_, self.data_.modelParameters(tradeType),
               self.data_.engineParameters(tradeType), self.data_.globalParameters())
        return b

    def legBuilder(self, legType: str) -> LegBuilder: ...
    def market(self) -> Market: return self.market_
    def modelBuilders(self): ...          # 엔진 빌더가 만든 모델 빌더들 (재캘리브레이션용, 2.7)
```

**왜**: **팩토리를 만들 때 넘긴 시장**이 모든 빌더에 전달된다. 그래서 `EngineFactory(data, todaysMarket)`과 `EngineFactory(data, simMarket)`의 차이만으로 같은 계약이 다른 시장에 연결된다. 3.8에서 이 사실을 그대로 쓴다.

**QuantTool**: `data/portfolio/enginefactory.py` `EngineFactory(engine_data, market, conventions)`, `from_config(cfg, market)`, `builder(trade_type)`, `conventions(name)`.

### 2.6 Swap::build: 데이터가 상품이 되는 순간

(`OREData/ored/portfolio/swap.cpp` `Swap::build`, 원본 순서 그대로 줄임)
```python
class Swap(Trade):
    def build(self, engineFactory):
        market = engineFactory.market()
        currency = parseCurrency(self.legData_[0].currency)            # EUR
        isXCCY = 레그 통화가 여럿인가                                    # False
        builder = engineFactory.builder("CrossCurrencySwap" if isXCCY else "Swap")   # → SwapEngineBuilder
        configuration = builder.configuration(MarketContext.pricing)    # "default"

        self.legs_, self.legPayers_ = [], []
        for ld in self.legData_:
            legBuilder = engineFactory.legBuilder(ld.legType)           # Fixed / Floating
            self.legs_.append(legBuilder.buildLeg(ld, engineFactory, self.requiredFixings_, configuration))
            self.legPayers_.append(ld.payer)

        self.npvCurrency_, self.notional_ = "EUR", 1e7
        swap = QuantLib.Swap(self.legs_, self.legPayers_)              # QuantLib 상품
        swap.setPricingEngine(builder.engine(currency, discountCurve="", securitySpread="", eqNames=set()))
        #     → 키 "EUR___" 로 캐시된 DiscountingSwapEngine(market.discountCurve("EUR"))
        self.instrument_ = VanillaInstrument(swap)                     # InstrumentWrapper(상품, 승수=1)
        self.maturity_ = 마지막 현금흐름 날짜
```

쓰는 코드
```python
factory = EngineFactory(engine_data, market)
portfolio.build(factory)                              # 모든 trade.build(factory)
t = portfolio.trades()["Swap_20y"]
t.instrument().NPV()                                  # InstrumentWrapper.NPV() = 승수 × QuantLib NPV
t.legs()[1][0].amount()                               # 첫 변동 쿠폰 (EURIBOR 6M 선도 × 기간 × 원금)
```

연결 구조 (build 후)
```
Trade "Swap_20y"
 └ instrument_: VanillaInstrument
    └ QuantLib.Swap(legs_, payers)
       ├ legs_[0]: FixedRateCoupon × 20
       ├ legs_[1]: IborCoupon × 40 ── index: Euribor6M ── 예측 커브 Handle ─┐
       └ engine: DiscountingSwapEngine ── 할인 커브 Handle ──────────────────┤
                                                                            ▼
                                                         market의 MarketImpl 창고 (EUR6M, EUR1D)
```

**엔진 팩토리가 없을 때와 비교**
```python
# QuantLib 직접: 상품마다 사람이 엔진과 커브를 고른다
for swap in swaps:                                              # 1000개
    swap.setPricingEngine(ql.DiscountingSwapEngine(eur1d))      # 엔진 1000개, 커브 선택 코드가 상품마다 흩어짐
# 시장을 바꾸려면(시나리오) 1000곳의 커브 연결을 다시 해야 한다

# ORE: 계약은 데이터, 엔진 선택은 설정, 커브 선택은 엔진 빌더 한 곳
portfolio.build(EngineFactory(engine_data, any_market))         # any_market만 바꾸면 전부 다시 연결
```

**QuantTool**: `data/portfolio/bond.py` `Bond.build`가 같은 순서로 동작한다. `factory.builder("Bond")` → `ql.FixedRateBond` → `builder.engine(self.discount)` → `InstrumentWrapper`.

### 2.7 Model: 엔진 빌더 안에서 만드는 동학 모델 (간단히)

(`OREData/ored/model/lgmbuilder.hpp`, `portfolio/builders/swaption.hpp/.cpp`)
```python
class LGMGridSwaptionEngineBuilder(LGMSwaptionEngineBuilder):    # model "LGM", engine "Grid" (Bermudan)
    def engineImpl(self, id, ccy, expiries, maturity, strikes):
        calib = LgmBuilder(self.market_, IrLgmData(reversion=0.03, calibration="Bootstrap", ...),
                           configuration(MarketContext.irCalibration), ...)   # 캘리브레이션 바스켓 → 모델
        self.modelBuilders_[id] = calib                                  # 시나리오에서 재캘리브레이션할 대상
        return NumericLgmMultiLegOptionEngine(calib.model(), ...)   # 격자 수치 엔진 (QuantExt)
```
- 모델은 시장(스왑션 vol)에 캘리브레이션된다. 그래서 시장이 흔들리면 **다시 캘리브레이션할지**를 고를 수 있다(`SensitivityAnalysis(..., recalibrateModels)`).
- **QuantTool**: `data/model/` 예정(LocalVolBuilder, HestonBuilder).

---

## 3. OREAnalytics: 민감도·시나리오 분석

> 범위: 민감도와 시나리오 분석, 그리고 그것에 쓰는 장치. 노출 시뮬레이션(XVA)과 VaR는 같은 장치를 쓰지만 범위 밖이라 3.10에 한 줄씩만 적는다.

### 3.1 RiskFactorKey와 Scenario: "무엇을 얼마로"

(`QuantExt/qle/termstructures/scenario.hpp`, `OREAnalytics/orea/scenario/scenario.hpp`, `simplescenario.hpp`)
```python
class RiskFactorKey:                     # 시뮬레이션 시장의 격자점 하나
    class KeyType(Enum):
        DiscountCurve, YieldCurve, IndexCurve, SwaptionVolatility, OptionletVolatility,
        FXSpot, FXVolatility, EquitySpot, DividendYield, EquityVolatility, ...
    keytype: KeyType
    name: str                            # "EUR", "EUR-EURIBOR-6M", "SPX"
    index: int                           # 격자 위치: 커브면 tenor 번호, vol 서페이스면 (만기 × 행사가)를 펼친 번호

RiskFactorKey(KeyType.DiscountCurve, "EUR", 6)      # EUR 할인 커브 격자 7번째 점(2Y)

class Scenario(ABC):                     # 격자점 → 값
    def asof(self) -> Date: ...
    def label(self) -> str: ...
    def keys(self) -> list[RiskFactorKey]: ...
    def add(self, key, value): ...
    def get(self, key) -> float: ...
    def has(self, key) -> bool: ...
    def isAbsolute(self) -> bool: ...    # True: 값 자체(할인계수 0.97), False: 기준 대비 차이(spreaded 모드)
    def clone(self) -> Scenario: ...

class SimpleScenario(Scenario): ...      # dict 기반 구현
```

**왜**: 시나리오는 시장 객체가 아니라 **좌표(키) → 숫자**다. 그래서 민감도·스트레스·과거 변화·PCA 같은 시나리오 생성 규칙이 모두 같은 형태의 결과를 내고, 시장 적용은 한 곳(`applyScenario`)에서 한다.

**QuantTool**: `qle/scenario.py` `RiskFactorKey(kind, name, point)`(정수 대신 `("5Y",)` 같은 라벨), `analytics/scenario/scenario.py` `Scenario(label, shifts)`(항상 기준 대비 이동량).

### 3.2 ScenarioSimMarketParameters: 흔들 수 있는 격자를 정한다

입력 (`Examples/MarketRisk/Input/simulation.xml`, 발췌. 마지막 블록은 `Examples/Performance/Input/sensimarket.xml`)
```xml
<Market>
  <BaseCurrency>EUR</BaseCurrency>
  <YieldCurves>
    <Configuration>
      <Tenors>2W,1M,3M,6M,9M,1Y,2Y,3Y,4Y,5Y,7Y,10Y,15Y,20Y,25Y,30Y</Tenors>
      <Interpolation>LogLinear</Interpolation>
      <Extrapolation>Y</Extrapolation>
    </Configuration>
  </YieldCurves>
  <Indices><Index>EUR-EURIBOR-6M</Index><Index>EUR-EONIA</Index>…</Indices>
  <EquityVolatilities>
    <Simulate>true</Simulate>
    <ReactionToTimeDecay>ForwardVariance</ReactionToTimeDecay>
    <Names><Name>SPX</Name></Names>
    <Expiries>2W,1M,3M,6M,1Y,2Y,3Y,5Y,10Y,15Y,20Y,30Y</Expiries>
    <SimulateATMOnly>true</SimulateATMOnly>
  </EquityVolatilities>
  <!-- sensimarket.xml: 서페이스 전체를 격자로, 스마일 동학 지정 -->
  <EquityVolatilities>
    <Surface><StandardDeviations name="RIC:.SPX">-3,-2,-1,-0.5,…,0,…,2,3</StandardDeviations></Surface>
    <SmileDynamics key="RIC:.SPX">StickyStrike</SmileDynamics>
  </EquityVolatilities>
</Market>
```

받는 클래스 (`OREAnalytics/orea/scenario/scenariosimmarketparameters.hpp`, `QuantExt/qle/termstructures/dynamicstype.hpp`)
```python
class ScenarioSimMarketParameters:
    baseCcy: str
    def yieldCurveTenors(self, key) -> list[Period]: ...   # 커브별 격자 만기 (없으면 기본 Configuration)
    def indices(self) -> list[str]: ...                    # 시뮬레이션할 지수 (예측 커브도 격자화)
    interpolation: str; extrapolation: str
    def equityVolIsSurface(self, name) -> bool: ...
    def equityVolMoneyness(self, name) -> list[float]: ...
    def equityVolSmileDynamics(self, name) -> str: ...     # "StickyStrike" | "StickyMoneyness"
    simulateEquityVolATMOnly: bool

class Stickyness(Enum): StickyStrike, StickyMoneyness, StickySABR       # dynamicstype.hpp
class ReactionToTimeDecay(Enum): ConstantVariance, ForwardForwardVariance
class YieldCurveRollDown(Enum): ConstantDiscounts, ForwardForward
```

**왜**: 원래 시장의 커브는 헬퍼 수십 개와 부트스트랩으로 만든 객체라 직접 흔들기 어렵다. 그래서 **정해진 격자점의 값으로 다시 표현**하고 그 점들만 흔든다.
- **빠르다**: 재부트스트랩이 없다.
- **좌표가 고정된다**: PCA, 과거 변화, 민감도가 같은 점을 가리킨다.
- **변화가 국소적이다**: 1Y vol을 흔들면 1Y만 움직이고, 재피팅이 변화를 다른 곳으로 번지게 하지 않는다.

**스마일 동학(SmileDynamics)이 여기 있다는 점이 중요하다.** spot이 움직일 때 vol 서페이스를 행사가 기준으로 붙잡을지(StickyStrike) moneyness 기준으로 붙잡을지(StickyMoneyness)를 **시뮬레이션 시장이** 정한다. SSR 같은 다른 동학 규칙도 이 자리에 들어간다. 계약·엔진은 모른다.

**QuantTool**: `configs/scenario/simmarket.yaml` → `data/configuration/simmarketparameters.py` `ScenarioSimMarketParameters`(커브별 tenors, `spreaded`, `roll_down: ForwardForward`). vol 격자와 스마일 동학은 예정이다.

### 3.3 ScenarioSimMarket: 초기 시장을 격자로 다시 표현한 "흔들 수 있는 시장"

(`OREAnalytics/orea/simulation/simmarket.hpp`, `orea/scenario/scenariosimmarket.hpp/.cpp`, `QuantExt/qle/termstructures/spreadeddiscountcurve.hpp`)
```python
class SimMarket(MarketImpl):             # 창고는 TodaysMarket과 같은 MarketImpl
    def update(self, d: Date):                       # simmarket.cpp, 원본 순서
        self.preUpdate()
        self.updateDate(self.loadNextScenario(d))    # 생성기.next(d) → 평가일 = d (기준 커브 roll)
        self.applyLoadedScenario()                   # applyScenario: 격자 Quote 변경 → Observer → 연결된 상품이 "낡음"
        self.postUpdate()
        self.updateAsd()                             # (집계용 부가 데이터)
    def reset(self): ...                             # asof, 기준 시나리오로

class ScenarioSimMarket(SimMarket):
    def __init__(self, initMarket: Market, parameters: ScenarioSimMarketParameters,
                 configuration="default", curveConfigs=..., todaysMarketParams=...,
                 continueOnError=False, useSpreadedTermStructures=False, ...):
        for name in parameters.yieldCurveNames() + 할인 통화들 + parameters.indices():
            init = initMarket.discountCurve(name)          # 초기 시장 커브
            dates = [asof + t for t in parameters.yieldCurveTenors(name)]
            if not useSpreadedTermStructures:
                # 절대 모드: 격자 Quote = 할인계수 자체
                quotes = [SimpleQuote(init.discount(d)) for d in dates]
                curve = InterpolatedDiscountCurve(dates, quotes, settlementDays=0, ...)   # 평가일을 따라 이동
            else:
                # spreaded 모드: 격자 Quote = 초기 커브 대비 비율(처음엔 1)
                quotes = [SimpleQuote(1.0) for d in dates]
                curve = SpreadedDiscountCurve(init, times, quotes, ...)   # 기준 상태 = 초기 커브와 정확히 같음
            for i, q in enumerate(quotes):
                self.simData_[RiskFactorKey(KeyType.DiscountCurve, name, i)] = q
            self.yieldCurves_[(configuration, Discount, name)] = Handle(curve)
            # 지수는 이 격자 커브를 예측 커브로 다시 연결: iborIndices_[...] = index.clone(simCurve)
        # vol: 서페이스를 (만기 × moneyness/행사가) 격자 Quote로. smileDynamics에 따라 spot 이동 시 반응을 정함
        self.baseScenario_ = SimpleScenario(asof, "BASE", {k: q.value() for k, q in self.simData_.items()})

    def applyScenario(self, scenario):
        for key in scenario.keys():
            self.simData_[key].setValue(scenario.get(key))   # 격자 Quote만 바꾼다

    def baseScenario(self) -> Scenario: ...
    def baseScenarioAbsolute(self) -> Scenario: ...          # spreaded일 때 절대값 버전
    scenarioGenerator_: ScenarioGenerator
```

쓰는 코드
```python
sim = ScenarioSimMarket(market, sim_params, useSpreadedTermStructures=True)
sim.discountCurve("EUR").discount(Date(5, 2, 2026))   # 초기 시장과 같은 값 (spreaded)
k = RiskFactorKey(KeyType.DiscountCurve, "EUR", 6)    # 2Y 격자점
s = sim.baseScenario().clone(); s.add(k, s.get(k) * exp(-0.0001 * 2.0))   # 2Y 제로 +1bp 상당
sim.applyScenario(s)                                  # 이 시장에 연결된 모든 상품이 낡음 → 다음 NPV에서 재계산
```

**왜**
- `TodaysMarket`과 **같은 창고·같은 규격**이라 계약 코드가 그대로 붙는다.
- **spreaded 모드**는 기준 상태에서 원 커브와 정확히 같아서 "격자로 바꾼 것 자체"에서 오는 오차가 없다.
- **흔드는 곳이 격자 Quote 하나뿐**이라 시나리오를 적용하고 되돌리기 쉽다.

**QuantTool**: `analytics/scenario/simmarket.py` `SimMarket`(`update`, `reset`, `active`), `ScenarioSimMarket`(`sim_data`, `base_values`, `apply_scenario`, spreaded = `PiecewiseZeroSpreadedTermStructure`, ForwardForward roll), `base_reconciliation`.

### 3.4 SensitivityScenarioData: 무엇을 얼마나, 어떤 방식으로 흔들지

입력 (`Examples/MarketRisk/Input/sensitivity.xml`, 발췌)
```xml
<DiscountCurves>
  <DiscountCurve ccy="EUR">
    <ShiftType>Absolute</ShiftType>
    <ShiftSize>0.0001</ShiftSize>
    <ShiftSize key="IR_FD">0.001</ShiftSize>            <!-- 템플릿 IR_FD인 거래는 10bp로 -->
    <ShiftScheme>Forward</ShiftScheme>
    <ShiftScheme key="IR_FD">Central</ShiftScheme>      <!-- 템플릿 IR_FD인 거래는 중심 차분 -->
    <ShiftTenors>2W,1M,3M,6M,9M,1Y,2Y,3Y,4Y,5Y,7Y,10Y,15Y,20Y,25Y,30Y</ShiftTenors>
    <ParConversion>
      <Instruments>OIS,OIS,…,OIS</Instruments>           <!-- 격자점마다 par 변환에 쓸 시장 상품 -->
      <SingleCurve>true</SingleCurve>
      <Conventions><Convention id="OIS">EUR-OIS-CONVENTIONS</Convention></Conventions>
    </ParConversion>
  </DiscountCurve>
</DiscountCurves>
<EquitySpots><EquitySpot equity="SPX"><ShiftType>Relative</ShiftType><ShiftSize>0.01</ShiftSize></EquitySpot></EquitySpots>
<EquityVolatilities>
  <EquityVolatility equity="SPX"><ShiftType>Absolute</ShiftType><ShiftSize>0.01</ShiftSize>
    <ShiftExpiries>2W,1M,…,30Y</ShiftExpiries><ShiftStrikes/></EquityVolatility>
</EquityVolatilities>
<CrossGammaFilter><Pair>DiscountCurve/EUR,IndexCurve/EUR</Pair></CrossGammaFilter>
```

받는 클래스 (`OREAnalytics/orea/scenario/sensitivityscenariodata.hpp`)
```python
class ShiftType(Enum): Absolute, Relative
class ShiftScheme(Enum): Forward, Backward, Central

@dataclass
class ShiftData:
    shiftType: ShiftType = Absolute
    shiftSize: float = 0.0
    shiftScheme: ShiftScheme = Forward
    # 템플릿별 덮어쓰기: keyedShiftSize["IR_FD"] = 0.001, keyedShiftScheme["IR_FD"] = Central
class CurveShiftData(ShiftData):      shiftTenors: list[Period]
class CurveShiftParData(CurveShiftData):
    parInstruments: list[str]          # ["OIS", …] 격자점별
    parInstrumentSingleCurve: bool
    parInstrumentConventions: dict[str, str]
class SpotShiftData(ShiftData): ...
class VolShiftData(ShiftData):        shiftExpiries: list[Period]; shiftStrikes: list[float]

class SensitivityScenarioData:
    discountCurveShiftData: dict[str, CurveShiftData]     # "EUR" → …
    indexCurveShiftData: dict[str, CurveShiftData]        # "EUR-EURIBOR-6M" → …
    equityShiftData: dict[str, SpotShiftData]
    equityVolShiftData: dict[str, VolShiftData]
    computeGamma: bool                                   # up/down 둘 다 만들지
    crossGammaFilter: list[tuple[str, str]]              # 교차 감마를 볼 요인 쌍
    useSpreadedTermStructures: bool
    thetaPeriod: Period                                  # theta 계산 시 하루 이동 등
    parConversion: bool
```

**왜**
- 흔드는 크기·방식·격자를 계약이나 코드가 아니라 **설정**이 정한다.
- 결과 단위가 명확해진다: "EUR 할인 커브 2Y 격자점 +1bp 절대 이동당 NPV 변화".

### 3.5 SensitivityScenarioGenerator: 시나리오 목록 만들기 (+ 거래별 템플릿)

(`OREAnalytics/orea/scenario/sensitivityscenariogenerator.hpp`, `shiftscenariogenerator.hpp`, `OREData/ored/portfolio/trade.cpp` `setSensitivityTemplate`)
```python
class ShiftScenarioGenerator(ScenarioGenerator):
    scenarios_: list[Scenario]           # [0]은 기준
    def next(self, d) -> Scenario: ...   # 차례로 하나씩
    def samples(self) -> int: ...
    def scenarioDescriptions(self) -> list[ScenarioDescription]: ...   # "Up:DiscountCurve/EUR/6/2Y" 같은 설명
    def shiftSizes(self) -> dict[RiskFactorKey, float]: ...

class SensitivityScenarioGenerator(ShiftScenarioGenerator):
    def __init__(self, sensitivityData, baseScenario, simMarketData, simMarket,
                 scenarioFactory, overrideTenors, sensitivityTemplate="", continueOnError=False,
                 baseScenarioAbsolute=None):
        self.generateScenarios()
    def generateScenarios(self):
        for up in [True, False] if 필요하면 else [True]:   # Forward면 up만, Central·gamma면 down도
            self.generateDiscountCurveScenarios(up)  # EUR 2W, 1M, …, 30Y 격자점을 하나씩 ±1bp
            self.generateIndexCurveScenarios(up)
            self.generateEquityScenarios(up)         # SPX spot ±1% (Relative)
            self.generateEquityVolScenarios(up)      # SPX vol 만기별 ±1%p
        self.generateCrossGammaScenarios()           # crossGammaFilter 쌍마다 두 점을 동시에 up
```

시나리오 목록 예시 (EUR 할인 커브 16점, Forward, gamma 없음)
```
0  BASE
1  Up:DiscountCurve/EUR/0/2W   (2W 격자점만 +1bp)
2  Up:DiscountCurve/EUR/1/1M
…
16 Up:DiscountCurve/EUR/15/30Y
```

**거래별 민감도 규칙: SensitivityTemplate**
- 엔진 설정에 `<Parameter name="SensitivityTemplate">IR_FD</Parameter>`를 두면, 그 엔진으로 평가되는 거래의 `trade.sensitivityTemplate()`이 `"IR_FD"`가 된다(`Examples/Exposure/Input/pricingengine_callablebond.xml`).
- sensitivity.xml의 `ShiftSize key="IR_FD"`, `ShiftScheme key="IR_FD"`가 그 거래들에만 적용된다. 예: 수치 엔진(FD)이라 1bp는 잡음이 커서 10bp 중심 차분을 쓴다.
- `SensitivityAnalysis`는 포트폴리오를 템플릿별로 나누고, 템플릿마다 생성기를 따로 만들어 돌린다(3.8).
- 결과는 목표 크기(기본 1bp)로 다시 환산한다. `scaling = targetShiftSize / actualShiftSize`
- 즉 **ORE에도 "상품별로 민감도 계산 규칙을 바꾸는" 공식 경로가 있다.** 다만 바꿀 수 있는 것은 이동 크기·방식이다. SSR처럼 요인 간 연동 규칙은 시뮬레이션 시장의 스마일 동학(3.2) 쪽 몫이다.

**QuantTool**: `analytics/scenario/sensitivityscenariogenerator.py` `SensitivityScenarioGenerator`(key rate +1bp와 평행 +1bp, Forward만). Central·gamma·템플릿은 예정이다.

### 3.6 ValuationEngine, ValuationCalculator, NPVCube: 반복 평가 루프

(`OREAnalytics/orea/engine/valuationengine.hpp`, `valuationcalculator.hpp`, `orea/cube/npvcube.hpp`)
```python
class NPVCube(ABC):                      # 거래 × 날짜 × 표본(× 깊이)
    def setT0(self, value, trade, depth=0): ...      # 기준 NPV
    def set(self, value, trade, date, sample, depth=0): ...
    def getT0(self, trade, depth=0) -> float: ...
    def get(self, trade, date, sample, depth=0) -> float: ...
class NPVSensiCube(NPVCube): ...         # 민감도용: 날짜 1개, 표본 = 시나리오, 기준과 다른 값만 저장(희소)

class ValuationCalculator(ABC):          # "평가 후 무엇을 기록할지"를 꽂는 자리
    def calculate(self, trade, tradeIndex, simMarket, outputCube, dateIndex, sample, isCloseOut): ...
class NPVCalculator(ValuationCalculator):            # NPV를 기준 통화로 바꿔 기록
    def calculate(self, trade, i, simMarket, cube, d, s, ...):
        cube.set(trade.instrument().NPV() * fx(trade.npvCurrency()), i, d, s)
class CashflowCalculator(ValuationCalculator): ...   # 기간 중 현금흐름

class ValuationEngine:
    def __init__(self, today, dateGrid, simMarket, modelBuilders={}, recalibrateModels=False, fixingManager=None): ...
    def buildCube(self, portfolio, outputCube, calculators, errorPolicy, ...):
        self.simMarket.reset()
        for calc in calculators: calc.calculateT0(...)          # 기준 NPV → setT0
        for sample in range(outputCube.samples()):               # 시나리오(표본)마다
            for d_idx, d in enumerate(self.dateGrid):            # 날짜마다 (민감도는 asof 하나)
                self.simMarket.update(d)                         # 생성기에서 다음 시나리오 → 적용
                if self.recalibrateModels: [mb.recalibrate() for mb in self.modelBuilders]
                for t_idx, trade in enumerate(portfolio.trades()):
                    for calc in calculators:
                        calc.calculate(trade, t_idx, self.simMarket, outputCube, d_idx, sample)
        self.simMarket.reset()
```

**왜**
- **포트폴리오는 한 번만 조립한다.** 시나리오마다 다시 build하지 않고, 시장 Quote만 바꾸면 Observer가 다시 계산하게 만든다.
- **계산기를 꽂는 구조**라 같은 루프로 NPV, 현금흐름, 행사 여부 등을 기록한다.
- 날짜 축은 노출 시뮬레이션용이다. 민감도는 `DateGrid("1,0W")`, 즉 날짜 하나만 쓴다.

**QuantTool**: `analytics/engine/valuationengine.py` `ValuationEngine(asof, dates, sim_market).build_cube(portfolio)` → `NPVCube(base, npv)`(pandas). 계산기 구조는 없고 NPV만 기록한다.

### 3.7 SensitivityCube: NPV 표 → delta, gamma, cross gamma

(`OREAnalytics/orea/cube/sensitivitycube.cpp`)
```python
class SensitivityCube:
    def __init__(self, cube: NPVSensiCube, scenarioDescriptions, targetShiftSizes, actualShiftSizes, shiftSchemes): ...
    def delta(self, trade, key: RiskFactorKey) -> float:
        base = cube.getT0(trade)
        if scheme[key] == Forward:  return (up(trade, key) - base) * scaling(key)
        if scheme[key] == Backward: return (base - down(trade, key)) * scaling(key)
        if scheme[key] == Central:  return (up(trade, key) - down(trade, key)) / 2 * scaling(key)
    def gamma(self, trade, key) -> float:
        return (up(trade, key) - 2 * base + down(trade, key)) * scaling(key) ** 2
    def crossGamma(self, trade, (k1, k2)) -> float:
        return up12(trade) - up(trade, k1) - up(trade, k2) + base
# scaling = targetShiftSize / actualShiftSize  (템플릿이 10bp로 계산했어도 1bp 기준으로 보고)
```
- ORE의 delta는 "**설정한 이동 1회당 NPV 변화**"다(1bp 이동이면 1bp당 손익). 단위 이동(1.0)당 미분값이 아니다.

**QuantTool**: `analytics/engine/sensitivityanalysis.py` `SensitivityCube(cube, data)`의 `key_rate_dv01(curve)`, `parallel_dv01(curve)`(Forward delta만). gamma·cross gamma는 예정이다.

### 3.8 SensitivityAnalysis: 위 전부를 원본 순서로

(`OREAnalytics/orea/engine/sensitivityanalysis.cpp` `generateSensitivities`, 단일 스레드 경로를 줄임)
```python
class SensitivityAnalysis:
    def __init__(self, portfolio, market, marketConfiguration, engineData,
                 simMarketData: ScenarioSimMarketParameters,
                 sensitivityData: SensitivityScenarioData,
                 recalibrateModels: bool, ...): ...

    def generateSensitivities(self):
        configurations = {MarketContext.pricing: self.marketConfiguration_}
        # 0) 템플릿을 알려면 먼저 오늘 시장에 한 번 build
        if not self.portfolio_.isBuilt():
            self.portfolio_.build(EngineFactory(self.engineData_, self.market_, configurations))
        templateIds = [""] + (설정에 있는 템플릿 ∩ 포트폴리오 거래들의 sensitivityTemplate())

        # a) 시뮬레이션 시장: 초기 시장을 격자로 재표현
        self.simMarket_ = ScenarioSimMarket(self.market_, self.simMarketData_, self.marketConfiguration_,
                                            ..., useSpreadedTermStructures=self.sensitivityData_.useSpreadedTermStructures())
        # b) 템플릿마다 시나리오 생성기
        generators = [SensitivityScenarioGenerator(self.sensitivityData_, self.simMarket_.baseScenario(),
                                                   self.simMarketData_, self.simMarket_,
                                                   DeltaScenarioFactory(self.simMarket_.baseScenario()),
                                                   overrideTenors, tid, ...) for tid in templateIds]
        ed = copy(self.engineData_); ed.globalParameters()["RunType"] = "SensitivityDelta" (또는 "SensitivityDeltaGamma")
        dg = DateGrid("1,0W")                                        # 날짜 하나 (asof)
        calculators = [NPVCalculator(self.simMarketData_.baseCcy())]

        self.sensiCubes_ = []
        for pf, gen in splitPortfolioByScenarioGenerators(self.portfolio_, templateIds, generators):
            cube = DoublePrecisionSensiCube(pf.ids(), asof, gen.samples())
            # c) 생성기를 시뮬레이션 시장에 건다
            self.simMarket_.scenarioGenerator = gen
            # d) 같은 계약을 시뮬레이션 시장에 다시 연결
            factory = EngineFactory(ed, self.simMarket_, configurations)
            pf.reset(); pf.build(factory)
            # e) 시나리오마다 update → NPV → cube
            engine = ValuationEngine(asof, dg, self.simMarket_, factory.modelBuilders(), self.recalibrateModels_)
            engine.buildCube(pf, cube, calculators)
            # f) 민감도
            self.sensiCubes_.append(SensitivityCube(cube, gen.scenarioDescriptions(),
                                                    generators[0].shiftSizes(), gen.shiftSizes(), gen.shiftSchemes()))
```

쓰는 코드 (build 포함 전체)
```python
# 1~2장: 오늘 시장과 포트폴리오
market = TodaysMarket(asof, tm_params, loader, curve_configs)
portfolio = Portfolio(); portfolio.fromFile("portfolio_swap.xml")
portfolio.build(EngineFactory(engine_data, market))
portfolio.trades()["Swap_20y"].instrument().NPV()                 # t0 가격

# 3장: 민감도
sim_params = ScenarioSimMarketParameters(); sim_params.fromFile("simulation.xml")
sensi_data = SensitivityScenarioData(); sensi_data.fromFile("sensitivity.xml")
sa = SensitivityAnalysis(portfolio, market, "default", engine_data, sim_params, sensi_data,
                         recalibrateModels=True)
sa.generateSensitivities()
cube = sa.sensiCubes()[0]
cube.delta("Swap_20y", RiskFactorKey(KeyType.DiscountCurve, "EUR", 6))       # EUR 할인 2Y +1bp당 손익
cube.delta("Swap_20y", RiskFactorKey(KeyType.IndexCurve, "EUR-EURIBOR-6M", 11))   # 예측 커브 10Y
```

**QuantTool**: `SensitivityAnalysis(portfolio, market, cfg).generate_sensitivities()` → `sensi_cube().key_rate_dv01("UST")`가 a)~f)를 같은 순서로 한다. 템플릿 분할은 없다.

### 3.9 ParSensitivityAnalysis: zero 민감도 → 헷지 상품(par) 민감도

(`OREAnalytics/orea/engine/parsensitivityanalysis.hpp/.cpp`, `parsensitivityinstrumentbuilder.cpp`)
```python
class ParSensitivityAnalysis:
    def __init__(self, asof, simMarketParams, sensitivityData, marketConfiguration, ...): ...
    def computeParInstrumentSensitivities(self, simMarket: ScenarioSimMarket):
        # 격자점마다 sensitivity.xml ParConversion의 상품(예: EUR 2Y OIS)을 시뮬레이션 시장 위에 만든다
        par_instruments = ParSensitivityInstrumentBuilder().createParInstruments(...)
        # 같은 zero 시나리오(격자점 하나 +1bp)마다 각 par 상품의 par rate 변화를 잰다
        for k_zero in 격자점:
            simMarket.applyScenario(up(k_zero))
            for k_par, inst in par_instruments:
                self.parSensi_[(k_par, k_zero)] = (inst.parRate() - base_par[k_par]) / shift   # ∂par_i/∂zero_j
        simMarket.reset()
    def alignPillars(self): ...          # par 상품 만기와 격자 만기 맞추기

class ParSensitivityConverter:
    def __init__(self, parSensitivities, shiftSizes): ...   # 야코비안 J[i][j] = ∂par_i/∂zero_j
    def convertSensitivity(self, zeroSensitivities):        # dNPV/dzero (벡터)
        return solve(J.T, zeroSensitivities)                # dNPV/dpar = (Jᵀ)⁻¹ · dNPV/dzero
```

**왜**: 격자 zero 민감도는 계산이 빠르지만 직접 사고팔 수 없다. 헷지 수량은 시장 상품(OIS, IRS, 국채) 기준이어야 한다. 연쇄법칙으로 변환하면 재부트스트랩 없이 par 민감도를 얻는다.

**QuantTool**: 아직 없다(`analytics/engine/parsensitivityanalysis.py` 예정). UST라면 par 상품은 국채 par bond다.

### 3.10 같은 장치를 쓰는 다른 분석 (한 줄씩)

| 분석 | 원본 | 어떻게 | 이 프로젝트 |
|---|---|---|---|
| 스트레스 테스트 | `orea/engine/stresstest.cpp`, `StressScenarioGenerator` | 정해진 이동 묶음(예: 평행 +100bp, spot −20%)을 시나리오로. 3.8과 같은 루프 | 결정론적 시나리오라 범위 안. PCA 시나리오도 같은 틀 |
| P&L explain | `orea/engine/pnlexplainreport.cpp` | t → t+1 실제 손익을 민감도 × 실제 요인 변화 + 잔차로 귀속 | 나중의 헷지 PnL 분석과 직접 관련 |
| 시장 위험 백테스트 | `orea/engine/marketriskbacktest.cpp` | 과거 날짜별 예측 손익과 실제 손익 비교 | 헷지 백테스트 설계 때 참고 |
| VaR | `parametricvar.cpp`, `historicalsimulationvar.cpp` | 공분산 또는 과거 시나리오 분포 | 범위 밖 (통계적 리스크) |
| 노출·XVA | `orea/aggregation/`, `amcvaluationengine.cpp` | 모델로 경로 × 날짜 시뮬레이션 → cube → CVA 등 | 범위 밖 (신용) |

---

## 4. 한눈에 보는 대응표

| 단계 | ORE | QuantTool | 상태 |
|---|---|---|---|
| 시세 | `MarketDatum`, `Loader`, `CSVLoader` | `data/marketdata/loader.py` | ✓ (DuckDBLoader 예정) |
| 관례 | `Conventions` (전역) | `data/configuration/conventions.py` (전달) | ✓ |
| 커브 레시피 | `CurveConfigurations`, `YieldCurveConfig` | `data/configuration/curveconfig.py` | ✓ (UST) |
| 오늘 시장 구성 | `TodaysMarketParameters` (+configuration, 이름→레시피) | `todaysmarketparameters.py` | ✓ 단순형 |
| 오늘 시장 | `TodaysMarket`, `MarketImpl`, `DependencyGraph`, `YieldCurve` | `todaysmarket.py`, `market.py`, `dependencygraph.py`, `yieldcurve.py` | ✓ |
| 계약 | `Trade`, `Envelope`, `LegData`, `Portfolio` | `trade.py`, `bond.py`, `portfolio.py` | ✓ Bond (LegData 예정) |
| 엔진 선택 | `EngineData` | `enginedata.py` | ✓ |
| 엔진 | `EngineBuilder`, `CachingPricingEngineBuilder`, `EngineFactory`, `LegBuilder` | `enginefactory.py`, `builders/bond.py` | ✓ (LegBuilder 예정) |
| 모델 | `ModelBuilder`, 재캘리브레이션 | `data/model/` | 예정 |
| 리스크 요인 | `RiskFactorKey`, `Scenario` | `qle/scenario.py`, `analytics/scenario/scenario.py` | ✓ |
| 격자 | `ScenarioSimMarketParameters` (+스마일 동학) | `simmarketparameters.py` | ✓ 커브 (vol·동학 예정) |
| 시뮬레이션 시장 | `SimMarket`, `ScenarioSimMarket` (spreaded) | `analytics/scenario/simmarket.py` | ✓ |
| 민감도 설정 | `SensitivityScenarioData` (Forward/Central, gamma, 템플릿) | `SensitivityScenarioData` (bp만) | 단순형 |
| 생성기 | `SensitivityScenarioGenerator` | `sensitivityscenariogenerator.py` | ✓ Forward (Central·gamma·템플릿 예정) |
| 반복 평가 | `ValuationEngine`, `ValuationCalculator`, `NPVCube` | `valuationengine.py` `NPVCube` | ✓ NPV만 |
| 민감도 결과 | `SensitivityCube` (delta·gamma·crossGamma) | `SensitivityCube` (key rate·평행 DV01) | 단순형 |
| par 변환 | `ParSensitivityAnalysis`, `ParSensitivityConverter` | — | 예정 |
| 스트레스·PnL explain | `StressTest`, `PnlExplainReport` | — | 예정 |
