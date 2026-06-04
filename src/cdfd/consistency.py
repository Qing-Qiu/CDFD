from __future__ import annotations

from collections import defaultdict
from typing import Any

from cdfd.models import CDFDGraph, CDFDProject, ConsistencyIssue


def inspect_project_consistency(project: CDFDProject) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    process_occurrences: dict[str, set[str]] = defaultdict(set)
    declared_data = _declared_module_data(project)

    for graph_name, graph in project.graphs.items():
        issues.extend(_inspect_data_declarations(project, graph_name, graph, declared_data))
        issues.extend(_inspect_data_stores(graph_name, graph))
        graph_inputs = _metadata_io(graph.metadata, "inputs")
        graph_outputs = _metadata_io(graph.metadata, "outputs")

        for node_id, node in graph.nodes.items():
            if node.type != "process":
                continue
            process_occurrences[node_id].add(graph_name)
            process = project.processes.get(node_id)
            if process is None:
                issues.append(
                    _issue(
                        "missing-process-spec",
                        f"Process node '{node_id}' occurs in graph '{graph_name}' but has no process specification.",
                        graph=graph_name,
                        node=node_id,
                        process=node_id,
                    )
                )
                continue

            observed_inputs = _incoming_data(graph, node_id) | set(graph_inputs.get(node_id, []))
            observed_outputs = _outgoing_data(graph, node_id) | set(graph_outputs.get(node_id, []))
            issues.extend(
                _compare_process_interface(
                    graph_name,
                    node_id,
                    "inputs",
                    set(process.inputs),
                    observed_inputs,
                )
            )
            issues.extend(
                _compare_process_interface(
                    graph_name,
                    node_id,
                    "outputs",
                    set(process.outputs),
                    observed_outputs,
                )
            )

    for process_id in sorted(project.processes):
        if process_id not in process_occurrences:
            issues.append(
                _issue(
                    "unused-process-spec",
                    f"Process specification '{process_id}' is not used by any CDFD graph node.",
                    process=process_id,
                )
            )

    return [_renumber(issue, index) for index, issue in enumerate(issues, start=1)]


def _inspect_data_declarations(
    project: CDFDProject,
    graph_name: str,
    graph: CDFDGraph,
    declared_data: set[str],
) -> list[ConsistencyIssue]:
    if project.module is None or not declared_data:
        return []

    issues: list[ConsistencyIssue] = []
    for edge in graph.edges:
        if edge.kind == "control":
            continue
        missing = [data_id for data_id in edge.data if data_id not in declared_data]
        if missing:
            issues.append(
                _issue(
                    "undeclared-data-flow",
                    f"Edge '{edge.id}' in graph '{graph_name}' uses undeclared data flow(s): {', '.join(missing)}.",
                    graph=graph_name,
                    edge=edge.id,
                    data=missing,
                )
            )
    return issues


def _inspect_data_stores(graph_name: str, graph: CDFDGraph) -> list[ConsistencyIssue]:
    issues: list[ConsistencyIssue] = []
    for node_id, node in graph.nodes.items():
        if node.type != "data_store":
            continue
        connected_data = _incoming_data(graph, node_id) | _outgoing_data(graph, node_id)
        if not connected_data:
            issues.append(
                _issue(
                    "disconnected-data-store",
                    f"Data store '{node_id}' in graph '{graph_name}' has no data-flow connection.",
                    graph=graph_name,
                    node=node_id,
                )
            )
    return issues


def _compare_process_interface(
    graph_name: str,
    process_id: str,
    field_name: str,
    declared: set[str],
    observed: set[str],
) -> list[ConsistencyIssue]:
    if declared == observed:
        return []
    if not declared and not observed:
        return []

    missing_from_spec = sorted(observed - declared)
    missing_from_graph = sorted(declared - observed)
    details: list[str] = []
    if missing_from_spec:
        details.append(f"in CDFD but not in process spec: {', '.join(missing_from_spec)}")
    if missing_from_graph:
        details.append(f"in process spec but not in CDFD: {', '.join(missing_from_graph)}")

    return [
        _issue(
            f"process-{field_name}-mismatch",
            f"Process '{process_id}' {field_name} mismatch in graph '{graph_name}' ({'; '.join(details)}).",
            graph=graph_name,
            node=process_id,
            process=process_id,
            data=[*missing_from_spec, *missing_from_graph],
        )
    ]


def _incoming_data(graph: CDFDGraph, node_id: str) -> set[str]:
    return {
        data_id
        for edge in graph.edges
        if edge.target == node_id and edge.kind != "control"
        for data_id in edge.data
    }


def _outgoing_data(graph: CDFDGraph, node_id: str) -> set[str]:
    return {
        data_id
        for edge in graph.edges
        if edge.source == node_id and edge.kind != "control"
        for data_id in edge.data
    }


def _metadata_io(metadata: dict[str, Any], key: str) -> dict[str, list[str]]:
    raw = metadata.get(key, {})
    if not isinstance(raw, dict):
        return {}

    values: dict[str, list[str]] = {}
    for node_id, item in raw.items():
        if isinstance(item, str):
            values[str(node_id)] = [item]
        elif isinstance(item, list):
            values[str(node_id)] = [str(value) for value in item]
    return values


def _declared_module_data(project: CDFDProject) -> set[str]:
    if project.module is None:
        return set()
    return {str(item).split("=", 1)[0].strip() for item in project.module.var if str(item).strip()}


def _issue(
    rule: str,
    message: str,
    *,
    graph: str | None = None,
    node: str | None = None,
    edge: str | None = None,
    process: str | None = None,
    data: list[str] | None = None,
) -> ConsistencyIssue:
    return ConsistencyIssue(
        id="C0",
        rule=rule,
        message=message,
        graph=graph,
        node=node,
        edge=edge,
        process=process,
        data=data or [],
    )


def _renumber(issue: ConsistencyIssue, index: int) -> ConsistencyIssue:
    update = {"id": f"C{index}"}
    if hasattr(issue, "model_copy"):
        return issue.model_copy(update=update)
    return issue.copy(update=update)
