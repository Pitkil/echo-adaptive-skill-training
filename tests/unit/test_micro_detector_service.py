from __future__ import annotations

import io
import wave

import pytest
from fastapi.testclient import TestClient

from services.micro_detector_real import app as service


@pytest.fixture(autouse=True)
def isolated_job_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_DETECTOR_JOB_STORE", str(tmp_path / "jobs.json"))
    service._jobs.clear()
    yield
    service._jobs.clear()


def _wav_bytes(duration_ms: int = 100) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\0\0" * (16_000 * duration_ms // 1000))
    return stream.getvalue()


def _form() -> dict[str, str]:
    return {
        "trace_id": "trace-1",
        "organization_id": "1",
        "learner_id": "2",
        "session_id": "3",
        "program_id": "1",
        "module_id": "1",
        "source_type": "learner_voice",
        "consent_granted": "true",
        "speaker_mapping_confirmed": "false",
    }


def test_health_identifies_real_detector(tmp_path, monkeypatch) -> None:
    wavlm_root = tmp_path / "wavlm-base-plus"
    wavlm_root.mkdir()
    (wavlm_root / "config.json").write_text("{}", encoding="utf-8")
    (wavlm_root / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    with (wavlm_root / "model.safetensors").open("wb") as weight:
        weight.truncate(300 * 1024 * 1024)
    (tmp_path / "behavior_prototypes.pt").write_bytes(b"prototype")
    monkeypatch.setenv("MICRO_MODEL_ROOT", str(tmp_path))

    response = TestClient(service.app).get("/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "real"


def test_health_rejects_lfs_pointer_instead_of_claiming_real_mode(tmp_path, monkeypatch) -> None:
    wavlm_root = tmp_path / "wavlm-base-plus"
    wavlm_root.mkdir()
    (wavlm_root / "config.json").write_text("{}", encoding="utf-8")
    (wavlm_root / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    (wavlm_root / "model.safetensors").write_text(
        "version https://git-lfs.github.com/spec/v1\n",
        encoding="utf-8",
    )
    (tmp_path / "behavior_prototypes.pt").write_bytes(b"prototype")
    monkeypatch.setenv("MICRO_MODEL_ROOT", str(tmp_path))

    response = TestClient(service.app).get("/health")

    assert response.status_code == 503
    assert "model.safetensors" in response.json()["detail"]


def test_detection_job_preserves_scope_and_returns_events(monkeypatch) -> None:
    def complete_job(job_id, audio_path) -> None:
        with service._jobs_lock:
            stored = service._jobs[job_id]
            stored.events = [
                service.DetectionEvent(
                    event_id=f"{job_id}-event-1",
                    job_id=job_id,
                    organization_id=stored.scope["organization_id"],
                    learner_id=stored.scope["learner_id"],
                    session_id=stored.scope["session_id"],
                    module_id=stored.scope["module_id"],
                    source_type=stored.scope["source_type"],
                    event_type="hesitation",
                    start_ms=10,
                    end_ms=90,
                    confidence=0.8,
                )
            ]
            stored.result = stored.result.model_copy(update={"status": "completed"})
        audio_path.unlink(missing_ok=True)

    monkeypatch.setattr(service, "_detect", complete_job)
    client = TestClient(service.app)

    created = client.post(
        "/v1/detection/jobs",
        data=_form(),
        files={"audio": ("answer.wav", _wav_bytes(), "audio/wav")},
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload["status"] == "queued"
    assert payload["audio_duration_ms"] == 100
    status = client.get(f"/v1/detection/jobs/{payload['job_id']}")
    assert status.json()["status"] == "completed"
    events = client.get(f"/v1/detection/jobs/{payload['job_id']}/events")
    assert events.status_code == 200
    assert events.json()["items"][0]["organization_id"] == 1
    assert events.json()["items"][0]["learner_id"] == 2
    assert service._jobs[payload["job_id"]].scope["trace_id"] == "trace-1"
    persisted = service._job_store_path().read_text(encoding="utf-8")
    assert "trace-1" in persisted
    assert "answer.wav" not in persisted


def test_detection_job_rejects_missing_consent() -> None:
    form = _form()
    form["consent_granted"] = "false"

    response = TestClient(service.app).post(
        "/v1/detection/jobs",
        data=form,
        files={"audio": ("answer.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 422


def test_segment_events_are_restored_to_original_recording_timeline() -> None:
    raw_results = [
        {
            "file": "segment_0000.wav",
            "label": "犹豫",
            "start": 29.0,
            "end": 30.0,
            "score": 0.8,
        },
        {
            "file": "segment_0001.wav",
            "label": "犹豫",
            "start": 0.0,
            "end": 1.5,
            "score": 0.9,
        },
    ]

    def merge_adjacent(items):
        assert items[0]["start"] == 29.0
        assert items[1]["start"] == 30.0
        return [
            {
                "file": items[0]["file"],
                "label": "犹豫",
                "start": 29.0,
                "end": 31.5,
                "score": 0.9,
            }
        ]

    restored = service._restore_original_timeline(
        raw_results,
        {"segment_0000.wav": 0, "segment_0001.wav": 30_000},
        merge_adjacent,
        "lesson.wav",
    )

    assert restored == [
        {
            "file": "lesson.wav",
            "label": "犹豫",
            "start": 29.0,
            "end": 31.5,
            "score": 0.9,
        }
    ]


def test_unknown_segment_is_rejected_instead_of_saving_wrong_time() -> None:
    raw_results = [
        {
            "file": "unexpected.wav",
            "label": "犹豫",
            "start": 0.0,
            "end": 1.5,
            "score": 0.8,
        }
    ]

    try:
        service._restore_original_timeline(raw_results, {}, lambda items: items, "lesson.wav")
    except RuntimeError as exc:
        assert "unknown audio segment" in str(exc)
    else:
        raise AssertionError("unknown detector segment must fail closed")


def test_completed_jobs_survive_service_restart(tmp_path, monkeypatch) -> None:
    store = tmp_path / "persistent-jobs.json"
    monkeypatch.setenv("MICRO_DETECTOR_JOB_STORE", str(store))
    stored = service.StoredJob(
        result=service.DetectionJob(job_id="speech-complete", status="completed"),
        scope={"trace_id": "trace-complete"},
        events=[],
    )
    with service._jobs_lock:
        service._jobs[stored.result.job_id] = stored
        service._persist_jobs_locked()
    service._jobs.clear()

    service._restore_jobs()

    assert service._jobs[stored.result.job_id].result.status == "completed"
    assert service._jobs[stored.result.job_id].scope["trace_id"] == "trace-complete"


def test_interrupted_job_is_failed_explicitly_after_restart(tmp_path, monkeypatch) -> None:
    store = tmp_path / "interrupted-jobs.json"
    monkeypatch.setenv("MICRO_DETECTOR_JOB_STORE", str(store))
    stored = service.StoredJob(
        result=service.DetectionJob(job_id="speech-processing", status="processing"),
        scope={"trace_id": "trace-processing"},
    )
    with service._jobs_lock:
        service._jobs[stored.result.job_id] = stored
        service._persist_jobs_locked()
    service._jobs.clear()

    service._restore_jobs()

    restored = service._jobs[stored.result.job_id].result
    assert restored.status == "failed"
    assert "restarted" in restored.error_message
