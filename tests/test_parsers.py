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
            {"from": "B", "to": "C", "data": ["x1"], "condition": "ok"}
          ]
        }
        """,
        "json",
    )

    assert graph.start == "A"
    assert graph.ends == {"C"}
    assert len(graph.edges) == 2
    assert graph.edges[1].data == ["x1"]
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


def test_parse_csv_edge_list_infers_start_and_end_when_unambiguous():
    graph = parse_cdfd(
        "from,to,condition\nA,B,\nB,C,done\n",
        "csv",
    )

    assert graph.start == "A"
    assert graph.ends == {"C"}


def test_parse_json_graph_infers_start_and_ends_when_omitted():
    graph = parse_cdfd(
        """
        {
          "nodes": ["A", "B", "C", "D"],
          "edges": [
            {"from": "A", "to": "B"},
            {"from": "A", "to": "C"},
            {"from": "B", "to": "D"},
            {"from": "C", "to": "D"}
          ]
        }
        """,
        "json",
    )

    assert graph.start == "A"
    assert graph.ends == {"D"}


def test_parse_requires_start_when_auto_detection_is_ambiguous():
    with pytest.raises(ParseError, match="multiple candidates"):
        parse_cdfd(
            "from,to\nA,C\nB,C\n",
            "csv",
        )


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
