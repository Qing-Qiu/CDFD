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
          "edges": [{"from": "A", "to": "B", "condition": "ok"}]
        }
        """,
        "json",
    )
    paths = find_paths(graph)

    markdown = export_paths(paths, "markdown")

    assert "| P1 | A -> B | ok |" in markdown


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
    assert "P1,A -> B,e1," in csv_output


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
