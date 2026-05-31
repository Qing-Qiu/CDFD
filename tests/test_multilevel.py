import json

import pytest

from cdfd.multilevel import find_project_paths
from cdfd.parsers import ParseError, parse_project
from cdfd.path_finder import PathFindingOptions


def test_parse_project_with_module_processes_and_graphs():
    project = parse_project(
        """
        {
          "module": {"name": "M", "behav": "Top", "type": ["int"], "var": ["x"]},
          "processes": [{"id": "A1", "pre": "x > 0", "post": "y = x", "decom": "A1_detail"}],
          "graphs": {
            "Top": {
              "start": "A1",
              "ends": ["A2"],
              "nodes": ["A1", "A2"],
              "edges": [{"id": "e1", "from": "A1", "to": "A2"}]
            },
            "A1_detail": {
              "start": "A11",
              "ends": ["A12"],
              "nodes": ["A11", "A12"],
              "edges": [{"id": "e1", "from": "A11", "to": "A12"}]
            }
          }
        }
        """,
        "json",
    )

    assert project.module is not None
    assert project.module.behav == "Top"
    assert project.module.types == ["int"]
    assert project.entry_graph == "Top"
    assert project.processes["A1"].decom == "A1_detail"


def test_multilevel_paths_expand_decomposed_processes():
    content = """
    {
      "module": {"name": "M", "behav": "Top"},
      "processes": [
        {"id": "A1", "pre": "s1 == 1", "decom": "A1_detail"},
        {"id": "A3", "decom": "A3_detail"},
        {"id": "A33", "pre": "s2 == 2", "decom": "A33_detail"}
      ],
      "graphs": {
        "Top": {
          "start": "A1",
          "ends": ["A4", "OUT_X7"],
          "nodes": ["A1", "A2", "A3", "A4", "OUT_X7"],
          "edges": [
            {"id": "e1", "from": "A1", "to": "A2", "data": ["x2"]},
            {"id": "e2", "from": "A1", "to": "A3", "data": ["x3"]},
            {"id": "e3", "from": "A2", "to": "A4", "data": ["x4"]},
            {"id": "e4", "from": "A3", "to": "A4", "data": ["x5"]},
            {"id": "e5", "from": "A3", "to": "OUT_X7", "data": ["x7"]}
          ]
        },
        "A1_detail": {
          "start": "A12",
          "ends": ["A13"],
          "nodes": ["A11", "A12", "A13"],
          "edges": [
            {"id": "e1", "from": "A12", "to": "A11", "data": ["y1"]},
            {"id": "e2", "from": "A11", "to": "A13", "data": ["y2"]}
          ]
        },
        "A3_detail": {
          "start": "A31",
          "ends": ["A32", "A33"],
          "metadata": {
            "outputs": {
              "A32": ["x5"],
              "A33": ["x7"]
            }
          },
          "nodes": ["A31", "A32", "A33"],
          "edges": [
            {"id": "e1", "from": "A31", "to": "A32", "data": ["z1"]},
            {"id": "e2", "from": "A31", "to": "A33", "data": ["z2"]}
          ]
        },
        "A33_detail": {
          "start": "A331",
          "ends": ["A332"],
          "nodes": ["A331", "A332"],
          "edges": [{"id": "e1", "from": "A331", "to": "A332", "data": ["d2"]}]
        }
      }
    }
    """
    project = parse_project(content, "json")

    paths = find_project_paths(project, PathFindingOptions(strategy="simple"))

    assert [path.nodes for path in paths] == [
        ["A12", "A11", "A13", "A2", "A4"],
        ["A12", "A11", "A13", "A31", "A32", "A4"],
        ["A12", "A11", "A13", "A31", "A331", "A332", "OUT_X7"],
    ]
    assert paths[0].edges == ["A1_detail:e1", "A1_detail:e2", "Top:e1", "Top:e3"]
    assert paths[2].data == ["y1", "y2", "x3", "z2", "d2", "x7"]
    assert paths[0].preconditions == ["A1: s1 == 1"]
    assert paths[2].preconditions == ["A1: s1 == 1", "A33: s2 == 2"]
    assert paths[2].conditions == []


def test_no_expand_keeps_top_level_processes():
    project = parse_project(
        """
        {
          "module": {"behav": "Top"},
          "processes": [{"id": "A1", "decom": "A1_detail"}],
          "graphs": {
            "Top": {
              "start": "A1",
              "ends": ["A2"],
              "nodes": ["A1", "A2"],
              "edges": [{"from": "A1", "to": "A2"}]
            },
            "A1_detail": {
              "start": "A11",
              "ends": ["A12"],
              "nodes": ["A11", "A12"],
              "edges": [{"from": "A11", "to": "A12"}]
            }
          }
        }
        """,
        "json",
    )

    paths = find_project_paths(project, expand=False)

    assert [path.nodes for path in paths] == [["A1", "A2"]]


def test_rejects_missing_decomposition_graph():
    with pytest.raises(ParseError):
        parse_project(
            json.dumps(
                {
                    "module": {"behav": "Top"},
                    "processes": [{"id": "A1", "decom": "Missing"}],
                    "graphs": {
                        "Top": {
                            "start": "A1",
                            "ends": ["A2"],
                            "nodes": ["A1", "A2"],
                            "edges": [{"from": "A1", "to": "A2"}],
                        }
                    },
                }
            ),
            "json",
        )
