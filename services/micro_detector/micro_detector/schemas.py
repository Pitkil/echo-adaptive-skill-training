"""Request and response models for the development detector service."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DetectionMetadata(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    organization_id: int
    learner_id: int | None = None
    session_id: int | None = None
    program_id: int
    module_id: int
    knowledge_point_id: int | None = None
    source_type: Literal["learner_voice", "mentor_recording"]
    consent_granted: bool
    speaker_mapping_confirmed: bool = False

    @model_validator(mode="after")
    def validate_consent_and_identity(self) -> DetectionMetadata:
        if not self.consent_granted:
            raise ValueError("consent_granted must be true before audio analysis.")
        if self.source_type == "learner_voice" and self.learner_id is None:
            raise ValueError("learner voice requires learner_id.")
        if self.source_type == "mentor_recording":
            if self.speaker_mapping_confirmed != (self.learner_id is not None):
                raise ValueError(
                    "mentor recording learner_id requires confirmed speaker mapping."
                )
        return self


class RemoteDetectionRequest(DetectionMetadata):
    audio_uri: str = Field(pattern=r"^https?://", min_length=1)


class DetectionJob(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    status: Literal["queued", "processing", "completed", "failed"]
    error_message: str | None = None
    audio_duration_ms: int | None = Field(default=None, gt=0)


class DetectionEvent(BaseModel):
    event_id: str
    job_id: str = Field(min_length=1, max_length=100)
    organization_id: int
    learner_id: int | None = None
    session_id: int | None = None
    module_id: int
    knowledge_point_id: int | None = None
    source_type: Literal["learner_voice", "mentor_recording"]
    event_type: Literal[
        "hesitation",
        "guessing",
        "thinking_pause",
        "uncertainty",
        "self_correction",
        "other",
    ]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    transcript: str | None = None
    evidence_uri: str | None = None
    speaker_ref: str | None = None
    speaker_mapping_confirmed: bool = False


class HealthResponse(BaseModel):
    status: Literal["ready"] = "ready"
    mode: Literal["mock"] = "mock"
    model_loaded: bool = False
    index_loaded: bool = False
