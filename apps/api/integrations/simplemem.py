"""SimpleMem adapter with the competition's three memory types and intents."""

from __future__ import annotations

import os
from typing import Any

from .contracts import MemoryRecord, MemorySearchRequest
from .http_client import JsonHttpClient


class SimpleMemClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.http = JsonHttpClient(
            base_url or os.getenv("SIMPLEMEM_BASE_URL", ""),
            timeout_seconds=float(os.getenv("SIMPLEMEM_TIMEOUT_SECONDS", "10")),
        )

    @property
    def configured(self) -> bool:
        return self.http.configured

    def remember(self, record: MemoryRecord) -> dict[str, Any]:
        return self.http.request("POST", "/v1/memories", record.model_dump(mode="json"))

    def search(self, request: MemorySearchRequest) -> list[dict[str, Any]]:
        payload = self.http.request(
            "POST",
            "/v1/memories/search",
            request.model_dump(mode="json"),
        )
        return payload.get("items", payload) if isinstance(payload, dict) else payload

    def update(self, memory_id: str, record: MemoryRecord) -> dict[str, Any]:
        return self.http.request(
            "PUT",
            f"/v1/memories/{memory_id}",
            record.model_dump(mode="json"),
        )

    def delete(self, memory_id: str, organization_id: int, user_id: int) -> dict[str, Any]:
        return self.http.request(
            "DELETE",
            f"/v1/memories/{memory_id}",
            {"organization_id": organization_id, "user_id": user_id},
        )

    def consolidate(self, organization_id: int, user_id: int, module_id: int) -> dict[str, Any]:
        return self.http.request(
            "POST",
            "/v1/memories/consolidate",
            {
                "organization_id": organization_id,
                "user_id": user_id,
                "module_id": module_id,
            },
        )
