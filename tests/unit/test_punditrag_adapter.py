from __future__ import annotations

from integrations.punditrag import PunditRAGClient


def test_punditrag_client_uses_stable_search_contract(monkeypatch) -> None:
    client = PunditRAGClient(base_url="http://punditrag.local")
    captured = {}

    def fake_request(method, path, payload):
        captured.update({"method": method, "path": path, "payload": payload})
        return {
            "items": [
                {
                    "text": "Evidence",
                    "metadata": {
                        "filename": "source.md",
                        "chapter": "1",
                        "knowledge_base_id": 7,
                        "module_id": 2,
                    },
                }
            ]
        }

    monkeypatch.setattr(client.http, "request", fake_request)
    results = client.search(
        query="question",
        knowledge_base_id=7,
        module_id=2,
        trace_id="trace-001",
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/retrieval/search"
    assert captured["payload"]["knowledge_base_id"] == 7
    assert captured["payload"]["module_id"] == 2
    assert captured["payload"]["trace_id"] == "trace-001"
    assert results[0]["metadata"]["filename"] == "source.md"
