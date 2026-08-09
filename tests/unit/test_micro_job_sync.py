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
from integrations.micro_sync import persist_micro_events, synchronize_micro_job
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
        {"job_id": job.external_job_id, "status": "completed"},
        events,
    )

    first = synchronize_micro_job(db, job, client)
    db.commit()
    second = synchronize_micro_job(db, job, client)
    db.commit()

    assert first == 2
    assert second == 0
    assert db.query(MicroRepresentationEvent).count() == 2
    assert db.get(MicroRepresentationEvent, "event-001").evidence_status == EvidenceStatus.CONFIRMED.value
    assert db.get(MicroRepresentationEvent, "event-002").evidence_status == EvidenceStatus.PENDING.value


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

    assert job.status == "processing"


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
