# 튜토리얼

순서대로 실행한다. 각 노트북 첫 셀에 그 단계의 코드 위치가 있다.

| 노트북 | 배우는 것 |
|---|---|
| `00_quantlib_basics` | SimpleQuote, Handle, Observer, RelinkableHandle, 전역 평가일 — QuantLib만으로 |
| `01_quotes_curve_market` | 시세 → 헬퍼 → 부트스트랩(직접, 그리고 `build_market`), 진단·커브 표, 시장 요인, 얼린 커브 vs 시세 연결 |
| `02_portfolio` | 포지션 YAML → QuantLib 채권 → NPV, 직접 계산과 비교, 다른 날짜 시장에 다시 붙이기 |
| `03_scenarios_risk` | 손으로 만든 시나리오·요인 로딩, key rate delta·gamma, 상품별 민감도 규칙, cross gamma |
| `04_time_history` | theta(ForwardForward), 날짜별 커브 이력, 평가일이 바꾸는 것 |

- 데이터는 `tests/fixtures/market_sample.txt` **합성 샘플**이다. 흐름 이해용이고 숫자로 시장을 해석하지 않는다.
- 실행 준비: `pip install -e ".[dev,notebook]"`
- 실제 데이터로 시장을 읽는 노트북은 `notebooks/01_ust_curve.ipynb`.
