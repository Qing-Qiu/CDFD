from __future__ import annotations

import re
from collections import defaultdict

from cdfd.models import PathGroup, PathResult


def build_path_groups(paths: list[PathResult]) -> list[PathGroup]:
    groups: list[PathGroup] = []
    group_index = 1

    for group_paths in _joined_output_candidates(paths):
        groups.append(_make_group(f"G{group_index}", "joined-output", group_paths))
        group_index += 1

    seen_parallel: set[tuple[str, ...]] = set()
    for group_paths in _parallel_candidates(paths):
        path_ids = tuple(_path_id(index) for index, _ in group_paths)
        if path_ids in seen_parallel:
            continue
        seen_parallel.add(path_ids)
        groups.append(_make_group(f"G{group_index}", "parallel", group_paths))
        group_index += 1

    return groups


def _joined_output_candidates(paths: list[PathResult]) -> list[list[tuple[int, PathResult]]]:
    by_output: dict[tuple[str, ...], list[tuple[int, PathResult]]] = defaultdict(list)
    for index, path in enumerate(paths, start=1):
        by_output[_output_key(path)].append((index, path))

    candidates: list[list[tuple[int, PathResult]]] = []
    for group_paths in by_output.values():
        if len(group_paths) < 2:
            continue
        if not _same_edge_conditions([path for _, path in group_paths]):
            continue
        if not _pairwise_compatible([path for _, path in group_paths]):
            continue
        candidates.append(group_paths)
    return candidates


def _parallel_candidates(paths: list[PathResult]) -> list[list[tuple[int, PathResult]]]:
    candidates: list[list[tuple[int, PathResult]]] = []

    for left_index, left in enumerate(paths, start=1):
        for right_index, right in enumerate(paths[left_index:], start=left_index + 1):
            if _can_run_in_parallel(left, right):
                candidates.append([(left_index, left), (right_index, right)])

    return candidates


def _make_group(group_id: str, kind: str, indexed_paths: list[tuple[int, PathResult]]) -> PathGroup:
    paths = [path for _, path in indexed_paths]
    path_ids = [_path_id(index) for index, _ in indexed_paths]
    shared_prefix = _common_prefix([path.nodes for path in paths])
    outputs = _unique(item for path in paths for item in _path_outputs(path))
    data = _unique(item for path in paths for item in path.data)
    preconditions = _unique(item for path in paths for item in path.preconditions)
    conditions = _unique(item for path in paths for item in path.conditions)

    if kind == "joined-output":
        output_text = ", ".join(outputs) if outputs else "same output"
        title = f"{output_text} joined from {len(paths)} branches"
        reason = "Multiple compatible linear flows reach the same output, so they are treated as input branches of one output slice."
    else:
        title = f"{len(paths)} independent paths can run in parallel"
        reason = "The paths share only their prefix and then use disjoint downstream nodes/data without conflicting conditions."

    return PathGroup(
        id=group_id,
        kind=kind,
        path_ids=path_ids,
        title=title,
        shared_prefix=shared_prefix,
        nodes=_unique(item for path in paths for item in path.nodes),
        edges=_unique(item for path in paths for item in path.edges),
        data=data,
        outputs=outputs,
        preconditions=preconditions,
        conditions=conditions,
        reason=reason,
    )


def _can_run_in_parallel(left: PathResult, right: PathResult) -> bool:
    if not left.nodes or not right.nodes:
        return False
    if left.nodes[0] != right.nodes[0]:
        return False
    if _output_key(left) == _output_key(right):
        return False
    if not _same_edge_conditions([left, right]):
        return False
    if not _conditions_compatible(left, right):
        return False

    prefix = _common_prefix([left.nodes, right.nodes])
    if len(prefix) < 1:
        return False

    left_suffix_nodes = set(left.nodes[len(prefix) :])
    right_suffix_nodes = set(right.nodes[len(prefix) :])
    if left_suffix_nodes & right_suffix_nodes:
        return False

    left_suffix_data = set(_suffix_data(left, len(prefix)))
    right_suffix_data = set(_suffix_data(right, len(prefix)))
    return not (left_suffix_data & right_suffix_data)


def _pairwise_compatible(paths: list[PathResult]) -> bool:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if not _conditions_compatible(left, right):
                return False
    return True


def _same_edge_conditions(paths: list[PathResult]) -> bool:
    condition_sets = {tuple(path.conditions) for path in paths}
    return len(condition_sets) <= 1


def _conditions_compatible(left: PathResult, right: PathResult) -> bool:
    facts: dict[str, str] = {}
    for condition in [*left.preconditions, *left.conditions, *right.preconditions, *right.conditions]:
        parsed = _parse_equality(condition)
        if not parsed:
            continue
        name, value = parsed
        if name in facts and facts[name] != value:
            return False
        facts[name] = value
    return True


def _parse_equality(text: str) -> tuple[str, str] | None:
    match = re.search(r"(?:^|[:;]\s*)([A-Za-z_]\w*)\s*==\s*([^;,\s]+)", text)
    if not match:
        return None
    return match.group(1), match.group(2)


def _output_key(path: PathResult) -> tuple[str, ...]:
    outputs = _path_outputs(path)
    if outputs:
        return tuple(outputs)
    if path.nodes:
        return (path.nodes[-1],)
    return ()


def _path_outputs(path: PathResult) -> list[str]:
    if path.outputs:
        return path.outputs
    if path.data:
        return [path.data[-1]]
    if path.nodes:
        return [path.nodes[-1]]
    return []


def _suffix_data(path: PathResult, prefix_len: int) -> list[str]:
    if len(path.data) == len(path.nodes) - 1:
        return path.data[max(prefix_len - 1, 0) :]
    return path.data


def _common_prefix(paths: list[list[str]]) -> list[str]:
    if not paths:
        return []

    prefix: list[str] = []
    for values in zip(*paths):
        if len(set(values)) != 1:
            break
        prefix.append(values[0])
    return prefix


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


def _path_id(index: int) -> str:
    return f"P{index}"
