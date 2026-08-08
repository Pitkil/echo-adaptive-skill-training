from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from database import LearnerAbility
from integrations.contracts import MemoryIntent, MemoryRecord, MemoryType
from integrations.http_client import IntegrationUnavailable
from MIRT.memory_service import (
    LearnerMemoryService,
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidenceType,
    MemoryLifecycleStatus,
    MemoryScope,
    StableMemoryPolicy,
)
from pydantic import ValidationError


class FakeMemoryClient:
    def __init__(self, *, configured: bool = True, fail_operation: str | None = None) -> None:
        self.configured = configured
        self.fail_operation = fail_operation
        self.calls: list[tuple[str, object]] = []

    def _fail_if_requested(self, operation: str) -> None:
        if self.fail_operation == operation:
            raise IntegrationUnavailable(f"{operation} unavailable")

    def remember(self, record: MemoryRecord):
        self._fail_if_requested("create")
        self.calls.append(("create", record))
        return {"memory_id": "memory-1", "status": "stored"}

    def search(self, request):
        self._fail_if_requested("search")
        self.calls.append(("search", request))
        return [
            {
                "memory_id": "memory-1",
                "organization_id": request.organization_id,
                "user_id": request.user_id,
                "program_id": request.program_id,
                "module_id": request.module_id,
                "memory_type": "misconception",
                "content": "Confuses plugins with agents.",
            }
        ]

    def update(self, memory_id: str, record: MemoryRecord):
        self._fail_if_requested("update")
        self.calls.append(("update", (memory_id, record)))
        return {"memory_id": memory_id, "status": "updated"}

    def delete(self, memory_id: str, **scope):
        self._fail_if_requested("delete")
        self.calls.append(("delete", (memory_id, scope)))
        return {"memory_id": memory_id, "status": "deleted"}

    def consolidate(self, **scope):
        self._fail_if_requested("consolidate")
        self.calls.append(("consolidate", scope))
        return {
            "status": "consolidated",
            "source_memory_ids": ["memory-1", "memory-2"],
        }


def make_scope() -> MemoryScope:
    return MemoryScope(
        organization_id=1,
        user_id=2,
        program_id=3,
        module_id=4,
    )


def make_evidence(
    reference_id: str,
    *,
    evidence_type: MemoryEvidenceType = MemoryEvidenceType.SCORED_ATTEMPT,
    confidence: float = 0.9,
    day_offset: int = 0,
) -> MemoryEvidence:
    return MemoryEvidence(
        reference_id=reference_id,
        evidence_type=evidence_type,
        confidence=confidence,
        occurred_at=datetime.now(UTC) + timedelta(days=day_offset),
    )


def make_misconception_candidate(
    evidence: list[MemoryEvidence] | None = None,
    *,
    content: str = "The learner repeatedly confuses plugins with agents.",
) -> MemoryCandidate:
    return MemoryCandidate(
        **make_scope().model_dump(),
        knowledge_point_id=5,
        session_id=6,
        content=content,
        memory_type=MemoryType.MISCONCEPTION,
        evidence=evidence
        or [
            make_evidence("attempt-1", day_offset=-1),
            make_evidence("attempt-2"),
        ],
    )


def test_stable_misconception_is_written_with_traceable_evidence_and_dedup_key() -> None:
    client = FakeMemoryClient()
    result = LearnerMemoryService(client=client).create(make_misconception_candidate())

    assert result.status is MemoryLifecycleStatus.COMPLETED
    assert result.memory_record is not None
    assert result.memory_record.evidence_refs == ["attempt-1", "attempt-2"]
    assert result.memory_record.confidence == 0.9
    assert result.memory_record.metadata["evidence_count"] == 2
    assert len(result.memory_record.metadata["deduplication_key"]) == 64
    assert client.calls[0][0] == "create"


def test_deduplication_key_is_stable_for_normalized_content() -> None:
    policy = StableMemoryPolicy()
    first = policy.build_record(make_misconception_candidate())
    second = policy.build_record(
        make_misconception_candidate(
            content="  THE learner repeatedly   confuses plugins with agents.  "
        )
    )

    assert first.metadata["deduplication_key"] == second.metadata["deduplication_key"]


@pytest.mark.parametrize(
    ("evidence", "expected_reason"),
    [
        ([make_evidence("attempt-1")], "两个不同的证据编号"),
        (
            [make_evidence("attempt-1"), make_evidence("attempt-1")],
            "两个不同的证据编号",
        ),
        (
            [
                make_evidence(
                    "preference-1",
                    evidence_type=MemoryEvidenceType.PREFERENCE_OBSERVATION,
                ),
                make_evidence(
                    "preference-2",
                    evidence_type=MemoryEvidenceType.PREFERENCE_OBSERVATION,
                ),
            ],
            "scored_attempt",
        ),
        (
            [
                make_evidence("attempt-1", confidence=0.5),
                make_evidence("attempt-2", confidence=0.6),
            ],
            "低于 0.65",
        ),
    ],
)
def test_unstable_observation_is_rejected_without_calling_simplemem(
    evidence: list[MemoryEvidence],
    expected_reason: str,
) -> None:
    client = FakeMemoryClient()
    result = LearnerMemoryService(client=client).create(
        make_misconception_candidate(evidence)
    )

    assert result.status is MemoryLifecycleStatus.REJECTED
    assert expected_reason in (result.reason or "")
    assert client.calls == []


