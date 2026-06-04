import json
from pathlib import Path

from jsonschema import Draft202012Validator

from cdfd.multilevel import find_project_paths
from cdfd.parsers import parse_project
from cdfd.path_finder import find_paths
from cdfd.path_groups import build_path_relations


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "cdfd-json-schema.json"


def test_official_json_examples_validate_against_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    for example_name in [
        "cdfd_v1.json",
        "choice.json",
        "join.json",
        "data_store.json",
        "multilevel.json",
    ]:
        document = json.loads((ROOT / "examples" / example_name).read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
        assert errors == []


def test_parallel_example_generates_paths_and_parallel_relation():
    project = _example_project("cdfd_v1.json")

    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)

    assert [path.nodes for path in paths] == [
        ["IN", "A", "B", "OUT_X4"],
        ["IN", "A", "C", "OUT_X5"],
    ]
    assert [(relation.kind, relation.path_ids, relation.structure_id) for relation in relations] == [
        ("parallel", ["P1", "P2"], "par_A")
    ]


def test_choice_example_marks_paths_as_exclusive_not_parallel():
    project = _example_project("choice.json")

    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)

    assert len(paths) == 2
    assert [relation.kind for relation in relations] == ["exclusive"]
    assert relations[0].structure_id == "choice_Check"


def test_join_example_marks_converging_paths_as_joined_output():
    project = _example_project("join.json")

    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)

    assert len(paths) == 2
    assert [relation.kind for relation in relations] == ["joined-output"]
    assert relations[0].outputs == ["combined"]
    assert relations[0].structure_id == "join_Combine"


def test_data_store_example_generates_paths_from_multiple_starts():
    project = _example_project("data_store.json")

    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)

    assert project.entry().starts == {"IN", "PROFILE_STORE"}
    assert [path.nodes for path in paths] == [
        ["IN", "BuildResponse", "OUT"],
        ["PROFILE_STORE", "BuildResponse", "OUT"],
    ]
    assert [relation.kind for relation in relations] == ["joined-output"]
    assert relations[0].structure_id == "join_response_inputs"


def test_multilevel_example_keeps_paths_and_relations_distinct():
    project = _example_project("multilevel.json")

    paths = find_project_paths(project)
    relations = build_path_relations(paths, project=project)

    assert [path.nodes for path in paths] == [
        ["IN", "A12", "A11", "A13", "A2", "A4", "OUT_X6"],
        ["IN", "A12", "A11", "A13", "A31", "A32", "A4", "OUT_X6"],
        ["IN", "A12", "A11", "A13", "A31", "A331", "A333", "OUT_X7"],
    ]
    assert [(relation.kind, relation.path_ids, relation.structure_id) for relation in relations] == [
        ("joined-output", ["P1", "P2"], "join_x6"),
        ("parallel", ["P1", "P3"], "parallel_outputs"),
        ("exclusive", ["P2", "P3"], "choice_A3_output"),
    ]


def test_multilevel_a33_detail_has_its_own_internal_choice():
    project = _example_project("multilevel.json")
    graph = project.graphs["A33_detail"]

    paths = find_paths(graph)
    relations = build_path_relations(paths, graph=graph, graph_name="A33_detail")

    assert [path.data for path in paths] == [["d2"], ["d1", "z3"]]
    assert len(relations) == 1
    assert relations[0].kind == "exclusive"
    assert set(relations[0].path_ids) == {"P1", "P2"}
    assert relations[0].structure_id == "choice_A33_output"


def _example_project(example_name: str):
    return parse_project((ROOT / "examples" / example_name).read_text(encoding="utf-8"), "json")
