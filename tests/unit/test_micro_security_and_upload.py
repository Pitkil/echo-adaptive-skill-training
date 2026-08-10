from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from app import (
    create_micro_job_record,
    get_micro_job,
    queue_awaiting_micro_job_retry,
    require_micro_callback_identity,
    require_micro_job_access,
    save_audio_file,
)
from config import Config
from database import (
    Base,
    ChatSession,
    KnowledgeBase,
    KnowledgePoint,
    MicroDetectionJob,
    Organization,
    TrainingModule,
    TrainingProgram,
    User,
    UserRole,
)
from fastapi import BackgroundTasks, HTTPException, UploadFile
from integrations.contracts import MicroSource
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers


def make_user(user_id: int, role: str, organization_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=role, organization_id=organization_id)


def make_job(**overrides: object) -> SimpleNamespace:
    values = {
        "organization_id": 1,
        "source_type": MicroSource.LEARNER_VOICE.value,
        "learner_id": 7,
        "created_by_user_id": 7,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_audio(content: bytes, filename: str = "turn.wav") -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": "audio/wav"}),
    )


def make_database_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    organization = Organization(code="ORG", name="Test Organization")
    db.add(organization)
    db.flush()
    learner = User(
        organization_id=organization.id,
        username="learner",
        hashed_password="unused",
        role=UserRole.LEARNER.value,
    )
    other_learner = User(
        organization_id=organization.id,
        username="other-learner",
        hashed_password="unused",
        role=UserRole.LEARNER.value,
    )
    knowledge_base = KnowledgeBase(organization_id=organization.id, code="KB", name="KB")
    program = TrainingProgram(organization_id=organization.id, code="P", name="Program")
    db.add_all([learner, other_learner, knowledge_base, program])
    db.flush()
    module = TrainingModule(
        program_id=program.id,
        knowledge_base_id=knowledge_base.id,
        code="M1",
        name="Module",
        sequence=1,
    )
    db.add(module)
    db.flush()
    point = KnowledgePoint(module_id=module.id, code="KP", name="Point", sequence=1)
    db.add(point)
    db.flush()
    session = ChatSession(
        user_id=other_learner.id,
        program_id=program.id,
        module_id=module.id,
        knowledge_base_id=knowledge_base.id,
    )
    db.add(session)
    db.commit()
    return db, organization, learner, other_learner, module, point, session


def test_learner_cannot_read_another_learners_job() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_micro_job_access(
            make_job(learner_id=8, created_by_user_id=8),
            make_user(7, UserRole.LEARNER.value),
        )
    assert exc_info.value.status_code == 404


def test_mentor_can_only_read_a_job_they_created() -> None:
    require_micro_job_access(
        make_job(created_by_user_id=10),
        make_user(10, UserRole.MENTOR.value),
    )
    with pytest.raises(HTTPException) as exc_info:
        require_micro_job_access(
            make_job(created_by_user_id=11),
            make_user(10, UserRole.MENTOR.value),
        )
    assert exc_info.value.status_code == 404


def test_callback_requires_independent_service_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config.security, "MICRO_CALLBACK_SECRET", "service-secret")
    require_micro_callback_identity("service-secret")
    with pytest.raises(HTTPException) as exc_info:
        require_micro_callback_identity("ordinary-user-token")
    assert exc_info.value.status_code == 401


def test_audio_is_streamed_hashed_and_size_limited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(Config.upload, "MAX_FILE_SIZE", 8)

    with pytest.raises(HTTPException) as exc_info:
        save_audio_file("too-large", make_audio(b"123456789"))
    assert exc_info.value.status_code == 413
    assert not list(tmp_path.rglob("too-large*"))

    path, digest, size = save_audio_file("valid", make_audio(b"12345678"))
    assert size == 8
    assert len(digest) == 64
    assert path.read_bytes() == b"12345678"


def test_audio_extension_and_content_type_are_validated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        save_audio_file("invalid", make_audio(b"audio", filename="turn.exe"))
    assert exc_info.value.status_code == 415


def test_learner_cannot_attach_another_learners_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, learner, _, module, point, session = make_database_context()

    with pytest.raises(HTTPException) as exc_info:
        create_micro_job_record(
            db,
            user=learner,
            module_id=module.id,
            source_type=MicroSource.LEARNER_VOICE,
            audio=make_audio(b"audio"),
            learner_id=learner.id,
            session_id=session.id,
            knowledge_point_id=point.id,
        )

    assert exc_info.value.status_code == 403
    assert not list(tmp_path.rglob("*.wav"))


def test_identical_upload_is_deduplicated_by_database_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, learner, _, module, point, _ = make_database_context()
    values = {
        "user": learner,
        "module_id": module.id,
        "source_type": MicroSource.LEARNER_VOICE,
        "learner_id": learner.id,
        "session_id": None,
        "knowledge_point_id": point.id,
    }

    first = create_micro_job_record(db, audio=make_audio(b"same-audio"), **values)
    db.commit()
    second = create_micro_job_record(db, audio=make_audio(b"same-audio"), **values)

    assert first.is_created is True
    assert second.is_created is False
    assert first.job.id == second.job.id
    assert first.job.dedupe_key
    assert db.query(MicroDetectionJob).count() == 1
    assert len(list(tmp_path.rglob("*.wav"))) == 1


def test_awaiting_detector_job_is_queued_only_once() -> None:
    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="awaiting-job",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="awaiting_detector",
    )
    db.add(job)
    db.commit()
    tasks = BackgroundTasks()

    assert queue_awaiting_micro_job_retry(db, job, tasks) is True
    assert queue_awaiting_micro_job_retry(db, job, tasks) is False
    assert job.status == "queued"
    assert len(tasks.tasks) == 1


def test_flush_failure_removes_saved_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, learner, _, module, point, _ = make_database_context()

    def fail_flush(*args, **kwargs) -> None:
        raise SQLAlchemyError("forced flush failure")

    monkeypatch.setattr(db, "flush", fail_flush)
    with pytest.raises(SQLAlchemyError, match="forced flush failure"):
        create_micro_job_record(
            db,
            user=learner,
            module_id=module.id,
            source_type=MicroSource.LEARNER_VOICE,
            audio=make_audio(b"audio-to-clean"),
            learner_id=learner.id,
            session_id=None,
            knowledge_point_id=point.id,
        )

    assert not list(tmp_path.rglob("*.wav"))


def test_unconfigured_detector_keeps_waiting_status_and_returns_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnconfiguredDetector:
        configured = False

    monkeypatch.setattr("app.MicroRepresentationClient", UnconfiguredDetector)
    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="unconfigured-job",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="awaiting_detector",
    )
    db.add(job)
    db.commit()
    tasks = BackgroundTasks()

    result = get_micro_job(job.id, tasks, db, learner)

    assert result["status"] == "awaiting_detector"
    assert result["degradation"] == "微表征检测服务未配置，任务仍在等待检测器"
    assert tasks.tasks == []
