from __future__ import annotations

from app import app
from fastapi.testclient import TestClient


def test_health_endpoint_reports_selected_provider() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["rag_provider"] == "punditrag"
