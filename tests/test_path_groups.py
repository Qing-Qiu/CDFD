from cdfd.parsers import parse_cdfd
from cdfd.path_finder import find_paths
from cdfd.path_groups import build_path_relations


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

    groups = build_path_relations(find_paths(graph))

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

    groups = build_path_relations(find_paths(graph))

    parallel = [group for group in groups if group.kind == "parallel"]
    assert len(parallel) == 1
    assert parallel[0].path_ids == ["P1", "P2"]
    assert parallel[0].outputs == ["x4", "x5"]
    assert parallel[0].shared_prefix == ["IN", "A"]


def test_infers_one_parallel_relation_for_three_independent_branches():
    graph = parse_cdfd(
        """
        {
          "start": "IN",
          "ends": ["O1", "O2", "O3"],
          "nodes": ["IN", "A", "B", "C", "D", "O1", "O2", "O3"],
          "edges": [
            {"from": "IN", "to": "A", "data": ["x"]},
            {"from": "A", "to": "B", "data": ["x1"]},
            {"from": "A", "to": "C", "data": ["x2"]},
            {"from": "A", "to": "D", "data": ["x3"]},
            {"from": "B", "to": "O1", "data": ["y1"]},
            {"from": "C", "to": "O2", "data": ["y2"]},
            {"from": "D", "to": "O3", "data": ["y3"]}
          ]
        }
        """,
        "json",
    )

    relations = build_path_relations(find_paths(graph))

    parallel = [relation for relation in relations if relation.kind == "parallel"]
    assert len(parallel) == 1
    assert parallel[0].path_ids == ["P1", "P2", "P3"]
    assert parallel[0].title == "3 paths can run in parallel"
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

    groups = build_path_relations(find_paths(graph))

    assert not groups


def test_explicit_parallel_structure_generates_parallel_relation():
    graph = parse_cdfd(
        """
        {
          "schema_version": "cdfd-json-v1",
          "start": "IN",
          "ends": ["O1", "O2"],
          "nodes": ["IN", "A", "B", "C", "O1", "O2"],
          "edges": [
            {"id": "e1", "from": "IN", "to": "A", "data": ["x1"]},
            {"id": "e2", "from": "A", "to": "B", "data": ["x2"]},
            {"id": "e3", "from": "A", "to": "C", "data": ["x3"]},
            {"id": "e4", "from": "B", "to": "O1", "data": ["x4"]},
            {"id": "e5", "from": "C", "to": "O2", "data": ["x5"]}
          ],
          "structures": [
            {
              "id": "par_A",
              "kind": "parallel",
              "source": "A",
              "branches": [
                {"id": "left", "edges": ["e2", "e4"]},
                {"id": "right", "edges": ["e3", "e5"]}
              ]
            }
          ]
        }
        """,
        "json",
    )

    relations = build_path_relations(find_paths(graph), graph=graph)

    assert relations[0].kind == "parallel"
    assert relations[0].structure_id == "par_A"
    assert relations[0].branch_ids == ["left", "right"]
    assert relations[0].path_ids == ["P1", "P2"]


def test_explicit_choice_structure_suppresses_inferred_parallel_relation():
    graph = parse_cdfd(
        """
        {
          "schema_version": "cdfd-json-v1",
          "start": "A",
          "ends": ["O1", "O2"],
          "nodes": ["A", "B", "C", "O1", "O2"],
          "edges": [
            {"id": "e1", "from": "A", "to": "B", "data": ["x1"]},
            {"id": "e2", "from": "A", "to": "C", "data": ["x2"]},
            {"id": "e3", "from": "B", "to": "O1", "data": ["x3"]},
            {"id": "e4", "from": "C", "to": "O2", "data": ["x4"]}
          ],
          "structures": [
            {
              "id": "choice_A",
              "kind": "choice",
              "source": "A",
              "branches": [
                {"id": "left", "edges": ["e1", "e3"]},
                {"id": "right", "edges": ["e2", "e4"]}
              ]
            }
          ]
        }
        """,
        "json",
    )

    relations = build_path_relations(find_paths(graph), graph=graph)

    assert [relation.kind for relation in relations] == ["exclusive"]
