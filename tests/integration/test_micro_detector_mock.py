from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[2] / "services" / "micro_detector"
sys.path.insert(0, str(SERVICE_ROOT))

from micro_detector.app import _jobs, app  # noqa: E402


def request_fields(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "trace_id": "trace-mock-001",
        "organization_id": 1,
        "learner_id": 7,
        "session_id": 11,
        "program_id": 1,
        "module_id": 2,
        "knowledge_point_id": 5,
        "source_type": "learner_voice",
        "consent_granted": True,
        "speaker_mapping_confirmed": True,
    }
    fields.update(overrides)
    return fields


def setup_function() -> None:
    _jobs.clear()


def test_health_identifies_mock_mode() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "mode": "mock",
        "model_loaded": False,
        "index_loaded": False,
    }


def test_uploaded_audio_completes_contract_and_is_idempotent() -> None:
    client = TestClient(app)
    first = client.post(
        "/v1/detection/jobs",
        data=request_fields(),
        files={"audio": ("turn.wav", b"RIFF-mock-audio", "audio/wav")},
    )
    second = client.post(
        "/v1/detection/jobs",
        data=request_fields(),
        files={"audio": ("turn.wav", b"RIFF-mock-audio", "audio/wav")},
    )

    assert first.status_code == 200
    assert second.json() == first.json()
    job_id = first.json()["job_id"]
    assert client.get(f"/v1/detection/jobs/{job_id}").json()["status"] == "completed"
    events = client.get(f"/v1/detection/jobs/{job_id}/events").json()["items"]
    assert len(events) == 1
    assert events[0]["job_id"] == job_id
    assert events[0]["event_type"] == "hesitation"


def test_unconfirmed_mentor_speaker_is_not_bound_to_learner() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/detection/jobs",
        json={
            **request_fields(
                source_type="mentor_recording",
                speaker_mapping_confirmed=False,
            ),
            "audio_uri": "https://media.example/lesson.wav",
        },
    )

    job_id = response.json()["job_id"]
    event = client.get(f"/v1/detection/jobs/{job_id}/events").json()["items"][0]
    assert event["learner_id"] is None


def test_audio_without_consent_is_rejected() -> None:
    response = TestClient(app).post(
        "/v1/detection/jobs",
        json={
            **request_fields(consent_granted=False),
            "audio_uri": "https://media.example/turn.wav",
        },
    )

    assert response.status_code == 422
