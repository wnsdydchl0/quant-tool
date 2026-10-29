"""의존 방향 검사 (docs/architecture.md 1.5 원칙 8).

qle·data.utilities·data.configuration → data.marketdata → data.portfolio
→ analytics.scenario → analytics.engine → analytics.app.
아래 층은 위 층을 import하지 않는다.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "quanttool"

LAYER = {
    "qle": 0,
    "data.utilities": 0,
    "data.configuration": 0,
    "data.marketdata": 1,
    "data.portfolio": 2,
    "data.model": 2,
    "analytics.scenario": 3,
    "analytics.engine": 4,
    "analytics.app": 5,
}


def _area(parts: tuple[str, ...]) -> str:
    """패키지 경로 → 층 이름. data·analytics는 두 단계, 나머지는 한 단계."""
    if parts and parts[0] in ("data", "analytics") and len(parts) > 1:
        return f"{parts[0]}.{parts[1]}"
    return parts[0] if parts else ""


def _imported_areas(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg = path.relative_to(SRC).parts[:-1]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".") for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # 상대 import: from ..x import y → 이 파일의 패키지 기준으로 해석
                base = pkg[: len(pkg) - (node.level - 1)]
                names = [["quanttool", *base, *(node.module.split(".") if node.module else [])]]
            else:
                names = [(node.module or "").split(".")]
        else:
            continue
        for parts in names:
            if parts[0] == "quanttool" and len(parts) > 1:
                found.add(_area(tuple(parts[1:])))
    return found


def _modules():
    return [p for p in SRC.rglob("*.py") if _area(p.relative_to(SRC).parts[:-1]) in LAYER]


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_upward_import(path: Path):
    own = _area(path.relative_to(SRC).parts[:-1])
    for area in _imported_areas(path):
        if area in LAYER:
            assert LAYER[area] <= LAYER[own], f"{own} → {area} 역방향 import"


def test_known_packages_only():
    areas = {
        _area(p.relative_to(SRC).parts)
        for p in SRC.glob("*/*")
        if p.is_dir() and not p.name.startswith("__")
    } | {p.name for p in SRC.iterdir() if p.is_dir() and p.name not in ("data", "analytics")}
    areas.discard("__pycache__")
    assert areas <= set(LAYER), f"LAYER에 없는 패키지: {areas - set(LAYER)}"
