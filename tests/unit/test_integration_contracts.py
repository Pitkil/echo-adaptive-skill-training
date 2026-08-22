from __future__ import annotations

import pytest
from integrations.contracts import (
    MicroDetectionJobResult,
    MicroDetectionRequest,
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


def test_mentor_identity_requires_explicit_speaker_confirmation() -> None:
    common = {
        "trace_id": "trace-mentor",
        "organization_id": 1,
        "program_id": 1,
        "module_id": 2,
        "source_type": "mentor_recording",
        "audio_uri": "https://media.example/lesson.wav",
        "consent_granted": True,
    }
    with pytest.raises(ValidationError, match="confirmed speaker mapping"):
        MicroDetectionRequest(
            **common,
            learner_id=7,
            speaker_mapping_confirmed=False,
        )
    with pytest.raises(ValidationError, match="confirmed speaker mapping"):
        MicroDetectionRequest(
            **common,
            learner_id=None,
            speaker_mapping_confirmed=True,
        )
    with pytest.raises(ValidationError, match="confirmed speaker mapping"):
        MicroRepresentationEvent(
            event_id="mentor-event",
            job_id="mentor-job",
            organization_id=1,
            learner_id=7,
            module_id=2,
            source_type="mentor_recording",
            event_type="hesitation",
            start_ms=100,
            end_ms=200,
            confidence=0.8,
            speaker_mapping_confirmed=False,
        )


def test_failed_detection_job_requires_reason() -> None:
    with pytest.raises(ValidationError, match="requires error_message"):
        MicroDetectionJobResult(job_id="detector-001", status="failed")


def test_detection_job_duration_is_positive_when_present() -> None:
    result = MicroDetectionJobResult(
        job_id="detector-001",
        status="completed",
        audio_duration_ms=4200,
    )

    assert result.audio_duration_ms == 4200
    with pytest.raises(ValidationError):
        MicroDetectionJobResult(
            job_id="detector-001",
            status="completed",
            audio_duration_ms=0,
        )


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
    assert MicroRepresentationEvent(
        event_id="e" * 100,
        job_id="detector-job",
        organization_id=1,
        learner_id=7,
        module_id=2,
        source_type="learner_voice",
        event_type="hesitation",
        start_ms=1,
        end_ms=2,
        confidence=0.8,
        speaker_mapping_confirmed=True,
    ).event_id == "e" * 100
