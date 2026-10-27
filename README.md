# QuantTool

QuantLib을 엔진으로 쓰고 ORE(Open Source Risk Engine)의 시스템 설계를 참조한 파이썬 가격결정·리스크 분석 툴.

- 설계: [docs/architecture.md](docs/architecture.md)
- 레퍼런스 요약: [docs/references/](docs/references/)

```bash
pip install -e .[dev]
python -m pytest -q && ruff check .
scripts/fetch_references.sh   # QuantLib-SWIG, ORE 원본 클론 (선택)
```
