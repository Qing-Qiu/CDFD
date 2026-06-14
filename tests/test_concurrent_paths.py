from pathlib import Path

from cdfd.concurrent_paths import format_notation, format_tree_lines
from cdfd.parsers import parse_project
from cdfd.path_finder import can_activate_node, find_concurrent_paths, PathFindingOptions


ROOT = Path(__file__).resolve().parents[1]


def test_can_activate_node_requires_all_process_inputs():
    project = _example_project("join.json")
    graph = project.entry()

    assert can_activate_node(graph, "Combine", {"l_done"}, project.processes) is False
    assert can_activate_node(graph, "Combine", {"l_done", "r_done"}, project.processes) is True


def test_find_concurrent_paths_for_parallel_fork():
    project = _example_project("cdfd_v1.json")
    graph = project.entry()

    concurrent = find_concurrent_paths(graph, PathFindingOptions(), project=project)

    assert len(concurrent) == 1
    assert concurrent[0].notation == "IN -> A -> [ B || C ] -> OUT_X4 -> OUT_X5"
    assert set(concurrent[0].nodes) == {"IN", "A", "B", "C", "OUT_X4", "OUT_X5"}


def test_find_concurrent_paths_for_join_example():
    project = _example_project("join.json")
    graph = project.entry()

    concurrent = find_concurrent_paths(graph, PathFindingOptions(), project=project)

    assert len(concurrent) == 1
    assert concurrent[0].notation == "IN -> Split -> [ L || R ] -> Combine -> OUT"
    assert concurrent[0].nodes == ["IN", "Split", "L", "R", "Combine", "OUT"]


def test_find_concurrent_paths_for_sync_multi_start():
    project = _example_project("data_store.json")
    graph = project.entry()

    concurrent = find_concurrent_paths(graph, PathFindingOptions(), project=project)

    assert len(concurrent) == 1
    assert concurrent[0].notation == "[ IN || PROFILE_STORE ] -> BuildResponse -> OUT"
    assert concurrent[0].nodes == ["IN", "PROFILE_STORE", "BuildResponse", "OUT"]
    assert "PARALLEL BRANCHES" in "\n".join(
        format_tree_lines(concurrent[0].root, title="Scenario 1")
    )


def _example_project(example_name: str):
    return parse_project((ROOT / "examples" / example_name).read_text(encoding="utf-8"), "json")
