"""SimpleMem adapter with the competition's three memory types and intents."""

from __future__ import annotations

import os
from typing import Any

from .contracts import (
    MemoryAuthorizationResponse,
    MemoryMutationResponse,
    MemoryMutationStatus,
    MemoryRecord,
    MemorySearchRequest,
    MemoryUpsertResponse,
)
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

    def upsert(self, record: MemoryRecord) -> dict[str, Any]:
        payload = self.http.request(
            "POST",
            "/v1/memories",
            record.model_dump(mode="json"),
        )
        try:
            response = MemoryUpsertResponse.model_validate(payload)
        except ValueError as exc:
            raise IntegrationUnavailable(
                f"Invalid SimpleMem upsert response: {exc}"
            ) from exc
        return response.model_dump(mode="json")

    def remember(self, record: MemoryRecord) -> dict[str, Any]:
        """Backward-compatible alias for the idempotent upsert operation."""
        return self.upsert(record)

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
        payload = self.http.request(
            "PATCH",
            f"/v1/memories/{memory_id}",
            record.model_dump(mode="json"),
        )
        return self._validate_mutation_response(
            payload,
            memory_id=memory_id,
            scope=self._record_scope(record),
            allowed_statuses={
                MemoryMutationStatus.UPDATED,
                MemoryMutationStatus.UNCHANGED,
            },
        )

    def authorize(
        self,
        memory_id: str,
        *,
        organization_id: int,
        user_id: int,
        program_id: int,
        module_id: int,
    ) -> dict[str, Any]:
        scope = {
            "organization_id": organization_id,
            "user_id": user_id,
            "program_id": program_id,
            "module_id": module_id,
        }
        payload = self.http.request(
            "POST",
            f"/v1/memories/{memory_id}/authorize",
            scope,
        )
        try:
            response = MemoryAuthorizationResponse.model_validate(payload)
        except ValueError as exc:
            raise IntegrationUnavailable(
                f"Invalid SimpleMem authorization response: {exc}"
            ) from exc
        actual_scope = {field: getattr(response, field) for field in scope}
        if response.memory_id != memory_id or actual_scope != scope:
            raise IntegrationUnavailable(
                "SimpleMem authorization response does not match the requested scope."
            )
        return response.model_dump(mode="json")

    def delete(
        self,
        memory_id: str,
        *,
        organization_id: int,
        user_id: int,
        program_id: int,
        module_id: int,
    ) -> dict[str, Any]:
        scope = {
            "organization_id": organization_id,
            "user_id": user_id,
            "program_id": program_id,
            "module_id": module_id,
        }
        payload = self.http.request(
            "DELETE",
            f"/v1/memories/{memory_id}",
            scope,
        )
        return self._validate_mutation_response(
            payload,
            memory_id=memory_id,
            scope=scope,
            allowed_statuses={MemoryMutationStatus.DELETED},
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

    @staticmethod
    def _record_scope(record: MemoryRecord) -> dict[str, int]:
        return {
            "organization_id": record.organization_id,
            "user_id": record.user_id,
            "program_id": record.program_id,
            "module_id": record.module_id,
        }

    @staticmethod
    def _validate_mutation_response(
        payload: Any,
        *,
        memory_id: str,
        scope: dict[str, int],
        allowed_statuses: set[MemoryMutationStatus],
    ) -> dict[str, Any]:
        try:
            response = MemoryMutationResponse.model_validate(payload)
        except ValueError as exc:
            raise IntegrationUnavailable(
                f"Invalid SimpleMem mutation response: {exc}"
            ) from exc
        actual_scope = {field: getattr(response, field) for field in scope}
        if (
            response.memory_id != memory_id
            or actual_scope != scope
            or response.status not in allowed_statuses
        ):
            raise IntegrationUnavailable(
                "SimpleMem mutation response does not match the requested operation and scope."
            )
        return response.model_dump(mode="json")
