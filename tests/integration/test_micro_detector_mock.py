from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from integrations.contracts import MicroDetectionRequest
from integrations.micro_representation import MicroRepresentationClient

SERVICE_ROOT = Path(__file__).resolve().parents[2] / "services" / "micro_detector"
sys.path.insert(0, str(SERVICE_ROOT))

from micro_detector.app import _jobs, app  # noqa: E402
from micro_detector.schemas import DetectionEvent, DetectionJob  # noqa: E402


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


def test_mock_response_models_enforce_the_shared_contract() -> None:
    with pytest.raises(ValueError, match="error_message"):
        DetectionJob(job_id="failed-job", status="failed")
    with pytest.raises(ValueError, match="end_ms"):
        DetectionEvent(
            event_id="e" * 100,
            job_id="detector-job",
            organization_id=1,
            learner_id=7,
            module_id=2,
            source_type="learner_voice",
            event_type="hesitation",
            start_ms=20,
            end_ms=10,
            confidence=0.8,
            speaker_mapping_confirmed=True,
        )


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
    assert first.json()["audio_duration_ms"] == 4000
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
                learner_id=None,
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


def test_echo_adapter_and_mock_service_share_the_multipart_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    detector = TestClient(app)

    def fake_post(url, *, files, data, timeout):
        return detector.post(urlparse(url).path, files=files, data=data)

    def fake_request(*, method, url, json, timeout):
        return detector.request(method, urlparse(url).path, json=json)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "request", fake_request)
    audio_path = tmp_path / "turn.wav"
    audio_path.write_bytes(b"RIFF-adapter-to-mock")
    client = MicroRepresentationClient("http://micro-detector:8030")

    created = client.create_job(
        MicroDetectionRequest(
            trace_id="echo-job-direct-completed",
            organization_id=1,
            learner_id=7,
            session_id=11,
            program_id=1,
            module_id=2,
            knowledge_point_id=5,
            source_type="learner_voice",
            audio_uri=audio_path.as_uri(),
            consent_granted=True,
            speaker_mapping_confirmed=True,
        )
    )
    detector_job_id = created["job_id"]

    assert created["status"] == "completed"
    assert created["audio_duration_ms"] == 4000
    assert client.get_job(detector_job_id)["job_id"] == detector_job_id
    events = client.get_events(detector_job_id)
    assert len(events) == 1
    assert events[0].job_id == detector_job_id
