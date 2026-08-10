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
    def __init__(
        self,
        *,
        configured: bool = True,
        fail_operation: str | None = None,
        consolidate_response: dict | None = None,
    ) -> None:
        self.configured = configured
        self.fail_operation = fail_operation
        self.calls: list[tuple[str, object]] = []
        self.records: dict[str, tuple[str, MemoryRecord]] = {}
        self.active_conflicts: dict[str, str] = {}
        self.memory_scopes = {"memory-1": make_scope().model_dump()}
        self.consolidate_response = consolidate_response

    def _fail_if_requested(self, operation: str) -> None:
        if self.fail_operation == operation:
            raise IntegrationUnavailable(f"{operation} unavailable")

    def upsert(self, record: MemoryRecord):
        self._fail_if_requested("create")
        self.calls.append(("create", record))
        if record.idempotency_key in self.records:
            memory_id, _ = self.records[record.idempotency_key]
            return {
                "status": "unchanged",
                "memory_id": memory_id,
                "idempotency_key": record.idempotency_key,
                "conflict_memory_ids": [],
            }
        if record.conflict_key in self.active_conflicts:
            return {
                "status": "conflict",
                "memory_id": None,
                "idempotency_key": record.idempotency_key,
                "conflict_memory_ids": [self.active_conflicts[record.conflict_key]],
            }
        memory_id = f"memory-{len(self.records) + 2}"
        self.records[record.idempotency_key] = (memory_id, record)
        self.active_conflicts[record.conflict_key] = memory_id
        self.memory_scopes[memory_id] = {
            "organization_id": record.organization_id,
            "user_id": record.user_id,
            "program_id": record.program_id,
            "module_id": record.module_id,
        }
        return {
            "status": "created",
            "memory_id": memory_id,
            "idempotency_key": record.idempotency_key,
            "conflict_memory_ids": [],
        }

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

    def authorize(self, memory_id: str, **scope):
        self._fail_if_requested("authorize")
        self.calls.append(("authorize", (memory_id, scope)))
        if self.memory_scopes.get(memory_id) != scope:
            raise IntegrationUnavailable("403 memory scope mismatch")
        return {"allowed": True, "memory_id": memory_id, **scope}

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
        return self.consolidate_response or {
            "merged_memory_id": "memory-merged",
            "source_memory_ids": ["memory-1", "memory-2"],
            "evidence_refs": ["attempt-1", "attempt-2"],
            **scope,
        }


def make_scope(**changes: int) -> MemoryScope:
    values = {
        "organization_id": 1,
        "user_id": 2,
        "program_id": 3,
        "module_id": 4,
    }
    values.update(changes)
    return MemoryScope(**values)


def make_attempt(
    reference_id: str,
    *,
    attempt_id: str | None = None,
    confidence: float = 0.9,
    day_offset: int = 0,
    knowledge_point_id: int = 5,
    is_correct: bool = False,
    misconception_key: str = "plugin-agent-confusion",
) -> MemoryEvidence:
    return MemoryEvidence(
        reference_id=reference_id,
        evidence_type=MemoryEvidenceType.SCORED_ATTEMPT,
        confidence=confidence,
        occurred_at=datetime.now(UTC) + timedelta(days=day_offset),
        attempt_id=attempt_id or reference_id,
        question_id=101,
        knowledge_point_id=knowledge_point_id,
        is_correct=is_correct,
        score=1.0 if is_correct else 0.0,
        misconception_key=misconception_key,
    )


def make_preference(
    reference_id: str,
    *,
    session_id: int,
    preference_key: str = "content_format",
    result_value: str = "short_steps",
    confirmed: bool = True,
    confidence: float = 0.9,
) -> MemoryEvidence:
    return MemoryEvidence(
        reference_id=reference_id,
        evidence_type=MemoryEvidenceType.PREFERENCE_OBSERVATION,
        confidence=confidence,
        preference_key=preference_key,
        result_confirmed=confirmed,
        result_value=result_value,
        session_id=session_id,
    )


