"""Build mentor-facing summaries from persisted micro-representation evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol


class MicroJobSummarySource(Protocol):
    audio_duration_ms: int | None
    status: str


class MicroEventSummarySource(Protocol):
    job_id: str
    event_type: str
    start_ms: int
    end_ms: int
    evidence_status: str


_PENDING_STATUS = "pending"
_REJECTED_STATUS = "rejected"


def build_mentor_batch_summary(
    jobs_by_id: Mapping[str, MicroJobSummarySource],
    events: Sequence[MicroEventSummarySource],
) -> dict[str, Any]:
    """Summarize active events and use real recording durations for trend counts."""

    ignored_count = sum(
        event.evidence_status == _REJECTED_STATUS for event in events
    )
    active_events = [
        event
        for event in events
        if event.evidence_status != _REJECTED_STATUS
    ]
    signals_by_type: dict[str, int] = {}
    total_pause_ms = 0
    pending_confirmation_count = 0
    for event in active_events:
        signals_by_type[event.event_type] = signals_by_type.get(event.event_type, 0) + 1
        if event.event_type in {"hesitation", "thinking_pause"}:
            total_pause_ms += max(event.end_ms - event.start_ms, 0)
        if event.evidence_status == _PENDING_STATUS:
            pending_confirmation_count += 1

    trend = _build_recording_half_trend(jobs_by_id, active_events)
    return {
        "signals_by_type": signals_by_type,
        "total_signal_count": len(active_events),
        "total_pause_ms": total_pause_ms,
        "pending_confirmation_count": pending_confirmation_count,
        "ignored_count": ignored_count,
        "trend": trend,
    }


def _build_recording_half_trend(
    jobs_by_id: Mapping[str, MicroJobSummarySource],
    events: Sequence[MicroEventSummarySource],
) -> dict[str, Any]:
    event_job_ids = {event.job_id for event in events}
    missing_duration_job_ids = {
        job_id
        for job_id, job in jobs_by_id.items()
        if job.audio_duration_ms is None
        and (job_id in event_job_ids or job.status == "completed")
    }
    missing_duration_job_ids.update({
        event.job_id
        for event in events
        if (job := jobs_by_id.get(event.job_id)) is None
        or job.audio_duration_ms is None
    })
    if missing_duration_job_ids:
        return {
            "is_available": False,
            "first_half_count": None,
            "second_half_count": None,
            "change": None,
            "degradation_reason": "部分录音缺少录音时长，无法计算前后半段趋势",
        }

    first_half_count = 0
    for event in events:
        job = jobs_by_id[event.job_id]
        event_midpoint_ms = (event.start_ms + event.end_ms) / 2
        if event_midpoint_ms < job.audio_duration_ms / 2:
            first_half_count += 1
    second_half_count = len(events) - first_half_count
    return {
        "is_available": True,
        "first_half_count": first_half_count,
        "second_half_count": second_half_count,
        "change": second_half_count - first_half_count,
        "degradation_reason": None,
    }
