from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import database as database_module
import pytest
from app import (
    MicroEventBatch,
    build_micro_dedupe_key,
    create_mentor_batch,
    create_micro_job,
    create_micro_job_record,
    get_mentor_batch,
    get_micro_job,
    ingest_micro_events,
    queue_awaiting_micro_job_retry,
    require_micro_callback_identity,
    require_micro_job_access,
    save_audio_file,
    submit_micro_job,
)
from config import Config
from database import (
    Base,
    ChatSession,
    EvidenceStatus,
    KnowledgeBase,
    KnowledgePoint,
    MicroDetectionJob,
    MicroRepresentationEvent,
    Organization,
    TrainingModule,
    TrainingProgram,
    User,
    UserRole,
    _ensure_micro_job_columns,
)
from fastapi import BackgroundTasks, HTTPException, UploadFile
from integrations.contracts import MicroRepresentationEvent as MicroEventContract
from integrations.contracts import MicroSource
from integrations.http_client import IntegrationContractError, IntegrationTransientError
from sqlalchemy import create_engine, inspect, text
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


def test_micro_job_migration_is_repeatable_for_legacy_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_engine = create_engine("sqlite:///:memory:")
    with legacy_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE micro_detection_jobs (id VARCHAR(64) PRIMARY KEY)")
        )
    monkeypatch.setattr(database_module, "engine", legacy_engine)

    _ensure_micro_job_columns()
    _ensure_micro_job_columns()

    inspector = inspect(legacy_engine)
    columns = {column["name"] for column in inspector.get_columns("micro_detection_jobs")}
    indexes = {index["name"] for index in inspector.get_indexes("micro_detection_jobs")}
    assert "audio_duration_ms" in columns
    assert "events_sync_status" in columns
    assert "uq_micro_detection_job_dedupe_key" in indexes


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


def test_identical_mentor_uploads_are_deduplicated_across_uploaders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, organization, _, _, module, point, session = make_database_context()
    first_mentor = User(
        organization_id=organization.id,
        username="mentor-one",
        hashed_password="unused",
        role=UserRole.MENTOR.value,
    )
    second_mentor = User(
        organization_id=organization.id,
        username="mentor-two",
        hashed_password="unused",
        role=UserRole.MENTOR.value,
    )
    db.add_all([first_mentor, second_mentor])
    db.commit()
    values = {
        "module_id": module.id,
        "source_type": MicroSource.MENTOR_RECORDING,
        "learner_id": None,
        "session_id": session.id,
        "knowledge_point_id": point.id,
    }

    first = create_micro_job_record(
        db, user=first_mentor, audio=make_audio(b"shared-audio"), **values
    )
    db.commit()
    second = create_micro_job_record(
        db, user=second_mentor, audio=make_audio(b"shared-audio"), **values
    )

    assert second.is_created is False
    assert second.job.id == first.job.id
    assert second.job.created_by_user_id == first_mentor.id
    assert db.query(MicroDetectionJob).count() == 1
    with pytest.raises(HTTPException) as exc_info:
        require_micro_job_access(second.job, second_mentor)
    assert exc_info.value.status_code == 404


def test_same_audio_in_different_business_scope_is_not_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, learner, other_learner, module, point, _ = make_database_context()

    first = create_micro_job_record(
        db,
        user=learner,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE,
        audio=make_audio(b"same-content"),
        learner_id=learner.id,
        session_id=None,
        knowledge_point_id=point.id,
    )
    db.commit()
    second = create_micro_job_record(
        db,
        user=other_learner,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE,
        audio=make_audio(b"same-content"),
        learner_id=other_learner.id,
        session_id=None,
        knowledge_point_id=point.id,
    )

    assert first.job.id != second.job.id
    assert db.query(MicroDetectionJob).count() == 2


