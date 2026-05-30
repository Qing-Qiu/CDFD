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
              "start": "A",
              "ends": ["B"],
              "nodes": ["A", "B"],
              "edges": [{"from": "A", "to": "B"}]
            }
            """,
        },
    )

    assert response.status_code == 200
    assert response.json()["paths"][0]["nodes"] == ["A", "B"]


def test_web_index_page():
    from fastapi.testclient import TestClient

    from cdfd.web import app

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "CDFD Path Generator" in response.text
