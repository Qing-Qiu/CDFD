from cdfd.parsers import parse_cdfd
from cdfd.path_finder import PathFindingOptions, detect_cycles, find_paths


def test_branch_graph_generates_all_simple_paths():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["D"],
          "nodes": ["A", "B", "C", "D"],
          "edges": [
            {"id": "e1", "from": "A", "to": "B"},
            {"id": "e2", "from": "A", "to": "C"},
            {"id": "e3", "from": "B", "to": "D", "data": ["x2"], "condition": "yes"},
            {"id": "e4", "from": "C", "to": "D", "data": ["x3"], "condition": "no"}
          ]
        }
        """,
        "json",
    )

    paths = find_paths(graph)

    assert [path.nodes for path in paths] == [["A", "B", "D"], ["A", "C", "D"]]
    assert paths[0].data == ["x2"]
    assert paths[1].data == ["x3"]
    assert paths[0].conditions == ["yes"]
    assert paths[1].conditions == ["no"]


def test_control_edges_annotate_paths_without_becoming_path_segments():
    graph = parse_cdfd(
        """
        {
          "nodes": [
            {"id": "IN", "type": "external"},
            {"id": "S1", "type": "state"},
            {"id": "A", "type": "process"},
            {"id": "OUT", "type": "external"}
          ],
          "edges": [
            {"id": "e1", "from": "IN", "to": "A", "data": ["x1"]},
            {"id": "c1", "from": "S1", "to": "A", "kind": "control", "condition": "s1 == 1"},
            {"id": "e2", "from": "A", "to": "OUT", "data": ["x2"]}
          ]
        }
        """,
        "json",
    )

    paths = find_paths(graph)

    assert [path.nodes for path in paths] == [["IN", "A", "OUT"]]
    assert paths[0].edges == ["e1", "e2"]
    assert paths[0].data == ["x1", "x2"]
    assert paths[0].conditions == ["s1 == 1"]


def test_control_edges_on_explicit_start_annotate_paths():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["OUT"],
          "nodes": [
            {"id": "S1", "type": "state"},
            {"id": "A", "type": "process"},
            {"id": "OUT", "type": "external"}
          ],
          "edges": [
            {"id": "c1", "from": "S1", "to": "A", "kind": "control", "condition": "s1 == 1"},
            {"id": "e1", "from": "A", "to": "OUT", "data": ["x1"]}
          ]
        }
        """,
        "json",
    )

    paths = find_paths(graph)

    assert paths[0].nodes == ["A", "OUT"]
    assert paths[0].edges == ["e1"]
    assert paths[0].conditions == ["s1 == 1"]


def test_simple_strategy_keeps_cycle_results_finite():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["C"],
          "nodes": ["A", "B", "C"],
          "edges": [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "A"},
            {"from": "B", "to": "C"}
          ]
        }
        """,
        "json",
    )

    paths = find_paths(graph, PathFindingOptions(strategy="simple"))

    assert [path.nodes for path in paths] == [["A", "B", "C"]]
    assert detect_cycles(graph) == [["A", "B", "A"]]


def test_control_edges_do_not_create_path_cycles():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["OUT"],
          "nodes": ["A", "B", "OUT"],
          "edges": [
            {"id": "e1", "from": "A", "to": "B"},
            {"id": "c1", "from": "B", "to": "A", "kind": "control", "condition": "ready"},
            {"id": "e2", "from": "B", "to": "OUT"}
          ]
        }
        """,
        "json",
    )

    assert detect_cycles(graph) == []


def test_max_depth_strategy_allows_bounded_revisits():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["C"],
          "nodes": ["A", "B", "C"],
          "edges": [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "A"},
            {"from": "B", "to": "C"}
          ]
        }
        """,
        "json",
    )

    paths = find_paths(graph, PathFindingOptions(strategy="max-depth", max_depth=4))

    assert [path.nodes for path in paths] == [["A", "B", "C"], ["A", "B", "A", "B", "C"]]
