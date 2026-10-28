# 시장 데이터 플랫폼 설계

QuantTool, 팩터 모델 등 여러 프로젝트가 같이 쓰는 시장 데이터를 받아 표준화해 보관하는 **별도 프로젝트**의 설계다.
지금은 이 레포에 두고, 시작할 때 독립 레포(예: `market-data`)로 옮긴다.

---

## 1. 왜 별도 프로젝트인가

```
            ┌──────────────── market-data (데이터 플랫폼) ────────────────┐
 출처들 ──► │ 수집 → 원본 보관 → 정규화 → 검증 → 적재 → market.duckdb    │
            └───────────────────────────────┬──────────────────────────────┘
                                            │  읽기 전용 (SQL)
                     ┌──────────────────────┼──────────────────────┐
                     ▼                      ▼                      ▼
               quant-tool              factor-model             노트북·연구
        (Loader가 SQL로 asof 조회)   (시계열 SQL로 조회)
```

- **의존 방향이 한쪽**이다. 분석 프로젝트들이 데이터 플랫폼을 쓰고, 데이터 플랫폼은 그 프로젝트들을 모른다.
- 수집 주기(매일)와 분석 개발 주기가 다르다. 분리해야 한쪽을 고칠 때 다른 쪽이 흔들리지 않는다.
- 데이터 키 규칙(어떤 시세를 어떤 이름으로 부르는지)을 한 곳에서 관리한다. QuantTool의 시세 키도 여기 규칙을 따른다.
- 작은 규모에서는 서버가 필요 없다. **DuckDB 파일 하나**가 DB다.

### DuckDB를 쓰는 이유

| | DuckDB | SQLite | Postgres |
|---|---|---|---|
| 형태 | 파일 하나, 서버 없음 | 파일 하나, 서버 없음 | 서버 |
| 강점 | 분석용(열 지향): 시계열 집계·피벗이 빠름, pandas·parquet와 바로 연동 | 거래용(행 단위 쓰기) | 여럿이 동시에 쓰기 |
| 이 용도 | **적합** | 가능하지만 분석이 느림 | 과함 |

DuckDB는 `ATTACH 'market.duckdb' (READ_ONLY)`로 다른 프로젝트에서 읽기 전용으로 붙일 수 있다.

---

## 2. 기본 개념

| 용어 | 뜻 | 이 설계에서 |
|---|---|---|
| **테이블** | 행과 열로 된 표. 행 하나가 기록 하나 | `series`, `observation` 등 |
| **기본키(PK)** | 행을 유일하게 식별하는 열 조합. 중복을 막는다 | `observation`의 `(series_id, obs_date)` |
| **외래키(FK)** | 다른 테이블의 기본키를 가리키는 열. 관계를 만든다 | `observation.series_id → series.series_id` |
| **엔티티(마스터·차원) 테이블** | "무엇인가"를 정의. 잘 안 바뀜 | `source`, `series` (어떤 시계열인지) |
| **관측(팩트) 테이블** | "언제 얼마였나". 계속 쌓임 | `observation` (날짜별 값) |
| **뷰(view)** | 저장하지 않고 조회문에 이름을 붙인 것 | `v_quote`(키로 바로 조회), `v_ust_par_wide`(넓은 표) |
| **ETL** | Extract(수집) → Transform(변환) → Load(적재) | 3장 |
| **upsert** | 있으면 갱신, 없으면 삽입 | 재실행해도 결과가 같게(멱등) |

**엔티티와 관측을 나누는 이유**: "UST 10년 par yield, 출처 FRED DGS10, 단위 퍼센트→소수, 만기 10Y" 같은 설명을 값마다 반복해 적지 않는다.
설명은 `series`에 한 번, 값은 `observation`에 `series_id`로만 붙인다. 설명을 고쳐도 값은 그대로다.

---

## 3. 흐름: 수집 → 원본 보관 → 정규화 → 검증 → 적재

```
① 수집(extract)      출처 API/파일에서 기간 단위로 받는다. 받은 그대로 저장한다.
                     data/raw/{source}/{yyyy}/{run_id}_{code}.{csv|json}
② 정규화(transform)  원본을 파싱해 공통 모양으로: (series_id, obs_date, value)
                     - 출처 코드 → series_id: series 표의 (source_id, source_code)로 찾는다
                     - 단위: 퍼센트 → 소수, 날짜 형식 통일, 결측("." "", NaN) 제거
③ 검증(validate)     - 기본키 중복, 값 범위(금리 -5%~30%), 전일 대비 급변(예: 100bp 초과 경고)
                     - 영업일 달력 대비 누락, 같은 날 같은 시리즈 값이 출처 재발표로 바뀌었는지
④ 적재(load)         staging 표에 넣고 observation에 upsert. 실행 기록을 ingest_run에 남긴다.
⑤ 조회(serve)        뷰로 제공. 소비 프로젝트는 SQL로 읽는다.
```

