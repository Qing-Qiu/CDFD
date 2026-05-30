import pytest

from cdfd.parsers import ParseError, parse_cdfd


def test_parse_json_graph():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["C"],
          "nodes": ["A", "B", "C"],
          "edges": [
            {"from": "A", "to": "B"},
            {"from": "B", "to": "C", "condition": "ok"}
          ]
        }
        """,
        "json",
    )

    assert graph.start == "A"
    assert graph.ends == {"C"}
    assert len(graph.edges) == 2
    assert graph.edges[1].condition == "ok"


def test_parse_yaml_graph():
    graph = parse_cdfd(
        """
        start: A
        ends: [D]
        nodes:
          - A
          - B
          - D
        edges:
          - from: A
            to: B
          - from: B
            to: D
        """,
        "yaml",
    )

    assert set(graph.nodes) == {"A", "B", "D"}
    assert graph.edges[0].id == "e1"


def test_parse_csv_edge_list_requires_cli_start_and_end():
    graph = parse_cdfd(
        "from,to,condition\nA,B,\nB,C,done\n",
        "csv",
        start="A",
        ends=["C"],
    )

    assert graph.start == "A"
    assert graph.ends == {"C"}
    assert set(graph.nodes) == {"A", "B", "C"}


def test_parse_rejects_missing_edge_node():
    with pytest.raises(ParseError):
        parse_cdfd(
            """
            {
              "start": "A",
              "ends": ["C"],
              "nodes": ["A", "C"],
              "edges": [{"from": "A", "to": "B"}]
            }
            """,
            "json",
        )
