"""Synchronize detector jobs and persist scoped micro-representation evidence."""

from __future__ import annotations

from collections.abc import Iterable

from database import EvidenceStatus, MicroDetectionJob, MicroRepresentationEvent
from sqlalchemy.orm import Session

from .contracts import MicroRepresentationEvent as MicroEventContract
from .contracts import MicroSource
from .http_client import IntegrationUnavailable
from .micro_representation import MicroRepresentationClient

DEFAULT_CONFIRMATION_THRESHOLD = 0.75


def persist_micro_events(
    db: Session,
    job: MicroDetectionJob,
    events: Iterable[MicroEventContract],
    *,
    expected_event_job_id: str,
    confirmation_threshold: float = DEFAULT_CONFIRMATION_THRESHOLD,
) -> int:
    """Validate and idempotently persist detector events for one ECHO job."""
    unique_events: dict[str, MicroEventContract] = {}
    for event in events:
        duplicate = unique_events.get(event.event_id)
        if duplicate is not None and duplicate != event:
            raise IntegrationUnavailable(
                "duplicate micro-representation event_id has conflicting content."
            )
        unique_events[event.event_id] = event
    event_items = list(unique_events.values())
    resolved_learners: dict[str, tuple[int | None, bool]] = {}
    for event in event_items:
        _validate_event_scope(job, event, expected_event_job_id)
        resolved_learners[event.event_id] = _resolve_learner(job, event)
        existing = db.get(MicroRepresentationEvent, event.event_id)
        if existing is not None and existing.job_id != job.id:
            raise IntegrationUnavailable(
                "micro-representation event_id is already used by another job."
            )

    accepted = 0
    for event in event_items:
        existing = db.get(MicroRepresentationEvent, event.event_id)
        if existing is not None:
            continue

        learner_id, is_speaker_confirmed = resolved_learners[event.event_id]
        evidence_status = (
            EvidenceStatus.CONFIRMED.value
            if is_speaker_confirmed and event.confidence >= confirmation_threshold
            else EvidenceStatus.PENDING.value
        )
        db.add(
            MicroRepresentationEvent(
                id=event.event_id,
                job_id=job.id,
                organization_id=job.organization_id,
                learner_id=learner_id,
                session_id=job.session_id,
                module_id=job.module_id,
                knowledge_point_id=job.knowledge_point_id,
                source_type=job.source_type,
                event_type=event.event_type,
                start_ms=event.start_ms,
                end_ms=event.end_ms,
                confidence=event.confidence,
                transcript=event.transcript,
                evidence_uri=event.evidence_uri,
                speaker_ref=event.speaker_ref,
                evidence_status=evidence_status,
            )
        )
        accepted += 1
    return accepted


def synchronize_micro_job(
    db: Session,
    job: MicroDetectionJob,
    client: MicroRepresentationClient,
) -> int:
    """Refresh one external job and persist events when detection is complete."""
    if not job.external_job_id:
        raise IntegrationUnavailable("micro-representation job has no external_job_id.")

    external_state = client.get_job(job.external_job_id)
    external_status = external_state["status"]
    if external_status != "completed":
        job.status = external_status
        job.error_message = external_state.get("error_message")
        return 0

    events = client.get_events(job.external_job_id)
    accepted = persist_micro_events(
        db,
        job,
        events,
        expected_event_job_id=job.external_job_id,
    )
    job.status = "completed"
    job.error_message = None
    return accepted


def _validate_event_scope(
    job: MicroDetectionJob,
    event: MicroEventContract,
    expected_event_job_id: str,
) -> None:
    expected = {
        "job_id": expected_event_job_id,
        "organization_id": job.organization_id,
        "session_id": job.session_id,
        "module_id": job.module_id,
        "knowledge_point_id": job.knowledge_point_id,
        "source_type": job.source_type,
    }
    actual = {
        "job_id": event.job_id,
        "organization_id": event.organization_id,
        "session_id": event.session_id,
        "module_id": event.module_id,
        "knowledge_point_id": event.knowledge_point_id,
        "source_type": event.source_type.value,
    }
    mismatched = [name for name, value in expected.items() if actual[name] != value]
    if mismatched:
        raise IntegrationUnavailable(
            "micro-representation event scope mismatch: " + ", ".join(mismatched)
        )


def _resolve_learner(
    job: MicroDetectionJob,
    event: MicroEventContract,
) -> tuple[int | None, bool]:
    if job.source_type == MicroSource.LEARNER_VOICE.value:
        if job.learner_id is None or event.learner_id != job.learner_id:
            raise IntegrationUnavailable("learner voice event learner_id does not match job.")
        return job.learner_id, True

    is_confirmed = (
        event.speaker_mapping_confirmed
        and job.learner_id is not None
        and event.learner_id == job.learner_id
    )
    return (job.learner_id, True) if is_confirmed else (None, False)
