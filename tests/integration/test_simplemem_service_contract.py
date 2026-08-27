from __future__ import annotations

from hashlib import sha256

from fastapi.testclient import TestClient
from integrations.contracts import MemoryIntent, MemoryRecord, MemorySearchRequest, MemoryType
from integrations.simplemem import SimpleMemClient

from services.simplemem.simplemem.app import create_app


class AsgiJsonClient:
    configured = True

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def request(self, method: str, path: str, payload: dict | None = None):
        response = self.client.request(method, path, json=payload)
        response.raise_for_status()
        return response.json()


def test_echo_client_round_trips_against_real_simplemem_service(tmp_path) -> None:
    application = create_app(
        tmp_path / "simplemem.db",
        api_key="",
        allow_insecure_dev=True,
    )
    with TestClient(application) as service_client:
        echo_client = SimpleMemClient("http://simplemem.test")
        echo_client.http = AsgiJsonClient(service_client)
        record = MemoryRecord(
            organization_id=1,
            user_id=2,
            program_id=3,
            module_id=4,
            knowledge_point_id=5,
            session_id=6,
            content="The learner repeatedly confuses plugins with agents.",
            memory_type=MemoryType.MISCONCEPTION,
            idempotency_key=sha256(b"integration-idempotency").hexdigest(),
            conflict_key=sha256(b"integration-conflict").hexdigest(),
            confidence=0.88,
            evidence_refs=["attempt-1", "attempt-2"],
        )

        created = echo_client.upsert(record)
        items = echo_client.search(
            MemorySearchRequest(
                organization_id=1,
                user_id=2,
                program_id=3,
                module_id=4,
                intent=MemoryIntent.LEARNER_DIAGNOSIS,
                query="plugins agents",
                knowledge_point_id=5,
            )
        )
        authorization = echo_client.authorize(
            created["memory_id"],
            organization_id=1,
            user_id=2,
            program_id=3,
            module_id=4,
        )
        purged = echo_client.purge_scope(
            organization_id=1,
            user_id=2,
            program_id=3,
            module_id=4,
        )
        remaining = echo_client.search(
            MemorySearchRequest(
                organization_id=1,
                user_id=2,
                program_id=3,
                module_id=4,
                intent=MemoryIntent.LEARNER_DIAGNOSIS,
                query="plugins agents",
                knowledge_point_id=5,
            )
        )

    assert created["status"] == "created"
    assert items[0]["memory_id"] == created["memory_id"]
    assert items[0]["content"] == record.content
    assert authorization["allowed"] is True
    assert purged["status"] == "deleted"
    assert purged["deleted_count"] == 1
    assert remaining == []
