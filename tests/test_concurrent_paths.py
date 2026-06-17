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


def test_or_input_ports_for_duoshuru_login():
    project = parse_project((ROOT / "examples" / "duoshuru.cdfd").read_text(encoding="utf-8"), "cdfd")
    graph = project.entry()
    p1 = "P1:用户登录认证"

    port_groups, _ = graph.get_node_input_port_groups(p1, project.processes)
    assert len(port_groups) == 2
    assert {edge.data[0] for edge in port_groups[0]} == {"passWord", "userAccount"}
    assert port_groups[1][0].data == ["token"]

    assert can_activate_node(
        graph,
        p1,
        {"token"},
        project.processes,
        activated_nodes={"user"},
    )
    assert can_activate_node(
        graph,
        p1,
        {"passWord", "userAccount"},
        project.processes,
        activated_nodes={"IN_passWord", "IN_userAccount"},
    )
    assert not can_activate_node(
        graph,
        p1,
        {"passWord"},
        project.processes,
        activated_nodes={"IN_passWord"},
    )
    assert not can_activate_node(
        graph,
        p1,
        {"token"},
        project.processes,
        activated_nodes=set(),
    )

    from cdfd.multilevel import find_project_paths

    paths = find_project_paths(project, PathFindingOptions(max_paths=50))
    login_paths = [path for path in paths if p1 in path.nodes]
    assert ["token"] in [sorted({item for item in path.data if item in {"token", "passWord", "userAccount"}}) for path in login_paths]
    assert ["passWord", "userAccount"] in [
        sorted({item for item in path.data if item in {"token", "passWord", "userAccount"}})
        for path in login_paths
    ]
    assert all(
        "passWord" not in path.data or "userAccount" in path.data or "token" in path.data
        for path in login_paths
    )


def test_sofl_late_auxiliary_inputs_do_not_start_paths():
    from cdfd.multilevel import find_project_paths

    project = parse_project((ROOT / "examples" / "duoshuru.cdfd").read_text(encoding="utf-8"), "cdfd")

    paths = find_project_paths(project, PathFindingOptions(max_paths=50))
    path_starts = {path.nodes[0] for path in paths}

    assert "D3:testSample_db" not in path_starts
    assert "IN_submissionRequest" not in path_starts


def _example_project(example_name: str):
    return parse_project((ROOT / "examples" / example_name).read_text(encoding="utf-8"), "json")
