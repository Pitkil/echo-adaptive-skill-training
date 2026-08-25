from __future__ import annotations

from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from services.simplemem.simplemem.app import create_app


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _scope(*, user_id: int = 2) -> dict[str, int]:
    return {
        "organization_id": 1,
        "user_id": user_id,
        "program_id": 3,
        "module_id": 4,
    }


def _record(
    name: str,
    *,
    content: str | None = None,
    conflict_domain: str | None = None,
    user_id: int = 2,
    memory_type: str = "misconception",
) -> dict:
    payload = {
        **_scope(user_id=user_id),
        "knowledge_point_id": 5 if memory_type == "misconception" else None,
        "session_id": 7,
        "content": content or f"{name} stable memory",
        "memory_type": memory_type,
        "idempotency_key": _digest(f"idempotency:{name}"),
        "conflict_key": _digest(f"conflict:{conflict_domain or name}"),
        "confidence": 0.82,
        "evidence_refs": [f"{name}-evidence-1", f"{name}-evidence-2"],
        "occurred_at": "2026-08-25T08:00:00Z",
        "metadata": {"topic": name},
    }
    return payload


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "simplemem.db", api_key="")) as test_client:
        yield test_client


def test_health_initializes_real_sqlite_database(client, tmp_path) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "simplemem",
        "version": "1.0.0",
        "database": "sqlite",
    }
    assert (tmp_path / "simplemem.db").is_file()


def test_upsert_is_idempotent_and_rejects_active_semantic_conflict(client) -> None:
    record = _record("plugin-call", conflict_domain="plugin-domain")
    created = client.post("/v1/memories", json=record)
    repeated = client.post("/v1/memories", json=record)
    conflict = client.post(
        "/v1/memories",
        json=_record(
            "plugin-call-opposite",
            content="Learner now claims plugins cannot expose functions.",
            conflict_domain="plugin-domain",
        ),
    )

    assert created.status_code == 200
    assert created.json()["status"] == "created"
    assert repeated.json() == {
        **created.json(),
        "status": "unchanged",
    }
    assert conflict.status_code == 200
    assert conflict.json()["status"] == "conflict"
    assert conflict.json()["memory_id"] is None
    assert conflict.json()["conflict_memory_ids"] == [created.json()["memory_id"]]


def test_search_and_authorization_never_cross_user_scope(client) -> None:
    own = client.post(
        "/v1/memories",
        json=_record("kernel-plugin", content="Plugin functions need clear descriptions."),
    ).json()
    client.post(
        "/v1/memories",
        json=_record(
            "other-user",
            content="Other user secret preference.",
            user_id=99,
        ),
    )

    search = client.post(
        "/v1/memories/search",
        json={
            **_scope(),
            "intent": "learner_diagnosis",
            "query": "plugin descriptions",
            "knowledge_point_id": 5,
            "limit": 8,
        },
    )
    forbidden = client.post(
        f"/v1/memories/{own['memory_id']}/authorize",
        json=_scope(user_id=99),
    )

    assert search.status_code == 200
    assert [item["memory_id"] for item in search.json()["items"]] == [own["memory_id"]]
    assert all(item["user_id"] == 2 for item in search.json()["items"])
    assert forbidden.status_code == 403


def test_update_delete_and_restart_persistence(tmp_path) -> None:
    database_path = tmp_path / "persistent.db"
    record = _record("reasoning")
    with TestClient(create_app(database_path, api_key="")) as first_client:
        memory_id = first_client.post("/v1/memories", json=record).json()["memory_id"]
        updated = {
            **record,
            "content": "reasoning stable memory with corrected guidance",
            "idempotency_key": _digest("idempotency:reasoning-updated"),
            "confidence": 0.91,
        }
        response = first_client.patch(f"/v1/memories/{memory_id}", json=updated)
        assert response.json()["status"] == "updated"

    with TestClient(create_app(database_path, api_key="")) as second_client:
        search = second_client.post(
            "/v1/memories/search",
            json={
                **_scope(),
                "intent": "echo_guidance",
                "query": "corrected guidance",
                "knowledge_point_id": 5,
                "limit": 8,
            },
        )
        assert search.json()["items"][0]["content"] == updated["content"]
        deleted = second_client.request(
            "DELETE",
            f"/v1/memories/{memory_id}",
            json=_scope(),
        )
        assert deleted.json()["status"] == "deleted"
        assert second_client.post(
            "/v1/memories/search",
            json={
                **_scope(),
                "intent": "echo_guidance",
                "query": "corrected guidance",
                "limit": 8,
            },
        ).json()["items"] == []


def test_consolidation_preserves_sources_and_exposes_only_merged_memory(client) -> None:
    first = client.post(
        "/v1/memories",
        json=_record(
            "preference-example",
            content="Learner benefits from worked examples.",
            memory_type="learning_preference",
        ),
    ).json()
    second = client.post(
        "/v1/memories",
        json=_record(
            "preference-steps",
            content="Learner benefits from shorter steps.",
            memory_type="learning_preference",
        ),
    ).json()

    consolidated = client.post("/v1/memories/consolidate", json=_scope())
    search = client.post(
        "/v1/memories/search",
        json={
            **_scope(),
            "intent": "echo_guidance",
            "query": "worked examples shorter steps",
            "limit": 8,
        },
    )

    assert consolidated.status_code == 200
    assert set(consolidated.json()["source_memory_ids"]) == {
        first["memory_id"],
        second["memory_id"],
    }
    assert len(search.json()["items"]) == 1
    assert search.json()["items"][0]["memory_id"] == consolidated.json()["merged_memory_id"]
    assert search.json()["items"][0]["metadata"]["source_count"] == 2


def test_optional_service_api_key_protects_v1_endpoints(tmp_path) -> None:
    with TestClient(create_app(tmp_path / "protected.db", api_key="secret-key")) as client:
        missing = client.post("/v1/memories", json=_record("protected"))
        accepted = client.post(
            "/v1/memories",
            json=_record("protected"),
            headers={"X-SimpleMem-API-Key": "secret-key"},
        )

    assert missing.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "created"
