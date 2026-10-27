# 시장 데이터 출처

조사일 2026-10-27. 아직 연결하지 않았다. 당시 클라우드 개발 환경은 아래 출처 전부에 네트워크가 막혀 있어서,
네트워크가 열린 로컬 환경에서 이어 하기로 했다. 엔드포인트·항목코드·이력 시작일은 실제 호출로 다시 확인할 것.

## 금리 종류 정리: 국채, IRS, OIS

| | 무엇 | 변동 레그 지표 | 예 |
|---|---|---|---|
| 국채 금리 | 정부 채권 수익률 | — | UST 10Y, 국고채 3Y |
| IRS | 고정금리 ↔ **기간물 지표금리** 교환 | 3M CD, (과거) 3M LIBOR, Term SOFR | KRW IRS = 고정 vs CD91, 분기 지급 |
| OIS | 고정금리 ↔ **익일물 금리의 기간 복리** 교환 | SOFR, KOFR, €STR | USD SOFR 스왑 |

- IRS는 상위 개념(금리 교환 전체)이고, OIS는 변동 레그가 익일물 복리인 IRS다.
- **미국은 LIBOR 종료(2023-06) 후 표준 스왑이 SOFR OIS다.** 시장에서 "SOFR 스왑", "SOFR IRS", "SOFR OIS"는 보통 같은 상품
  (고정 vs SOFR 일별 복리, 연 지급, Act/360)을 가리킨다. Term SOFR(CME 기간물) 기준 스왑도 있지만 대출 헷지용으로 작다.
- **한국은 표준 IRS가 여전히 CD91 기준**이다. KOFR(익일물 RP 금리) 기준 OIS는 도입 단계라 유동성이 작다.
- 커브 구축 차이: USD는 SOFR OIS 하나로 예측과 할인을 같이 한다. KRW는 CD91 IRS로 예측 커브를 만들고,
  할인 커브는 담보 조건(청산소 규칙 포함)에 따라 달라지므로 확인이 필요하다.

## 출처 표

| 대상 | 출처 | 이력 | 신뢰도·비고 |
|---|---|---|---|
| 미 국채 par yield | FRED `DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2, DGS3, DGS5, DGS7, DGS10, DGS20, DGS30` — `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` | 수십 년 (DGS10은 1962년~, DGS1MO는 2001년~). DGS30은 2002-02~2006-02 공백 | 공식 (H.15, 재무부 CMT와 같은 값). 키 없이 받는지 확인. 재무부 원본은 `pipeline/ust_par.py` |
| SOFR 고시 | NY Fed `https://markets.newyorkfed.org/api/rates/secured/sofr/...` 또는 FRED `SOFR` | 2018-04-02~ | 공식 |
| 한국 국고채 | 한국은행 ECOS 시장금리(일별) `817Y002` — `https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/1/{N}/817Y002/D/{YYYYMMDD}/{YYYYMMDD}/{item}` | 수십 년 (만기별로 발행 시작 이후, 시작일 확인 필요) | 공식 (원천: 금투협 최종호가수익률). 무료 인증키 필요 → 환경 변수 `ECOS_API_KEY`. 국고채 10년 = `010210000`, 나머지 항목코드는 ECOS 통계표에서 확인 |
| CD91 | ECOS `817Y002` (항목코드 확인 필요) | 수십 년 (확인 필요) | 공식. KRW IRS 변동 레그 지표 |
| USD SOFR OIS | **무료 공식 커브 없음** (FRED의 ICE 스왑 시리즈는 2016년 중단) | 아래 결정 1 | SOFR 스왑 시장 자체가 2021~2022년부터 본격화, 그 전은 LIBOR 스왑 |
| KRW IRS (CD91) | 서울외국환중개 `http://smbs.biz/Exchange/IRS.jsp`, 한국자금중개 `https://www.kmbco.com/kor/rate/deri_rate.do` | SMBS는 한 번에 최대 36개월 조회. 최대 과거 범위는 확인 필요 | 아래 결정 2 |

