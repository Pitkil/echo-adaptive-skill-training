from __future__ import annotations

from integrations.punditrag import PunditRAGClient


def test_punditrag_client_uses_separate_import_and_query_timeouts(monkeypatch) -> None:
    monkeypatch.setenv("PUNDITRAG_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("PUNDITRAG_QUERY_TIMEOUT_SECONDS", "60")

    client = PunditRAGClient(base_url="http://punditrag.local")

    assert client.import_http.timeout_seconds == 180
    assert client.query_http.timeout_seconds == 60


def test_punditrag_client_maps_search_to_native_query_contract(monkeypatch) -> None:
    client = PunditRAGClient(
        query_base_url="http://punditrag.local:8001",
        import_base_url="http://punditrag.local:8000",
    )
    captured = {}

    def fake_request(method, path, payload):
        captured.update({"method": method, "path": path, "payload": payload})
        return {
            "answer": "answer [1]",
            "sources": [
                {
                    "content": "Evidence",
                    "file_title": "source.md",
                    "parent_title": "Section 1",
                    "kb_id": "external-kb",
                    "document_id": "document-1",
                    "part": 3,
                    "score": 0.93,
                }
            ],
        }

    monkeypatch.setattr(client.query_http, "request", fake_request)
    results = client.search(
        query="question",
        knowledge_base_id=7,
        module_id=2,
        external_knowledge_base_id="external-kb",
        trace_id="trace-001",
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/query"
    assert captured["payload"] == {
        "query": "question",
        "session_id": "trace-001",
        "scope_mode": "knowledge_base",
        "kb_ids": ["external-kb"],
        "document_ids": [],
        "is_stream": False,
        "enable_web_search": False,
    }
    assert results[0]["metadata"]["external_document_id"] == "document-1"
    assert results[0]["metadata"]["chunk_id"] == "document-1:3"


def test_punditrag_client_uploads_to_native_import_contract(monkeypatch) -> None:
    client = PunditRAGClient(base_url="http://punditrag.local")
    captured = {}

    def fake_upload(path, **kwargs):
        captured.update({"path": path, **kwargs})
        return {
            "kb_id": "external-kb",
            "task_ids": ["task-1"],
            "document_ids": ["document-1"],
        }

    monkeypatch.setattr(client.import_http, "upload", fake_upload)
    result = client.ingest_document(
        knowledge_base_id=7,
        module_id=2,
        filename="source.md",
        content=b"official content",
        content_type="text/markdown",
        trace_id="trace-001",
        external_knowledge_base_id="external-kb",
    )

    assert captured["path"] == "/upload"
    assert captured["field_name"] == "files"
    assert captured["data"] == {"kb_id": "external-kb"}
    assert result["task_id"] == "task-1"
    assert result["document_id"] == "document-1"
    assert result["status"] == "pending"


def test_punditrag_client_can_restrict_query_to_registered_documents(monkeypatch) -> None:
    client = PunditRAGClient(base_url="http://punditrag.local")
    captured = {}

    def fake_request(method, path, payload):
        captured.update(payload)
        return {"answer": "answer [1]", "sources": []}

    monkeypatch.setattr(client.query_http, "request", fake_request)
    client.search(
        query="module-scoped question",
        knowledge_base_id=7,
        module_id=2,
        external_knowledge_base_id="external-kb",
        external_document_ids=["doc-2", "doc-2", "doc-3"],
    )

    assert captured["scope_mode"] == "documents"
    assert captured["kb_ids"] == ["external-kb"]
    assert captured["document_ids"] == ["doc-2", "doc-3"]


def test_punditrag_client_reuses_matching_knowledge_base(monkeypatch) -> None:
    client = PunditRAGClient(base_url="http://punditrag.local")

    def fake_request(method, path, payload=None):
        assert method == "GET"
        assert path == "/knowledge-bases"
        return {
            "items": [
                {"kb_id": "existing-kb", "name": "Official Semantic Kernel"},
            ]
        }

    monkeypatch.setattr(client.import_http, "request", fake_request)
    result = client.ensure_knowledge_base(name="Official Semantic Kernel")

    assert result["kb_id"] == "existing-kb"
