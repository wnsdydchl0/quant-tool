# 튜토리얼: 흐름을 따라가며 이해하기

순서대로 실행한다. 각 노트북 첫 셀에 "이 단계의 QuantTool 코드 위치 / QuantLib·ORE 원본 위치" 표가 있으니,
셀을 실행하면서 해당 파일을 같이 열어 본다. ORE 경로는 `references/Engine/` 기준(`scripts/fetch_references.sh`로 클론).

| 노트북 | 배우는 것 | 주로 보는 코드 |
|---|---|---|
| `00_quantlib_basics` | SimpleQuote, Handle, Observer, RelinkableHandle, 전역 평가일 — QuantLib만으로 | `docs/architecture.md` 0.1 |
| `01_quotes_to_curve` | 재무부 par yield → 헬퍼 → 부트스트랩을 손으로, 그다음 `TodaysMarket`과 비교. 얼린 시장 vs 시세 연결 유지 | `src/quanttool/data/marketdata/yieldcurve.py`, `src/quanttool/qle/` |
| `02_todaysmarket_step_by_step` | 레시피 → Loader → QuoteStore → 빌더 → 의존 그래프 → `MarketImpl` 보관소, 한 줄씩 | `src/quanttool/data/marketdata/`, `data/configuration/`, `data/utilities/` |
| `03_trade_to_npv` | 계약서(YAML) → `EngineFactory.builder` → 엔진 → NPV, QuantLib 직접 계산과 비교 | `src/quanttool/data/portfolio/` |
| `04_simmarket_sensitivity` | 격자, `ScenarioSimMarket`(spreaded/절대), 손으로 만든 시나리오, `ValuationEngine`, `SensitivityAnalysis` | `src/quanttool/analytics/scenario/`, `analytics/engine/` |
| `05_time_and_history` | `SimMarket.update`로 theta, 날짜별 `TodaysMarket` → 커브 이력 표, 평가일이 바꾸는 것 | `src/quanttool/analytics/scenario/simmarket.py` |

- 데이터는 `tests/fixtures/ust_par_sample.csv` **합성 샘플**(재무부 CSV와 형식만 같음)이다. 흐름 이해용이고 숫자로 시장을 해석하지 않는다.
- 실행 준비: `pip install -e ".[dev,notebook]"`
- 실제 데이터로 시장을 읽는 분석 노트북은 `notebooks/01_ust_curve.ipynb`.
