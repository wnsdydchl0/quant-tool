"""시장 객체 구축 순서. ORE 대응: OREData/ored/marketdata/dependencygraph.hpp.

관계는 레시피의 참조(MarketBuilder.requires)에서 뽑아 넣는다. 여기서는 순서와 순환만 다룬다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

Node = tuple[str, str]  # (kind, name), 예: ("YieldCurve", "UST")


class CycleError(ValueError):
    pass


class DependencyGraph:
    def __init__(self, edges: Mapping[Node, Iterable[Node]]) -> None:
        self._deps: dict[Node, tuple[Node, ...]] = {n: tuple(d) for n, d in edges.items()}
        for node, deps in self._deps.items():
            for dep in deps:
                if dep not in self._deps:
                    raise KeyError(f"{node}가 정의되지 않은 {dep}를 참조한다")

    def order(self, targets: Iterable[Node]) -> list[Node]:
        """targets와 그 의존 대상을 의존 먼저 순서로 돌려준다."""
        done: dict[Node, None] = {}
        path: list[Node] = []

        def visit(node: Node) -> None:
            if node in done:
                return
            if node in path:
                cycle = path[path.index(node) :] + [node]
                raise CycleError(" → ".join(f"{k}:{n}" for k, n in cycle))
            if node not in self._deps:
                raise KeyError(f"정의되지 않은 시장 객체 {node}")
            path.append(node)
            for dep in self._deps[node]:
                visit(dep)
            path.pop()
            done[node] = None

        for t in targets:
            visit(t)
        return list(done)
