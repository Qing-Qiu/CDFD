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


def test_json_process_ports_define_mutually_exclusive_input_alternatives():
    project = parse_project(
        """
        {
          "schema_version": "cdfd-json-v1",
          "module": {
            "name": "PortExample",
            "var": ["userAccount", "passWord", "token", "loginResult"],
            "behav": "Top"
          },
          "processes": [
            {
              "id": "Login",
              "input_ports": [
                { "id": "password", "data": ["userAccount", "passWord"] },
                { "id": "token", "data": ["token"] }
              ],
              "output_ports": [
                { "id": "result", "data": ["loginResult"] }
              ],
              "outputs": ["loginResult"]
            }
          ],
          "graphs": {
            "Top": {
              "starts": ["IN_USER", "IN_PASS", "IN_TOKEN"],
              "ends": ["OUT"],
              "nodes": [
                { "id": "IN_USER", "type": "external" },
                { "id": "IN_PASS", "type": "external" },
                { "id": "IN_TOKEN", "type": "external" },
                { "id": "Login", "type": "process" },
                { "id": "OUT", "type": "external" }
              ],
              "edges": [
                { "id": "e1", "from": "IN_USER", "to": "Login", "data": ["userAccount"] },
                { "id": "e2", "from": "IN_PASS", "to": "Login", "data": ["passWord"] },
                { "id": "e3", "from": "IN_TOKEN", "to": "Login", "data": ["token"] },
                { "id": "e4", "from": "Login", "to": "OUT", "data": ["loginResult"] }
              ]
            }
          }
        }
        """,
        "json",
    )
    graph = project.entry()

    port_groups, _ = graph.get_node_input_port_groups("Login", project.processes)
    assert len(port_groups) == 2
    assert {edge.id for edge in port_groups[0]} == {"e1", "e2"}
    assert {edge.id for edge in port_groups[1]} == {"e3"}

    assert can_activate_node(
        graph,
        "Login",
        {"token"},
        project.processes,
        activated_nodes={"IN_TOKEN"},
    )
    assert can_activate_node(
        graph,
        "Login",
        {"userAccount", "passWord"},
        project.processes,
        activated_nodes={"IN_USER", "IN_PASS"},
    )
    assert not can_activate_node(
        graph,
        "Login",
        {"passWord"},
        project.processes,
        activated_nodes={"IN_PASS"},
    )

    from cdfd.multilevel import find_project_paths

    paths = find_project_paths(project, PathFindingOptions(max_paths=20))
    assert [path.data for path in paths] == [
        ["token", "loginResult"],
        ["userAccount", "passWord", "loginResult"],
    ]

    from cdfd.consistency import inspect_project_consistency

    assert inspect_project_consistency(project) == []


def test_json_process_output_ports_are_choices_unless_parallel_is_explicit():
    project = parse_project(
        """
        {
          "schema_version": "cdfd-json-v1",
          "module": {
            "name": "OutputPortExample",
            "var": ["x", "left", "right"],
            "behav": "Top"
          },
          "processes": [
            {
              "id": "Split",
              "inputs": ["x"],
              "output_ports": [
                { "id": "left_port", "data": ["left"] },
                { "id": "right_port", "data": ["right"] }
              ]
            }
          ],
          "graphs": {
            "Top": {
              "start": "IN",
              "ends": ["OUT_L", "OUT_R"],
              "nodes": ["IN", "Split", "L", "R", "OUT_L", "OUT_R"],
              "edges": [
                { "id": "e1", "from": "IN", "to": "Split", "data": ["x"] },
                { "id": "e2", "from": "Split", "to": "L", "data": ["left"] },
                { "id": "e3", "from": "Split", "to": "R", "data": ["right"] },
                { "id": "e4", "from": "L", "to": "OUT_L", "data": ["left"] },
                { "id": "e5", "from": "R", "to": "OUT_R", "data": ["right"] }
              ]
            }
          }
        }
        """,
        "json",
    )

    concurrent = find_concurrent_paths(project.entry(), PathFindingOptions(), project=project)
    assert [item.notation for item in concurrent] == [
        "IN -> Split -> L -> OUT_L",
        "IN -> Split -> R -> OUT_R",
    ]


def test_json_process_edges_on_same_output_port_can_fork_together():
    project = parse_project(
        """
        {
          "schema_version": "cdfd-json-v1",
          "module": {
            "name": "SameOutputPortExample",
            "var": ["x", "left", "right", "l_done", "r_done", "combined", "error"],
            "behav": "Top"
          },
          "processes": [
            {
              "id": "Split",
              "inputs": ["x"],
              "output_ports": [
                { "id": "success", "edges": ["e2", "e3"], "data": ["left", "right"] },
                { "id": "error", "data": ["error"] }
              ]
            },
            { "id": "Combine", "inputs": ["l_done", "r_done"], "outputs": ["combined"] }
          ],
          "graphs": {
            "Top": {
              "start": "IN",
              "ends": ["OUT"],
              "nodes": ["IN", "Split", "L", "R", "Combine", "OUT"],
              "edges": [
                { "id": "e1", "from": "IN", "to": "Split", "data": ["x"] },
                { "id": "e2", "from": "Split", "to": "L", "data": ["left"] },
                { "id": "e3", "from": "Split", "to": "R", "data": ["right"] },
                { "id": "e4", "from": "L", "to": "Combine", "data": ["l_done"] },
                { "id": "e5", "from": "R", "to": "Combine", "data": ["r_done"] },
                { "id": "e6", "from": "Combine", "to": "OUT", "data": ["combined"] }
              ]
            }
          }
        }
        """,
        "json",
    )

    concurrent = find_concurrent_paths(project.entry(), PathFindingOptions(), project=project)

    assert [item.notation for item in concurrent] == [
        "IN -> Split -> [ L || R ] -> Combine -> OUT",
    ]


def test_json_input_port_mode_any_accepts_one_ready_edge():
    project = parse_project(
        """
        {
          "schema_version": "cdfd-json-v1",
          "module": {
            "name": "AnyPortExample",
            "var": ["email", "phone", "result"],
            "behav": "Top"
          },
          "processes": [
            {
              "id": "Recover",
              "input_ports": [
                { "id": "contact", "data": ["email", "phone"], "mode": "any" }
              ],
              "outputs": ["result"]
            }
          ],
          "graphs": {
            "Top": {
              "starts": ["IN_EMAIL", "IN_PHONE"],
              "ends": ["OUT"],
              "nodes": ["IN_EMAIL", "IN_PHONE", "Recover", "OUT"],
              "edges": [
                { "id": "e1", "from": "IN_EMAIL", "to": "Recover", "data": ["email"] },
                { "id": "e2", "from": "IN_PHONE", "to": "Recover", "data": ["phone"] },
                { "id": "e3", "from": "Recover", "to": "OUT", "data": ["result"] }
              ]
            }
          }
        }
        """,
        "json",
    )
    graph = project.entry()

    assert can_activate_node(
        graph,
        "Recover",
        {"email"},
        project.processes,
        activated_nodes={"IN_EMAIL"},
    )
    assert can_activate_node(
        graph,
        "Recover",
        {"phone"},
        project.processes,
        activated_nodes={"IN_PHONE"},
    )


def test_concurrent_notation_collapses_repeated_join_nodes():
    project = parse_project((ROOT / "examples" / "duoshuru.cdfd").read_text(encoding="utf-8"), "cdfd")

    concurrent = find_concurrent_paths(project.entry(), PathFindingOptions(max_paths=50), project=project)

    assert all(
        "P9:汇总判题结果 -> P9:汇总判题结果" not in (item.notation or "")
        for item in concurrent
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
