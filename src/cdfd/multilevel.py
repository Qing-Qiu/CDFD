from __future__ import annotations

from cdfd.models import CDFDGraph, CDFDProject, PathResult
from cdfd.path_finder import PathFindingOptions, PathLimitExceeded, detect_cycles, find_paths


def find_project_paths(
    project: CDFDProject,
    options: PathFindingOptions | None = None,
    *,
    entry_graph: str | None = None,
    expand: bool = True,
) -> list[PathResult]:
    return decompose_project_flow(project, options, entry_graph=entry_graph, expand=expand).paths


def decompose_project_flow(
    project: CDFDProject,
    options: PathFindingOptions | None = None,
    *,
    entry_graph: str | None = None,
    expand: bool = True,
):
    from cdfd.flow_decomposition import _build_flow_distribution, decompose_flow
    from cdfd.models import FlowDecompositionResult

    options = options or PathFindingOptions()
    graph_name = entry_graph or project.entry_graph
    if graph_name not in project.graphs:
        raise ValueError(f"Graph '{graph_name}' is not defined.")

    if not expand:
        return decompose_flow(project.graphs[graph_name], options, project=project)

    paths = _expand_graph(project, graph_name, options, stack=[])
    if len(paths) > options.max_paths:
        raise PathLimitExceeded(f"Path generation exceeded max_paths={options.max_paths}.")
    sorted_paths = sorted(paths, key=lambda path: (len(path.nodes), path.nodes, path.edges))
    cycles = [cycle for graph_cycles in detect_project_cycles(project).values() for cycle in graph_cycles]
    flow_distribution = _build_flow_distribution(sorted_paths, project.graphs[graph_name])
    return FlowDecompositionResult(
        paths=sorted_paths,
        cycles=cycles,
        flow_distribution=flow_distribution,
    )


def detect_project_cycles(project: CDFDProject) -> dict[str, list[list[str]]]:
    cycles: dict[str, list[list[str]]] = {}
    for graph_name, graph in project.graphs.items():
        graph_cycles = detect_cycles(graph)
        if graph_cycles:
            cycles[graph_name] = graph_cycles
    return cycles


def _expand_graph(
    project: CDFDProject,
    graph_name: str,
    options: PathFindingOptions,
    *,
    stack: list[str],
) -> list[PathResult]:
    if graph_name in stack:
        chain = " -> ".join([*stack, graph_name])
        raise ValueError(f"Recursive process decomposition detected: {chain}")

    graph = project.graphs[graph_name]
    base_paths = find_paths(graph, options, project=project)
    expanded_paths: list[PathResult] = []
    next_stack = [*stack, graph_name]

    for base_path in base_paths:
        expanded_paths.extend(_expand_base_path(project, graph_name, base_path, options, stack=next_stack))
        if len(expanded_paths) > options.max_paths:
            raise PathLimitExceeded(f"Path generation exceeded max_paths={options.max_paths}.")

    return expanded_paths


def _expand_base_path(
    project: CDFDProject,
    graph_name: str,
    base_path: PathResult,
    options: PathFindingOptions,
    *,
    stack: list[str],
) -> list[PathResult]:
    initial_conditions = _start_conditions(project, graph_name, base_path.nodes[0] if base_path.nodes else None)
    partials = [
        PathResult(
            nodes=[],
            edges=[],
            edge_sources=[],
            edge_targets=[],
            edge_data=[],
            data=[],
            outputs=[],
            preconditions=[],
            conditions=initial_conditions,
        )
    ]

    for index, node_id in enumerate(base_path.nodes):
        node_segments = _node_segments(project, node_id, options, stack=stack)
        parent_edge_id = base_path.edges[index] if index < len(base_path.edges) else None
        if parent_edge_id:
            parent_edge_data, _ = _edge_values(project, graph_name, parent_edge_id)
            node_segments = _compatible_segments(node_segments, parent_edge_data)
        next_partials: list[PathResult] = []

        for partial in partials:
            for segment in node_segments:
                edges = [*partial.edges, *segment.edges]
                edge_sources = [*partial.edge_sources, *segment.edge_sources]
                edge_targets = [*partial.edge_targets, *segment.edge_targets]
                edge_data_path = [*partial.edge_data, *segment.edge_data]
                data = [*partial.data, *segment.data]
                preconditions = [*partial.preconditions, *segment.preconditions]
                conditions = [*partial.conditions, *segment.conditions]

                if parent_edge_id:
                    edges.append(_qualify_edge(graph_name, parent_edge_id))
                    edge_data, _, edge_source, edge_target = _edge_details(project, graph_name, parent_edge_id)
                    edge_sources.append(edge_source)
                    edge_targets.append(edge_target)
                    edge_data_path.append(list(edge_data))
                    data.extend(edge_data)
                    conditions = _extend_unique(conditions, _edge_conditions(project, graph_name, parent_edge_id))

                next_partials.append(
                    PathResult(
                        nodes=[*partial.nodes, *segment.nodes],
                        edges=edges,
                        edge_sources=edge_sources,
                        edge_targets=edge_targets,
                        edge_data=edge_data_path,
                        data=data,
                        outputs=segment.outputs or base_path.outputs,
                        preconditions=preconditions,
                        conditions=conditions,
                    )
                )

        partials = next_partials

    return partials


