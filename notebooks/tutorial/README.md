# 튜토리얼: 흐름을 따라가며 이해하기

순서대로 실행한다. 각 노트북 첫 셀에 "이 단계의 QuantTool 코드 위치 / QuantLib·ORE 원본 위치" 표가 있으니,
셀을 실행하면서 해당 파일을 같이 열어 본다. ORE 경로는 `references/Engine/` 기준(`scripts/fetch_references.sh`로 클론).

| 노트북 | 배우는 것 | 주로 보는 코드 |
|---|---|---|
| `00_quantlib_basics` | SimpleQuote, Handle, Observer, RelinkableHandle, 전역 평가일 — QuantLib만으로 | `docs/references/quantlib.md` |
| `01_quotes_to_curve` | 재무부 par yield → 헬퍼 → 부트스트랩을 손으로, 그다음 `Snapshot.build`와 비교 | `src/quanttool/market/rates.py` |
| `02_snapshot_step_by_step` | 레시피 → Loader → QuoteStore → 빌더 → 의존 그래프 → 보관소, 한 줄씩 | `src/quanttool/market/market.py`, `config/`, `core/` |
| `03_trade_to_npv` | 계약서(YAML) → EngineFactory → 엔진 → NPV, QuantLib 직접 계산과 비교 | `src/quanttool/derivatives/` |
| `04_scenarios` | 격자, 시나리오 시장, 손으로 만든 시나리오, key rate DV01 | `src/quanttool/scenario/` |

- 데이터는 `tests/fixtures/ust_par_sample.csv` **합성 샘플**(재무부 CSV와 형식만 같음)이다. 흐름 이해용이고 숫자로 시장을 해석하지 않는다.
- 실행 준비: `pip install -e ".[dev,notebook]"`
- 실제 데이터로 시장을 읽는 분석 노트북은 `notebooks/01_ust_curve.ipynb`.
