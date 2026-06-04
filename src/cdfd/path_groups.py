from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations

from cdfd.models import CDFDGraph, CDFDProject, GraphStructure, PathRelation, PathResult, StructureBranch


PARALLEL_KINDS = {"parallel", "broadcast", "separate", "fork"}
JOINED_OUTPUT_KINDS = {"join", "merge", "joined-output"}
EXCLUSIVE_KINDS = {"choice", "select", "condition", "conditional", "non-determinism", "nondeterminism"}


def build_path_relations(
    paths: list[PathResult],
    *,
    project: CDFDProject | None = None,
    graph: CDFDGraph | None = None,
    graph_name: str | None = None,
) -> list[PathRelation]:
    has_explicit_structures = bool(_structure_contexts(project, graph, graph_name))
    explicit, covered_pairs, suppressed_pairs = _explicit_relations(paths, project, graph, graph_name)
    relations = list(explicit)
    if has_explicit_structures:
        return relations

    relation_index = len(relations) + 1

    for relation_paths in _joined_output_candidates(paths):
        pair_key = _pair_key(_path_id(index) for index, _ in relation_paths)
        if pair_key & covered_pairs:
            continue
        relations.append(_make_relation(f"R{relation_index}", "joined-output", relation_paths))
        relation_index += 1

    seen_parallel: set[tuple[str, ...]] = set()
    for relation_paths in _parallel_candidates(paths):
        path_ids = tuple(_path_id(index) for index, _ in relation_paths)
        pair_key = _pair_key(path_ids)
        if path_ids in seen_parallel or pair_key & covered_pairs or pair_key & suppressed_pairs:
            continue
        seen_parallel.add(path_ids)
        relations.append(_make_relation(f"R{relation_index}", "parallel", relation_paths))
        relation_index += 1

    return relations


def build_path_groups(paths: list[PathResult]) -> list[PathRelation]:
    return build_path_relations(paths)


def _explicit_relations(
    paths: list[PathResult],
    project: CDFDProject | None,
    graph: CDFDGraph | None,
    graph_name: str | None,
) -> tuple[list[PathRelation], set[tuple[str, str]], set[tuple[str, str]]]:
    contexts = _structure_contexts(project, graph, graph_name)
    indexed_paths = list(enumerate(paths, start=1))
    relations: list[PathRelation] = []
    covered_pairs: set[tuple[str, str]] = set()
    suppressed_pairs: set[tuple[str, str]] = set()

    for context_graph_name, structure in contexts:
        relation_kind = _relation_kind(structure.kind)
        if not relation_kind:
            continue

        branch_matches = _structure_branch_matches(indexed_paths, structure, context_graph_name)
        matched_branch_ids = [branch_id for branch_id, matches in branch_matches.items() if matches]
        if len(branch_matches) > 1 and len(matched_branch_ids) < 2:
            continue
        relation_paths = _dedupe_indexed_path(
            match
            for matches in branch_matches.values()
            for match in matches
        )
        if len(relation_paths) < 2:
            continue

        relation_id = f"R{len(relations) + 1}"
        relation = _make_relation(
            relation_id,
            relation_kind,
            relation_paths,
            structure=structure,
            branch_ids=matched_branch_ids,
        )
        relations.append(relation)

        pairs = _pair_key(relation.path_ids)
        if relation_kind == "exclusive":
            suppressed_pairs.update(pairs)
        else:
            covered_pairs.update(pairs)

    return relations, covered_pairs, suppressed_pairs


def _structure_contexts(
    project: CDFDProject | None,
    graph: CDFDGraph | None,
    graph_name: str | None,
) -> list[tuple[str | None, GraphStructure]]:
    if project:
        return [
            (name, structure)
            for name, project_graph in project.graphs.items()
            for structure in project_graph.structures
        ]
    if graph:
        return [(graph_name, structure) for structure in graph.structures]
    return []


def _structure_branch_matches(
    paths: list[tuple[int, PathResult]],
    structure: GraphStructure,
    graph_name: str | None,
) -> dict[str, list[tuple[int, PathResult]]]:
    branches = structure.branches or [
        StructureBranch(
            id=structure.id,
            source=structure.source,
            target=structure.target,
            edges=structure.edges,
            nodes=structure.nodes,
            data=structure.data,
            condition=structure.condition,
        )
    ]
    matches: dict[str, list[tuple[int, PathResult]]] = {}
    for index, branch in enumerate(branches, start=1):
        branch_id = branch.id or f"b{index}"
        matches[branch_id] = [
            indexed_path
            for indexed_path in paths
            if _path_matches_branch(indexed_path[1], branch, graph_name)
        ]
    return matches


