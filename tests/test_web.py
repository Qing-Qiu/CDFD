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
        },
    )

    assert response.status_code == 200
    assert response.json()["paths"][0]["nodes"] == ["A", "B"]
    assert response.json()["paths"][0]["id"] == "P1"


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


def test_web_index_page():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "CDFD Path Generator" in response.text


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
    assert data["path_relations"] == []
    assert set(data["graph_svgs"]) == {"Top", "A1_detail"}