- **원본을 남기는 이유**: 정규화 규칙에 실수가 있거나 키 규칙이 바뀌어도 다시 받지 않고 ②부터 재처리할 수 있다.
- **증분 수집**: 시리즈마다 마지막 날짜를 `SELECT max(obs_date)`로 구해 그다음 날부터 받는다. 처음 한 번은 전체 이력(backfill).
- **멱등성**: 같은 기간을 두 번 돌려도 결과가 같아야 한다. upsert와 기본키가 이를 보장한다.
- **실행**: 처음에는 수동 CLI(`python -m marketdata update --source fred`). 익숙해지면 매일 OS 스케줄러(cron, 작업 스케줄러)로.

---

## 4. 스키마

```sql
-- 출처
CREATE TABLE source (
    source_id   VARCHAR PRIMARY KEY,        -- 'FRED', 'ECOS', 'NYFED', 'TREASURY', 'SMBS'
    name        VARCHAR NOT NULL,
    url         VARCHAR,
    license     VARCHAR,                    -- 이용 조건 메모
    notes       VARCHAR
);

-- 시계열 정의 (엔티티)
CREATE TABLE series (
    series_id       VARCHAR PRIMARY KEY,    -- 표준 키, QuantTool 시세 키와 같음: 'BOND/YIELD/USD/UST/PAR/10Y'
    asset_class     VARCHAR NOT NULL,       -- 'RATES', 'EQUITY', 'FX'
    instrument_type VARCHAR NOT NULL,       -- 'BOND_YIELD', 'IR_SWAP', 'OIS', 'FIXING', 'EQUITY_PRICE' …
    currency        VARCHAR,
    name            VARCHAR,                -- 'UST', 'KTB', 'CD91', 'SOFR'
    tenor           VARCHAR,                -- '10Y', NULL(fixing)
    unit            VARCHAR NOT NULL,       -- 저장 단위: 'decimal', 'price', 'index'
    source_id       VARCHAR NOT NULL REFERENCES source(source_id),
    source_code     VARCHAR NOT NULL,       -- 출처 쪽 식별자: 'DGS10', '817Y002/010210000'
    source_unit     VARCHAR NOT NULL,       -- 출처 단위: 'percent' → 정규화 때 소수로
    calendar        VARCHAR,                -- 'UnitedStates.GovernmentBond'
    description     VARCHAR,
    active          BOOLEAN DEFAULT TRUE,
    UNIQUE (source_id, source_code)
);

-- 관측값 (팩트)
CREATE TABLE observation (
    series_id   VARCHAR NOT NULL REFERENCES series(series_id),
    obs_date    DATE    NOT NULL,
    value       DOUBLE  NOT NULL,           -- 항상 series.unit (금리는 소수)
    run_id      BIGINT  NOT NULL,           -- 어느 수집 실행에서 왔나
    loaded_at   TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, obs_date)
);

-- 수집 실행 기록 (운영)
CREATE SEQUENCE run_seq;
CREATE TABLE ingest_run (
    run_id      BIGINT PRIMARY KEY DEFAULT nextval('run_seq'),
    source_id   VARCHAR NOT NULL,
    started_at  TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    date_from   DATE, date_to DATE,
    rows_in     INTEGER, rows_upserted INTEGER,
    status      VARCHAR,                    -- 'ok', 'warn', 'fail'
    message     VARCHAR,
    raw_path    VARCHAR                     -- 원본 파일 위치
);

-- 검증 경고 (품질)
CREATE TABLE dq_issue (
    run_id      BIGINT, series_id VARCHAR, obs_date DATE,
    check_name  VARCHAR,                    -- 'jump', 'range', 'missing_business_day'
    detail      VARCHAR
);
```

뷰:
```sql
-- 키로 바로 조회 (QuantTool Loader가 쓰는 모양: date, key, value — ORE market.txt와 같다)
CREATE VIEW v_quote AS
SELECT o.obs_date AS date, o.series_id AS quote_key, o.value
FROM observation o JOIN series s USING (series_id)
WHERE s.active;

-- 넓은 표 (팩터 모델·노트북용): 행 = 날짜, 열 = 만기
CREATE VIEW v_ust_par_wide AS
PIVOT (SELECT obs_date, tenor, value FROM observation JOIN series USING (series_id)
       WHERE name = 'UST' AND instrument_type = 'BOND_YIELD')
ON tenor USING first(value) GROUP BY obs_date ORDER BY obs_date;
```