## 결정할 것

1. **USD SOFR OIS 출처**
   - DTCC SDR 공개 체결 (`https://pddata.dtcc.com/ppd/cftcdashboard`, 자산군별 CSV zip): CFTC 의무 공시라 1차 출처.
     만기별로 당일 시작 SOFR OIS 거래의 중앙값을 par 금리로 쓴다. 정제 로직이 필요하고 거래가 적은 만기는 빈다.
     **공개 대시보드 누적 파일은 약 1년(366일)만 보관**(사용자 안내서 기준)이라, 몇 년치 이력은 지금부터 매일 쌓아야 한다.
     그 이전은 DTCC 지원팀 요청이 필요하다.
   - checkmyswap 무료 API (`https://www.checkmyswap.com/rates`): 간단하지만 제3자 가공, 방법론과 이력 기간 미검증.
   - SOFR 고시 + 국채 커브 스프레드 근사: 실제 스왑 시세가 아니다.
   - 학교·회사 단말기(Bloomberg, Refinitiv)를 쓸 수 있으면 몇 년치 이력을 한 번에 받을 수 있는 유일한 경로.
2. **KRW IRS 출처**
   - 서울외국환중개·한국자금중개 조회 페이지: 중개사 공시라 신뢰도가 높다. 두 곳을 서로 대조할 수 있다.
     HTML이라 형식이 바뀌면 깨질 수 있고, 36개월씩 나눠 받아야 한다.
   - 단말기(Infomax·Bloomberg 등) CSV를 정해진 형식으로 공급.

## 연결 순서

1. 위 결정 확정, ECOS 인증키 발급.
2. `pipeline/`: `fred.py`(UST·SOFR), `ecos.py`(KTB·CD91), 스왑 수집기 → `data/` 아래 정규화 CSV(`date,quote_id,value`).
   DTCC를 쓰면 이력이 1년뿐이므로 수집기를 먼저 만들어 매일 적재부터 시작한다.
3. `market/quotes.py`: 정규화 CSV를 읽는 범용 `StoreLoader` + 출처별 원본 형식 fixture 테스트.
4. 커브 설정 `configs/market/curves/{krw_ktb,usd_sofr,krw_irs}.yaml`, 관례 `configs/conventions/rates.yaml`에 추가
   - KTB: SouthKorea.Settlement, ActualActual.ISMA, Semiannual, T+1
   - KRW IRS: 분기 고정 레그, Act/365, CD91 변동
   - USD SOFR OIS: Annual, Act/360, T+2
5. `market/rates.py`: 스왑 구간 세그먼트(`SwapRateHelper`/`OISRateHelper`), `IndexBuilder`(CD91·SOFR, fixing은 구축 시 1회 로드).
6. 실제 데이터로 `notebooks/01_ust_curve.ipynb` 재실행, 국채–스왑 스프레드 노트북 추가.

## 참고
- FRED SOFR: https://fred.stlouisfed.org/series/SOFR
- FRED DGS30 (공백 기간): https://eco3min.fr/en/us-30-year-treasury-yield-dataset/
- ECOS API 사용 예: https://wikidocs.net/144528
- ECOS 817Y002/010210000 사용 예: https://github.com/chjogit/kic-agent-data/pull/10
- DTCC PPD 안내: https://dtcclearning.com/helpfiles_secure/rds/noa_lp/Content/Topics/service_helps/noa/coveo_exclude/ppd_dashboard.htm
- DTCC PPD 사용자 안내서 (보관 기간): https://kgc0418-tdw-data-0.s3.amazonaws.com/gtr/static/gtr/docs/RT_PPD_quick_ref_guide.pdf
- 서울외국환중개 IRS: http://smbs.biz/Exchange/IRS.jsp
- 한국자금중개 파생금리: https://www.kmbco.com/kor/rate/deri_rate.do
- KRW IRS 지표(제3자 전재): https://cbonds.pl/indexes/219683/