def test_dedupe_key_separates_module_and_source_type() -> None:
    common = {
        "organization_id": 1,
        "learner_id": 7,
        "session_id": 11,
        "knowledge_point_id": None,
        "audio_sha256": "a" * 64,
    }
    learner_voice = build_micro_dedupe_key(
        module_id=1,
        source_type=MicroSource.LEARNER_VOICE,
        **common,
    )
    another_module = build_micro_dedupe_key(
        module_id=2,
        source_type=MicroSource.LEARNER_VOICE,
        **common,
    )
    mentor_recording = build_micro_dedupe_key(
        module_id=1,
        source_type=MicroSource.MENTOR_RECORDING,
        **common,
    )

    assert len({learner_voice, another_module, mentor_recording}) == 3


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


def test_stale_queued_job_without_external_id_is_reclaimed_once() -> None:
    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="stale-queued-job",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="queued",
        updated_at=datetime.now() - timedelta(minutes=5),
    )
    db.add(job)
    db.commit()
    tasks = BackgroundTasks()

    assert queue_awaiting_micro_job_retry(db, job, tasks) is True
    assert queue_awaiting_micro_job_retry(db, job, tasks) is False
    assert len(tasks.tasks) == 1


def test_duplicate_upload_requeues_an_awaiting_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, learner, _, module, point, _ = make_database_context()
    first_tasks = BackgroundTasks()
    first = create_micro_job(
        background_tasks=first_tasks,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE,
        consent_granted=True,
        audio=make_audio(b"retry-audio"),
        session_id=None,
        knowledge_point_id=point.id,
        learner_id=None,
        db=db,
        user=learner,
    )
    job = db.query(MicroDetectionJob).filter_by(id=first["job_id"]).one()
    job.status = "awaiting_detector"
    job.error_message = "detector timed out"
    db.commit()
    retry_tasks = BackgroundTasks()

    repeated = create_micro_job(
        background_tasks=retry_tasks,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE,
        consent_granted=True,
        audio=make_audio(b"retry-audio"),
        session_id=None,
        knowledge_point_id=point.id,
        learner_id=None,
        db=db,
        user=learner,
    )

    assert repeated["job_id"] == first["job_id"]
    assert repeated["status"] == "queued"
    assert len(retry_tasks.tasks) == 1
    assert db.query(MicroDetectionJob).count() == 1


def test_single_voice_endpoint_rejects_mentor_recording() -> None:
    db, _, mentor, _, module, point, _ = make_database_context()
    mentor.role = UserRole.MENTOR.value
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_micro_job(
            background_tasks=BackgroundTasks(),
            module_id=module.id,
            source_type=MicroSource.MENTOR_RECORDING,
            consent_granted=True,
            audio=make_audio(b"mentor-audio"),
            session_id=None,
            knowledge_point_id=point.id,
            learner_id=None,
            db=db,
            user=mentor,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize(
    ("learner_id", "speaker_mapping_confirmed"),
    [(7, False), (None, True)],
)
def test_mentor_batch_rejects_inconsistent_speaker_mapping(
    learner_id: int | None,
    speaker_mapping_confirmed: bool,
) -> None:
    db, _, mentor, learner, module, point, _ = make_database_context()
    mentor.role = UserRole.MENTOR.value
    db.commit()
    resolved_learner_id = learner.id if learner_id is not None else None

    with pytest.raises(HTTPException) as exc_info:
        create_mentor_batch(
            background_tasks=BackgroundTasks(),
            module_id=module.id,
            consent_granted=True,
            audio_files=[make_audio(b"mentor-audio")],
            learner_id=resolved_learner_id,
            session_id=None,
            knowledge_point_id=point.id,
            speaker_mapping_confirmed=speaker_mapping_confirmed,
            db=db,
            user=mentor,
        )

    assert exc_info.value.status_code == 422


def test_temporary_submit_failure_returns_job_to_awaiting_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TemporarilyUnavailableDetector:
        configured = True

        def create_job(self, request):
            raise IntegrationTransientError("detector timed out")

    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="temporary-failure",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="queued",
    )
    db.add(job)
    db.commit()
    job_id = job.id
    monkeypatch.setattr("app.SessionLocal", lambda: db)
    monkeypatch.setattr("app.MicroRepresentationClient", TemporarilyUnavailableDetector)

    submit_micro_job(job_id)

    stored = db.query(MicroDetectionJob).filter_by(id=job_id).one()
    assert stored.status == "awaiting_detector"
    assert stored.error_message == "detector timed out"


