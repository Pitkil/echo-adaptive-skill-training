from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from integrations.contracts import MemoryRecord
from integrations.http_client import IntegrationUnavailable
from MIRT.analysis_agent import (
    CONTENT_FORMAT_BY_DIMENSION,
    LEARNER_PROFILE_REQUIREMENTS,
    LearnerInsightService,
)
from MIRT.memory_service import (
    LearnerMemoryService,
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidenceType,
    MemoryLifecycleStatus,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MEMBER_C_ROOT = REPOSITORY_ROOT / "docs" / "member-c"


def _load_json(name: str) -> dict:
    return json.loads((MEMBER_C_ROOT / name).read_text(encoding="utf-8"))


def _scored_evidence(profile_id: str, attempts: int, accuracy: float) -> list[dict]:
    correct_count = round(attempts * accuracy)
    return [
        {
            "attempt_id": f"{profile_id}-attempt-{index + 1}",
            "question_id": 200 + index,
            "knowledge_point_id": 23,
            "score": 1.0 if index < correct_count else 0.0,
            "is_correct": index < correct_count,
            "occurred_at": f"2026-02-{index + 1:02d}T10:00:00",
        }
        for index in range(attempts)
    ]


class _CaseMemoryClient:
    def __init__(self, *, configured: bool = True, forbid_authorization: bool = False) -> None:
        self.configured = configured
        self.forbid_authorization = forbid_authorization
        self.records: dict[str, str] = {}

    def upsert(self, record: MemoryRecord) -> dict:
        existing_id = self.records.get(record.idempotency_key)
        if existing_id is not None:
            return {
                "status": "unchanged",
                "memory_id": existing_id,
                "idempotency_key": record.idempotency_key,
                "conflict_memory_ids": [],
            }
        memory_id = f"case-memory-{len(self.records) + 1}"
        self.records[record.idempotency_key] = memory_id
        return {
            "status": "created",
            "memory_id": memory_id,
            "idempotency_key": record.idempotency_key,
            "conflict_memory_ids": [],
        }

    def authorize(self, memory_id: str, **scope: int) -> dict:
        if self.forbid_authorization:
            raise IntegrationUnavailable("403 memory scope mismatch")
        return {"allowed": True, "memory_id": memory_id, **scope}


def _memory_candidate(case: dict) -> MemoryCandidate:
    execution = case["execution"]
    evidence: list[MemoryEvidence] = []
    for index, identity in enumerate(case["evidence_identity"]):
        common = {
            "reference_id": f"{case['case_id']}-reference-{index + 1}",
            "occurred_at": datetime(2026, 3, index + 1, tzinfo=UTC),
            "confidence": 0.9,
            "session_id": case["session_ids"][index],
        }
        if case["memory_type"] == "misconception":
            evidence.append(
                MemoryEvidence(
                    **common,
                    evidence_type=MemoryEvidenceType.SCORED_ATTEMPT,
                    attempt_id=identity.removeprefix("attempt:"),
                    question_id=100 + case["evidence_identity"].index(identity),
                    knowledge_point_id=execution["evidence_knowledge_point_ids"][index],
                    is_correct=False,
                    score=0.0,
                    misconception_key=execution["misconception_keys"][index],
                )
            )
        elif case["memory_type"] == "learning_preference":
            evidence.append(
                MemoryEvidence(
                    **common,
                    evidence_type=MemoryEvidenceType.PREFERENCE_OBSERVATION,
                    preference_key=execution["preference_keys"][index],
                    result_confirmed=execution["confirmed"][index],
                    result_value=execution["result_values"][index],
                )
            )
        else:
            evidence.append(
                MemoryEvidence(
                    **common,
                    evidence_type=MemoryEvidenceType.INTERVENTION_RESULT,
                    intervention_id=identity.removeprefix("intervention:"),
                    intervention_type=execution["intervention_types"][index],
                    result_confirmed=execution["confirmed"][index],
                    result_value=execution["result_values"][index],
                )
            )

    return MemoryCandidate(
        organization_id=1,
        user_id={"P1": 1, "P2": 2, "P3": 3}[case["learner_profile"]],
        program_id=1,
        module_id={"M1": 1, "M2": 2, "M3": 3}[case["module_id"]],
        knowledge_point_id=execution.get("knowledge_point_id"),
        session_id=case["session_ids"][-1],
        content=execution["content"],
        memory_type=case["memory_type"],
        evidence=evidence,
        metadata={"case_id": case["case_id"]},
    )


def _execute_memory_case(case: dict) -> tuple[MemoryLifecycleStatus, str, bool]:
    operation = case["execution"]["operation"]
    client = _CaseMemoryClient(
        configured=operation != "create_unavailable",
        forbid_authorization=operation == "update_forbidden",
    )
    service = LearnerMemoryService(client=client)
    candidate = _memory_candidate(case)

    if operation == "create_twice":
        service.create(candidate)
        result = service.create(candidate)
    elif operation == "update_forbidden":
        result = service.update("foreign-memory", candidate)
    else:
        result = service.create(candidate)

    if result.status is MemoryLifecycleStatus.COMPLETED:
        outcome = result.data["status"]
    elif result.status is MemoryLifecycleStatus.DEGRADED:
        outcome = "audit_record_retained" if result.memory_record else "scope_forbidden"
    else:
        reason = result.reason or ""
        if "语义不同的证据编号" in reason:
            outcome = "insufficient_distinct_evidence"
        elif "知识点必须与候选误区一致" in reason:
            outcome = "knowledge_point_mismatch"
        elif "结果互相矛盾" in reason:
            outcome = "contradictory_evidence"
        elif "必须已确认结果" in reason:
            outcome = "unconfirmed_result"
        else:
            raise AssertionError(f"Unmapped lifecycle result for {case['case_id']}: {reason}")
    return result.status, outcome, result.memory_record is not None


def test_fixed_profiles_cover_p1_p2_p3_with_distinct_single_resource_decisions() -> None:
    payload = _load_json("learner-profile-samples.json")
    profiles = payload["profiles"]

    assert len(profiles) == 3
    assert {item["profile_id"] for item in profiles} == {"P1", "P2", "P3"}
    assert payload["module_id"] == "M2"
    assert payload["knowledge_point_id"] == "M2-KP3"
    assert all(len(item["evidence_refs"]) >= 2 for item in profiles)

    service = LearnerInsightService(db_session=None)
    for item in profiles:
        ability = item["ability"]
        scored_evidence = _scored_evidence(
            item["profile_id"],
            item["attempt_count"],
            item["average_accuracy"],
        )
        blind_spots = [
            {
                "knowledge_point_id": index + 1,
                "evidence": [],
            }
            for index in range(item["blind_spot_count"])
        ]
        classified = LearnerInsightService._classify_learner_profile(
            ability_values=ability,
            profile_accuracy=item["average_accuracy"],
            blind_spots=blind_spots,
            scored_evidence=scored_evidence,
        )
        expected = item["expected"]
        weakest_dimension = min(ability, key=ability.get)
        recommendation = service._build_recommendation(
            ability_payload={**ability, "attempt_count": item["attempt_count"]},
            profile_accuracy=item["average_accuracy"],
            scored_evidence=scored_evidence,
            blind_spots=blind_spots,
            learning_path=[
                {
                    "knowledge_point_id": 23,
                    "code": payload["knowledge_point_id"],
                    "name": "记忆与相关内容检索",
                    "status": "priority_review" if blind_spots else "planned",
                }
            ],
            micro={"confirmed_event_count": 0, "items": []},
            memory_items=[
                {
                    "memory_id": f"{item['profile_id']}-memory-1",
                    "memory_type": "learning_preference",
                    "content": item["memory_hints"][0],
                }
            ],
        )

        assert classified["type"] == expected["profile_type"]
        assert classified["label"] == item["label"]
        assert classified["content_requirements"]["support_level"] == expected["support_level"]
        assert CONTENT_FORMAT_BY_DIMENSION[weakest_dimension] == expected["resource_type"]
        assert recommendation["learner_profile"]["type"] == expected["profile_type"]
        assert recommendation["recommended_difficulty"] == expected["difficulty"]
        assert recommendation["primary_content_decision"]["resource_type"] == expected[
            "resource_type"
        ]
        assert recommendation["primary_content_decision"]["resource_count"] == 1
        assert (
            recommendation["primary_content_decision"]["selection_policy"]
            == "single_most_needed"
        )

    assert {
        item["expected"]["resource_type"] for item in profiles
    } == {"custom_note", "practice_guide", "staged_test"}
    assert {
        item["expected"]["difficulty"] for item in profiles
    } == {"foundation", "standard", "advanced"}
    assert {
        profile: requirements["support_level"]
        for profile, requirements in LEARNER_PROFILE_REQUIREMENTS.items()
    } == {"P1": "high", "P2": "medium", "P3": "low"}


def test_memory_difference_cases_cover_profiles_modules_and_lifecycle_boundaries() -> None:
    payload = _load_json("memory-difference-cases.json")
    cases = payload["cases"]

    assert payload["total_cases"] == 10
    assert len(cases) == 10
    assert len({item["case_id"] for item in cases}) == 10
    assert {item["learner_profile"] for item in cases} == {"P1", "P2", "P3"}
    assert {item["module_id"] for item in cases} == {"M1", "M2", "M3"}
    assert {item["memory_type"] for item in cases} == {
        "misconception",
        "learning_preference",
        "intervention_outcome",
    }
    assert Counter(item["expected"]["status"] for item in cases) == {
        MemoryLifecycleStatus.COMPLETED.value: 4,
        MemoryLifecycleStatus.REJECTED.value: 4,
        MemoryLifecycleStatus.DEGRADED.value: 2,
    }
    assert all(len(item["session_ids"]) >= 2 for item in cases)
    assert all(len(set(item["session_ids"])) >= 2 for item in cases)
    assert all(len(item["evidence_identity"]) >= 2 for item in cases)
    assert all(item.get("execution", {}).get("operation") for item in cases)
    assert all(item["expected"]["mirt_unchanged"] for item in cases)

    outcomes = {item["expected"]["outcome"] for item in cases}
    assert outcomes == {
        "created",
        "insufficient_distinct_evidence",
        "knowledge_point_mismatch",
        "contradictory_evidence",
        "unconfirmed_result",
        "unchanged",
        "scope_forbidden",
        "audit_record_retained",
    }

    for item in cases:
        status, outcome, has_validated_record = _execute_memory_case(item)
        assert status.value == item["expected"]["status"], item["case_id"]
        assert outcome == item["expected"]["outcome"], item["case_id"]
        if outcome == "audit_record_retained":
            assert has_validated_record, item["case_id"]
