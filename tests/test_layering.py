"""의존 방향 검사: config·core → market → derivatives → scenario → analytics.

아래 층은 위 층을 import하지 않는다 (docs/architecture.md 1.5 원칙 8).
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "quanttool"

LAYER = {
    "config": 0,
    "core": 0,
    "qlext": 0,
    "market": 1,
    "derivatives": 2,
    "scenario": 3,
    "analytics": 4,
}


def _imported_packages(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # 상대 import: from ..market import x → 패키지 기준으로 해석
                rel = path.relative_to(SRC).parts[:-1]
                base = rel[: len(rel) - (node.level - 1)] if node.level > 1 else rel
                mod = ".".join(("quanttool", *base, *(node.module or "").split(".")))
                names = [mod.rstrip(".")]
            else:
                names = [node.module or ""]
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[0] == "quanttool" and len(parts) > 1:
                found.add(parts[1])
    return found


def _modules():
    return [p for p in SRC.rglob("*.py") if p.relative_to(SRC).parts[0] in LAYER]


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_upward_import(path: Path):
    own = path.relative_to(SRC).parts[0]
    for pkg in _imported_packages(path):
        if pkg in LAYER:
            assert LAYER[pkg] <= LAYER[own], f"{own} → {pkg} 역방향 import"


def test_known_packages_only():
    pkgs = {p.name for p in SRC.iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert pkgs <= set(LAYER), f"LAYER에 없는 패키지: {pkgs - set(LAYER)}"
