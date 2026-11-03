# 튜토리얼

순서대로 실행한다. 각 노트북 첫 셀에 그 단계의 코드 위치가 있다.

| 노트북 | 배우는 것 |
|---|---|
| `01_quotes_curve_market` | 시세 → 헬퍼 → 부트스트랩(직접, 그리고 `build_market`), 진단·커브 표, 요인 층(부트스트랩 커브 + 격자 이동, 보간), 얼린 커브 vs 시세 연결 |
| `02_portfolio` | 거래 = 상품 템플릿 + 거래 값(파일·코드 `trade`), QuantLib 채권 → NPV, 직접 계산과 비교, 다른 날짜 시장에 다시 붙이기 |
| `03_scenarios_risk` | 시나리오 생성 → 시장 적용 → 재평가 → risk 흐름, 손으로 만든 시나리오·요인 로딩, key rate delta·gamma, 상품별 민감도 규칙, cross gamma |
| `04_time_history` | 얼린 커브와 roll(ForwardForward, theta ≈ carry), 날짜별 커브 이력, 전역 평가일과 `active()`, 평가일만 옮긴 경우 vs roll |
| `05_dual_curve` | KOFR 할인 + CD91 예측 듀얼 커브, 조립 순서, 지수(파생 객체), IRS, 할인·예측 key rate |

- 데이터는 `tests/fixtures/market_sample.txt` **합성 샘플**이다. 흐름 이해용이고 숫자로 시장을 해석하지 않는다.
- 실행 준비: `pip install -e ".[dev,notebook]"`
- 실제 데이터로 시장을 읽는 노트북은 `notebooks/01_ust_curve.ipynb`.
