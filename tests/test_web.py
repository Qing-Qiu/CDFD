import importlib.util

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("fastapi") is None, reason="FastAPI is not installed.")


def test_web_analyze_endpoint():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={
            "input_format": "json",
            "content": """
            {
              "schema_version": "cdfd-json-v1",
              "module": {"var": ["x"], "behav": "Top"},
              "processes": [{"id": "A", "inputs": ["x"], "outputs": ["x"]}],
              "graphs": {
                "Top": {
                  "start": "IN",
                  "ends": ["B"],
                  "nodes": [
                    {"id": "IN", "type": "external"},
                    {"id": "A", "type": "process"},
                    {"id": "B", "type": "external"}
                  ],
                  "edges": [
                    {"from": "IN", "to": "A", "data": ["x"]},
                    {"from": "A", "to": "B", "data": ["x"]}
                  ]
                }
              }
            }
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["paths"][0]["nodes"] == ["IN", "A", "B"]
    assert payload["paths"][0]["id"] == "P1"
    single_path_scenarios = [
        scenario for scenario in payload["functional_scenarios"] if scenario.get("kind") == "single-path"
    ]
    assert single_path_scenarios[0]["id"] == "FS1"
    assert single_path_scenarios[0]["path_ids"] == ["P1"]
    assert payload["consistency_issues"] == []


def test_web_analyze_reports_cdfd_module_consistency_warnings():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={
            "input_format": "json",
            "content": """
            {
              "schema_version": "cdfd-json-v1",
              "module": {"var": ["x"], "behav": "Top"},
              "processes": [],
              "graphs": {
                "Top": {
                  "start": "IN",
                  "ends": ["OUT"],
                  "nodes": [
                    {"id": "IN", "type": "external"},
                    {"id": "A", "type": "process"},
                    {"id": "OUT", "type": "external"}
                  ],
                  "edges": [
                    {"from": "IN", "to": "A", "data": ["x"]},
                    {"from": "A", "to": "OUT", "data": ["y"]}
                  ]
                }
              }
            }
            """,
        },
    )

    assert response.status_code == 200
    rules = [issue["rule"] for issue in response.json()["consistency_issues"]]
    assert rules == ["undeclared-data-flow", "missing-process-spec"]


def test_web_analyze_rejects_json_that_does_not_match_project_schema():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={
            "input_format": "json",
            "content": """
            {
              "start": "A",
              "ends": ["B"],
              "nodes": ["A", "B"],
              "edges": [{"from": "A", "to": "B"}]
            }
            """,
        },
    )

    assert response.status_code == 400
    assert "CDFD JSON schema validation failed" in response.json()["detail"]
    assert "schema_version" in response.json()["detail"]


def test_web_analyze_rejects_removed_input_format():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={"input_format": "yaml", "content": "graphs: {}"},
    )

    assert response.status_code == 422


def test_web_index_page():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "CDFD Path Generator" in response.text
    assert 'id="zoomIn"' in response.text
    assert 'id="zoomOut"' in response.text
    assert 'id="resetZoom"' in response.text
    assert 'id="fitGraph"' in response.text
    assert "Paths" in response.text
    assert "Path relations" in response.text
    assert "View or edit CDFD source" in response.text
    assert 'class="workspace"' in response.text
    assert "CDFD JSON" in response.text
    assert "SOFL .cdfd" in response.text
    assert ">YAML<" not in response.text
    assert ">CSV<" not in response.text
    assert ">Results<" not in response.text
    assert "Paths generated successfully." not in response.text
    assert "Functional scenarios" not in response.text
    assert "Cycle Strategy" not in response.text
    assert "Start node" not in response.text
    assert "End node(s)" not in response.text


def test_web_analyze_multilevel_project():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        json={
            "input_format": "json",
            "content": """
            {
              "schema_version": "cdfd-json-v1",
              "module": {"behav": "Top"},
              "processes": [{"id": "A1", "decom": "A1_detail"}],
              "graphs": {
                "Top": {
                  "start": "A1",
                  "ends": ["A2"],
                  "nodes": ["A1", "A2"],
                  "edges": [{"from": "A1", "to": "A2"}]
                },
                "A1_detail": {
                  "start": "A11",
                  "ends": ["A12"],
                  "nodes": ["A11", "A12"],
                  "edges": [{"from": "A11", "to": "A12"}]
                }
              }
            }
            """,
            "expand": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project"]["graph_count"] == 2
    assert data["paths"][0]["nodes"] == ["A11", "A12", "A2"]
    single_path_scenarios = [
        scenario for scenario in data["functional_scenarios"] if scenario.get("kind") == "single-path"
    ]
    assert single_path_scenarios[0]["path_ids"] == ["P1"]
    assert data["path_relations"] == []
    assert set(data["graph_svgs"]) == {"Top", "A1_detail"}
