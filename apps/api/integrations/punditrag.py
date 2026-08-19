"""Adapter for PunditRAG's separate import and query services."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from .contracts import normalize_punditrag_query_payload
from .http_client import JsonHttpClient


def _infer_query_url(import_url: str) -> str:
    """Infer PunditRAG's default query port from its import service URL."""

    parsed = urlsplit(import_url)
    if parsed.port != 8000:
        return import_url
    host = parsed.hostname or "localhost"
    netloc = f"{host}:8001"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials += f":{parsed.password}"
        netloc = f"{credentials}@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


class PunditRAGClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        *,
        query_base_url: str | None = None,
        import_base_url: str | None = None,
    ) -> None:
        timeout = timeout_seconds or float(os.getenv("PUNDITRAG_TIMEOUT_SECONDS", "30"))
        configured_import_url = (
            import_base_url
            or base_url
            or os.getenv("PUNDITRAG_IMPORT_BASE_URL")
            or os.getenv("PUNDITRAG_BASE_URL", "")
        )
        configured_query_url = (
            query_base_url
            or base_url
            or os.getenv("PUNDITRAG_QUERY_BASE_URL")
            or (_infer_query_url(configured_import_url) if configured_import_url else "")
        )
        self.import_http = JsonHttpClient(configured_import_url, timeout_seconds=timeout)
        self.query_http = JsonHttpClient(configured_query_url, timeout_seconds=timeout)
        self.http = self.query_http

    @property
    def configured(self) -> bool:
        return self.query_http.configured

    @property
    def import_configured(self) -> bool:
        return self.import_http.configured

    def search(
        self,
        query: str,
        knowledge_base_id: int,
        module_id: int,
        *,
        external_knowledge_base_id: str | None = None,
        trace_id: str | None = None,
        knowledge_point_ids: list[int] | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        del top_k  # PunditRAG applies its configured retrieval and reranking limits.
        payload = self.query_http.request(
            "POST",
            "/query",
            {
                "query": query,
                "session_id": trace_id,
                "scope_mode": "knowledge_base",
                "kb_ids": [external_knowledge_base_id or str(knowledge_base_id)],
                "document_ids": [],
                "is_stream": False,
                "enable_web_search": False,
            },
        )
        return normalize_punditrag_query_payload(
            payload,
            knowledge_base_id=knowledge_base_id,
            module_id=module_id,
            knowledge_point_ids=knowledge_point_ids,
        )

    def create_knowledge_base(self, *, name: str, description: str = "") -> dict:
        payload = self.import_http.request(
            "POST",
            "/knowledge-bases",
            {"name": name, "description": description},
        )
        if not isinstance(payload, dict) or not str(payload.get("kb_id") or "").strip():
            raise ValueError("PunditRAG did not return a knowledge base id.")
        return payload

    def ensure_knowledge_base(self, *, name: str, description: str = "") -> dict:
        """Reuse an exact-name PunditRAG knowledge base or create it."""

        payload = self.import_http.request("GET", "/knowledge-bases")
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("PunditRAG knowledge base listing is invalid.")
        normalized_name = name.strip()
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "").strip() != normalized_name:
                continue
            if str(item.get("kb_id") or "").strip():
                return item
        return self.create_knowledge_base(name=normalized_name, description=description)

    def ingest_document(
        self,
        *,
        knowledge_base_id: int,
        module_id: int,
        filename: str,
        content: bytes,
        content_type: str,
        trace_id: str,
        external_knowledge_base_id: str | None = None,
    ) -> dict:
        del module_id, trace_id
        payload = self.import_http.upload(
            "/upload",
            filename=filename,
            content=content,
            content_type=content_type,
            field_name="files",
            data={"kb_id": external_knowledge_base_id or str(knowledge_base_id)},
        )
        if not isinstance(payload, dict):
            raise ValueError("PunditRAG upload response must be an object.")
        task_ids = payload.get("task_ids")
        document_ids = payload.get("document_ids")
        if not isinstance(task_ids, list) or len(task_ids) != 1:
            raise ValueError("PunditRAG upload did not return one task id.")
        if not isinstance(document_ids, list) or len(document_ids) != 1:
            raise ValueError("PunditRAG upload did not return one document id.")
        return {
            **payload,
            "task_id": str(task_ids[0]),
            "document_id": str(document_ids[0]),
            "status": "pending",
        }

    def get_import_status(self, task_id: str) -> dict:
        payload = self.import_http.request("GET", f"/status/{task_id}")
        if not isinstance(payload, dict) or str(payload.get("task_id") or "") != task_id:
            raise ValueError("PunditRAG returned an invalid import status.")
        return payload

    def health(self) -> dict:
        return {
            "import": self.import_http.request("GET", "/health"),
            "query": self.query_http.request("GET", "/health"),
        }
