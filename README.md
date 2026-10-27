# QuantTool

QuantLib을 엔진으로 쓰고 ORE(Open Source Risk Engine)의 시스템 설계를 참조한 파이썬 가격결정·리스크 분석 툴.

- 설계: [docs/architecture.md](docs/architecture.md)
- 레퍼런스 요약: [docs/references/](docs/references/)

```bash
pip install -e .[dev]
python -m pytest -q && ruff check .
scripts/fetch_references.sh   # QuantLib-SWIG, ORE 원본 클론 (선택)
```

## 첫 줄기: UST 커브 → 국채 → key rate DV01

```python
from datetime import date
from quanttool.config import load_config
from quanttool.market import Snapshot, UstParCsvLoader
from quanttool.derivatives import Portfolio
from quanttool.scenario import ScenarioGrid, ScenarioMarket, ScenarioRunner, SensitivityGenerator
from quanttool.analytics.market_monitor import curve_table
from quanttool.analytics.sensitivity import key_rate_dv01

cfg = load_config("configs")
snap = Snapshot.build(date(2026, 10, 23), cfg, UstParCsvLoader("data/ust_par/2026.csv"))
curve_table(snap, "UST", cfg)

book = Portfolio.load("positions/ust_book.yaml")
grid = ScenarioGrid(cfg.grid)
res = ScenarioRunner(book, ScenarioMarket(snap, grid), cfg).run(
    SensitivityGenerator(grid, cfg.sensitivity).generate()
)
key_rate_dv01(res, cfg.sensitivity, "UST")
```

- 데이터 수집: `python pipeline/ust_par.py 2026` → `data/ust_par/2026.csv`
- 노트북: `pip install -e .[notebook]` 후 `notebooks/01_ust_curve.ipynb`
