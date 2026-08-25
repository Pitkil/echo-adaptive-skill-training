"""Independent API schemas matching ECHO's frozen SimpleMem contract."""

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


class MemoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)


class MemoryRecord(MemoryScope):
    model_config = ConfigDict(extra="forbid")

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


class MemorySearchRequest(MemoryScope):
    model_config = ConfigDict(extra="forbid")

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


class MemoryUpsertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MemoryUpsertStatus
    memory_id: str | None = Field(default=None, min_length=1, max_length=128)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    conflict_memory_ids: list[str] = Field(default_factory=list)


class MemoryAuthorizationResponse(MemoryScope):
    model_config = ConfigDict(extra="forbid")

    allowed: Literal[True] = True
    memory_id: str = Field(min_length=1, max_length=128)


class MemoryMutationResponse(MemoryScope):
    model_config = ConfigDict(extra="forbid")

    status: MemoryMutationStatus
    memory_id: str = Field(min_length=1, max_length=128)


class MemoryConsolidationResult(MemoryScope):
    model_config = ConfigDict(extra="forbid")

    merged_memory_id: str = Field(min_length=1, max_length=128)
    source_memory_ids: list[str] = Field(min_length=2)
    evidence_refs: list[str] = Field(min_length=2)

    @field_validator("source_memory_ids", "evidence_refs")
    @classmethod
    def normalize_distinct_identifiers(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if len(unique) < 2:
            raise ValueError("consolidation requires at least two distinct identifiers.")
        return unique


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["simplemem"] = "simplemem"
    version: str
    database: Literal["sqlite"] = "sqlite"