def test_contract_submit_failure_is_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidDetector:
        configured = True

        def create_job(self, request):
            raise IntegrationContractError("invalid detection job response")

    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="contract-failure",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="queued",
    )
    db.add(job)
    db.commit()
    job_id = job.id
    monkeypatch.setattr("app.SessionLocal", lambda: db)
    monkeypatch.setattr("app.MicroRepresentationClient", InvalidDetector)

    submit_micro_job(job_id)

    stored = db.query(MicroDetectionJob).filter_by(id=job_id).one()
    assert stored.status == "failed"
    assert stored.error_message == "invalid detection job response"


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


def test_query_requeues_awaiting_job_when_detector_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ConfiguredDetector:
        configured = True

    monkeypatch.setattr("app.MicroRepresentationClient", ConfiguredDetector)
    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="recovered-job",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="awaiting_detector",
        error_message="detector timed out",
    )
    db.add(job)
    db.commit()
    tasks = BackgroundTasks()

    result = get_micro_job(job.id, tasks, db, learner)

    assert result["status"] == "queued"
    assert result["error_message"] is None
    assert len(tasks.tasks) == 1


def test_contract_sync_error_permanently_fails_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidEventDetector:
        configured = True
        event_calls = 0

        def get_job(self, job_id):
            return {"job_id": job_id, "status": "completed"}

        def get_events(self, job_id):
            self.event_calls += 1
            raise IntegrationContractError("event scope mismatch")

    detector = InvalidEventDetector()
    monkeypatch.setattr("app.MicroRepresentationClient", lambda: detector)
    db, organization, learner, _, module, _, _ = make_database_context()
    job = MicroDetectionJob(
        id="invalid-event-job",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///audio.wav",
        consent_granted=True,
        status="completed",
        external_job_id="external-invalid-event",
        events_sync_status="failed",
    )
    db.add(job)
    db.commit()

    first = get_micro_job(job.id, BackgroundTasks(), db, learner)
    second = get_micro_job(job.id, BackgroundTasks(), db, learner)

    assert first["status"] == "failed"
    assert second["status"] == "failed"
    assert first["error_message"] == "event scope mismatch"
    assert first["degradation"] == "微表征检测服务同步失败：event scope mismatch"
    assert first["events_sync_error"] == first["degradation"]
    assert detector.event_calls == 1


def test_mentor_batch_can_be_queried_with_session_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, organization, mentor, _, module, point, session = make_database_context()
    mentor.role = UserRole.MENTOR.value
    db.commit()
    tasks = BackgroundTasks()

    created = create_mentor_batch(
        background_tasks=tasks,
        module_id=module.id,
        consent_granted=True,
        audio_files=[make_audio(b"first"), make_audio(b"second"), make_audio(b"first")],
        learner_id=None,
        session_id=session.id,
        knowledge_point_id=point.id,
        speaker_mapping_confirmed=False,
        db=db,
        user=mentor,
    )
    first_job_id, second_job_id = created.job_ids
    assert created.accepted == 2
    first_job = db.get(MicroDetectionJob, first_job_id)
    second_job = db.get(MicroDetectionJob, second_job_id)
    first_job.audio_duration_ms = 2000
    second_job.audio_duration_ms = 1200
    db.add_all(
        [
            MicroRepresentationEvent(
                id="batch-event-1",
                job_id=first_job_id,
                organization_id=organization.id,
                session_id=session.id,
                module_id=module.id,
                knowledge_point_id=point.id,
                source_type=MicroSource.MENTOR_RECORDING.value,
                event_type="thinking_pause",
                start_ms=100,
                end_ms=500,
                confidence=0.9,
                evidence_status=EvidenceStatus.CONFIRMED.value,
            ),
            MicroRepresentationEvent(
                id="batch-event-2",
                job_id=second_job_id,
                organization_id=organization.id,
                session_id=session.id,
                module_id=module.id,
                knowledge_point_id=point.id,
                source_type=MicroSource.MENTOR_RECORDING.value,
                event_type="hesitation",
                start_ms=700,
                end_ms=1000,
                confidence=0.6,
                evidence_status=EvidenceStatus.PENDING.value,
            ),
            MicroRepresentationEvent(
                id="batch-event-ignored",
                job_id=first_job_id,
                organization_id=organization.id,
                session_id=session.id,
                module_id=module.id,
                knowledge_point_id=point.id,
                source_type=MicroSource.MENTOR_RECORDING.value,
                event_type="guessing",
                start_ms=1500,
                end_ms=1600,
                confidence=0.9,
                evidence_status=EvidenceStatus.REJECTED.value,
            ),
        ]
    )
    db.commit()

    result = get_mentor_batch(created.batch_id, db, mentor)

    assert result["batch_id"] == created.batch_id
    assert [item["job_id"] for item in result["jobs"]] == created.job_ids
    assert result["summary"]["signals_by_type"] == {
        "thinking_pause": 1,
        "hesitation": 1,
    }
    assert result["summary"]["total_pause_ms"] == 700
    assert result["summary"]["pending_confirmation_count"] == 1
    assert result["summary"]["ignored_count"] == 1
    assert result["summary"]["trend"] == {
        "is_available": True,
        "first_half_count": 1,
        "second_half_count": 1,
        "change": 0,
        "degradation_reason": None,
    }


