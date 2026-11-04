# 튜토리얼: 파일 하나 = 노트북 하나 (의존성 순서)

앞 노트북의 파일만 알면 다음 노트북을 볼 수 있다. 각 노트북은 그 파일의 공개 객체마다
"무엇 · 입력 구조 · 출력 구조 · 짧은 예"를 실행해 보여 주고, 끝에 요약 표와 `내 메모` 칸이 있다.

```
config → quotes → curves → market → portfolio → scenarios → risk
```

| 노트북 | 파일 | 배우는 것 |
|---|---|---|
| `01_config` | `src/quanttool/config.py`, `configs/*.yaml` | 매핑 사전, 관례(앵커), 지수·커브 레시피, 엔진·템플릿, 리스크 규칙, 교차 검사와 `build_order` |
| `02_quotes` | `src/quanttool/market/quotes.py` | 시세 파일 형식 → `{날짜: {키: 값}}`, 오류 |
| `03_curves` | `src/quanttool/market/curves.py` | `Context`, 헬퍼 5종(`HELPERS`)과 부트스트랩, `build_curve` → (커브, 시세 Quote), 얼림 vs linked, 듀얼 커브, `CurveFactors`(요인 층·보간·roll) |
| `04_market` | `src/quanttool/market/market.py` | `MarketObject` 규격, `build_market` 한 줄씩, `Market` 속성·조회·`quotes`(linked 시세 갱신), 시나리오 적용·해제, `active`, `roll`(fixing 채움) |
| `05_portfolio` | `src/quanttool/portfolio.py` | 거래 명세, 템플릿(`trade`), `BUILDERS`·`ENGINES`, `build`·`npvs`, 직접 계산 비교, par 스왑 |
| `06_scenarios` | `src/quanttool/analysis/scenarios.py` | `parallel`, `from_loadings`, `combine`, 삼각 가중치와 `bucket` |
| `07_risk` | `src/quanttool/analysis/risk.py` | 흐름, `scenario_pnl`, `key_rate`(규칙·성긴 만기·할인/예측 분리), `factor_delta`, `cross_gamma`, `theta` |

- 데이터는 `tests/fixtures/`의 **합성 샘플**(시세 `market_sample.txt`, 예시 북 `ust_book.yaml`·`krw_swaps.yaml`)이다.
- 실행 준비: `pip install -e ".[dev,notebook]"`
- 실제 데이터로 시장을 읽는 노트북은 `notebooks/01_ust_curve.ipynb`.
