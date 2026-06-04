from __future__ import annotations

from cdfd.models import CDFDProject, FunctionalScenario, PathResult, ScenarioOperation


def build_functional_scenarios(
    paths: list[PathResult],
    *,
    project: CDFDProject | None = None,
) -> list[FunctionalScenario]:
    return [
        _scenario_from_path(path, index, project=project)
        for index, path in enumerate(paths, start=1)
    ]


def _scenario_from_path(
    path: PathResult,
    index: int,
    *,
    project: CDFDProject | None,
) -> FunctionalScenario:
    operations = _scenario_operations(path, project)
    input_data = _input_data(path, operations)
    output_data = _output_data(path, operations)
    postconditions = _unique(operation.post for operation in operations if operation.post)

    return FunctionalScenario(
        id=f"FS{index}",
        path_ids=[f"P{index}"],
        source=path.nodes[0] if path.nodes else None,
        sink=path.nodes[-1] if path.nodes else None,
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
    if project is None:
        return []

    operations: list[ScenarioOperation] = []
    seen: set[str] = set()
    for node_id in path.nodes:
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
    if operations and operations[0].inputs:
        return list(operations[0].inputs)
    return path.data[:1]


def _output_data(path: PathResult, operations: list[ScenarioOperation]) -> list[str]:
    if operations and operations[-1].outputs:
        return list(operations[-1].outputs)
    if path.outputs:
        return list(path.outputs)
    return path.data[-1:] if path.data else []


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