def test_mentor_batch_trend_degrades_without_recording_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, mentor, _, module, point, session = make_database_context()
    mentor.role = UserRole.MENTOR.value
    db.commit()
    created = create_mentor_batch(
        background_tasks=BackgroundTasks(),
        module_id=module.id,
        consent_granted=True,
        audio_files=[make_audio(b"no-duration")],
        learner_id=None,
        session_id=session.id,
        knowledge_point_id=point.id,
        speaker_mapping_confirmed=False,
        db=db,
        user=mentor,
    )
    db.add(
        MicroRepresentationEvent(
            id="event-without-duration",
            job_id=created.job_ids[0],
            organization_id=mentor.organization_id,
            session_id=session.id,
            module_id=module.id,
            knowledge_point_id=point.id,
            source_type=MicroSource.MENTOR_RECORDING.value,
            event_type="hesitation",
            start_ms=100,
            end_ms=300,
            confidence=0.8,
            evidence_status=EvidenceStatus.PENDING.value,
        )
    )
    db.commit()

    trend = get_mentor_batch(created.batch_id, db, mentor)["summary"]["trend"]

    assert trend["is_available"] is False
    assert trend["first_half_count"] is None
    assert trend["second_half_count"] is None
    assert trend["change"] is None
    assert "录音时长" in trend["degradation_reason"]


def test_empty_completed_batch_degrades_without_recording_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, _, mentor, _, module, point, session = make_database_context()
    mentor.role = UserRole.MENTOR.value
    db.commit()
    created = create_mentor_batch(
        background_tasks=BackgroundTasks(),
        module_id=module.id,
        consent_granted=True,
        audio_files=[make_audio(b"empty-result-no-duration")],
        learner_id=None,
        session_id=session.id,
        knowledge_point_id=point.id,
        speaker_mapping_confirmed=False,
        db=db,
        user=mentor,
    )
    job = db.get(MicroDetectionJob, created.job_ids[0])
    job.status = "completed"
    job.events_sync_status = "synced"
    db.commit()

    summary = get_mentor_batch(created.batch_id, db, mentor)["summary"]

    assert summary["total_signal_count"] == 0
    assert summary["trend"]["is_available"] is False
    assert "录音时长" in summary["trend"]["degradation_reason"]