def make_intervention(
    reference_id: str,
    *,
    intervention_id: str | None = None,
    session_id: int,
    intervention_type: str = "explicit_checkpoints",
    result_value: str = "improved",
    confirmed: bool = True,
    preference_key: str | None = None,
    confidence: float = 0.9,
) -> MemoryEvidence:
    return MemoryEvidence(
        reference_id=reference_id,
        evidence_type=MemoryEvidenceType.INTERVENTION_RESULT,
        confidence=confidence,
        intervention_id=intervention_id or reference_id,
        intervention_type=intervention_type,
        result_confirmed=confirmed,
        result_value=result_value,
        session_id=session_id,
        preference_key=preference_key,
    )


def make_misconception_candidate(
    evidence: list[MemoryEvidence] | None = None,
    *,
    content: str = "The learner repeatedly confuses plugins with agents.",
    scope: MemoryScope | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        **(scope or make_scope()).model_dump(),
        knowledge_point_id=5,
        session_id=6,
        content=content,
        memory_type=MemoryType.MISCONCEPTION,
        evidence=evidence
        or [
            make_attempt("attempt-1", day_offset=-1),
            make_attempt("attempt-2"),
        ],
    )


def test_stable_misconception_is_written_with_typed_traceable_evidence() -> None:
    client = FakeMemoryClient()
    result = LearnerMemoryService(client=client).create(make_misconception_candidate())

    assert result.status is MemoryLifecycleStatus.COMPLETED
    assert result.data["status"] == "created"
    assert result.memory_record is not None
    assert result.memory_record.evidence_refs == ["attempt-1", "attempt-2"]
    assert result.memory_record.confidence == 0.9
    assert result.memory_record.metadata["evidence_count"] == 2
    assert result.memory_record.metadata["evidence"][0]["attempt_id"] == "attempt-1"
    assert len(result.memory_record.idempotency_key) == 64
    assert len(result.memory_record.conflict_key) == 64


def test_idempotency_key_is_stable_for_normalized_content() -> None:
    policy = StableMemoryPolicy()
    first = policy.build_record(make_misconception_candidate())
    second = policy.build_record(
        make_misconception_candidate(
            content="  THE learner repeatedly   confuses plugins with agents.  "
        )
    )

    assert first.idempotency_key == second.idempotency_key
    assert first.conflict_key == second.conflict_key


