from __future__ import annotations

from dataclasses import dataclass

from cdfd.models import CDFDGraph, PathResult


class PathLimitExceeded(RuntimeError):
    """Raised when path generation exceeds the configured safety limit."""


@dataclass(frozen=True)
class PathFindingOptions:
    strategy: str = "simple"
    max_depth: int = 20
    max_paths: int = 10000


def find_paths(
    graph: CDFDGraph,
    options: PathFindingOptions | None = None,
) -> list[PathResult]:
    options = options or PathFindingOptions()
    strategy = _normalize_strategy(options.strategy)

    if options.max_depth < 1:
        raise ValueError("max_depth must be at least 1.")
    if options.max_paths < 1:
        raise ValueError("max_paths must be at least 1.")

    paths: list[PathResult] = []

    def dfs(
        current: str,
        node_path: list[str],
        edge_path: list[str],
        data_path: list[str],
        conditions: list[str],
        depth: int,
    ) -> None:
        if current in graph.ends:
            paths.append(
                PathResult(
                    nodes=list(node_path),
                    edges=list(edge_path),
                    data=list(data_path),
                    conditions=list(conditions),
                )
            )
            if len(paths) > options.max_paths:
                raise PathLimitExceeded(f"Path generation exceeded max_paths={options.max_paths}.")
            return

        if strategy == "max-depth" and depth >= options.max_depth:
            return

        for edge in graph.outgoing_edges(current):
            if strategy == "simple" and edge.target in node_path:
                continue
            dfs(
                edge.target,
                [*node_path, edge.target],
                [*edge_path, edge.id],
                [*data_path, *edge.data],
                [*conditions, edge.condition] if edge.condition else list(conditions),
                depth + 1,
            )

    dfs(graph.start, [graph.start], [], [], [], 0)
    return sorted(paths, key=lambda path: (len(path.nodes), path.nodes, path.edges))


def detect_cycles(graph: CDFDGraph) -> list[list[str]]:
    state: dict[str, str] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def visit(node_id: str) -> None:
        state[node_id] = "gray"
        stack.append(node_id)

        for edge in graph.outgoing_edges(node_id):
            target = edge.target
            if state.get(target) == "gray":
                start_index = stack.index(target)
                cycle = [*stack[start_index:], target]
                key = _canonical_cycle_key(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
            elif state.get(target) is None:
                visit(target)

        stack.pop()
        state[node_id] = "black"

    for node_id in graph.nodes:
        if state.get(node_id) is None:
            visit(node_id)

    return cycles


def _canonical_cycle_key(cycle: list[str]) -> tuple[str, ...]:
    body = cycle[:-1]
    if not body:
        return tuple(cycle)
    rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
    return min(rotations)


def _normalize_strategy(strategy: str) -> str:
    normalized = strategy.replace("_", "-").lower()
    if normalized in {"simple", "simple-paths"}:
        return "simple"
    if normalized in {"max-depth", "depth"}:
        return "max-depth"
    raise ValueError("strategy must be either 'simple' or 'max-depth'.")
