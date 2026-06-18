from pathlib import Path

from cdfd.flow_decomposition import collect_path_outputs, decompose_flow
from cdfd.multilevel import decompose_project_flow
from cdfd.parsers import parse_cdfd, parse_project
from cdfd.path_finder import find_concurrent_paths, find_paths
from cdfd.scenarios import build_functional_scenarios


ROOT = Path(__file__).resolve().parents[1]


def test_decompose_flow_generates_paths_to_any_sink():
    graph = parse_cdfd(
        """
        {
          "start": "IN",
          "ends": ["OUT_LEFT", "OUT_RIGHT"],
          "nodes": ["IN", "Fork", "Left", "Right", "OUT_LEFT", "OUT_RIGHT"],
          "edges": [
            {"id": "e1", "from": "IN", "to": "Fork", "data": ["x"]},
            {"id": "e2", "from": "Fork", "to": "Left", "data": ["left"]},
            {"id": "e3", "from": "Fork", "to": "Right", "data": ["right"]},
            {"id": "e4", "from": "Left", "to": "OUT_LEFT", "data": ["out_left"]},
            {"id": "e5", "from": "Right", "to": "OUT_RIGHT", "data": ["out_right"]}
          ]
        }
        """,
        "json",
    )

    result = decompose_flow(graph)

    assert sorted(path.sink or path.nodes[-1] for path in result.paths) == ["OUT_LEFT", "OUT_RIGHT"]
    assert result.flow_distribution == {"IN": {"OUT_LEFT": 1, "OUT_RIGHT": 1}}
    assert result.cycles == []


def test_collect_path_outputs_uses_metadata_and_process_spec():
    project = parse_project((ROOT / "examples" / "11_multi_output.json").read_text(encoding="utf-8"), "json")
    graph = project.entry()

    assert collect_path_outputs(graph, "OUT_RECEIPT", processes=project.processes) == ["receipt_pdf"]
    assert collect_path_outputs(graph, "OUT_INVOICE", processes=project.processes) == ["invoice_pdf"]


def test_parallel_paths_include_sink_and_outputs():
    project = parse_project((ROOT / "examples" / "11_multi_output.json").read_text(encoding="utf-8"), "json")
    paths = find_paths(project.entry(), project=project)

    assert len(paths) == 2
    assert {path.sink for path in paths} == {"OUT_RECEIPT", "OUT_INVOICE"}
    assert sorted(path.outputs[0] for path in paths) == ["invoice_pdf", "receipt_pdf"]


def test_concurrent_parallel_end_notation_and_scenario_outputs():
    project = parse_project((ROOT / "examples" / "11_multi_output.json").read_text(encoding="utf-8"), "json")
    decomposition = decompose_project_flow(project)
    concurrent = find_concurrent_paths(project.entry(), project=project)
    scenarios = build_functional_scenarios(
        decomposition.paths,
        project=project,
        concurrent_paths=concurrent,
    )

    notation = concurrent[0].notation or ""
    assert "OUT_RECEIPT" in notation and "OUT_INVOICE" in notation
    assert "||" in notation.split("->")[-1]
    assert len(scenarios) == 1
    assert scenarios[0].kind == "concurrent"
    assert set(scenarios[0].output_data) == {"receipt_pdf", "invoice_pdf"}
