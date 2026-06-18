import pytest
from pathlib import Path

from cdfd.multilevel import find_project_paths
from cdfd.parsers import ParseError, infer_format, parse_cdfd, parse_project
from cdfd.path_groups import build_path_relations


ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize("input_format", ["yaml", "yml", "csv"])
def test_parse_rejects_removed_input_formats(input_format):
    with pytest.raises(ParseError, match="Unsupported input format"):
        parse_cdfd("content", input_format)


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


def test_parse_infers_start_and_end_from_data_flow_edges_only():
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
            {"id": "c1", "from": "S1", "to": "A", "kind": "Control", "condition": "s1 == 1"},
            {"id": "e2", "from": "A", "to": "OUT", "data": ["x2"]}
          ]
        }
        """,
        "json",
    )

    assert graph.starts == {"IN"}
    assert graph.start == "IN"
    assert graph.ends == {"OUT"}
    assert graph.edges[1].kind == "control"


def test_parse_project_rejects_json_missing_schema_version():
    with pytest.raises(ParseError, match="schema_version"):
        parse_project(
            """
            {
              "module": {"behav": "Top"},
              "processes": [],
              "graphs": {
                "Top": {
                  "start": "A",
                  "ends": ["B"],
                  "nodes": ["A", "B"],
                  "edges": [{"from": "A", "to": "B"}]
                }
              }
            }
            """,
            "json",
        )


def test_parse_project_rejects_invalid_structure_kind_before_path_generation():
    with pytest.raises(ParseError, match=r"\$\.graphs\.Top\.structures\.0\.kind"):
        parse_project(
            """
            {
              "schema_version": "cdfd-json-v1",
              "module": {"behav": "Top"},
              "processes": [],
              "graphs": {
                "Top": {
                  "start": "A",
                  "ends": ["B", "C"],
                  "nodes": ["A", "B", "C"],
                  "edges": [
                    {"id": "e1", "from": "A", "to": "B"},
                    {"id": "e2", "from": "A", "to": "C"}
                  ],
                  "structures": [
                    {
                      "id": "bad",
                      "kind": "maybe-parallel",
                      "branches": [
                        {"id": "left", "edges": ["e1"]},
                        {"id": "right", "edges": ["e2"]}
                      ]
                    }
                  ]
                }
              }
            }
            """,
            "json",
        )


def test_parse_json_graph_with_explicit_structures():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["D", "E"],
          "nodes": ["A", "B", "C", "D", "E"],
          "edges": [
            {"id": "e1", "from": "A", "to": "B"},
            {"id": "e2", "from": "A", "to": "C"},
            {"id": "e3", "from": "B", "to": "D"},
            {"id": "e4", "from": "C", "to": "E"}
          ],
          "structures": [
            {
              "id": "par_A",
              "kind": "parallel",
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

    assert graph.structures[0].id == "par_A"
    assert graph.structures[0].kind == "parallel"
    assert graph.structures[0].branches[1].edges == ["e2", "e4"]


def test_parse_infers_multiple_starts_when_sources_are_unambiguous():
    graph = parse_cdfd(
        """
        {
          "nodes": ["A", "B", "C"],
          "edges": [
            {"from": "A", "to": "C"},
            {"from": "B", "to": "C"}
          ]
        }
        """,
        "json",
    )

    assert graph.starts == {"A", "B"}
    assert graph.start == "A"
    assert graph.ends == {"C"}


def test_parse_rejects_structure_referencing_missing_edge():
    with pytest.raises(ParseError, match="missing edge"):
        parse_cdfd(
            """
            {
              "start": "A",
              "ends": ["B"],
              "nodes": ["A", "B"],
              "edges": [{"id": "e1", "from": "A", "to": "B"}],
              "structures": [
                {
                  "id": "bad",
                  "kind": "parallel",
                  "branches": [{"id": "broken", "edges": ["missing"]}]
                }
              ]
            }
            """,
            "json",
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


def test_infer_format_accepts_sofl_cdfd_files():
    assert infer_format("model.cdfd") == "cdfd"


def test_parse_sofl_cdfd_records_process_output_ports():
    project = parse_project(
        """
        <CDFD module="ports">
          <componentList>
            <process name="A" inputPorts="1" outputPorts="2" x="10" y="20" width="120" height="80" shapeIndex="0" />
            <process name="B" inputPorts="1" outputPorts="1" x="200" y="10" width="120" height="60" shapeIndex="1" />
            <process name="C" inputPorts="1" outputPorts="1" x="200" y="110" width="120" height="60" shapeIndex="2" />
          </componentList>
          <connectionList>
            <activeDataFlow name="x" fromX="130" fromY="46" toX="200" toY="40">
              <from belongToName="A" belongToType="Process" belongToConnector="0" shapeIndex="0" />
              <to belongToName="B" belongToType="Process" belongToConnector="0" shapeIndex="1" />
            </activeDataFlow>
            <activeDataFlow name="y" fromX="130" fromY="74" toX="200" toY="140">
              <from belongToName="A" belongToType="Process" belongToConnector="1" shapeIndex="0" />
              <to belongToName="C" belongToType="Process" belongToConnector="0" shapeIndex="2" />
            </activeDataFlow>
          </connectionList>
        </CDFD>
        """,
        "cdfd",
    )

    graph = project.entry()
    by_data = {edge.data[0]: edge for edge in graph.edges}

    assert project.processes["A"].metadata["output_port_count"] == 2
    assert by_data["x"].metadata["output_port"] == 0
    assert by_data["y"].metadata["output_port"] == 1


@pytest.mark.parametrize("filename", ["model.yaml", "model.yml", "model.csv"])
def test_infer_format_rejects_removed_input_extensions(filename):
    with pytest.raises(ParseError, match="Cannot infer input format"):
        infer_format(filename)


def test_parse_sofl_cdfd_xml_project_generates_paths():
    project = parse_project((ROOT / "examples" / "xuexitong.cdfd").read_text(encoding="utf-8"), "cdfd")
    graph = project.entry()

    assert project.entry_graph == "xuexitong"
    assert graph.starts == {"course_db", "user_db"}
    assert graph.ends == {"homework_db", "查看我的课程"}
    assert graph.nodes["single_condition_5"].type == "single_condition"
    assert graph.edges[2].kind == "active-flow"
    assert graph.edges[3].source == "single_condition_5"
    assert graph.edges[3].target == "查看我的课程"
    assert graph.edges[3].condition == "账号密码正确"

    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)

    assert [path.nodes for path in paths] == [
        ["course_db", "查看我的课程"],
        ["user_db", "userLogin", "single_condition_5", "查看我的课程"],
        ["user_db", "userLogin", "single_condition_5", "修改作业", "homework_db"],
        ["user_db", "userLogin", "single_condition_5", "提交作业", "homework_db"],
    ]
    assert paths[1].conditions == ["userAccount", "passWord", "账号密码正确"]
    assert [(relation.kind, relation.path_ids, relation.structure_id) for relation in relations] == [
        ("exclusive", ["P2", "P4", "P3"], "condition_single_condition_5")
    ]
