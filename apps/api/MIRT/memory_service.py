"""Stable-memory policy and degradation-safe SimpleMem lifecycle service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from integrations.contracts import (
    MemoryAuthorizationResponse,
    MemoryConsolidationResult,
    MemoryIntent,
    MemoryMutationResponse,
    MemoryMutationStatus,
    MemoryRecord,
    MemorySearchRequest,
    MemoryType,
    MemoryUpsertResponse,
    MemoryUpsertStatus,
)
from integrations.http_client import IntegrationUnavailable
from integrations.simplemem import SimpleMemClient
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


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
    attempt_id: str | None = Field(default=None, max_length=128)
    question_id: int | None = Field(default=None, gt=0)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    is_correct: bool | None = None
    score: float | None = None
    misconception_key: str | None = Field(default=None, max_length=128)
    preference_key: str | None = Field(default=None, max_length=128)
    intervention_id: str | None = Field(default=None, max_length=128)
    intervention_type: str | None = Field(default=None, max_length=128)
    result_confirmed: bool | None = None
    result_value: str | None = Field(default=None, max_length=256)
    session_id: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "reference_id",
        "attempt_id",
        "misconception_key",
        "preference_key",
        "intervention_id",
        "intervention_type",
        "result_value",
    )
    @classmethod
    def normalize_text_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence identifiers must not be blank.")
        return normalized

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_typed_evidence(self) -> MemoryEvidence:
        if self.evidence_type is MemoryEvidenceType.SCORED_ATTEMPT:
            required = {
                "attempt_id": self.attempt_id,
                "question_id": self.question_id,
                "knowledge_point_id": self.knowledge_point_id,
                "is_correct": self.is_correct,
                "score": self.score,
                "misconception_key": self.misconception_key,
            }
        elif self.evidence_type is MemoryEvidenceType.PREFERENCE_OBSERVATION:
            required = {
                "preference_key": self.preference_key,
                "result_confirmed": self.result_confirmed,
                "result_value": self.result_value,
                "session_id": self.session_id,
            }
        else:
            required = {
                "intervention_id": self.intervention_id,
                "intervention_type": self.intervention_type,
                "result_confirmed": self.result_confirmed,
                "result_value": self.result_value,
                "session_id": self.session_id,
            }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(
                f"{self.evidence_type.value} missing required fields: {', '.join(missing)}."
            )
        return self


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
        if (
            candidate.memory_type is MemoryType.MISCONCEPTION
            and candidate.knowledge_point_id is None
        ):
            raise MemoryPolicyError("稳定误区必须绑定知识点。")

        allowed_types = self.REQUIRED_EVIDENCE_TYPES[candidate.memory_type]
        unrelated = [
            item.evidence_type.value
            for item in candidate.evidence
            if item.evidence_type not in allowed_types
        ]
        if unrelated:
            expected = "、".join(sorted(item.value for item in allowed_types))
            raise MemoryPolicyError(
                f"{candidate.memory_type.value} 只接受 {expected} 证据，不能混入其他类型。"
            )

        evidence_by_identity: dict[str, MemoryEvidence] = {}
        for item in candidate.evidence:
            identity = self._evidence_identity(item)
            existing = evidence_by_identity.get(identity)
            if existing is not None:
                if self._evidence_semantics(existing) != self._evidence_semantics(item):
                    raise MemoryPolicyError(
                        f"同一证据身份 {identity} 出现互相矛盾的数据。"
                    )
                continue
            evidence_by_identity[identity] = item
        evidence = list(evidence_by_identity.values())
        if len(evidence) < self.MIN_EVIDENCE_COUNT:
            raise MemoryPolicyError("长期记忆至少需要两个语义不同的证据编号。")

        self._validate_evidence_consistency(candidate, evidence)

        average_confidence = sum(item.confidence for item in evidence) / len(evidence)
        if average_confidence < self.MIN_AVERAGE_CONFIDENCE:
            raise MemoryPolicyError(
                f"证据平均可靠程度 {average_confidence:.2f} 低于 0.65。"
            )

        metadata = dict(candidate.metadata)
        metadata.update(
            {
                "evidence_count": len(evidence),
                "evidence": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in evidence
                ],
            }
        )
        conflict_key = self._conflict_key(candidate, evidence)
        idempotency_key = self._idempotency_key(candidate, conflict_key)
        return MemoryRecord(
            organization_id=candidate.organization_id,
            user_id=candidate.user_id,
            program_id=candidate.program_id,
            module_id=candidate.module_id,
            knowledge_point_id=candidate.knowledge_point_id,
            session_id=candidate.session_id,
            content=candidate.content,
            memory_type=candidate.memory_type,
            idempotency_key=idempotency_key,
            conflict_key=conflict_key,
            confidence=round(average_confidence, 4),
            evidence_refs=[item.reference_id for item in evidence],
            occurred_at=max(item.occurred_at for item in evidence),
            metadata=metadata,
        )

    @staticmethod
    def _evidence_identity(evidence: MemoryEvidence) -> str:
        if evidence.evidence_type is MemoryEvidenceType.SCORED_ATTEMPT:
            return f"attempt:{evidence.attempt_id}"
        if evidence.evidence_type is MemoryEvidenceType.PREFERENCE_OBSERVATION:
            return f"preference:{evidence.preference_key}:{evidence.session_id}"
        return f"intervention:{evidence.intervention_id}"

    @staticmethod
    def _evidence_semantics(evidence: MemoryEvidence) -> tuple[Any, ...]:
        if evidence.evidence_type is MemoryEvidenceType.SCORED_ATTEMPT:
            return (
                evidence.evidence_type,
                evidence.question_id,
                evidence.knowledge_point_id,
                evidence.is_correct,
                evidence.score,
                evidence.misconception_key,
            )
        if evidence.evidence_type is MemoryEvidenceType.PREFERENCE_OBSERVATION:
            return (
                evidence.evidence_type,
                evidence.preference_key,
                evidence.session_id,
                evidence.result_confirmed,
                StableMemoryPolicy._normalized_result(evidence.result_value),
            )
        return (
            evidence.evidence_type,
            evidence.intervention_id,
            evidence.intervention_type,
            evidence.session_id,
            evidence.preference_key,
            evidence.result_confirmed,
            StableMemoryPolicy._normalized_result(evidence.result_value),
        )

    def _validate_evidence_consistency(
        self,
        candidate: MemoryCandidate,
        evidence: list[MemoryEvidence],
    ) -> None:
        if candidate.memory_type is MemoryType.MISCONCEPTION:
            if any(item.is_correct is not False for item in evidence):
                raise MemoryPolicyError("稳定误区只能由真实错误作答形成。")
            if any(
                item.knowledge_point_id != candidate.knowledge_point_id
                for item in evidence
            ):
                raise MemoryPolicyError("错误作答的知识点必须与候选误区一致。")
            if len({item.misconception_key for item in evidence}) != 1:
                raise MemoryPolicyError("错误作答必须支持同一个误区结论。")
            return

        if any(item.result_confirmed is not True for item in evidence):
            raise MemoryPolicyError("偏好或干预证据必须已确认结果。")

        if candidate.memory_type is MemoryType.LEARNING_PREFERENCE:
            if any(item.preference_key is None for item in evidence):
                raise MemoryPolicyError("学习偏好证据必须明确 preference_key。")
            if len({item.preference_key for item in evidence}) != 1:
                raise MemoryPolicyError("学习偏好证据必须指向同一个偏好。")
            intervention_types = {
                item.intervention_type
                for item in evidence
                if item.evidence_type is MemoryEvidenceType.INTERVENTION_RESULT
            }
            if len(intervention_types) > 1:
                raise MemoryPolicyError("学习偏好的干预证据必须来自同一种干预。")
            if len({self._normalized_result(item.result_value) for item in evidence}) != 1:
                raise MemoryPolicyError("学习偏好证据结果互相矛盾。")
            return

        if len({item.intervention_type for item in evidence}) != 1:
            raise MemoryPolicyError("干预结果必须来自同一种干预。")
        if len({self._normalized_result(item.result_value) for item in evidence}) != 1:
            raise MemoryPolicyError("干预结果互相矛盾。")

    @staticmethod
    def _normalized_result(value: str | None) -> str:
        return " ".join((value or "").casefold().split())

    def _conflict_key(
        self,
        candidate: MemoryCandidate,
        evidence: list[MemoryEvidence],
    ) -> str:
        if candidate.memory_type is MemoryType.MISCONCEPTION:
            domain = f"{candidate.knowledge_point_id}:{evidence[0].misconception_key}"
        elif candidate.memory_type is MemoryType.LEARNING_PREFERENCE:
            domain = str(evidence[0].preference_key)
        else:
            domain = str(evidence[0].intervention_type)
        payload = "|".join(
            [
                str(candidate.organization_id),
                str(candidate.user_id),
                str(candidate.program_id),
                str(candidate.module_id),
                candidate.memory_type.value,
                domain.casefold(),
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _idempotency_key(candidate: MemoryCandidate, conflict_key: str) -> str:
        normalized_content = " ".join(candidate.content.casefold().split())
        payload = f"{conflict_key}|{normalized_content}"
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
        result = self._write_candidate("create", candidate, self.client.upsert)
        if result.status is not MemoryLifecycleStatus.COMPLETED:
            return result
        try:
            response = MemoryUpsertResponse.model_validate(result.data)
        except ValidationError as exc:
            return self._degraded(
                "create",
                f"SimpleMem 幂等写入响应无效：{exc}",
                memory_record=result.memory_record,
            )
        if response.idempotency_key != result.memory_record.idempotency_key:
            return self._degraded(
                "create",
                "SimpleMem 返回了不匹配的 idempotency_key。",
                memory_record=result.memory_record,
            )
        if response.status is MemoryUpsertStatus.CONFLICT:
            return MemoryLifecycleResult(
                operation="create",
                status=MemoryLifecycleStatus.REJECTED,
                data=response.model_dump(mode="json"),
                reason="同一记忆领域已有语义冲突的活跃记忆。",
                memory_record=result.memory_record,
            )
        return MemoryLifecycleResult(
            operation="create",
            status=MemoryLifecycleStatus.COMPLETED,
            data=response.model_dump(mode="json"),
            memory_record=result.memory_record,
        )

    def update(
        self,
        memory_id: str,
        candidate: MemoryCandidate,
    ) -> MemoryLifecycleResult:
        memory_id = memory_id.strip()
        if not memory_id:
            return self._rejected("update", "memory_id 不能为空。")
        authorization = self._authorize("update", memory_id, candidate)
        if authorization is not None:
            return authorization
        result = self._write_candidate(
            "update",
            candidate,
            lambda record: self.client.update(memory_id, record),
        )
        return self._validate_mutation_result(
            result,
            memory_id=memory_id,
            scope=candidate,
            allowed_statuses={
                MemoryMutationStatus.UPDATED,
                MemoryMutationStatus.UNCHANGED,
            },
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
        try:
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
        except ValidationError as exc:
            return self._rejected("search", f"记忆查询参数无效：{exc}")
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
        authorization = self._authorize("delete", memory_id, scope)
        if authorization is not None:
            return authorization
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
        return self._validate_mutation_result(
            MemoryLifecycleResult(
                operation="delete",
                status=MemoryLifecycleStatus.COMPLETED,
                data=data,
            ),
            memory_id=memory_id,
            scope=scope,
            allowed_statuses={MemoryMutationStatus.DELETED},
        )

    def consolidate(self, scope: MemoryScope) -> MemoryLifecycleResult:
        if not self.client.configured:
            return self._degraded("consolidate", "SimpleMem 未配置。")
        try:
            raw_data = self.client.consolidate(
                organization_id=scope.organization_id,
                user_id=scope.user_id,
                program_id=scope.program_id,
                module_id=scope.module_id,
            )
            data = MemoryConsolidationResult.model_validate(raw_data)
            expected_scope = scope.model_dump()
            actual_scope = {
                field: getattr(data, field)
                for field in expected_scope
            }
            if actual_scope != expected_scope:
                raise ValueError("SimpleMem 合并结果超出请求作用域。")
        except (IntegrationUnavailable, ValidationError, ValueError) as exc:
            return self._degraded("consolidate", f"SimpleMem 合并降级：{exc}")
        return MemoryLifecycleResult(
            operation="consolidate",
            status=MemoryLifecycleStatus.COMPLETED,
            data=data.model_dump(mode="json"),
        )

    def _authorize(
        self,
        operation: str,
        memory_id: str,
        scope: MemoryScope,
    ) -> MemoryLifecycleResult | None:
        if not self.client.configured:
            return self._degraded(operation, "SimpleMem 未配置。")
        expected_scope = {
            "organization_id": scope.organization_id,
            "user_id": scope.user_id,
            "program_id": scope.program_id,
            "module_id": scope.module_id,
        }
        try:
            response = self.client.authorize(memory_id, **expected_scope)
            authorization = MemoryAuthorizationResponse.model_validate(response)
            actual_scope = {
                field: getattr(authorization, field)
                for field in expected_scope
            }
            if authorization.memory_id != memory_id or actual_scope != expected_scope:
                raise ValueError("SimpleMem 授权响应与请求作用域不一致。")
        except (IntegrationUnavailable, ValidationError, ValueError) as exc:
            return self._degraded(
                operation,
                f"SimpleMem 作用域授权失败：{exc}；未执行变更。",
            )
        return None

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

    def _validate_mutation_result(
        self,
        result: MemoryLifecycleResult,
        *,
        memory_id: str,
        scope: MemoryScope,
        allowed_statuses: set[MemoryMutationStatus],
    ) -> MemoryLifecycleResult:
        if result.status is not MemoryLifecycleStatus.COMPLETED:
            return result
        try:
            response = MemoryMutationResponse.model_validate(result.data)
            expected_scope = scope.model_dump(
                include={"organization_id", "user_id", "program_id", "module_id"}
            )
            actual_scope = {field: getattr(response, field) for field in expected_scope}
            if (
                response.memory_id != memory_id
                or actual_scope != expected_scope
                or response.status not in allowed_statuses
            ):
                raise ValueError("SimpleMem 变更结果与请求操作或作用域不一致。")
        except (ValidationError, ValueError) as exc:
            return self._degraded(
                result.operation,
                f"SimpleMem 变更结果无效：{exc}",
                memory_record=result.memory_record,
            )
        return MemoryLifecycleResult(
            operation=result.operation,
            status=MemoryLifecycleStatus.COMPLETED,
            data=response.model_dump(mode="json"),
            memory_record=result.memory_record,
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
