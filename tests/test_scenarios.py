from pathlib import Path

from cdfd.exporters import export_analysis
from cdfd.multilevel import find_project_paths
from cdfd.parsers import parse_project
from cdfd.path_groups import build_path_relations
from cdfd.scenarios import build_functional_scenarios


ROOT = Path(__file__).resolve().parents[1]


def test_functional_scenarios_wrap_paths_with_process_specs():
    project = _example_project("cdfd_v1.json")
    paths = find_project_paths(project)

    scenarios = build_functional_scenarios(paths, project=project)

    assert [scenario.id for scenario in scenarios] == ["FS1", "FS2"]
    assert scenarios[0].path_ids == ["P1"]
    assert scenarios[0].source == "IN"
    assert scenarios[0].sink == "OUT_X4"
    assert scenarios[0].input_data == ["x1"]
    assert scenarios[0].output_data == ["x4"]
    assert [operation.process for operation in scenarios[0].operations] == ["A", "B"]
    assert scenarios[0].postconditions == ["x2 and x3 are derived from x1"]


def test_multilevel_functional_scenario_uses_expanded_process_sequence():
    project = _example_project("multilevel.json")
    paths = find_project_paths(project)

    scenarios = build_functional_scenarios(paths, project=project)

    assert scenarios[2].path_ids == ["P3"]
    assert scenarios[2].input_data == ["x1"]
    assert scenarios[2].output_data == ["x7"]
    assert [operation.process for operation in scenarios[2].operations] == [
        "A12",
        "A11",
        "A13",
        "A31",
        "A331",
        "A333",
    ]
    assert "A33: s2 == 2" in scenarios[2].preconditions


def test_export_analysis_can_include_functional_scenarios_separately_from_paths_and_relations():
    project = _example_project("choice.json")
    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)
    scenarios = build_functional_scenarios(paths, project=project)

    output = export_analysis(paths, relations, "json", scenarios)

    assert '"paths"' in output
    assert '"path_relations"' in output
    assert '"functional_scenarios"' in output
    assert '"FS1"' in output


def _example_project(example_name: str):
    return parse_project((ROOT / "examples" / example_name).read_text(encoding="utf-8"), "json")
