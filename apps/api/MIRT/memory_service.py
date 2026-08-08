"""Stable-memory policy and degradation-safe SimpleMem lifecycle service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from integrations.contracts import (
    MemoryIntent,
    MemoryRecord,
    MemorySearchRequest,
    MemoryType,
)
from integrations.http_client import IntegrationUnavailable
from integrations.simplemem import SimpleMemClient
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryEvidenceType(StrEnum):
    SCORED_ATTEMPT = "scored_attempt"
    PREFERENCE_OBSERVATION = "preference_observation"
    INTERVENTION_RESULT = "intervention_result"


class MemoryLifecycleStatus(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    DEGRADED = "degraded"


class MemoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    module_id: int = Field(gt=0)


class MemoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: str = Field(min_length=1, max_length=128)
    evidence_type: MemoryEvidenceType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reference_id")
    @classmethod
    def normalize_reference_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reference_id must not be blank.")
        return normalized

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class MemoryCandidate(MemoryScope):
    knowledge_point_id: int | None = Field(default=None, gt=0)
    session_id: int | None = Field(default=None, gt=0)
    content: str = Field(min_length=1, max_length=2000)
    memory_type: MemoryType
    evidence: list[MemoryEvidence] = Field(min_length=1, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("content must not be blank.")
        return normalized


class MemoryPolicyError(ValueError):
    """Raised when an observation is not stable enough for long-term memory."""


@dataclass(frozen=True)
class MemoryLifecycleResult:
    operation: str
    status: MemoryLifecycleStatus
    data: Any = None
    reason: str | None = None
    memory_record: MemoryRecord | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status.value,
            "data": self.data,
            "reason": self.reason,
            "memory_record": (
                self.memory_record.model_dump(mode="json")
                if self.memory_record is not None
                else None
            ),
        }


class StableMemoryPolicy:
    MIN_EVIDENCE_COUNT = 2
    MIN_AVERAGE_CONFIDENCE = 0.65
    REQUIRED_EVIDENCE_TYPES = {
        MemoryType.MISCONCEPTION: {MemoryEvidenceType.SCORED_ATTEMPT},
        MemoryType.LEARNING_PREFERENCE: {
            MemoryEvidenceType.PREFERENCE_OBSERVATION,
            MemoryEvidenceType.INTERVENTION_RESULT,
        },
        MemoryType.INTERVENTION_OUTCOME: {MemoryEvidenceType.INTERVENTION_RESULT},
    }

    def build_record(self, candidate: MemoryCandidate) -> MemoryRecord:
        evidence_by_ref = {
            item.reference_id: item
            for item in candidate.evidence
        }
        evidence = list(evidence_by_ref.values())
        if len(evidence) < self.MIN_EVIDENCE_COUNT:
            raise MemoryPolicyError("长期记忆至少需要两个不同的证据编号。")
        if (
            candidate.memory_type is MemoryType.MISCONCEPTION
            and candidate.knowledge_point_id is None
        ):
            raise MemoryPolicyError("稳定误区必须绑定知识点。")

        allowed_types = self.REQUIRED_EVIDENCE_TYPES[candidate.memory_type]
        matching_evidence = [
            item for item in evidence if item.evidence_type in allowed_types
        ]
        if len(matching_evidence) < self.MIN_EVIDENCE_COUNT:
            expected = "、".join(sorted(item.value for item in allowed_types))
            raise MemoryPolicyError(
                f"{candidate.memory_type.value} 至少需要两个 {expected} 证据。"
            )

        average_confidence = sum(item.confidence for item in evidence) / len(evidence)
        if average_confidence < self.MIN_AVERAGE_CONFIDENCE:
            raise MemoryPolicyError(
                f"证据平均可靠程度 {average_confidence:.2f} 低于 0.65。"
            )

        metadata = dict(candidate.metadata)
        metadata.update(
            {
                "deduplication_key": self._deduplication_key(candidate),
                "evidence_count": len(evidence),
                "evidence": [
                    {
                        "reference_id": item.reference_id,
                        "evidence_type": item.evidence_type.value,
                        "occurred_at": item.occurred_at.isoformat(),
                        "confidence": item.confidence,
                        "metadata": item.metadata,
                    }
                    for item in evidence
                ],
            }
        )
        return MemoryRecord(
            organization_id=candidate.organization_id,
            user_id=candidate.user_id,
            program_id=candidate.program_id,
            module_id=candidate.module_id,
            knowledge_point_id=candidate.knowledge_point_id,
            session_id=candidate.session_id,
            content=candidate.content,
            memory_type=candidate.memory_type,
            confidence=round(average_confidence, 4),
            evidence_refs=[item.reference_id for item in evidence],
            occurred_at=max(item.occurred_at for item in evidence),
            metadata=metadata,
        )

    @staticmethod
    def _deduplication_key(candidate: MemoryCandidate) -> str:
        normalized_content = " ".join(candidate.content.casefold().split())
        payload = "|".join(
            [
                str(candidate.organization_id),
                str(candidate.user_id),
                str(candidate.program_id),
                str(candidate.module_id),
                candidate.memory_type.value,
                str(candidate.knowledge_point_id or "-"),
                normalized_content,
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()


class LearnerMemoryService:
    """Applies memory policy and turns optional-service failures into degradation."""

    def __init__(
        self,
        client: SimpleMemClient | None = None,
        policy: StableMemoryPolicy | None = None,
    ) -> None:
        self.client = client or SimpleMemClient()
        self.policy = policy or StableMemoryPolicy()

    def create(self, candidate: MemoryCandidate) -> MemoryLifecycleResult:
        return self._write_candidate("create", candidate, self.client.remember)

    def update(
        self,
        memory_id: str,
        candidate: MemoryCandidate,
    ) -> MemoryLifecycleResult:
        memory_id = memory_id.strip()
        if not memory_id:
            return self._rejected("update", "memory_id 不能为空。")
        return self._write_candidate(
            "update",
            candidate,
            lambda record: self.client.update(memory_id, record),
        )

    def search(
        self,
        scope: MemoryScope,
        *,
        intent: MemoryIntent,
        query: str,
        knowledge_point_id: int | None = None,
        limit: int = 8,
    ) -> MemoryLifecycleResult:
        if not self.client.configured:
            return self._degraded("search", "SimpleMem 未配置。", data=[])
        request = MemorySearchRequest(
            organization_id=scope.organization_id,
            user_id=scope.user_id,
            program_id=scope.program_id,
            module_id=scope.module_id,
            intent=intent,
            query=query,
            knowledge_point_id=knowledge_point_id,
            limit=limit,
        )
        try:
            items = self.client.search(request)
        except IntegrationUnavailable as exc:
            return self._degraded("search", f"SimpleMem 查询降级：{exc}", data=[])
        return MemoryLifecycleResult(
            operation="search",
            status=MemoryLifecycleStatus.COMPLETED,
            data=items,
        )

    def delete(self, memory_id: str, scope: MemoryScope) -> MemoryLifecycleResult:
        memory_id = memory_id.strip()
        if not memory_id:
            return self._rejected("delete", "memory_id 不能为空。")
        if not self.client.configured:
            return self._degraded("delete", "SimpleMem 未配置。")
        try:
            data = self.client.delete(
                memory_id,
                organization_id=scope.organization_id,
                user_id=scope.user_id,
                program_id=scope.program_id,
                module_id=scope.module_id,
            )
        except IntegrationUnavailable as exc:
            return self._degraded("delete", f"SimpleMem 删除降级：{exc}")
        return MemoryLifecycleResult(
            operation="delete",
            status=MemoryLifecycleStatus.COMPLETED,
            data=data,
        )

    def consolidate(self, scope: MemoryScope) -> MemoryLifecycleResult:
        if not self.client.configured:
            return self._degraded("consolidate", "SimpleMem 未配置。")
        try:
            data = self.client.consolidate(
                organization_id=scope.organization_id,
                user_id=scope.user_id,
                program_id=scope.program_id,
                module_id=scope.module_id,
            )
        except IntegrationUnavailable as exc:
            return self._degraded("consolidate", f"SimpleMem 合并降级：{exc}")
        return MemoryLifecycleResult(
            operation="consolidate",
            status=MemoryLifecycleStatus.COMPLETED,
            data=data,
        )

    def _write_candidate(
        self,
        operation: str,
        candidate: MemoryCandidate,
        writer,
    ) -> MemoryLifecycleResult:
        try:
            record = self.policy.build_record(candidate)
        except MemoryPolicyError as exc:
            return self._rejected(operation, str(exc))
        if not self.client.configured:
            return self._degraded(
                operation,
                "SimpleMem 未配置；业务数据库事实不受影响。",
                memory_record=record,
            )
        try:
            data = writer(record)
        except IntegrationUnavailable as exc:
            return self._degraded(
                operation,
                f"SimpleMem 写入降级：{exc}；业务数据库事实不受影响。",
                memory_record=record,
            )
        return MemoryLifecycleResult(
            operation=operation,
            status=MemoryLifecycleStatus.COMPLETED,
            data=data,
            memory_record=record,
        )

    @staticmethod
    def _rejected(operation: str, reason: str) -> MemoryLifecycleResult:
        return MemoryLifecycleResult(
            operation=operation,
            status=MemoryLifecycleStatus.REJECTED,
            reason=reason,
        )

    @staticmethod
    def _degraded(
        operation: str,
        reason: str,
        *,
        data: Any = None,
        memory_record: MemoryRecord | None = None,
    ) -> MemoryLifecycleResult:
        return MemoryLifecycleResult(
            operation=operation,
            status=MemoryLifecycleStatus.DEGRADED,
            data=data,
            reason=reason,
            memory_record=memory_record,
        )