def _path_matches_branch(path: PathResult, branch: StructureBranch, graph_name: str | None) -> bool:
    if branch.edges and not all(_path_has_edge(path, edge_id, graph_name) for edge_id in branch.edges):
        return False
    if branch.nodes and not all(node_id in path.nodes for node_id in branch.nodes):
        return False
    if branch.data and not all(data_id in path.data for data_id in branch.data):
        return False
    if branch.source and branch.source not in path.nodes:
        return False
    if branch.target and branch.target not in path.nodes:
        return False
    if branch.condition:
        all_conditions = [*path.preconditions, *path.conditions]
        if not any(branch.condition in condition for condition in all_conditions):
            return False
    return bool(branch.edges or branch.nodes or branch.data or branch.source or branch.target or branch.condition)


def _path_has_edge(path: PathResult, edge_id: str, graph_name: str | None) -> bool:
    candidates = {edge_id}
    if graph_name and ":" not in edge_id:
        candidates.add(f"{graph_name}:{edge_id}")
    return bool(candidates & set(path.edges))


def _relation_kind(structure_kind: str) -> str | None:
    normalized = structure_kind.lower().replace("_", "-")
    if normalized in PARALLEL_KINDS:
        return "parallel"
    if normalized in JOINED_OUTPUT_KINDS:
        return "joined-output"
    if normalized in EXCLUSIVE_KINDS:
        return "exclusive"
    return None


def _joined_output_candidates(paths: list[PathResult]) -> list[list[tuple[int, PathResult]]]:
    by_output: dict[tuple[str, ...], list[tuple[int, PathResult]]] = defaultdict(list)
    for index, path in enumerate(paths, start=1):
        by_output[_output_key(path)].append((index, path))

    candidates: list[list[tuple[int, PathResult]]] = []
    for relation_paths in by_output.values():
        if len(relation_paths) < 2:
            continue
        if not _same_edge_conditions([path for _, path in relation_paths]):
            continue
        if not _pairwise_compatible([path for _, path in relation_paths]):
            continue
        candidates.append(relation_paths)
    return candidates


def _parallel_candidates(paths: list[PathResult]) -> list[list[tuple[int, PathResult]]]:
    candidates: list[list[tuple[int, PathResult]]] = []

    for left_index, left in enumerate(paths, start=1):
        for right_index, right in enumerate(paths[left_index:], start=left_index + 1):
            if _can_run_in_parallel(left, right):
                candidates.append([(left_index, left), (right_index, right)])

    return candidates


def _make_relation(
    relation_id: str,
    kind: str,
    indexed_paths: list[tuple[int, PathResult]],
    *,
    structure: GraphStructure | None = None,
    branch_ids: list[str] | None = None,
) -> PathRelation:
    paths = [path for _, path in indexed_paths]
    path_ids = [_path_id(index) for index, _ in indexed_paths]
    shared_prefix = _common_prefix([path.nodes for path in paths])
    outputs = _unique(item for path in paths for item in _path_outputs(path))
    data = _unique(item for path in paths for item in path.data)
    preconditions = _unique(item for path in paths for item in path.preconditions)
    conditions = _unique(item for path in paths for item in path.conditions)

    title, reason = _relation_text(kind, outputs, len(paths), explicit=structure is not None)

    return PathRelation(
        id=relation_id,
        kind=kind,
        path_ids=path_ids,
        title=title,
        structure_id=structure.id if structure else None,
        branch_ids=branch_ids or [],
        shared_prefix=shared_prefix,
        nodes=_unique(item for path in paths for item in path.nodes),
        edges=_unique(item for path in paths for item in path.edges),
        data=data,
        outputs=outputs,
        preconditions=preconditions,
        conditions=conditions,
        reason=reason,
    )


def _relation_text(kind: str, outputs: list[str], path_count: int, *, explicit: bool) -> tuple[str, str]:
    source = "explicit CDFD structure" if explicit else "graph analysis"
    if kind == "joined-output":
        output_text = ", ".join(outputs) if outputs else "same output"
        return (
            f"{output_text} joined from {path_count} paths",
            f"Detected from {source}: compatible paths feed the same output.",
        )
    if kind == "exclusive":
        return (
            f"{path_count} paths are alternative choices",
            f"Detected from {source}: these paths belong to a choice/conditional structure.",
        )
    return (
        f"{path_count} paths can run in parallel",
        f"Detected from {source}: these paths are independent branches.",
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


def _dedupe_indexed_path(paths) -> list[tuple[int, PathResult]]:
    seen: set[int] = set()
    deduped: list[tuple[int, PathResult]] = []
    for index, path in paths:
        if index in seen:
            continue
        seen.add(index)
        deduped.append((index, path))
    return deduped


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


def _pair_key(path_ids) -> set[tuple[str, str]]:
    return {tuple(sorted(pair)) for pair in combinations(path_ids, 2)}


def _path_id(index: int) -> str:
    return f"P{index}"
