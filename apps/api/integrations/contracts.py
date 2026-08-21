"""Versioned contracts shared with PunditRAG, SimpleMem and signal detection."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MemoryType(StrEnum):
    MISCONCEPTION = "misconception"
    LEARNING_PREFERENCE = "learning_preference"
    INTERVENTION_OUTCOME = "intervention_outcome"


class MemoryIntent(StrEnum):
    LEARNER_DIAGNOSIS = "learner_diagnosis"
    ECHO_GUIDANCE = "echo_guidance"
    RESOURCE_GENERATION = "resource_generation"


class MemoryUpsertStatus(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


class MemoryMutationStatus(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DELETED = "deleted"


class MicroSource(StrEnum):
    LEARNER_VOICE = "learner_voice"
    MENTOR_RECORDING = "mentor_recording"


class RetrievalMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str | None = None
    filename: str | None = None
    chapter: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_section: str | None = None
    knowledge_base_id: int
    module_id: int
    knowledge_point_ids: list[int] = Field(default_factory=list)
    chunk_id: str | None = None
    version: str | None = None
    external_knowledge_base_id: str | None = None
    external_document_id: str | None = None


class RetrievalHit(BaseModel):
    text: str = Field(min_length=1)
    score: float | None = None
    metadata: RetrievalMetadata


class MemoryRecord(BaseModel):
    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    session_id: int | None = Field(default=None, gt=0)
    content: str = Field(min_length=1)
    memory_type: MemoryType
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    conflict_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=2)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("content must not be blank.")
        return normalized

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        unique = list(dict.fromkeys(normalized))
        if len(unique) < 2:
            raise ValueError("long-term memory requires at least two distinct evidence refs.")
        return unique

    @model_validator(mode="after")
    def validate_memory_scope(self) -> MemoryRecord:
        if self.memory_type is MemoryType.MISCONCEPTION and self.knowledge_point_id is None:
            raise ValueError("misconception memory requires knowledge_point_id.")
        return self


class MemoryUpsertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MemoryUpsertStatus
    memory_id: str | None = Field(default=None, min_length=1, max_length=128)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    conflict_memory_ids: list[str] = Field(default_factory=list)

    @field_validator("conflict_memory_ids")
    @classmethod
    def normalize_conflict_memory_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def validate_status_payload(self) -> MemoryUpsertResponse:
        if self.status is MemoryUpsertStatus.CONFLICT:
            if not self.conflict_memory_ids:
                raise ValueError("conflict response requires conflict_memory_ids.")
        elif self.memory_id is None:
            raise ValueError("successful upsert response requires memory_id.")
        return self


class MemoryAuthorizationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: Literal[True]
    memory_id: str = Field(min_length=1, max_length=128)
    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)


class MemoryMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MemoryMutationStatus
    memory_id: str = Field(min_length=1, max_length=128)
    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)


class MemoryConsolidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merged_memory_id: str = Field(min_length=1, max_length=128)
    source_memory_ids: list[str] = Field(min_length=2)
    evidence_refs: list[str] = Field(min_length=2)
    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)

    @field_validator("source_memory_ids", "evidence_refs")
    @classmethod
    def normalize_distinct_identifiers(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if len(unique) < 2:
            raise ValueError("consolidation requires at least two distinct identifiers.")
        return unique


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)
    intent: MemoryIntent
    query: str = Field(min_length=1)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=8, ge=1, le=30)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("memory search query must not be blank.")
        return normalized


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
        if self.source_type is MicroSource.MENTOR_RECORDING:
            if self.speaker_mapping_confirmed != (self.learner_id is not None):
                raise ValueError(
                    "mentor recording learner_id requires confirmed speaker mapping."
                )
        return self


class MicroDetectionJobResult(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    status: Literal["queued", "processing", "completed", "failed"]
    error_message: str | None = None
    audio_duration_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_failure_reason(self) -> MicroDetectionJobResult:
        if self.status == "failed" and not (self.error_message or "").strip():
            raise ValueError("failed detection job requires error_message.")
        return self


class MicroRepresentationEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    job_id: str = Field(min_length=1, max_length=100)
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
        if self.source_type is MicroSource.MENTOR_RECORDING:
            if self.speaker_mapping_confirmed != (self.learner_id is not None):
                raise ValueError(
                    "mentor event learner_id requires confirmed speaker mapping."
                )
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


def normalize_punditrag_query_payload(
    payload: Any,
    *,
    knowledge_base_id: int,
    module_id: int,
    knowledge_point_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Convert PunditRAG `/query` sources into ECHO retrieval hits."""

    if not isinstance(payload, dict):
        raise ValueError("PunditRAG query response must be an object.")
    raw_sources = payload.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("PunditRAG query response sources must be a list.")

    items: list[dict[str, Any]] = []
    for position, source in enumerate(raw_sources, start=1):
        if not isinstance(source, dict):
            raise ValueError("PunditRAG source must be an object.")
        source_text = str(source.get("content") or source.get("text") or "").strip()
        if not source_text:
            continue
        external_document_id = str(source.get("document_id") or "").strip() or None
        part = source.get("part")
        chunk_id = (
            f"{external_document_id}:{part}"
            if external_document_id and part is not None
            else external_document_id or str(source.get("index") or position)
        )
        title = str(source.get("file_title") or source.get("title") or "").strip() or None
        section = str(source.get("parent_title") or source.get("title") or "").strip() or None
        items.append(
            {
                "text": source_text,
                "score": source.get("score"),
                "metadata": {
                    "source_title": title,
                    "source_url": source.get("url"),
                    "source_section": section,
                    "filename": title,
                    "chapter": section,
                    "knowledge_base_id": knowledge_base_id,
                    "module_id": module_id,
                    "knowledge_point_ids": knowledge_point_ids or [],
                    "chunk_id": chunk_id,
                    "external_knowledge_base_id": source.get("kb_id"),
                    "external_document_id": external_document_id,
                    "search_rank": source.get("search_rank"),
                },
            }
        )
    return normalize_retrieval_payload({"items": items})
