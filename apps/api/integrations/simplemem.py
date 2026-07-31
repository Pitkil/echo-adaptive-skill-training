"""SimpleMem adapter with the competition's three memory types and intents."""

from __future__ import annotations

import os
from typing import Any

from .contracts import MemoryRecord, MemorySearchRequest
from .http_client import IntegrationUnavailable, JsonHttpClient


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
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise IntegrationUnavailable("SimpleMem response must contain a list of memory items.")

        expected_scope = {
            "organization_id": request.organization_id,
            "user_id": request.user_id,
            "program_id": request.program_id,
            "module_id": request.module_id,
        }
        for item in items:
            for field, expected in expected_scope.items():
                if field not in item or item[field] != expected:
                    raise IntegrationUnavailable(
                        f"SimpleMem returned an item outside the requested {field} scope."
                    )
        return items

    def update(self, memory_id: str, record: MemoryRecord) -> dict[str, Any]:
        return self.http.request(
            "PATCH",
            f"/v1/memories/{memory_id}",
            record.model_dump(mode="json"),
        )

    def delete(
        self,
        memory_id: str,
        *,
        organization_id: int,
        user_id: int,
        program_id: int,
        module_id: int,
    ) -> dict[str, Any]:
        return self.http.request(
            "DELETE",
            f"/v1/memories/{memory_id}",
            {
                "organization_id": organization_id,
                "user_id": user_id,
                "program_id": program_id,
                "module_id": module_id,
            },
        )

    def consolidate(
        self,
        *,
        organization_id: int,
        user_id: int,
        program_id: int,
        module_id: int,
    ) -> dict[str, Any]:
        return self.http.request(
            "POST",
            "/v1/memories/consolidate",
            {
                "organization_id": organization_id,
                "user_id": user_id,
                "program_id": program_id,
                "module_id": module_id,
            },
        )

    def health(self) -> dict[str, Any]:
        payload = self.http.request("GET", "/health")
        if not isinstance(payload, dict):
            raise IntegrationUnavailable("SimpleMem health response must be an object.")
        return payload
