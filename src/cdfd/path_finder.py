from __future__ import annotations

from dataclasses import dataclass

from cdfd.models import CDFDGraph, Edge, PathResult


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
                    outputs=_node_outputs(graph, current),
                    preconditions=[],
                    conditions=list(conditions),
                )
            )
            if len(paths) > options.max_paths:
                raise PathLimitExceeded(f"Path generation exceeded max_paths={options.max_paths}.")
            return

        if strategy == "max-depth" and depth >= options.max_depth:
            return

        for edge in graph.outgoing_edges(current):
            if _is_control_edge(edge):
                continue
            if strategy == "simple" and edge.target in node_path:
                continue
            next_conditions = _extend_unique(
                conditions,
                [*_edge_conditions(edge), *_incoming_control_conditions(graph, edge.target)],
            )
            dfs(
                edge.target,
                [*node_path, edge.target],
                [*edge_path, edge.id],
                [*data_path, *edge.data],
                next_conditions,
                depth + 1,
            )

    for start in sorted(graph.starts or {graph.start}):
        dfs(start, [start], [], [], _incoming_control_conditions(graph, start), 0)
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
            if _is_control_edge(edge):
                continue
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


def _node_outputs(graph: CDFDGraph, node_id: str) -> list[str]:
    raw_outputs = graph.metadata.get("outputs", {})
    if isinstance(raw_outputs, dict):
        value = raw_outputs.get(node_id, [])
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _is_control_edge(edge: Edge) -> bool:
    return edge.kind.lower().replace("_", "-") == "control"


def _edge_conditions(edge: Edge) -> list[str]:
    return [edge.condition] if edge.condition else []


def _incoming_control_conditions(graph: CDFDGraph, node_id: str) -> list[str]:
    conditions: list[str] = []
    for edge in graph.incoming_edges(node_id):
        if not _is_control_edge(edge):
            continue
        if edge.condition:
            conditions.append(edge.condition)
        elif edge.label:
            conditions.append(edge.label)
        elif edge.data:
            conditions.append(", ".join(edge.data))
    return conditions


def _extend_unique(existing: list[str], additions: list[str]) -> list[str]:
    values = list(existing)
    seen = set(values)
    for item in additions:
        if item not in seen:
            values.append(item)
            seen.add(item)
    return values