키 규칙(`series_id`): ORE 시세 키처럼 스스로를 설명하게 쓴다.

| 예 | 뜻 |
|---|---|
| `BOND/YIELD/USD/UST/PAR/10Y` | 미 국채 10년 par yield |
| `BOND/YIELD/KRW/KTB/MKT/3Y` | 국고채 3년 최종호가수익률 |
| `IR_SWAP/RATE/KRW/1D/3M/5Y` | 원화 IRS 5년 (CD91, 분기) |
| `OIS/RATE/USD/2D/1D/10Y` | USD SOFR OIS 10년 |
| `FIXING/SOFR`, `FIXING/CD91` | 지표금리 고시 |

---

## 5. SQL로 쓰는 예

```sql
-- 적재: staging에 넣고 upsert (재실행해도 같은 결과)
INSERT INTO observation (series_id, obs_date, value, run_id)
SELECT series_id, obs_date, value, 42 FROM stg_fred
ON CONFLICT (series_id, obs_date) DO UPDATE SET value = excluded.value, run_id = excluded.run_id,
                                              loaded_at = now();

-- 증분 수집 시작점
SELECT s.source_code, max(o.obs_date) AS last_date
FROM series s LEFT JOIN observation o USING (series_id)
WHERE s.source_id = 'FRED' GROUP BY s.source_code;

-- 하루치 커브 (QuantTool Loader.load(asof))
SELECT quote_key, value FROM v_quote WHERE date = DATE '2026-10-23' AND quote_key LIKE 'BOND/YIELD/USD/UST/%';

-- 시계열 (팩터 모델): 10년 - 2년 스프레드
SELECT a.obs_date, a.value - b.value AS s2s10
FROM observation a JOIN observation b ON a.obs_date = b.obs_date
WHERE a.series_id = 'BOND/YIELD/USD/UST/PAR/10Y' AND b.series_id = 'BOND/YIELD/USD/UST/PAR/2Y'
ORDER BY a.obs_date;

-- 품질: 최근 실행 결과와 경고
SELECT * FROM ingest_run ORDER BY run_id DESC LIMIT 5;
SELECT check_name, count(*) FROM dq_issue WHERE run_id = 42 GROUP BY check_name;
```

---

## 6. 프로젝트 구조 (market-data)

```
market-data/
├── pyproject.toml                 duckdb, pandas, httpx(or requests), pydantic
├── catalog/
│   ├── sources.yaml               source 표 내용
│   └── series/{fred,ecos,…}.yaml  series 표 내용 (series_id ↔ source_code, 단위)
├── src/marketdata/
│   ├── db.py                      연결, 스키마 생성(migrations/), upsert 헬퍼
│   ├── catalog.py                 YAML → source/series 표 동기화
│   ├── sources/                   출처별: fetch(기간) → 원본 저장, parse(원본) → DataFrame(series_id, obs_date, value)
│   │   ├── fred.py, ecos.py, nyfed.py, treasury.py, smbs.py
│   ├── validate.py                범위·급변·누락·중복 검사 → dq_issue
│   ├── pipeline.py                update(source, date_from=None): 증분 결정 → fetch → parse → validate → load → ingest_run
│   ├── client.py                  소비 프로젝트용: quotes(asof, prefix), series(keys, start, end), wide(name)
│   └── __main__.py                CLI: init / sync-catalog / update / backfill / status
├── migrations/001_init.sql        4장 스키마
├── tests/                         출처별 원본 샘플 fixture로 parse 검사, upsert 멱등성 검사
└── data/                          (gitignore) raw/, market.duckdb
```

- 출처 하나를 추가하는 일 = `catalog/series/x.yaml`에 시리즈를 적고, `sources/x.py`에 fetch·parse 두 함수를 쓰는 것.
- 비밀값(ECOS 인증키 등)은 환경 변수(`ECOS_API_KEY`)로만.

---

## 7. QuantTool이 쓰는 방법

```python
# quant-tool: data/marketdata/loader.py
class DuckDBLoader(Loader):
    """market.duckdb의 v_quote 뷰에서 asof 하루치를 읽는다 (ORE Loader 대응)."""
    def __init__(self, path: str):
        self.con = duckdb.connect(path, read_only=True)

    def load(self, asof: date) -> list[MarketDatum]:
        rows = self.con.execute(
            "SELECT quote_key, value FROM v_quote WHERE date = ?", [asof]).fetchall()
        return [MarketDatum(asof, key, value) for key, value in rows]
```

