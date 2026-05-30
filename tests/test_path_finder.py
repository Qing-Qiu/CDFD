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
            {"id": "e3", "from": "B", "to": "D", "condition": "yes"},
            {"id": "e4", "from": "C", "to": "D", "condition": "no"}
          ]
        }
        """,
        "json",
    )

    paths = find_paths(graph)

    assert [path.nodes for path in paths] == [["A", "B", "D"], ["A", "C", "D"]]
    assert paths[0].conditions == ["yes"]
    assert paths[1].conditions == ["no"]


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