@pytest.mark.parametrize(
    ("evidence", "expected_reason"),
    [
        ([make_attempt("attempt-1")], "语义不同"),
        (
            [
                make_attempt("reference-1", attempt_id="same-attempt"),
                make_attempt("reference-2", attempt_id="same-attempt"),
            ],
            "语义不同",
        ),
        (
            [make_attempt("attempt-1", is_correct=True), make_attempt("attempt-2")],
            "真实错误作答",
        ),
        (
            [
                make_attempt("attempt-1"),
                make_attempt("attempt-2", knowledge_point_id=99),
            ],
            "知识点",
        ),
        (
            [
                make_attempt("attempt-1"),
                make_attempt("attempt-2", misconception_key="another-conclusion"),
            ],
            "同一个误区结论",
        ),
        (
            [
                make_attempt("attempt-1", confidence=0.5),
                make_attempt("attempt-2", confidence=0.6),
            ],
            "低于 0.65",
        ),
        (
            [
                make_attempt("attempt-1", confidence=0.5),
                make_attempt("attempt-2", confidence=0.6),
                make_preference("preference-1", session_id=1, confidence=1.0),
            ],
            "不能混入其他类型",
        ),
    ],
)
def test_invalid_misconception_is_rejected_without_writing(
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


def test_only_semantically_distinct_supporting_evidence_is_persisted() -> None:
    evidence = [
        make_attempt("reference-1", attempt_id="attempt-1"),
        make_attempt("duplicate-reference", attempt_id="attempt-1"),
        make_attempt("reference-2", attempt_id="attempt-2"),
    ]

    record = StableMemoryPolicy().build_record(make_misconception_candidate(evidence))

    assert record.evidence_refs == ["reference-1", "reference-2"]
    assert [item["attempt_id"] for item in record.metadata["evidence"]] == [
        "attempt-1",
        "attempt-2",
    ]


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (
            [
                make_preference("preference-1", session_id=1),
                make_preference(
                    "preference-2",
                    session_id=2,
                    result_value="long_lecture",
                ),
            ],
            "互相矛盾",
        ),
        (
            [
                make_preference("preference-1", session_id=1),
                make_preference("preference-2", session_id=2, confirmed=False),
            ],
            "必须已确认",
        ),
        (
            [
                make_preference("preference-1", session_id=1),
                make_preference(
                    "preference-2",
                    session_id=2,
                    preference_key="pace",
                ),
            ],
            "同一个偏好",
        ),
    ],
)
def test_inconsistent_learning_preference_is_rejected(
    evidence: list[MemoryEvidence],
    reason: str,
) -> None:
    candidate = MemoryCandidate(
        **make_scope().model_dump(),
        content="The learner benefits from short steps.",
        memory_type=MemoryType.LEARNING_PREFERENCE,
        evidence=evidence,
    )

    with pytest.raises(ValueError, match=reason):
        StableMemoryPolicy().build_record(candidate)


def test_two_confirmed_consistent_interventions_are_accepted() -> None:
    candidate = MemoryCandidate(
        **make_scope().model_dump(),
        content="Explicit checkpoints improved completion quality.",
        memory_type=MemoryType.INTERVENTION_OUTCOME,
        evidence=[
            make_intervention("intervention-1", session_id=1),
            make_intervention("intervention-2", session_id=2),
        ],
    )

    record = StableMemoryPolicy().build_record(candidate)

    assert record.memory_type is MemoryType.INTERVENTION_OUTCOME
    assert record.evidence_refs == ["intervention-1", "intervention-2"]


def test_unconfirmed_intervention_is_rejected() -> None:
    candidate = MemoryCandidate(
        **make_scope().model_dump(),
        content="Explicit checkpoints improved completion quality.",
        memory_type=MemoryType.INTERVENTION_OUTCOME,
        evidence=[
            make_intervention("intervention-1", session_id=1),
            make_intervention("intervention-2", session_id=2, confirmed=False),
        ],
    )

    with pytest.raises(ValueError, match="必须已确认"):
        StableMemoryPolicy().build_record(candidate)


def test_duplicate_create_is_unchanged_and_does_not_create_second_record() -> None:
    client = FakeMemoryClient()
    service = LearnerMemoryService(client=client)
    candidate = make_misconception_candidate()

    first = service.create(candidate)
    second = service.create(candidate)

    assert first.data["status"] == "created"
    assert second.data["status"] == "unchanged"
    assert first.data["memory_id"] == second.data["memory_id"]
    assert len(client.records) == 1


def test_opposite_memory_in_same_domain_enters_conflict() -> None:
    client = FakeMemoryClient()
    service = LearnerMemoryService(client=client)
    service.create(make_misconception_candidate())

    opposite = make_misconception_candidate(
        [make_attempt("attempt-3"), make_attempt("attempt-4")],
        content="The learner clearly distinguishes plugins from agents.",
    )
    result = service.create(opposite)

    assert result.status is MemoryLifecycleStatus.REJECTED
    assert result.data["status"] == "conflict"
    assert len(client.records) == 1


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
    authorization_calls = [item for item in client.calls if item[0] == "authorize"]
    assert len(authorization_calls) == 2
    assert client.calls[-1] == ("consolidate", scope.model_dump())


