from __future__ import annotations

import pytest
from integrations.contracts import (
    MemoryIntent,
    MemoryRecord,
    MemorySearchRequest,
    MemoryType,
)
from integrations.http_client import IntegrationUnavailable
from integrations.simplemem import SimpleMemClient


class FakeHttpClient:
    configured = True

    def __init__(self, response=None) -> None:
        self.response = {} if response is None else response
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        return self.response


def make_record() -> MemoryRecord:
    return MemoryRecord(
        organization_id=1,
        user_id=2,
        program_id=3,
        module_id=4,
        knowledge_point_id=5,
        content="The learner repeatedly confuses plugins with agents.",
        memory_type=MemoryType.MISCONCEPTION,
        idempotency_key="a" * 64,
        conflict_key="b" * 64,
        confidence=0.9,
        evidence_refs=["attempt-1", "attempt-2"],
    )


def make_search_request() -> MemorySearchRequest:
    return MemorySearchRequest(
        organization_id=1,
        user_id=2,
        program_id=3,
        module_id=4,
        intent=MemoryIntent.LEARNER_DIAGNOSIS,
        query="stable misconceptions",
    )


def test_simplemem_uses_patch_and_full_scope_for_mutating_operations() -> None:
    client = SimpleMemClient("http://simplemem.test")
    fake_http = FakeHttpClient()
    client.http = fake_http
    record = make_record()

    fake_http.response = {
        "status": "updated",
        "memory_id": "memory-1",
        "organization_id": 1,
        "user_id": 2,
        "program_id": 3,
        "module_id": 4,
    }
    client.update("memory-1", record)
    fake_http.response = {
        "status": "deleted",
        "memory_id": "memory-1",
        "organization_id": 1,
        "user_id": 2,
        "program_id": 3,
        "module_id": 4,
    }
    client.delete(
        "memory-1",
        organization_id=1,
        user_id=2,
        program_id=3,
        module_id=4,
    )
    fake_http.response = {}
    client.consolidate(
        organization_id=1,
        user_id=2,
        program_id=3,
        module_id=4,
    )

    assert fake_http.calls[0][:2] == ("PATCH", "/v1/memories/memory-1")
    assert fake_http.calls[1] == (
        "DELETE",
        "/v1/memories/memory-1",
        {
            "organization_id": 1,
            "user_id": 2,
            "program_id": 3,
            "module_id": 4,
        },
    )
    assert fake_http.calls[2] == (
        "POST",
        "/v1/memories/consolidate",
        {
            "organization_id": 1,
            "user_id": 2,
            "program_id": 3,
            "module_id": 4,
        },
    )


@pytest.mark.parametrize(
    ("operation", "response"),
    [
        ("update", {}),
        (
            "update",
            {
                "status": "updated",
                "memory_id": "another-memory",
                "organization_id": 1,
                "user_id": 2,
                "program_id": 3,
                "module_id": 4,
            },
        ),
        (
            "delete",
            {
                "status": "updated",
                "memory_id": "memory-1",
                "organization_id": 1,
                "user_id": 2,
                "program_id": 3,
                "module_id": 4,
            },
        ),
    ],
)
def test_simplemem_rejects_invalid_mutation_response(
    operation: str,
    response: dict,
) -> None:
    client = SimpleMemClient("http://simplemem.test")
    client.http = FakeHttpClient(response)

    with pytest.raises(IntegrationUnavailable, match="mutation response"):
        if operation == "update":
            client.update("memory-1", make_record())
        else:
            client.delete(
                "memory-1",
                organization_id=1,
                user_id=2,
                program_id=3,
                module_id=4,
            )


def test_simplemem_upsert_sends_formal_idempotency_contract() -> None:
    record = make_record()
    client = SimpleMemClient("http://simplemem.test")
    fake_http = FakeHttpClient(
        {
            "status": "unchanged",
            "memory_id": "memory-1",
            "idempotency_key": record.idempotency_key,
            "conflict_memory_ids": [],
        }
    )
    client.http = fake_http

    result = client.upsert(record)

    assert result["status"] == "unchanged"
    assert fake_http.calls[0][0:2] == ("POST", "/v1/memories")
    assert fake_http.calls[0][2]["idempotency_key"] == "a" * 64
    assert fake_http.calls[0][2]["conflict_key"] == "b" * 64


def test_simplemem_authorization_requires_matching_memory_and_scope() -> None:
    client = SimpleMemClient("http://simplemem.test")
    client.http = FakeHttpClient(
        {
            "allowed": True,
            "memory_id": "memory-1",
            "organization_id": 1,
            "user_id": 999,
            "program_id": 3,
            "module_id": 4,
        }
    )

    with pytest.raises(IntegrationUnavailable, match="requested scope"):
        client.authorize(
            "memory-1",
            organization_id=1,
            user_id=2,
            program_id=3,
            module_id=4,
        )
    assert client.http.calls[0] == (
        "POST",
        "/v1/memories/memory-1/authorize",
        {
            "organization_id": 1,
            "user_id": 2,
            "program_id": 3,
            "module_id": 4,
        },
    )


def test_simplemem_search_rejects_items_outside_requested_scope() -> None:
    client = SimpleMemClient("http://simplemem.test")
    client.http = FakeHttpClient(
        {
            "items": [
                {
                    "memory_id": "memory-other-user",
                    "organization_id": 1,
                    "user_id": 999,
                    "program_id": 3,
                    "module_id": 4,
                    "content": "Must not leak.",
                }
            ]
        }
    )

    with pytest.raises(IntegrationUnavailable, match="user_id scope"):
        client.search(make_search_request())


def test_simplemem_search_returns_only_well_scoped_items() -> None:
    expected = {
        "memory_id": "memory-1",
        "organization_id": 1,
        "user_id": 2,
        "program_id": 3,
        "module_id": 4,
        "memory_type": "misconception",
        "content": "Stable misconception.",
    }
    client = SimpleMemClient("http://simplemem.test")
    client.http = FakeHttpClient({"items": [expected]})

    assert client.search(make_search_request()) == [expected]
