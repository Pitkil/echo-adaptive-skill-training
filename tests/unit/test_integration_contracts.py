from __future__ import annotations

import pytest
from integrations.contracts import (
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