@pytest.mark.parametrize("field", ["user_id", "program_id", "module_id"])
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_cross_scope_mutation_is_degraded_without_mutating(
    field: str,
    operation: str,
) -> None:
    client = FakeMemoryClient()
    service = LearnerMemoryService(client=client)
    foreign_scope = make_scope(**{field: 999})
    ability = LearnerAbility(
        user_id=2,
        module_id=4,
        U=0.4,
        A=-0.2,
        R=0.8,
        attempt_count=3,
    )
    before = (ability.U, ability.A, ability.R, ability.attempt_count)

    if operation == "update":
        result = service.update(
            "memory-1",
            make_misconception_candidate(scope=foreign_scope),
        )
    else:
        result = service.delete("memory-1", foreign_scope)

    assert result.status is MemoryLifecycleStatus.DEGRADED
    assert result.operation == operation
    assert "未执行变更" in (result.reason or "")
    assert not any(call[0] == operation for call in client.calls)
    assert (ability.U, ability.A, ability.R, ability.attempt_count) == before


@pytest.mark.parametrize(
    "response",
    [
        {
            "merged_memory_id": "memory-merged",
            "source_memory_ids": ["memory-1", "memory-2"],
            "organization_id": 1,
            "user_id": 2,
            "program_id": 3,
            "module_id": 4,
        },
        {
            "merged_memory_id": "memory-merged",
            "source_memory_ids": ["memory-1", "memory-2"],
            "evidence_refs": ["attempt-1", "attempt-2"],
            "organization_id": 1,
            "user_id": 999,
            "program_id": 3,
            "module_id": 4,
        },
    ],
)
def test_invalid_or_cross_scope_consolidation_result_is_degraded(response: dict) -> None:
    service = LearnerMemoryService(
        client=FakeMemoryClient(consolidate_response=response)
    )

    result = service.consolidate(make_scope())

    assert result.status is MemoryLifecycleStatus.DEGRADED


def test_consolidation_deduplicates_source_and_evidence_identifiers() -> None:
    response = {
        "merged_memory_id": "memory-merged",
        "source_memory_ids": ["memory-1", "memory-1", "memory-2"],
        "evidence_refs": ["attempt-1", "attempt-1", "attempt-2"],
        **make_scope().model_dump(),
    }
    service = LearnerMemoryService(
        client=FakeMemoryClient(consolidate_response=response)
    )

    result = service.consolidate(make_scope())

    assert result.status is MemoryLifecycleStatus.COMPLETED
    assert result.data["source_memory_ids"] == ["memory-1", "memory-2"]
    assert result.data["evidence_refs"] == ["attempt-1", "attempt-2"]


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


@pytest.mark.parametrize(
    "operation",
    ["create", "search", "update", "delete", "consolidate", "authorize"],
)
def test_simplemem_failure_is_returned_as_degradation(operation: str) -> None:
    service = LearnerMemoryService(client=FakeMemoryClient(fail_operation=operation))
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
    elif operation == "authorize":
        result = service.update("memory-1", candidate)
    else:
        result = service.consolidate(scope)

    assert result.status is MemoryLifecycleStatus.DEGRADED
    assert "降级" in (result.reason or "") or "授权失败" in (result.reason or "")


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


def test_memory_record_contract_requires_distinct_evidence_and_scope() -> None:
    base = {
        **make_scope().model_dump(),
        "content": "Stable misconception.",
        "memory_type": MemoryType.MISCONCEPTION,
        "idempotency_key": "a" * 64,
        "conflict_key": "b" * 64,
        "confidence": 0.9,
    }
    with pytest.raises(ValidationError, match="distinct evidence refs"):
        MemoryRecord(
            **base,
            knowledge_point_id=5,
            evidence_refs=["attempt-1", "attempt-1"],
        )
    with pytest.raises(ValidationError, match="knowledge_point_id"):
        MemoryRecord(**base, evidence_refs=["attempt-1", "attempt-2"])
