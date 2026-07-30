"""Plan-scoped tools exposed to ECHO agents."""

from __future__ import annotations

import json

from integrations.punditrag import PunditRAGClient


class RAGPlugin:
    def __init__(self, client: PunditRAGClient | None = None) -> None:
        self.client = client or PunditRAGClient()
        self.knowledge_base_id: int | None = None
        self.module_id: int | None = None
        self.trace_id: str | None = None
        self.enabled = True

    def set_context(
        self,
        *,
        knowledge_base_id: int,
        module_id: int,
        trace_id: str,
        enabled: bool = True,
    ) -> None:
        self.knowledge_base_id = knowledge_base_id
        self.module_id = module_id
        self.trace_id = trace_id
        self.enabled = enabled

    def retrieve(self, query: str) -> str:
        if not self.enabled:
            return json.dumps({"items": [], "degraded": True}, ensure_ascii=False)
        if self.knowledge_base_id is None or self.module_id is None:
            raise RuntimeError("RAGPlugin context is incomplete.")
        items = self.client.search(
            query,
            self.knowledge_base_id,
            self.module_id,
            trace_id=self.trace_id,
        )
        return json.dumps({"items": items, "degraded": False}, ensure_ascii=False)
