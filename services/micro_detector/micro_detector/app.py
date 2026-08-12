"""Contract-compatible mock service used for Docker and team integration tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from .schemas import (
    DetectionEvent,
    DetectionJob,
    DetectionMetadata,
    HealthResponse,
    RemoteDetectionRequest,
)

app = FastAPI(title="ECHO Micro Detector (Mock)", version="1.0.0")


@dataclass(frozen=True)
class StoredJob:
    result: DetectionJob
    events: tuple[DetectionEvent, ...]


_jobs: dict[str, StoredJob] = {}
_MAX_MOCK_AUDIO_BYTES = 25 * 1024 * 1024


def _create_completed_job(metadata: DetectionMetadata, audio_identity: bytes) -> DetectionJob:
    digest = hashlib.sha256(metadata.trace_id.encode() + b":" + audio_identity).hexdigest()
    job_id = f"mock-{digest[:24]}"
    if job_id in _jobs:
        return _jobs[job_id].result

    learner_id = metadata.learner_id
    if metadata.source_type == "mentor_recording" and not metadata.speaker_mapping_confirmed:
        learner_id = None
    event = DetectionEvent(
        event_id=f"mock-event-{digest[:20]}",
        job_id=job_id,
        organization_id=metadata.organization_id,
        learner_id=learner_id,
        session_id=metadata.session_id,
        module_id=metadata.module_id,
        knowledge_point_id=metadata.knowledge_point_id,
        source_type=metadata.source_type,
        event_type="hesitation",
        start_ms=1000,
        end_ms=1800,
        confidence=0.82,
        transcript="Mock event for contract integration only.",
        evidence_uri=f"mock://detection-jobs/{job_id}",
        speaker_mapping_confirmed=metadata.speaker_mapping_confirmed,
    )
    result = DetectionJob(job_id=job_id, status="completed")
    _jobs[job_id] = StoredJob(result=result, events=(event,))
    return result


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/v1/detection/jobs", response_model=DetectionJob)
async def create_job(request: Request) -> DetectionJob:
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            audio = form.get("audio")
            if not isinstance(audio, UploadFile):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="audio file is required",
                )
            metadata = DetectionMetadata.model_validate(
                {key: value for key, value in form.items() if key != "audio"}
            )
            audio_hash = hashlib.sha256()
            size = 0
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_MOCK_AUDIO_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="audio exceeds the 25 MiB mock-service limit",
                    )
                audio_hash.update(chunk)
            if size == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="audio is empty",
                )
            return _create_completed_job(metadata, audio_hash.digest())

        payload = RemoteDetectionRequest.model_validate(await request.json())
        return _create_completed_job(payload, payload.audio_uri.encode())
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_url=False, include_context=False),
        ) from exc


@app.get("/v1/detection/jobs/{job_id}", response_model=DetectionJob)
def get_job(job_id: str) -> DetectionJob:
    stored = _jobs.get(job_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return stored.result


@app.get("/v1/detection/jobs/{job_id}/events")
def get_events(job_id: str) -> dict[str, list[DetectionEvent]]:
    stored = _jobs.get(job_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return {"items": list(stored.events)}
