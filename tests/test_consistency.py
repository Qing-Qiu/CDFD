from pathlib import Path

from cdfd.consistency import inspect_project_consistency
from cdfd.parsers import parse_project


ROOT = Path(__file__).resolve().parents[1]


def test_official_examples_have_no_cdfd_module_consistency_warnings():
    for example_name in [
        "cdfd_v1.json",
        "choice.json",
        "join.json",
        "data_store.json",
        "multilevel.json",
    ]:
        project = parse_project((ROOT / "examples" / example_name).read_text(encoding="utf-8"), "json")

        assert inspect_project_consistency(project) == []


def test_sofl_cdfd_data_stores_are_connected_by_unlabeled_flows():
    project = parse_project((ROOT / "examples" / "xuexitong.cdfd").read_text(encoding="utf-8"), "cdfd")

    assert inspect_project_consistency(project) == []


def test_consistency_check_reports_process_interface_mismatch():
    project = parse_project(
        """
        {
          "schema_version": "cdfd-json-v1",
          "module": {
            "name": "MismatchExample",
            "var": ["x", "y", "z"],
            "behav": "Top"
          },
          "processes": [
            { "id": "A", "inputs": ["x"], "outputs": ["z"] }
          ],
          "graphs": {
            "Top": {
              "start": "IN",
              "ends": ["OUT"],
              "nodes": [
                { "id": "IN", "type": "external" },
                { "id": "A", "type": "process" },
                { "id": "OUT", "type": "external" }
              ],
              "edges": [
                { "id": "e1", "from": "IN", "to": "A", "data": ["x"] },
                { "id": "e2", "from": "A", "to": "OUT", "data": ["y"] }
              ]
            }
          }
        }
        """,
        "json",
    )

    issues = inspect_project_consistency(project)

    assert [(issue.id, issue.rule, issue.process, issue.data) for issue in issues] == [
        ("C1", "process-outputs-mismatch", "A", ["y", "z"])
    ]


def test_consistency_check_reports_undeclared_data_and_missing_process_spec():
    project = parse_project(
        """
        {
          "schema_version": "cdfd-json-v1",
          "module": {
            "name": "MissingSpecExample",
            "var": ["x"],
            "behav": "Top"
          },
          "processes": [],
          "graphs": {
            "Top": {
              "start": "IN",
              "ends": ["OUT"],
              "nodes": [
                { "id": "IN", "type": "external" },
                { "id": "A", "type": "process" },
                { "id": "OUT", "type": "external" }
              ],
              "edges": [
                { "id": "e1", "from": "IN", "to": "A", "data": ["x"] },
                { "id": "e2", "from": "A", "to": "OUT", "data": ["missing"] }
              ]
            }
          }
        }
        """,
        "json",
    )

    issues = inspect_project_consistency(project)

    assert [issue.rule for issue in issues] == ["undeclared-data-flow", "missing-process-spec"]
    assert issues[0].edge == "e2"
    assert issues[1].process == "A"