- QuantTool의 계산 결과(날짜별 격자값 `risk_factors`, NPV·민감도 `results`)는 **QuantTool 쪽 DB 파일**에 쓴다.
  관측값(사실)과 계산 결과(모델 산출)를 섞지 않기 위해서다. 필요하면 DuckDB에서 두 파일을 `ATTACH`해 함께 조회한다.
- 팩터 모델은 `client.series([...], start, end)`나 SQL로 시계열을 읽는다.

---

## 8. 출처 (조사 2026-10-27, 미연결)

| 대상 | 출처 | 이력 | 비고 |
|---|---|---|---|
| 미 국채 par yield | FRED `DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2, DGS3, DGS5, DGS7, DGS10, DGS20, DGS30` (`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10`), 재무부 원본 | 수십 년 (10Y 1962~, 1M 2001~). 30Y는 2002-02~2006-02 공백 | 공식 (H.15 = 재무부 CMT). 키 없이 받는지 확인 |
| SOFR 고시 | NY Fed `https://markets.newyorkfed.org/api/rates/secured/sofr/...`, FRED `SOFR` | 2018-04-02~ | 공식 |
| 국고채 | 한국은행 ECOS 시장금리(일별) `817Y002` — `https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/1/{N}/817Y002/D/{시작}/{끝}/{항목}` | 수십 년 (만기별 시작일 확인) | 공식 (원천: 금투협 최종호가수익률). 무료 인증키. 국고채 10년 = `010210000` |
| CD91 | ECOS `817Y002` (항목코드 확인) | 수십 년 (확인) | 공식 |
| USD SOFR OIS | **무료 공식 커브 없음** (FRED ICE 스왑은 2016년 중단) | — | 아래 결정 |
| KRW IRS (CD91) | 서울외국환중개 `http://smbs.biz/Exchange/IRS.jsp`, 한국자금중개 `https://www.kmbco.com/kor/rate/deri_rate.do` | SMBS는 한 번에 최대 36개월 | 중개사 공시, HTML |
| 그 밖의 무료 | 금투협 채권정보센터, KRX 정보데이터시스템, yfinance(현재 옵션 체인), 증권사 API(KIS) | | 옵션 체인은 이력이 없으니 일찍 적재 시작 |

결정할 것:
- **USD SOFR OIS**: ① DTCC SDR 공개 체결(`https://pddata.dtcc.com/ppd/cftcdashboard`, CFTC 의무 공시, 1차 출처). 만기별 당일 시작 거래의
  중앙값을 par 금리로 쓴다. 공개 파일은 약 1년치만 보관하므로 몇 년치는 지금부터 매일 쌓아야 한다. ② checkmyswap 무료 API(제3자, 미검증).
  ③ SOFR + 국채 스프레드 근사(실제 시세 아님). ④ Bloomberg·Refinitiv를 쓸 수 있으면 몇 년치를 한 번에 받는 유일한 경로.
  SOFR 스왑 시장이 2021~2022년에 본격화돼 이력은 길어야 4~5년이다.
- **KRW IRS**: 중개사 두 곳을 서로 대조하며 수집, 또는 단말기 CSV 공급.
- 사실상 불가: swaption·cap/floor vol.

### 금리 종류

| | 무엇 | 변동 레그 | 예 |
|---|---|---|---|
| 국채 금리 | 정부 채권 수익률 | — | UST 10Y, 국고채 3Y |
| IRS | 고정 ↔ 기간물 지표금리 | 3M CD, (과거) 3M LIBOR, Term SOFR | KRW IRS = 고정 vs CD91, 분기 지급 |
| OIS | 고정 ↔ 익일물 금리의 기간 복리 | SOFR, KOFR, €STR | USD SOFR 스왑 |

- OIS는 변동 레그가 익일물 복리인 IRS다. 미국은 LIBOR 종료(2023-06) 후 표준 스왑이 SOFR OIS라 "SOFR 스왑/IRS/OIS"는 보통 같은 상품이다.
- 한국 표준 IRS는 여전히 CD91 기준이고, KOFR OIS는 도입 단계라 유동성이 작다.

---

## 9. 시작 순서

1. 레포 생성, `migrations/001_init.sql`, `db.py`(init), `catalog`(UST par 11개 시리즈 + SOFR).
2. `sources/fred.py` + `pipeline.update` + `validate`(범위·중복) → 몇 년치 backfill → `v_quote`, `v_ust_par_wide`로 확인.
3. QuantTool에 `DuckDBLoader` 추가, `notebooks/01_ust_curve`를 실제 데이터로 실행.
4. `sources/ecos.py`(국고채·CD91), 스왑 출처 결정 후 수집기.
5. 매일 자동 실행.
