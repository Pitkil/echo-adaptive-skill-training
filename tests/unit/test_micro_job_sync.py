from __future__ import annotations

import pytest
from database import (
    Base,
    EvidenceStatus,
    KnowledgeBase,
    KnowledgePoint,
    MicroDetectionJob,
    MicroRepresentationEvent,
    Organization,
    TrainingModule,
    TrainingProgram,
    User,
)
from integrations.contracts import MicroRepresentationEvent as MicroEventContract
from integrations.http_client import IntegrationUnavailable
from integrations.micro_sync import (
    apply_micro_audio_duration,
    apply_micro_job_creation_result,
    persist_micro_events,
    synchronize_micro_job,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class FakeDetectorClient:
    def __init__(self, state: dict, events: list[MicroEventContract]) -> None:
        self.state = state
        self.events = events

    def get_job(self, job_id: str) -> dict:
        return self.state

    def get_events(self, job_id: str) -> list[MicroEventContract]:
        return self.events


class FailingEventClient(FakeDetectorClient):
    def get_events(self, job_id: str) -> list[MicroEventContract]:
        raise IntegrationUnavailable("detector event endpoint timed out")


def make_job_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    organization = Organization(code="ORG", name="Test Organization")
    db.add(organization)
    db.flush()
    learner = User(
        organization_id=organization.id,
        username="micro-learner",
        hashed_password="not-used",
    )
    knowledge_base = KnowledgeBase(
        organization_id=organization.id,
        code="KB",
        name="Test Knowledge Base",
    )
    program = TrainingProgram(
        organization_id=organization.id,
        code="PROGRAM",
        name="Semantic Kernel",
    )
    db.add_all([learner, knowledge_base, program])
    db.flush()
    module = TrainingModule(
        program_id=program.id,
        knowledge_base_id=knowledge_base.id,
        code="M1",
        name="Kernel and Plugins",
        sequence=1,
    )
    db.add(module)
    db.flush()
    point = KnowledgePoint(module_id=module.id, code="KP1", name="Plugins", sequence=1)
    db.add(point)
    db.flush()
    job = MicroDetectionJob(
        id="echo-job-001",
        external_job_id="detector-job-001",
        organization_id=organization.id,
        learner_id=learner.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type="learner_voice",
        audio_uri="file:///test.webm",
        consent_granted=True,
        status="processing",
    )
    db.add(job)
    db.commit()
    return db, job, organization, learner, module, point


def make_event(job, organization, learner, module, point, **overrides):
    values = {
        "event_id": "event-001",
        "job_id": job.external_job_id,
        "organization_id": organization.id,
        "learner_id": learner.id,
        "session_id": None,
        "module_id": module.id,
        "knowledge_point_id": point.id,
        "source_type": "learner_voice",
        "event_type": "hesitation",
        "start_ms": 1200,
        "end_ms": 1800,
        "confidence": 0.84,
        "speaker_mapping_confirmed": True,
    }
    values.update(overrides)
    return MicroEventContract(**values)


def test_completed_job_persists_events_idempotently() -> None:
    db, job, organization, learner, module, point = make_job_context()
    events = [
        make_event(job, organization, learner, module, point),
        make_event(
            job,
            organization,
            learner,
            module,
            point,
            event_id="event-002",
            confidence=0.62,
        ),
    ]
    client = FakeDetectorClient(
        {
            "job_id": job.external_job_id,
            "status": "completed",
            "audio_duration_ms": 4000,
        },
        events,
    )

    first = synchronize_micro_job(db, job, client)
    db.commit()
    second = synchronize_micro_job(db, job, client)
    db.commit()

    assert first == 2
    assert second == 0
    assert db.query(MicroRepresentationEvent).count() == 2
    assert job.audio_duration_ms == 4000
    assert db.get(MicroRepresentationEvent, "event-001").evidence_status == EvidenceStatus.CONFIRMED.value
    assert db.get(MicroRepresentationEvent, "event-002").evidence_status == EvidenceStatus.PENDING.value


def test_create_response_completed_immediately_imports_events() -> None:
    db, job, organization, learner, module, point = make_job_context()
    job.external_job_id = None
    client = FakeDetectorClient(
        {"job_id": "unused", "status": "processing"},
        [make_event(job, organization, learner, module, point, job_id="detector-direct")],
    )

    accepted = apply_micro_job_creation_result(
        db,
        job,
        client,
        {
            "job_id": "detector-direct",
            "status": "completed",
            "audio_duration_ms": 4000,
        },
    )
    db.commit()

    assert accepted == 1
    assert job.status == "completed"
    assert job.events_sync_status == "synced"
    assert job.events_synced_at is not None
    assert job.audio_duration_ms == 4000


def test_event_outside_recording_duration_is_rejected() -> None:
    db, job, organization, learner, module, point = make_job_context()
    job.audio_duration_ms = 1500
    event = make_event(job, organization, learner, module, point, end_ms=1800)

    with pytest.raises(IntegrationUnavailable, match="recording duration"):
        persist_micro_events(
            db,
            job,
            [event],
            expected_event_job_id=job.external_job_id,
        )

    assert db.query(MicroRepresentationEvent).count() == 0


def test_recording_duration_cannot_change_after_it_is_stored() -> None:
    db, job, *_ = make_job_context()

    apply_micro_audio_duration(job, 4000)

    with pytest.raises(IntegrationUnavailable, match="conflicts"):
        apply_micro_audio_duration(job, 3500)
    assert job.audio_duration_ms == 4000
    db.close()


@pytest.mark.parametrize("duration_ms", [0, -1, True, 1.5, "4000"])
def test_recording_duration_requires_a_positive_integer(duration_ms) -> None:
    db, job, *_ = make_job_context()

    with pytest.raises(IntegrationUnavailable, match="positive integer"):
        apply_micro_audio_duration(job, duration_ms)
    db.close()


def test_completed_job_with_empty_events_is_still_marked_synced() -> None:
    db, job, *_ = make_job_context()
    client = FakeDetectorClient(
        {"job_id": job.external_job_id, "status": "completed"},
        [],
    )

    assert synchronize_micro_job(db, job, client) == 0
    assert job.events_sync_status == "synced"
    assert job.events_synced_at is not None


def test_event_scope_mismatch_is_rejected() -> None:
    db, job, organization, learner, module, point = make_job_context()
    event = make_event(
        job,
        organization,
        learner,
        module,
        point,
        organization_id=organization.id + 1,
    )

    with pytest.raises(IntegrationUnavailable, match="organization_id"):
        persist_micro_events(
            db,
            job,
            [event],
            expected_event_job_id=job.external_job_id,
        )

    assert db.query(MicroRepresentationEvent).count() == 0


def test_mixed_valid_and_invalid_batch_is_not_partially_persisted() -> None:
    db, job, organization, learner, module, point = make_job_context()
    valid = make_event(job, organization, learner, module, point)
    invalid = make_event(
        job,
        organization,
        learner,
        module,
        point,
        event_id="event-002",
        module_id=module.id + 1,
    )

    with pytest.raises(IntegrationUnavailable, match="module_id"):
        persist_micro_events(
            db,
            job,
            [valid, invalid],
            expected_event_job_id=job.external_job_id,
        )

    assert db.query(MicroRepresentationEvent).count() == 0


def test_duplicate_event_in_same_batch_is_counted_once() -> None:
    db, job, organization, learner, module, point = make_job_context()
    event = make_event(job, organization, learner, module, point)

    accepted = persist_micro_events(
        db,
        job,
        [event, event.model_copy(deep=True)],
        expected_event_job_id=job.external_job_id,
    )
    db.commit()

    assert accepted == 1
    assert db.query(MicroRepresentationEvent).count() == 1


def test_event_fetch_failure_does_not_mark_job_completed() -> None:
    db, job, *_ = make_job_context()
    client = FailingEventClient(
        {"job_id": job.external_job_id, "status": "completed"},
        [],
    )

    with pytest.raises(IntegrationUnavailable, match="timed out"):
        synchronize_micro_job(db, job, client)

    assert job.status == "completed"
    assert job.events_sync_status == "failed"
    assert "timed out" in job.events_sync_error


def test_stored_event_with_changed_content_is_rejected() -> None:
    db, job, organization, learner, module, point = make_job_context()
    event = make_event(job, organization, learner, module, point)
    persist_micro_events(
        db,
        job,
        [event],
        expected_event_job_id=job.external_job_id,
    )
    db.commit()

    with pytest.raises(IntegrationUnavailable, match="conflicting content"):
        persist_micro_events(
            db,
            job,
            [event.model_copy(update={"start_ms": 1300})],
            expected_event_job_id=job.external_job_id,
        )


def test_confirmed_mentor_event_with_wrong_learner_is_rejected() -> None:
    db, job, organization, learner, module, point = make_job_context()
    job.source_type = "mentor_recording"
    event = make_event(
        job,
        organization,
        learner,
        module,
        point,
        source_type="mentor_recording",
        learner_id=learner.id + 1,
        speaker_mapping_confirmed=True,
    )

    with pytest.raises(IntegrationUnavailable, match="learner_id does not match"):
        persist_micro_events(
            db,
            job,
            [event],
            expected_event_job_id=job.external_job_id,
        )


def test_failed_external_job_keeps_failure_reason() -> None:
    db, job, *_ = make_job_context()
    client = FakeDetectorClient(
        {
            "job_id": job.external_job_id,
            "status": "failed",
            "error_message": "unsupported audio format",
        },
        [],
    )

    accepted = synchronize_micro_job(db, job, client)
    db.commit()

    assert accepted == 0
    assert job.status == "failed"
    assert job.error_message == "unsupported audio format"