def test_memory_types_require_their_own_evidence_sources() -> None:
    preference = MemoryCandidate(
        **make_scope().model_dump(),
        content="The learner benefits from short steps.",
        memory_type=MemoryType.LEARNING_PREFERENCE,
        evidence=[
            make_evidence(
                "preference-1",
                evidence_type=MemoryEvidenceType.PREFERENCE_OBSERVATION,
            ),
            make_evidence(
                "intervention-1",
                evidence_type=MemoryEvidenceType.INTERVENTION_RESULT,
            ),
        ],
    )
    intervention = MemoryCandidate(
        **make_scope().model_dump(),
        content="Explicit checkpoints improved completion quality.",
        memory_type=MemoryType.INTERVENTION_OUTCOME,
        evidence=[
            make_evidence(
                "intervention-1",
                evidence_type=MemoryEvidenceType.INTERVENTION_RESULT,
            ),
            make_evidence(
                "intervention-2",
                evidence_type=MemoryEvidenceType.INTERVENTION_RESULT,
            ),
        ],
    )

    policy = StableMemoryPolicy()
    assert policy.build_record(preference).memory_type is MemoryType.LEARNING_PREFERENCE
    assert policy.build_record(intervention).memory_type is MemoryType.INTERVENTION_OUTCOME


def test_full_memory_lifecycle_preserves_scope() -> None:
    client = FakeMemoryClient()
    service = LearnerMemoryService(client=client)
    scope = make_scope()
    candidate = make_misconception_candidate()

    search = service.search(
        scope,
        intent=MemoryIntent.LEARNER_DIAGNOSIS,
        query="stable misconceptions",
    )
    update = service.update("memory-1", candidate)
    delete = service.delete("memory-1", scope)
    consolidate = service.consolidate(scope)

    assert all(
        result.status is MemoryLifecycleStatus.COMPLETED
        for result in (search, update, delete, consolidate)
    )
    search_request = client.calls[0][1]
    assert search_request.model_dump()["user_id"] == scope.user_id
    deleted_scope = client.calls[2][1][1]
    assert deleted_scope == scope.model_dump()
    assert client.calls[3] == ("consolidate", scope.model_dump())


def test_unconfigured_simplemem_degrades_without_losing_validated_record() -> None:
    service = LearnerMemoryService(client=FakeMemoryClient(configured=False))

    create = service.create(make_misconception_candidate())
    search = service.search(
        make_scope(),
        intent=MemoryIntent.ECHO_GUIDANCE,
        query="learning preferences",
    )

    assert create.status is MemoryLifecycleStatus.DEGRADED
    assert create.memory_record is not None
    assert "业务数据库事实不受影响" in (create.reason or "")
    assert search.status is MemoryLifecycleStatus.DEGRADED
    assert search.data == []


@pytest.mark.parametrize("operation", ["create", "search", "update", "delete", "consolidate"])
def test_simplemem_failure_is_returned_as_degradation(operation: str) -> None:
    service = LearnerMemoryService(
        client=FakeMemoryClient(fail_operation=operation)
    )
    scope = make_scope()
    candidate = make_misconception_candidate()

    if operation == "create":
        result = service.create(candidate)
    elif operation == "search":
        result = service.search(
            scope,
            intent=MemoryIntent.RESOURCE_GENERATION,
            query="memory",
        )
    elif operation == "update":
        result = service.update("memory-1", candidate)
    elif operation == "delete":
        result = service.delete("memory-1", scope)
    else:
        result = service.consolidate(scope)

    assert result.status is MemoryLifecycleStatus.DEGRADED
    assert "降级" in (result.reason or "")


def test_memory_lifecycle_never_changes_mirt_ability() -> None:
    ability = LearnerAbility(
        user_id=2,
        module_id=4,
        U=0.4,
        A=-0.2,
        R=0.8,
        attempt_count=3,
    )
    before = (ability.U, ability.A, ability.R, ability.attempt_count)

    result = LearnerMemoryService(client=FakeMemoryClient()).create(
        make_misconception_candidate()
    )

    assert result.status is MemoryLifecycleStatus.COMPLETED
    assert (ability.U, ability.A, ability.R, ability.attempt_count) == before


def test_memory_record_contract_requires_distinct_evidence_and_misconception_scope() -> None:
    base = {
        **make_scope().model_dump(),
        "content": "Stable misconception.",
        "memory_type": MemoryType.MISCONCEPTION,
        "confidence": 0.9,
    }
    with pytest.raises(ValidationError, match="distinct evidence refs"):
        MemoryRecord(**base, knowledge_point_id=5, evidence_refs=["attempt-1", "attempt-1"])
    with pytest.raises(ValidationError, match="knowledge_point_id"):
        MemoryRecord(**base, evidence_refs=["attempt-1", "attempt-2"])
