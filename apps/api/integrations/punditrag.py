"""PunditRAG adapter for module-scoped, traceable evidence retrieval."""

from __future__ import annotations

import os

from .contracts import normalize_retrieval_payload
from .http_client import JsonHttpClient


class PunditRAGClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        self.http = JsonHttpClient(
            base_url or os.getenv("PUNDITRAG_BASE_URL", ""),
            timeout_seconds=timeout_seconds
            or float(os.getenv("PUNDITRAG_TIMEOUT_SECONDS", "15")),
        )

    @property
    def configured(self) -> bool:
        return self.http.configured

    def search(
        self,
        query: str,
        knowledge_base_id: int,
        module_id: int,
        *,
        trace_id: str | None = None,
        knowledge_point_ids: list[int] | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        payload = self.http.request(
            "POST",
            "/v1/retrieval/search",
            {
                "query": query,
                "knowledge_base_id": knowledge_base_id,
                "module_id": module_id,
                "knowledge_point_ids": knowledge_point_ids or [],
                "trace_id": trace_id,
                "top_k": top_k or int(os.getenv("PUNDITRAG_TOP_K", "5")),
            },
        )
        return normalize_retrieval_payload(payload)

    def ingest_document(
        self,
        *,
        knowledge_base_id: int,
        module_id: int,
        filename: str,
        content: bytes,
        content_type: str,
        trace_id: str,
    ) -> dict:
        return self.http.upload(
            f"/v1/knowledge-bases/{knowledge_base_id}/documents",
            filename=filename,
            content=content,
            content_type=content_type,
            data={
                "module_id": str(module_id),
                "trace_id": trace_id,
            },
        )
