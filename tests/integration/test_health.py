from __future__ import annotations

import app as app_module
from app import app
from fastapi.testclient import TestClient


def test_health_endpoint_reports_selected_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "collect_dependency_health",
        lambda: {
            "punditrag_import": {"status": "ok"},
            "punditrag_query": {"status": "ok"},
            "simplemem": {"status": "ok", "service": "simplemem"},
            "micro_representation": {"status": "ok", "mode": "mock"},
        },
    )
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["rag_provider"] == "punditrag"
    assert payload["unavailable_count"] == 0
    assert payload["dependencies"]["database"]["status"] == "ok"


def test_health_endpoint_distinguishes_optional_service_degradation(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "collect_dependency_health",
        lambda: {
            "punditrag_import": {"status": "unavailable", "detail": "无法连接"},
            "punditrag_query": {"status": "ok"},
            "simplemem": {"status": "ok"},
            "micro_representation": {"status": "not_configured"},
        },
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["unavailable_count"] == 2
