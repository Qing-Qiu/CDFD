import json
import re

from cdfd.exporters import export_paths, render_svg
from cdfd.parsers import parse_cdfd
from cdfd.path_finder import find_paths


def test_export_paths_as_markdown():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["B"],
          "nodes": ["A", "B"],
          "edges": [{"from": "A", "to": "B", "data": ["x1"], "condition": "ok"}]
        }
        """,
        "json",
    )
    paths = find_paths(graph)

    markdown = export_paths(paths, "markdown")

    assert "| P1 | A -> B | x1 | - | ok |" in markdown


def test_export_paths_as_json_and_csv():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["B"],
          "nodes": ["A", "B"],
          "edges": [{"id": "e1", "from": "A", "to": "B"}]
        }
        """,
        "json",
    )
    paths = find_paths(graph)

    json_output = export_paths(paths, "json")
    csv_output = export_paths(paths, "csv")

    assert json.loads(json_output)[0]["nodes"] == ["A", "B"]
    assert "P1,A -> B,e1,," in csv_output


def test_render_svg_contains_nodes_and_edges():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["B"],
          "nodes": ["A", "B"],
          "edges": [{"id": "e1", "from": "A", "to": "B"}]
        }
        """,
        "json",
    )

    svg = render_svg(graph, find_paths(graph))

    assert "<svg" in svg
    assert "A" in svg
    assert "B" in svg


def test_render_svg_draws_control_edges_as_dashed():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["B"],
          "nodes": [
            {"id": "S1", "type": "state", "label": "1 s1"},
            "A",
            "B"
          ],
          "edges": [
            {"id": "c1", "from": "S1", "to": "A", "kind": "control", "condition": "s1 == 1"},
            {"id": "e1", "from": "A", "to": "B", "data": ["x1"]}
          ]
        }
        """,
        "json",
    )

    svg = render_svg(graph)

    assert "stroke-dasharray" in svg
    assert "s1 == 1" in svg


def test_render_svg_places_control_state_near_target():
    graph = parse_cdfd(
        """
        {
          "start": "IN",
          "ends": ["OUT"],
          "nodes": [
            {"id": "IN", "type": "external"},
            {"id": "S1", "type": "state", "label": "1 s1"},
            {"id": "A1", "type": "process"},
            {"id": "A2", "type": "process"},
            {"id": "OUT", "type": "external"}
          ],
          "edges": [
            {"id": "e0", "from": "IN", "to": "A1", "data": ["x1"]},
            {"id": "c1", "from": "S1", "to": "A1", "kind": "control", "condition": "s1 == 1"},
            {"id": "e1", "from": "A1", "to": "A2", "data": ["x2"]},
            {"id": "e2", "from": "A2", "to": "OUT", "data": ["x3"]}
          ]
        }
        """,
        "json",
    )

    svg = render_svg(graph)
    s1 = _rect_position(svg, "S1")
    a1 = _rect_position(svg, "A1")

    assert abs(s1[0] - a1[0]) <= 90
    assert s1[1] < a1[1]


def _rect_position(svg: str, node_id: str) -> tuple[int, int]:
    match = re.search(rf'data-node-id="{node_id}" x="(?P<x>\d+)" y="(?P<y>\d+)"', svg)
    assert match is not None
    return int(match.group("x")), int(match.group("y"))
