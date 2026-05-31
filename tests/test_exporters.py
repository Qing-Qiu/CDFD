import json

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
