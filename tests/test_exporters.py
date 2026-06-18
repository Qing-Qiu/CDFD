import json
import re
from pathlib import Path

from cdfd.exporters import export_analysis, export_paths, render_svg
from cdfd.models import PathRelation
from cdfd.parsers import parse_cdfd, parse_project
from cdfd.path_finder import PathFindingOptions, find_concurrent_paths, find_paths
from cdfd.path_groups import build_path_relations


ROOT = Path(__file__).resolve().parents[1]


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

    assert json.loads(json_output)[0]["id"] == "P1"
    assert json.loads(json_output)[0]["source"] == "A"
    assert json.loads(json_output)[0]["sink"] == "B"
    assert json.loads(json_output)[0]["route"] == "A -> B"
    assert json.loads(json_output)[0]["nodes"] == ["A", "B"]
    assert "P1,A -> B,e1,," in csv_output


def test_export_analysis_includes_path_relations_in_json():
    graph = parse_cdfd(
        """
        {
          "start": "IN",
          "ends": ["O1", "O2"],
          "nodes": ["IN", "A", "B", "C", "O1", "O2"],
          "edges": [
            {"from": "IN", "to": "A", "data": ["x1"]},
            {"from": "A", "to": "B", "data": ["x2"]},
            {"from": "A", "to": "C", "data": ["x3"]},
            {"from": "B", "to": "O1", "data": ["x4"]},
            {"from": "C", "to": "O2", "data": ["x5"]}
          ]
        }
        """,
        "json",
    )
    paths = find_paths(graph)

    output = json.loads(export_analysis(paths, build_path_relations(paths), "json"))

    assert output["paths"][0]["id"] == "P1"
    assert output["paths"][0]["source"] == "IN"
    assert output["paths"][0]["sink"] == "O1"
    assert output["paths"][0]["nodes"] == ["IN", "A", "B", "O1"]
    assert output["path_relations"][0]["kind"] == "parallel"


def test_export_analysis_can_include_concurrent_paths():
    project = parse_project((ROOT / "examples" / "join.json").read_text(encoding="utf-8"), "json")
    graph = project.entry()
    paths = find_paths(graph, project=project)
    relations = build_path_relations(paths, project=project, graph=graph, graph_name=project.entry_graph)
    concurrent = find_concurrent_paths(graph, PathFindingOptions(), project=project)

    output = json.loads(export_analysis(paths, relations, "json", concurrent_paths=concurrent))
    text = export_analysis(paths, relations, "text", concurrent_paths=concurrent)

    assert output["concurrent_paths"][0]["notation"] == "IN -> Split -> [ L || R ] -> Combine -> OUT"
    assert "Concurrent Paths:" in text
    assert "CP1: IN -> Split -> [ L || R ] -> Combine -> OUT" in text


