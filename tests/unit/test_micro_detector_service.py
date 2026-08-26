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


def _create_fake_model_root(tmp_path, *, lfs_pointer: bool = False) -> None:
    wavlm_root = tmp_path / "wavlm-base-plus"
    wavlm_root.mkdir()
    (wavlm_root / "config.json").write_text("{}", encoding="utf-8")
    (wavlm_root / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    weight_path = wavlm_root / "model.safetensors"
    if lfs_pointer:
        weight_path.write_text(
            "version https://git-lfs.github.com/spec/v1\n",
            encoding="utf-8",
        )
    else:
        with weight_path.open("wb") as weight:
            weight.truncate(300 * 1024 * 1024)
    (tmp_path / "behavior_prototypes.pt").write_bytes(b"prototype")


def test_health_identifies_real_detector(tmp_path, monkeypatch) -> None:
    _create_fake_model_root(tmp_path)
    monkeypatch.setenv("MICRO_MODEL_ROOT", str(tmp_path))
    monkeypatch.setattr(service.shutil, "which", lambda executable: f"/tools/{executable}")

    response = TestClient(service.app).get("/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "real"


def test_health_rejects_lfs_pointer_instead_of_claiming_real_mode(tmp_path, monkeypatch) -> None:
    _create_fake_model_root(tmp_path, lfs_pointer=True)
    monkeypatch.setenv("MICRO_MODEL_ROOT", str(tmp_path))
    monkeypatch.setattr(service.shutil, "which", lambda executable: f"/tools/{executable}")

    response = TestClient(service.app).get("/health")

    assert response.status_code == 503
    assert "model.safetensors" in response.json()["detail"]


def test_health_rejects_missing_ffmpeg(tmp_path, monkeypatch) -> None:
    _create_fake_model_root(tmp_path)
    monkeypatch.setenv("MICRO_MODEL_ROOT", str(tmp_path))
    monkeypatch.setattr(service.shutil, "which", lambda _: None)

    response = TestClient(service.app).get("/health")

    assert response.status_code == 503
    assert "ffmpeg" in response.json()["detail"]


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


def test_non_wav_job_records_converted_duration_and_clamps_events(
    tmp_path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "answer.webm"
    audio_path.write_bytes(b"not-retained")
    stored = service.StoredJob(
        result=service.DetectionJob(job_id="speech-webm", status="queued"),
        scope={
            "organization_id": 1,
            "learner_id": 2,
            "session_id": 3,
            "module_id": 4,
            "knowledge_point_id": 5,
            "source_type": "learner_voice",
            "speaker_mapping_confirmed": True,
        },
    )
    with service._jobs_lock:
        service._jobs[stored.result.job_id] = stored
    monkeypatch.setattr(
        service,
        "_run_time_aligned_pipeline",
        lambda _: (
            [
                {
                    "label": "犹豫",
                    "start": 1.0,
                    "end": 2.0,
                    "score": 0.8,
                }
            ],
            1250,
        ),
    )

    service._detect(stored.result.job_id, audio_path)

    completed = service._jobs[stored.result.job_id]
    assert completed.result.status == "completed"
    assert completed.result.audio_duration_ms == 1250
    assert completed.events[0].end_ms == 1250
    assert not audio_path.exists()


def test_detection_cleanup_runs_when_processing_persistence_fails(
    tmp_path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "answer.wav"
    audio_path.write_bytes(_wav_bytes())

    def fail_update(*_args, **_kwargs) -> None:
        raise OSError("store unavailable")

    monkeypatch.setattr(service, "_update_job", fail_update)

    service._detect("missing-job", audio_path)

    assert not audio_path.exists()


def test_detection_job_rejects_missing_consent() -> None:
    form = _form()
    form["consent_granted"] = "false"

    response = TestClient(service.app).post(
        "/v1/detection/jobs",
        data=form,
        files={"audio": ("answer.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 422


def test_detection_job_rejects_oversized_audio_and_removes_temporary_file(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MICRO_DETECTOR_MAX_AUDIO_BYTES", "16")
    monkeypatch.setattr(service.tempfile, "gettempdir", lambda: str(tmp_path))

    response = TestClient(service.app).post(
        "/v1/detection/jobs",
        data=_form(),
        files={"audio": ("answer.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "audio file is too large"
    upload_root = tmp_path / "echo-micro-detector"
    assert list(upload_root.iterdir()) == []


@pytest.mark.parametrize("configured_value", ["0", "-1", "invalid"])
def test_invalid_audio_size_limit_fails_closed(monkeypatch, configured_value) -> None:
    monkeypatch.setenv("MICRO_DETECTOR_MAX_AUDIO_BYTES", configured_value)

    with pytest.raises(RuntimeError, match="must be a positive integer"):
        service._max_audio_bytes()


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
