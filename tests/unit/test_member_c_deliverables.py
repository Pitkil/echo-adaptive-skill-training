from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from MIRT.analysis_agent import (
    CONTENT_FORMAT_BY_DIMENSION,
    LEARNER_PROFILE_REQUIREMENTS,
    LearnerInsightService,
)
from MIRT.memory_service import MemoryLifecycleStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MEMBER_C_ROOT = REPOSITORY_ROOT / "docs" / "member-c"


def _load_json(name: str) -> dict:
    return json.loads((MEMBER_C_ROOT / name).read_text(encoding="utf-8"))


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
        blind_spots = [
            {
                "knowledge_point_id": index + 1,
                "evidence": [],
            }
            for index in range(item["blind_spot_count"])
        ]
        classified = LearnerInsightService._classify_learner_profile(
            attempts=item["attempt_count"],
            ability_values=ability,
            average_accuracy=item["average_accuracy"],
            blind_spots=blind_spots,
        )
        expected = item["expected"]
        weakest_dimension = min(ability, key=ability.get)
        recommendation = service._build_recommendation(
            ability_payload={**ability, "attempt_count": item["attempt_count"]},
            average_accuracy=item["average_accuracy"],
            blind_spots=blind_spots,
            mastered=[],
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
