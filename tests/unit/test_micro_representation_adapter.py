from __future__ import annotations

from pathlib import Path

import pytest
from integrations.contracts import MicroDetectionRequest
from integrations.http_client import IntegrationUnavailable
from integrations.micro_representation import MicroRepresentationClient


def build_request(audio_uri: str) -> MicroDetectionRequest:
    return MicroDetectionRequest(
        trace_id="trace-001",
        organization_id=1,
        learner_id=7,
        session_id=11,
        program_id=1,
        module_id=2,
        knowledge_point_id=5,
        source_type="learner_voice",
        audio_uri=audio_uri,
        consent_granted=True,
        speaker_mapping_confirmed=True,
    )


def test_local_audio_is_uploaded_without_exposing_file_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "learner turn.webm"
    audio_path.write_bytes(b"test-audio")
    client = MicroRepresentationClient("http://detector.test")
    captured: dict = {}

    def fake_upload(path, *, filename, content, content_type, data):
        captured.update(
            path=path,
            filename=filename,
            content=content,
            content_type=content_type,
            data=data,
        )
        return {"job_id": "external-001", "status": "queued"}

    monkeypatch.setattr(client.http, "upload", fake_upload)

    result = client.create_job(build_request(audio_path.as_uri()))

    assert result == {"job_id": "external-001", "status": "queued"}
    assert captured["path"] == "/v1/detection/jobs"
    assert captured["filename"] == "learner turn.webm"
    assert captured["content"] == b"test-audio"
    assert captured["content_type"] == "audio/webm"
    assert "audio_uri" not in captured["data"]
    assert captured["data"]["consent_granted"] == "true"
    assert captured["data"]["module_id"] == "2"


def test_remote_audio_uri_uses_json_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MicroRepresentationClient("http://detector.test")
    captured: dict = {}

    def fake_request(method, path, payload):
        captured.update(method=method, path=path, payload=payload)
        return {"job_id": "external-002", "status": "processing"}

    monkeypatch.setattr(client.http, "request", fake_request)

    result = client.create_job(build_request("https://media.example/turn.webm"))

    assert result["job_id"] == "external-002"
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/detection/jobs"
    assert captured["payload"]["audio_uri"] == "https://media.example/turn.webm"


def test_local_audio_must_exist(tmp_path: Path) -> None:
    client = MicroRepresentationClient("http://detector.test")

    with pytest.raises(IntegrationUnavailable, match="audio file does not exist"):
        client.create_job(build_request((tmp_path / "missing.webm").as_uri()))


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"job_id": "", "status": "queued"},
        {"job_id": "external-003", "status": "unknown"},
    ],
)
def test_create_job_rejects_invalid_detector_response(
    monkeypatch: pytest.MonkeyPatch,
    response: dict,
) -> None:
    client = MicroRepresentationClient("http://detector.test")
    monkeypatch.setattr(client.http, "request", lambda method, path, payload: response)

    with pytest.raises(IntegrationUnavailable, match="invalid detection job response"):
        client.create_job(build_request("https://media.example/turn.webm"))


def test_get_job_validates_identity_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MicroRepresentationClient("http://detector.test")
    monkeypatch.setattr(
        client.http,
        "request",
        lambda method, path, payload: {"job_id": "another-job", "status": "completed"},
    )

    with pytest.raises(IntegrationUnavailable, match="job_id does not match"):
        client.get_job("external-004")


def test_get_events_validates_event_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MicroRepresentationClient("http://detector.test")
    monkeypatch.setattr(
        client.http,
        "request",
        lambda method, path, payload: {
            "items": [
                {
                    "event_id": "event-001",
                    "job_id": "external-005",
                    "organization_id": 1,
                    "learner_id": 7,
                    "session_id": 11,
                    "module_id": 2,
                    "knowledge_point_id": 5,
                    "source_type": "learner_voice",
                    "event_type": "hesitation",
                    "start_ms": 1200,
                    "end_ms": 1800,
                    "confidence": 0.84,
                    "speaker_mapping_confirmed": True,
                }
            ]
        },
    )

    events = client.get_events("external-005")

    assert len(events) == 1
    assert events[0].event_type == "hesitation"
    assert events[0].start_ms == 1200


def test_get_events_rejects_event_from_another_job(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MicroRepresentationClient("http://detector.test")
    monkeypatch.setattr(
        client.http,
        "request",
        lambda method, path, payload: {
            "items": [
                {
                    "event_id": "event-002",
                    "job_id": "another-job",
                    "organization_id": 1,
                    "learner_id": 7,
                    "module_id": 2,
                    "source_type": "learner_voice",
                    "event_type": "thinking_pause",
                    "start_ms": 2000,
                    "end_ms": 3200,
                    "confidence": 0.79,
                    "speaker_mapping_confirmed": True,
                }
            ]
        },
    )

    with pytest.raises(IntegrationUnavailable, match="event job_id does not match"):
        client.get_events("external-006")
