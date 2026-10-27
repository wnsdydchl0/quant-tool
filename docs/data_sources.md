# 시장 데이터 출처

조사일 2026-10-27. 아직 연결하지 않았다. 당시 클라우드 개발 환경은 아래 출처 전부에 네트워크가 막혀 있어서,
네트워크가 열린 로컬 환경에서 이어 하기로 했다. 엔드포인트·항목코드는 실제 호출로 다시 확인할 것.

## 출처 표

| 대상 | 출처 | 신뢰도·비고 |
|---|---|---|
| 미 국채 par yield | FRED `DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2, DGS3, DGS5, DGS7, DGS10, DGS20, DGS30` — `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` | 공식 (H.15, 재무부 CMT와 같은 값). 키 없이 받는지 확인. 재무부 원본은 `pipeline/ust_par.py`(home.treasury.gov) |
| SOFR 고시 | NY Fed `https://markets.newyorkfed.org/api/rates/secured/sofr/...` 또는 FRED `SOFR` | 공식 |
| 한국 국고채 | 한국은행 ECOS 시장금리(일별) `817Y002` — `https://ecos.bok.or.kr/api/StatisticSearch/{KEY}/json/kr/1/{N}/817Y002/D/{YYYYMMDD}/{YYYYMMDD}/{item}` | 공식 (원천: 금투협 최종호가수익률). 무료 인증키 필요 → 환경 변수 `ECOS_API_KEY`. 국고채 10년 = `010210000`, 나머지 항목코드는 ECOS 통계표에서 확인 |
| CD91 | ECOS `817Y002` (항목코드 확인 필요) | 공식. KRW IRS 변동 레그 지표 |
| USD SOFR 스왑 | **무료 공식 커브 없음** (FRED의 ICE 스왑 시리즈는 2016년 중단) | 아래 결정 1 |
| KRW IRS (CD91) | 서울외국환중개 `http://smbs.biz/Exchange/IRS.jsp` | 아래 결정 2 |

## 결정할 것

1. **USD SOFR 스왑 출처**
   - DTCC SDR 공개 체결 (`https://pddata.dtcc.com/ppd/cftcdashboard`, 자산군별 CSV zip): CFTC 의무 공시라
     1차 출처. 만기별로 당일 시작 SOFR OIS 거래의 중앙값을 par 금리로 쓴다. 정제 로직이 필요하고 거래가 적은 만기는 빈다.
   - checkmyswap 무료 API (`https://www.checkmyswap.com/rates`): 간단하지만 제3자 가공, 방법론 미검증.
   - SOFR 고시 + 국채 커브 스프레드 근사: 인수인계서 원안에 가깝지만 실제 스왑 시세가 아니다.
2. **KRW IRS 출처**
   - 서울외국환중개 IRS 조회 페이지: 중개사 공시라 신뢰도는 높지만 HTML이라 형식이 바뀌면 깨질 수 있다.
   - 단말기(Infomax·Bloomberg 등) CSV를 정해진 형식으로 공급.

## 연결 순서

1. 위 결정 확정, ECOS 인증키 발급.
2. `pipeline/`: `fred.py`(UST·SOFR), `ecos.py`(KTB·CD91), 스왑 수집기 → `data/` 아래 정규화 CSV(`date,quote_id,value`).
3. `market/quotes.py`: 정규화 CSV를 읽는 범용 `StoreLoader` + 출처별 원본 형식 fixture 테스트.
4. 커브 설정 `configs/market/curves/{krw_ktb,usd_sofr,krw_irs}.yaml`, 관례 `configs/conventions/rates.yaml`에 추가
   - KTB: SouthKorea.Settlement, ActualActual.ISMA, Semiannual, T+1
   - KRW IRS: 분기 고정 레그, Act/365, CD91 변동
   - USD SOFR OIS: Annual, Act/360, T+2
5. `market/rates.py`: 스왑 구간 세그먼트(`SwapRateHelper`/`OISRateHelper`), `IndexBuilder`(CD91·SOFR, fixing은 구축 시 1회 로드).
6. 실제 데이터로 `notebooks/01_ust_curve.ipynb` 재실행, 국채–스왑 스프레드 노트북 추가.

## 참고
- FRED SOFR: https://fred.stlouisfed.org/series/SOFR
- ECOS API 사용 예: https://wikidocs.net/144528
- ECOS 817Y002/010210000 사용 예: https://github.com/chjogit/kic-agent-data/pull/10
- DTCC PPD 안내: https://dtcclearning.com/helpfiles_secure/rds/noa_lp/Content/Topics/service_helps/noa/coveo_exclude/ppd_dashboard.htm
- KRW IRS 지표(제3자 전재): https://cbonds.pl/indexes/219683/
