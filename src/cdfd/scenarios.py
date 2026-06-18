from __future__ import annotations

from cdfd.concurrent_paths import format_notation, format_tree_lines
from cdfd.models import (
    ConcurrentPathResult,
    CDFDProject,
    FunctionalScenario,
    PathRelation,
    PathResult,
    ScenarioOperation,
)


def build_functional_scenarios(
    paths: list[PathResult],
    *,
    project: CDFDProject | None = None,
    concurrent_paths: list[ConcurrentPathResult] | None = None,
    path_relations: list[PathRelation] | None = None,
) -> list[FunctionalScenario]:
    scenarios: list[FunctionalScenario] = []
    covered_path_ids: set[str] = set()
    scenario_index = 1

    if concurrent_paths:
        for concurrent in concurrent_paths:
            if not _has_parallel_node(concurrent.root):
                continue
            path_ids = _covered_path_ids(concurrent, paths)
            covered_path_ids.update(path_ids)
            scenarios.append(
                _scenario_from_concurrent(
                    concurrent,
                    scenario_index,
                    path_ids=path_ids,
                    project=project,
                )
            )
            scenario_index += 1

    for path_index, path in enumerate(paths, start=1):
        path_id = f"P{path_index}"
        if path_id in covered_path_ids:
            continue
        scenarios.append(_scenario_from_path(path, scenario_index, path_index, project=project))
        scenario_index += 1

    return scenarios


def _scenario_from_concurrent(
    concurrent: ConcurrentPathResult,
    index: int,
    *,
    path_ids: list[str],
    project: CDFDProject | None,
) -> FunctionalScenario:
    operations = _scenario_operations_from_nodes(concurrent.nodes, project)
    input_data = _input_data_from_operations(operations, concurrent.data)
    output_data = _output_data_from_operations(operations, concurrent.outputs, concurrent.data)
    postconditions = _unique(operation.post for operation in operations if operation.post)
    notation = concurrent.notation or format_notation(concurrent.root)
    tree_lines = format_tree_lines(concurrent.root, title=f"Scenario {index} Concurrent Path")

    return FunctionalScenario(
        id=f"FS{index}",
        kind="concurrent",
        path_ids=path_ids,
        concurrent_path=concurrent.root,
        notation=notation,
        source=concurrent.nodes[0] if concurrent.nodes else None,
        sink=concurrent.nodes[-1] if concurrent.nodes else None,
        input_data=input_data,
        output_data=output_data,
        operations=operations,
        data=list(concurrent.data),
        preconditions=list(concurrent.preconditions),
        postconditions=postconditions,
        conditions=list(concurrent.conditions),
        description="\n".join(tree_lines),
    )


def _scenario_from_path(
    path: PathResult,
    index: int,
    path_index: int,
    *,
    project: CDFDProject | None,
) -> FunctionalScenario:
    operations = _scenario_operations(path, project)
    input_data = _input_data(path, operations)
    output_data = _output_data(path, operations)
    postconditions = _unique(operation.post for operation in operations if operation.post)

    return FunctionalScenario(
        id=f"FS{index}",
        path_ids=[f"P{path_index}"],
        source=path.nodes[0] if path.nodes else None,
        sink=path.sink or (path.nodes[-1] if path.nodes else None),
        input_data=input_data,
        output_data=output_data,
        operations=operations,
        data=list(path.data),
        preconditions=list(path.preconditions),
        postconditions=postconditions,
        conditions=list(path.conditions),
        description=_scenario_description(path, input_data, output_data, operations),
    )


def _scenario_operations(path: PathResult, project: CDFDProject | None) -> list[ScenarioOperation]:
    return _scenario_operations_from_nodes(path.nodes, project)


def _scenario_operations_from_nodes(
    node_ids: list[str],
    project: CDFDProject | None,
) -> list[ScenarioOperation]:
    if project is None:
        return []

    operations: list[ScenarioOperation] = []
    seen: set[str] = set()
    for node_id in node_ids:
        process = project.processes.get(node_id)
        if process is None or node_id in seen:
            continue
        seen.add(node_id)
        operations.append(
            ScenarioOperation(
                process=node_id,
                inputs=list(process.inputs),
                outputs=list(process.outputs),
                pre=process.pre,
                post=process.post,
            )
        )
    return operations


def _input_data(path: PathResult, operations: list[ScenarioOperation]) -> list[str]:
    return _input_data_from_operations(operations, path.data)


def _input_data_from_operations(operations: list[ScenarioOperation], data: list[str]) -> list[str]:
    if operations and operations[0].inputs:
        return list(operations[0].inputs)
    return data[:1]


def _output_data(path: PathResult, operations: list[ScenarioOperation]) -> list[str]:
    return _output_data_from_operations(operations, path.outputs, path.data)


def _output_data_from_operations(
    operations: list[ScenarioOperation],
    outputs: list[str],
    data: list[str],
) -> list[str]:
    if outputs:
        return list(outputs)
    if operations and operations[-1].outputs:
        return list(operations[-1].outputs)
    return data[-1:] if data else []


def _scenario_description(
    path: PathResult,
    input_data: list[str],
    output_data: list[str],
    operations: list[ScenarioOperation],
) -> str:
    source = path.nodes[0] if path.nodes else "unknown source"
    sink = path.nodes[-1] if path.nodes else "unknown sink"
    input_text = ", ".join(input_data) if input_data else "input data"
    output_text = ", ".join(output_data) if output_data else "output data"
    operation_text = " -> ".join(operation.process for operation in operations) or "the CDFD path"
    return f"{input_text} is transformed to {output_text} from {source} to {sink} through {operation_text}."


def _has_parallel_node(root) -> bool:
    if root.kind == "parallel":
        return True
    return any(_has_parallel_node(child) for child in root.children)


def _covered_path_ids(concurrent: ConcurrentPathResult, paths: list[PathResult]) -> list[str]:
    concurrent_edges = {_edge_key(edge_id) for edge_id in concurrent.edges}
    if not concurrent_edges:
        return []

    path_ids: list[str] = []
    for index, path in enumerate(paths, start=1):
        path_edges = {_edge_key(edge_id) for edge_id in path.edges}
        if path_edges and path_edges <= concurrent_edges:
            path_ids.append(f"P{index}")
    return path_ids


def _edge_key(edge_id: str) -> str:
    return edge_id.rsplit(":", 1)[-1]


def _unique(items) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values
