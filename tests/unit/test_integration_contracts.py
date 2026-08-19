from __future__ import annotations

import pytest
from integrations.contracts import (
    MicroDetectionJobResult,
    MicroRepresentationEvent,
    RetrievalHit,
    normalize_retrieval_payload,
)
from pydantic import ValidationError


def test_retrieval_payload_normalizes_to_enterprise_shape() -> None:
    result = normalize_retrieval_payload(
        {
            "items": [
                {
                    "text": "Grounded answer evidence.",
                    "score": 0.91,
                        "metadata": {
                            "filename": "guide.pdf",
                            "chapter": "Evaluation",
                            "knowledge_base_id": 3,
                            "module_id": 2,
                        },
                }
            ]
        }
    )

    assert result[0]["text"] == "Grounded answer evidence."
    assert result[0]["metadata"]["filename"] == "guide.pdf"
    assert result[0]["score"] == pytest.approx(0.91)


def test_retrieval_hit_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        RetrievalHit(text="")


def test_micro_representation_validates_time_and_confidence() -> None:
    event = MicroRepresentationEvent(
        event_id="event-001",
        job_id="job-001",
        organization_id=1,
        learner_id=7,
        module_id=2,
        source_type="learner_voice",
        event_type="hesitation",
        start_ms=1200,
        end_ms=1800,
        confidence=0.84,
    )

    assert event.end_ms > event.start_ms

    with pytest.raises(ValidationError):
        MicroRepresentationEvent(
            event_id="event-002",
            job_id="job-001",
            organization_id=1,
            learner_id=7,
            module_id=2,
            source_type="learner_voice",
            event_type="hesitation",
            start_ms=1200,
            end_ms=1800,
            confidence=1.2,
        )


def test_failed_detection_job_requires_reason() -> None:
    with pytest.raises(ValidationError, match="requires error_message"):
        MicroDetectionJobResult(job_id="detector-001", status="failed")


def test_event_accepts_same_job_id_length_as_job_result() -> None:
    detector_job_id = "d" * 100
    assert MicroDetectionJobResult(job_id=detector_job_id, status="completed").job_id == detector_job_id
    event = MicroRepresentationEvent(
        event_id="event-long-job-id",
        job_id=detector_job_id,
        organization_id=1,
        learner_id=7,
        module_id=2,
        source_type="learner_voice",
        event_type="hesitation",
        start_ms=1,
        end_ms=2,
        confidence=0.8,
    )
    assert event.job_id == detector_job_id
