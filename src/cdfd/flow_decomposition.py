from __future__ import annotations

from collections import defaultdict

from cdfd.models import CDFDGraph, CDFDProject, Edge, FlowDecompositionResult, PathResult, ProcessSpec
from cdfd.path_finder import PathFindingOptions, detect_cycles, find_paths

SINK_POLICIES = {"demand", "distance", "capacity"}


def collect_path_outputs(
    graph: CDFDGraph,
    sink_node: str,
    *,
    node_path: list[str] | None = None,
    processes: dict[str, ProcessSpec] | None = None,
) -> list[str]:
    """Pack multi-output items for a path terminating at sink_node."""
    raw_outputs = graph.metadata.get("outputs", {})
    if isinstance(raw_outputs, dict):
        value = raw_outputs.get(sink_node, [])
        if isinstance(value, str):
            return [value]
        if isinstance(value, list) and value:
            return [str(item) for item in value]

    incoming = [
        edge
        for edge in graph.incoming_edges(sink_node)
        if edge.kind.lower().replace("_", "-") != "control"
    ]
    if processes:
        for edge in incoming:
            process = processes.get(edge.source)
            if not process:
                continue
            if process.output_ports:
                for port in process.output_ports:
                    port_edges = set(port.edges)
                    port_data = set(port.data)
                    if (port_edges and edge.id in port_edges) or (
                        port_data and port_data & set(edge.data)
                    ):
                        return list(port.data) if port.data else list(edge.data)
            if process.outputs:
                if edge.data:
                    matched = [item for item in process.outputs if item in edge.data]
                    if matched:
                        return matched
                elif not edge.data:
                    return list(process.outputs)

    outputs: list[str] = []
    for edge in incoming:
        outputs.extend(edge.data)
    return _unique(outputs)


def decompose_flow(
    graph: CDFDGraph,
    options: PathFindingOptions | None = None,
    project: CDFDProject | None = None,
) -> FlowDecompositionResult:
    options = options or PathFindingOptions()
    _normalize_sink_policy(options.sink_policy)
    paths = find_paths(graph, options, project=project)
    ordered_paths = _order_paths_by_sink_policy(graph, paths, options.sink_policy)
    return FlowDecompositionResult(
        paths=ordered_paths,
        cycles=detect_cycles(graph),
        flow_distribution=_build_flow_distribution(ordered_paths, graph),
    )


def _order_paths_by_sink_policy(
    graph: CDFDGraph,
    paths: list[PathResult],
    sink_policy: str,
) -> list[PathResult]:
    if not paths or sink_policy == "demand":
        return list(paths)

    sink_counts: dict[str, int] = defaultdict(int)
    scored: list[tuple[tuple[float, ...], PathResult]] = []
    for index, path in enumerate(paths):
        sink = path.sink or (path.nodes[-1] if path.nodes else "")
        demand = 1.0 / (1.0 + float(sink_counts[sink]))
        sink_counts[sink] += 1
        distance = float(max(0, len(path.nodes) - 1))
        capacity = float(_sink_path_capacity(graph, path))
        if sink_policy == "distance":
            key = (-distance, demand, float(index))
        elif sink_policy == "capacity":
            key = (capacity, demand, -distance, float(index))
        else:
            key = (demand, -distance, float(index))
        scored.append((key, path))

    scored.sort(key=lambda item: item[0])
    return [path for _, path in scored]


def _sink_path_capacity(graph: CDFDGraph, path: PathResult) -> int:
    if not path.edges:
        return 0
    capacities: list[int] = []
    for edge_id in path.edges:
        for edge in graph.edges:
            if edge.id != edge_id:
                continue
            raw = edge.metadata.get("capacity")
            if raw is not None:
                try:
                    capacities.append(max(0, int(raw)))
                    break
                except (TypeError, ValueError):
                    pass
            capacities.append(1)
            break
    return min(capacities) if capacities else 0


def _build_flow_distribution(paths: list[PathResult], graph: CDFDGraph) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    starts = sorted(graph.starts or {graph.start})
    for path in paths:
        if not path.nodes:
            continue
        source = path.nodes[0]
        sink = path.sink or path.nodes[-1]
        if source in starts:
            matrix[source][sink] += 1
    return {source: dict(sinks) for source, sinks in sorted(matrix.items())}


def _normalize_sink_policy(policy: str) -> str:
    normalized = policy.replace("_", "-").lower()
    if normalized in SINK_POLICIES:
        return normalized
    raise ValueError("sink_policy must be one of: demand, distance, capacity.")


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values
