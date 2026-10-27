# 작업 현황 (인계)

최종 갱신 2026-10-27. 브랜치 `claude/confident-hamilton-ui198k`, PR https://github.com/wnsdydchl0/quant-tool/pull/1

## 로컬에서 시작하기

```bash
git clone https://github.com/wnsdydchl0/quant-tool.git && cd quant-tool
git checkout claude/confident-hamilton-ui198k
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,notebook]"
scripts/fetch_references.sh                              # QuantLib-SWIG, ORE 원본 (선택, gitignore)
python -m pytest -q && ruff check . && ruff format --check .
python pipeline/ust_par.py 2026                          # 재무부 par yield → data/ust_par/2026.csv
```

- `pytest`는 `python -m pytest`로 돌린다. PATH의 `pytest`가 다른 환경(QuantLib 없음)을 가리킬 수 있다.
- 처음이면 `notebooks/tutorial/`(00~04)을 순서대로 실행하며 코드 위치를 따라간다.
- 노트북 `notebooks/01_ust_curve.ipynb`는 `data/ust_par/*.csv`가 있으면 실제 데이터를, 없으면 합성 샘플을 쓰고 경고를 띄운다.

## 완료

- Phase 0: 문서 분할(`docs/architecture.md`, `docs/references/`), CLAUDE.md, 패키지 골격, 의존 방향 테스트.
- Phase 1 첫 줄기 (UST 커브 → 국채 → key rate DV01): core, config, market, derivatives, scenario, analytics, 노트북.
- 튜토리얼 노트북 5개 (`notebooks/tutorial/`): QuantLib 기초 → 시세→커브 → Snapshot 내부 → 계약서→NPV → 시나리오.
- 테스트 81개 통과. 완료 기준 (합성 샘플 `tests/fixtures/ust_par_sample.csv` 기준, 실제 시장 값 아님):

| 기준 | 결과 |
|---|---|
| 헬퍼 재가격 오차 < 0.01bp | 약 1e-9bp |
| QuantLib 직접 조립 채권과 NPV 일치 | 상대오차 1e-12 이내 |
| Σ key rate DV01 = 평행 DV01 | −8,245.95 대 −8,246.30 (차이 5e-4 이내, 한쪽 차분의 2차 항) |
| 격자 시장 기준 NPV ≈ 스냅샷 NPV | 최대 상대오차 5.1e-4 (30Y) |
| 평행 DV01 vs QuantLib 직접 1bp 이동 | 1e-3 이내 |

## 정한 관례와 알아둘 것

- **UST par 헬퍼**: 쿠폰채 구간은 명목 만기(조정 없음) 정규 일정 + Unadjusted 지급(수익률 관례)으로 par 가격이 정확히 100.
  bill(≤1Y)은 BEY(Act/365, 반년 초과 시 반기복리 1회) → 할인채 가격. 쿠폰은 구축 시점 고정, 수익률 변화는 `DerivedQuote`로 가격에 전달.
- **격자**: `configs/scenario/grid.yaml` 20개 점, 제로금리 선형·바깥 평탄. 대사 오차는 격자점 사이 보간 차이에서 나며,
  합성 샘플의 1Y→2Y 곡률 때문에 2Y 근처가 크다. 실제 데이터로 허용 수준을 다시 볼 것.
- **QuantLib 1.44 동작**: `PiecewiseZeroSpreadedTermStructure`는 Quote가 바뀌면 `enableExtrapolation` 설정이 풀린다.
  `scenario/scenario_market.py`에서 마지막 격자 Quote에 묶인 100Y 끝점을 두어 평탄 외삽한다(100Y 넘는 날짜는 조회 불가).
- 결정 기록은 `docs/architecture.md` 9장 표.

## 다음 단계 (우선순위)

1. **실제 데이터 연결** — 출처와 순서는 `docs/data_sources.md`. USD 스왑·KRW IRS 출처 결정이 먼저.
2. `scenario/par.py`: 격자 민감도 → 국채 par 민감도(헷지 수량).
3. `market/persist.py` + 일별 스냅샷 적재 (옵션 체인은 이력이 없으니 일찍 시작).
4. KRW_KTB 커브 + IRSwap, PCA 시나리오 → 주식 줄기 → P&L explain → 오토콜·LV (`docs/architecture.md` 10.2).