def _node_segments(
    project: CDFDProject,
    node_id: str,
    options: PathFindingOptions,
    *,
    stack: list[str],
) -> list[PathResult]:
    process = project.processes.get(node_id)
    if not process or not process.decom:
        return [
            PathResult(
                nodes=[node_id],
                edges=[],
                data=[],
                outputs=process.outputs if process else [],
                preconditions=_process_preconditions(node_id, process),
                conditions=[],
            )
        ]
    if process.decom not in project.graphs:
        raise ValueError(f"Process '{node_id}' decomposes to missing graph '{process.decom}'.")
    segments = _expand_graph(project, process.decom, options, stack=stack)
    return [
            PathResult(
                nodes=segment.nodes,
                edges=segment.edges,
                edge_sources=segment.edge_sources,
                edge_targets=segment.edge_targets,
                edge_data=segment.edge_data,
                data=segment.data,
                outputs=segment.outputs,
                preconditions=[*_process_preconditions(node_id, process), *segment.preconditions],
            conditions=segment.conditions,
        )
        for segment in segments
    ]


def _qualify_edge(graph_name: str, edge_id: str) -> str:
    return f"{graph_name}:{edge_id}"


def _edge_values(project: CDFDProject, graph_name: str, edge_id: str) -> tuple[list[str], str | None]:
    data, condition, _, _ = _edge_details(project, graph_name, edge_id)
    return data, condition


def _edge_details(project: CDFDProject, graph_name: str, edge_id: str) -> tuple[list[str], str | None, str, str]:
    for edge in project.graphs[graph_name].edges:
        if edge.id == edge_id:
            return edge.data, edge.condition, edge.source, edge.target
    return [], None, "", ""


def _edge_conditions(project: CDFDProject, graph_name: str, edge_id: str) -> list[str]:
    graph = project.graphs[graph_name]
    for edge in graph.edges:
        if edge.id != edge_id:
            continue
        edge_conditions = [edge.condition] if edge.condition else []
        return [*edge_conditions, *_control_conditions_for_target(graph, edge.target)]
    return []


def _start_conditions(project: CDFDProject, graph_name: str, node_id: str | None) -> list[str]:
    if node_id is None:
        return []
    graph = project.graphs[graph_name]
    return _control_conditions_for_target(graph, node_id)


def _control_conditions_for_target(graph: CDFDGraph, node_id: str) -> list[str]:
    conditions: list[str] = []
    for control_edge in graph.incoming_edges(node_id):
        if control_edge.kind.lower().replace("_", "-") != "control":
            continue
        if control_edge.condition:
            conditions.append(control_edge.condition)
        elif control_edge.label:
            conditions.append(control_edge.label)
        elif control_edge.data:
            conditions.append(", ".join(control_edge.data))
    return conditions


def _compatible_segments(segments: list[PathResult], parent_edge_data: list[str]) -> list[PathResult]:
    if not parent_edge_data:
        return segments
    constrained = [segment for segment in segments if not segment.outputs or set(segment.outputs) & set(parent_edge_data)]
    return constrained or segments


def _process_preconditions(node_id: str, process) -> list[str]:
    if process and process.pre:
        return [f"{node_id}: {process.pre}"]
    return []


def _extend_unique(existing: list[str], additions: list[str]) -> list[str]:
    values = list(existing)
    seen = set(values)
    for item in additions:
        if item not in seen:
            values.append(item)
            seen.add(item)
    return values