def test_markdown_relations_use_semantic_symbols_for_relation_kinds():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["B", "C"],
          "nodes": ["A", "B", "C"],
          "edges": [
            {"id": "e1", "from": "A", "to": "B"},
            {"id": "e2", "from": "A", "to": "C"}
          ]
        }
        """,
        "json",
    )
    paths = find_paths(graph)
    relations = [
        PathRelation(id="R1", kind="exclusive", path_ids=["P1", "P2"]),
        PathRelation(id="R2", kind="parallel", path_ids=["P1", "P2"]),
    ]

    markdown = export_analysis(paths, relations, "markdown")

    assert "| R1 | exclusive | P1 XOR P2 |" in markdown
    assert "| R2 | parallel | P1 || P2 |" in markdown


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
    assert "#b45309" not in svg
    assert "arrow-highlight" not in svg


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

    assert 'class="control-flow"' in svg
    assert 'stroke-dasharray="1 5"' in svg
    assert "s1 == 1" in svg


def test_render_svg_uses_sofl_node_symbols():
    graph = parse_cdfd(
        """
        {
          "start": "A",
          "ends": ["D"],
          "nodes": [
            {"id": "A", "type": "process"},
            {"id": "STORE", "type": "data_store"},
            {"id": "C", "type": "single_condition"},
            {"id": "D", "type": "process"}
          ],
          "edges": [
            {"id": "e1", "from": "A", "to": "STORE"},
            {"id": "e2", "from": "STORE", "to": "C"},
            {"id": "e3", "from": "C", "to": "D"}
          ]
        }
        """,
        "json",
    )

    svg = render_svg(graph)

    assert 'data-node-shape="process"' in svg
    assert 'data-node-shape="data-store"' in svg
    assert 'data-node-shape="condition"' in svg
    assert 'id="sofl-grid"' in svg
    assert "<polygon" in svg
    assert svg.count('class="sofl-process-band"') == 4
    assert svg.count('class="sofl-process-port-rail"') == 4
    assert '<rect class="sofl-process-boundary"' in svg


def test_render_svg_draws_sofl_process_port_dividers_from_xml_counts():
    project = parse_project(
        """
        <CDFD module="ports">
          <componentList>
            <process name="P" inputPorts="2" outputPorts="3" x="10" y="20" width="120" height="80" shapeIndex="0" />
            <process name="Q" inputPorts="1" outputPorts="1" x="200" y="20" width="120" height="80" shapeIndex="1" />
          </componentList>
          <connectionList>
            <activeDataFlow name="x" fromX="130" fromY="60" toX="200" toY="60">
              <from belongToName="P" belongToType="Process" belongToConnector="0" shapeIndex="0" />
              <to belongToName="Q" belongToType="Process" belongToConnector="0" shapeIndex="1" />
            </activeDataFlow>
          </connectionList>
        </CDFD>
        """,
        "cdfd",
    )

    svg = render_svg(project.entry())

    assert svg.count('class="sofl-process-input-port-divider"') == 1
    assert svg.count('class="sofl-process-output-port-divider"') == 2


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


def test_render_svg_uses_sofl_saved_component_layout():
    project = parse_project((ROOT / "examples" / "xuexitong.cdfd").read_text(encoding="utf-8"), "cdfd")

    svg = render_svg(project.entry())
    user_login = _rect_position(svg, "userLogin")
    course_db = _rect_position(svg, "course_db")

    assert user_login == (375, 264)
    assert course_db == (710, 60)
    assert 'M477,180 L465,265' in svg
    assert 'class="control-flow" data-edge-id="control_data_flow_1" d="M232,296 L375,294"' in svg
    assert 'class="control-flow" data-edge-id="control_data_flow_2" d="M235,340 L375,336"' in svg
    assert "#b45309" not in svg


def test_render_svg_hides_inferred_sofl_external_endpoint_nodes():
    project = parse_project((ROOT / "examples" / "duoshuru.cdfd").read_text(encoding="utf-8"), "cdfd")

    svg = render_svg(project.entry())

    assert 'data-node-id="IN_userAccount"' not in svg
    assert 'data-node-id="IN_passWord"' not in svg
    assert 'data-node-id="IN_submissionRequest"' not in svg
    assert "userAccount" in svg
    assert "passWord" in svg
    assert "submissionRequest" in svg
    assert svg.count("C1:") == 1


def test_render_svg_preserves_compact_sofl_symbol_sizes():
    project = parse_project((ROOT / "examples" / "duoshuru.cdfd").read_text(encoding="utf-8"), "cdfd")

    svg = render_svg(project.entry())

    assert 'points="1415,246 1440,246 1452,236 1452,286 1440,276 1415,276"' in svg
    assert 'data-edge-id="active_data_flow_14" d="M1452,261 L1524,142"' in svg


def test_render_svg_draws_sofl_merging_before_edges():
    project = parse_project(
        """
        <CDFD module="merge_demo">
          <componentList>
            <process name="A" inputPorts="1" outputPorts="1" x="10" y="20" width="100" height="50" shapeIndex="0" />
            <process name="B" inputPorts="1" outputPorts="1" x="10" y="100" width="100" height="50" shapeIndex="1" />
            <merging x="160" y="55" width="37" height="50" shapeIndex="2" />
            <process name="C" inputPorts="1" outputPorts="1" x="240" y="60" width="100" height="50" shapeIndex="3" />
          </componentList>
          <connectionList>
            <activeDataFlow name="r1" fromX="110" fromY="45" toX="160" toY="70">
              <from belongToName="A" belongToType="Process" belongToConnector="0" shapeIndex="0" />
              <to belongToName="" belongToType="Merging" belongToConnector="0" shapeIndex="2" />
            </activeDataFlow>
            <activeDataFlow name="r2" fromX="110" fromY="125" toX="160" toY="92">
              <from belongToName="B" belongToType="Process" belongToConnector="0" shapeIndex="1" />
              <to belongToName="" belongToType="Merging" belongToConnector="1" shapeIndex="2" />
            </activeDataFlow>
            <activeDataFlow name="" fromX="197" fromY="80" toX="240" toY="85">
              <from belongToName="" belongToType="Merging" belongToConnector="0" shapeIndex="2" />
              <to belongToName="C" belongToType="Process" belongToConnector="0" shapeIndex="3" />
            </activeDataFlow>
          </connectionList>
        </CDFD>
        """,
        "cdfd",
    )

    svg = render_svg(project.entry())

    assert 'class="sofl-node sofl-merging"' in svg
    assert 'data-node-id="merging_2"' in svg
    assert svg.index('class="sofl-node sofl-merging"') < svg.index('data-edge-id="active_data_flow_1"')


def _rect_position(svg: str, node_id: str) -> tuple[int, int]:
    match = re.search(rf'data-node-id="{node_id}" x="(?P<x>\d+)" y="(?P<y>\d+)"', svg)
    assert match is not None
    return int(match.group("x")), int(match.group("y"))