def test_callback_rejects_job_without_external_detector_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config.security, "MICRO_CALLBACK_SECRET", "service-secret")
    db, organization, learner, _, module, point, session = make_database_context()
    job = MicroDetectionJob(
        id="echo-job-without-detector-id",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        session_id=session.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///controlled/audio.wav",
        consent_granted=True,
        status="queued",
    )
    db.add(job)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        ingest_micro_events(
            job.id,
            MicroEventBatch(items=[]),
            db=db,
            x_micro_service_key="service-secret",
        )

    assert exc_info.value.status_code == 409
    db.refresh(job)
    assert job.status == "queued"
    assert job.events_sync_status == "pending"


def test_callback_does_not_resurrect_failed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config.security, "MICRO_CALLBACK_SECRET", "service-secret")
    db, organization, learner, _, module, point, session = make_database_context()
    job = MicroDetectionJob(
        id="failed-echo-job",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        session_id=session.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///controlled/audio.wav",
        consent_granted=True,
        status="failed",
        external_job_id="failed-detector-job",
        error_message="event scope mismatch",
    )
    db.add(job)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        ingest_micro_events(
            job.id,
            MicroEventBatch(items=[]),
            db=db,
            x_micro_service_key="service-secret",
        )

    assert exc_info.value.status_code == 409
    db.refresh(job)
    assert job.status == "failed"


def test_callback_scope_failure_is_atomic_and_marks_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Config.security, "MICRO_CALLBACK_SECRET", "service-secret")
    db, organization, learner, _, module, point, session = make_database_context()
    job = MicroDetectionJob(
        id="echo-job-scope-failure",
        organization_id=organization.id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        session_id=session.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type=MicroSource.LEARNER_VOICE.value,
        audio_uri="file:///controlled/audio.wav",
        consent_granted=True,
        status="processing",
        external_job_id="detector-job-scope-failure",
    )
    db.add(job)
    db.commit()
    event = MicroEventContract(
        event_id="wrong-scope-event",
        job_id=job.external_job_id,
        organization_id=organization.id + 1,
        learner_id=learner.id,
        session_id=session.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type=MicroSource.LEARNER_VOICE,
        event_type="hesitation",
        start_ms=100,
        end_ms=300,
        confidence=0.9,
        speaker_mapping_confirmed=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        ingest_micro_events(
            job.id,
            MicroEventBatch(items=[event], audio_duration_ms=1000),
            db=db,
            x_micro_service_key="service-secret",
        )

    assert exc_info.value.status_code == 422
    db.refresh(job)
    assert job.status == "failed"
    assert job.events_sync_status == "failed"
    assert "organization_id" in job.events_sync_error
    assert job.audio_duration_ms is None
    assert db.get(MicroRepresentationEvent, event.event_id) is None


def test_cross_mentor_duplicate_batch_does_not_expose_original_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    db, organization, _, _, module, point, session = make_database_context()
    first_mentor = User(
        organization_id=organization.id,
        username="batch-mentor-one",
        hashed_password="unused",
        role=UserRole.MENTOR.value,
    )
    second_mentor = User(
        organization_id=organization.id,
        username="batch-mentor-two",
        hashed_password="unused",
        role=UserRole.MENTOR.value,
    )
    db.add_all([first_mentor, second_mentor])
    db.commit()
    first = create_micro_job_record(
        db,
        user=first_mentor,
        module_id=module.id,
        source_type=MicroSource.MENTOR_RECORDING,
        audio=make_audio(b"shared-batch-audio"),
        learner_id=None,
        session_id=session.id,
        knowledge_point_id=point.id,
    )
    first.job.status = "completed"
    db.commit()

    result = create_mentor_batch(
        background_tasks=BackgroundTasks(),
        module_id=module.id,
        consent_granted=True,
        audio_files=[make_audio(b"shared-batch-audio")],
        learner_id=None,
        session_id=session.id,
        knowledge_point_id=point.id,
        speaker_mapping_confirmed=False,
        db=db,
        user=second_mentor,
    )
    batch = get_mentor_batch(result.batch_id, db, second_mentor)

    assert result.accepted == 0
    assert result.already_submitted == 1
    assert result.job_ids == []
    assert batch["jobs"] == []
    assert batch["summary"]["total_signal_count"] == 0
    assert db.query(MicroDetectionJob).count() == 1
