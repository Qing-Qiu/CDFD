from cdfd.parsers import parse_cdfd
from cdfd.path_finder import find_paths
from cdfd.path_groups import build_path_groups


def test_builds_joined_output_group_for_converging_branches():
    graph = parse_cdfd(
        """
        {
          "start": "IN",
          "ends": ["OUT"],
          "nodes": ["IN", "A", "B", "C", "J", "OUT"],
          "edges": [
            {"from": "IN", "to": "A", "data": ["x1"]},
            {"from": "A", "to": "B", "data": ["x2"]},
            {"from": "A", "to": "C", "data": ["x3"]},
            {"from": "B", "to": "J", "data": ["x4"]},
            {"from": "C", "to": "J", "data": ["x5"]},
            {"from": "J", "to": "OUT", "data": ["x6"]}
          ]
        }
        """,
        "json",
    )

    groups = build_path_groups(find_paths(graph))

    joined = [group for group in groups if group.kind == "joined-output"]
    assert len(joined) == 1
    assert joined[0].path_ids == ["P1", "P2"]
    assert joined[0].outputs == ["x6"]
    assert joined[0].shared_prefix == ["IN", "A"]


def test_builds_parallel_group_for_disjoint_output_paths():
    graph = parse_cdfd(
        """
        {
          "start": "IN",
          "ends": ["OUT_X4", "OUT_X5"],
          "nodes": ["IN", "A", "B", "C", "OUT_X4", "OUT_X5"],
          "edges": [
            {"from": "IN", "to": "A", "data": ["x1"]},
            {"from": "A", "to": "B", "data": ["x2"]},
            {"from": "A", "to": "C", "data": ["x3"]},
            {"from": "B", "to": "OUT_X4", "data": ["x4"]},
            {"from": "C", "to": "OUT_X5", "data": ["x5"]}
          ]
        }
        """,
        "json",
    )

    groups = build_path_groups(find_paths(graph))

    parallel = [group for group in groups if group.kind == "parallel"]
    assert len(parallel) == 1
    assert parallel[0].path_ids == ["P1", "P2"]
    assert parallel[0].outputs == ["x4", "x5"]
    assert parallel[0].shared_prefix == ["IN", "A"]


def test_does_not_group_mutually_conditioned_alternatives_as_joined_output():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["D"],
          "nodes": ["A", "B", "C", "D"],
          "edges": [
            {"from": "A", "to": "B", "condition": "mode == left"},
            {"from": "A", "to": "C", "condition": "mode == right"},
            {"from": "B", "to": "D", "data": ["x"]},
            {"from": "C", "to": "D", "data": ["x"]}
          ]
        }
        """,
        "json",
    )

    groups = build_path_groups(find_paths(graph))

    assert not groups
