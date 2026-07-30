"""Versioned contracts shared with PunditRAG, SimpleMem and signal detection."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryType(StrEnum):
    MISCONCEPTION = "misconception"
    LEARNING_PREFERENCE = "learning_preference"
    INTERVENTION_OUTCOME = "intervention_outcome"


class MemoryIntent(StrEnum):
    LEARNER_DIAGNOSIS = "learner_diagnosis"
    ECHO_GUIDANCE = "echo_guidance"
    RESOURCE_GENERATION = "resource_generation"


class MicroSource(StrEnum):
    LEARNER_VOICE = "learner_voice"
    MENTOR_RECORDING = "mentor_recording"


class RetrievalMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str | None = None
    filename: str | None = None
    chapter: str | None = None
    knowledge_base_id: int
    module_id: int
    knowledge_point_ids: list[int] = Field(default_factory=list)
    chunk_id: str | None = None
    version: str | None = None


class RetrievalHit(BaseModel):
    text: str = Field(min_length=1)
    score: float | None = None
    metadata: RetrievalMetadata


class MemoryRecord(BaseModel):
    organization_id: int
    user_id: int
    program_id: int
    module_id: int
    knowledge_point_id: int | None = None
    session_id: int | None = None
    content: str = Field(min_length=1)
    memory_type: MemoryType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    organization_id: int
    user_id: int
    program_id: int
    module_id: int
    intent: MemoryIntent
    query: str = Field(min_length=1)
    knowledge_point_id: int | None = None
    limit: int = Field(default=8, ge=1, le=30)


class MicroDetectionRequest(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    organization_id: int
    learner_id: int | None = None
    session_id: int | None = None
    program_id: int
    module_id: int
    knowledge_point_id: int | None = None
    source_type: MicroSource
    audio_uri: str = Field(min_length=1)
    consent_granted: bool
    speaker_mapping_confirmed: bool = False

    @model_validator(mode="after")
    def validate_consent_and_identity(self) -> MicroDetectionRequest:
        if not self.consent_granted:
            raise ValueError("consent_granted must be true before audio analysis.")
        if self.source_type is MicroSource.LEARNER_VOICE and self.learner_id is None:
            raise ValueError("learner voice requires learner_id.")
        return self


class MicroRepresentationEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    job_id: str = Field(min_length=1, max_length=64)
    organization_id: int
    learner_id: int | None = None
    session_id: int | None = None
    module_id: int
    knowledge_point_id: int | None = None
    source_type: MicroSource
    event_type: Literal[
        "hesitation",
        "guessing",
        "thinking_pause",
        "uncertainty",
        "self_correction",
        "other",
    ]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    transcript: str | None = None
    evidence_uri: str | None = None
    speaker_ref: str | None = None
    speaker_mapping_confirmed: bool = False

    @model_validator(mode="after")
    def validate_event(self) -> MicroRepresentationEvent:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms.")
        if self.source_type is MicroSource.MENTOR_RECORDING and not self.speaker_mapping_confirmed:
            self.learner_id = None
        return self


def normalize_retrieval_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw_items = payload.get("items", payload.get("results", []))
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raise ValueError("Retrieval response must be a list or an object containing items.")

    hits = [RetrievalHit.model_validate(item) for item in raw_items]
    return [hit.model_dump(exclude_none=True) for hit in hits]
