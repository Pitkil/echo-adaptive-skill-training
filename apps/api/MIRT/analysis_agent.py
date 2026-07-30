"""Evidence-aware learner insight aggregation owned by member C."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from database import (
    EvidenceStatus,
    KnowledgePoint,
    LearnerAbility,
    MicroRepresentationEvent,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
)
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from MIRT.mirt_daily_stats import build_daily_series


class LearnerInsightService:
    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def build_profile(
        self,
        user_id: int,
        module_id: int,
        *,
        memory_items: list[dict] | None = None,
    ) -> dict:
        module = self.db.query(TrainingModule).filter_by(id=module_id).first()
        if module is None:
            raise ValueError("Training module not found.")

        ability = (
            self.db.query(LearnerAbility)
            .filter_by(user_id=user_id, module_id=module_id)
            .first()
        )
        ability_payload = {
            "U": round(float(ability.U), 4) if ability else 0.0,
            "A": round(float(ability.A), 4) if ability else 0.0,
            "R": round(float(ability.R), 4) if ability else 0.0,
            "attempt_count": int(ability.attempt_count) if ability else 0,
            "updated_at": ability.updated_at.isoformat() if ability else None,
        }
        blind_spots, mastered = self._knowledge_point_status(user_id, module_id)
        micro = self._micro_evidence(user_id, module_id)
        difficulty = self._difficulty_match(user_id, module_id, ability)
        path = self._learning_path(module_id, blind_spots)
        confidence = self._diagnosis_confidence(
            ability_payload["attempt_count"],
            micro["confirmed_event_count"],
            len(memory_items or []),
        )
        recent = build_daily_series(self.db, user_id, module_id, days=30)

        return {
            "module": {"id": module.id, "code": module.code, "name": module.name},
            "views": {
                "ability_and_trend": {
                    "ability": ability_payload,
                    "daily_series": recent,
                    "average_accuracy": self._average_accuracy(recent),
                },
                "evidence_and_blind_spots": {
                    "mastered_knowledge_points": mastered,
                    "knowledge_blind_spots": blind_spots,
                    "micro_evidence": micro,
                    "memory_summary": memory_items or [],
                    "diagnosis_confidence": confidence,
                },
                "path_and_resources": {
                    "difficulty_match_curve": difficulty,
                    "learning_path": path,
                    "recommendation_reason": self._recommendation_reason(
                        blind_spots,
                        micro,
                        memory_items or [],
                    ),
                },
            },
        }

    def _knowledge_point_status(self, user_id: int, module_id: int) -> tuple[list[dict], list[dict]]:
        points = (
            self.db.query(KnowledgePoint)
            .filter(KnowledgePoint.module_id == module_id)
            .order_by(KnowledgePoint.sequence)
            .all()
        )
        aggregates = (
            self.db.query(
                Quiz.knowledge_point_id,
                func.count(StudentQuestionHistory.id),
                func.sum(cast(StudentQuestionHistory.is_correct, Integer)),
            )
            .join(StudentQuestionHistory, StudentQuestionHistory.question_id == Quiz.id)
            .filter(
                StudentQuestionHistory.user_id == user_id,
                Quiz.module_id == module_id,
            )
            .group_by(Quiz.knowledge_point_id)
            .all()
        )
        by_point = {
            point_id: (int(total or 0), int(correct or 0))
            for point_id, total, correct in aggregates
        }
        blind_spots: list[dict] = []
        mastered: list[dict] = []
        for point in points:
            total, correct = by_point.get(point.id, (0, 0))
            accuracy = correct / total if total else None
            payload = {
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "attempt_count": total,
                "accuracy": round(accuracy, 4) if accuracy is not None else None,
            }
            if total >= 2 and accuracy is not None and accuracy < 0.6:
                blind_spots.append(payload)
            elif total >= 2 and accuracy is not None and accuracy >= 0.8:
                mastered.append(payload)
        return blind_spots, mastered

    def _micro_evidence(self, user_id: int, module_id: int) -> dict:
        events = (
            self.db.query(MicroRepresentationEvent)
            .filter(
                MicroRepresentationEvent.learner_id == user_id,
                MicroRepresentationEvent.module_id == module_id,
                MicroRepresentationEvent.evidence_status == EvidenceStatus.CONFIRMED.value,
            )
            .order_by(MicroRepresentationEvent.created_at.desc())
            .limit(50)
            .all()
        )
        counts: dict[str, int] = defaultdict(int)
        confidences: list[float] = []
        evidence = []
        for event in events:
            counts[event.event_type] += 1
            confidences.append(float(event.confidence))
            evidence.append(
                {
                    "event_id": event.id,
                    "knowledge_point_id": event.knowledge_point_id,
                    "event_type": event.event_type,
                    "confidence": event.confidence,
                    "transcript": event.transcript,
                    "evidence_uri": event.evidence_uri,
                }
            )
        return {
            "confirmed_event_count": len(events),
            "average_model_confidence": round(sum(confidences) / len(confidences), 4)
            if confidences
            else None,
            "event_counts": dict(counts),
            "items": evidence,
            "notice": "微表征只作为辅助证据，不直接更新MIRT能力。",
        }

    def _difficulty_match(
        self,
        user_id: int,
        module_id: int,
        ability: LearnerAbility | None,
    ) -> list[dict]:
        if ability is None:
            return []
        recent = (
            self.db.query(StudentQuestionHistory, Quiz)
            .join(Quiz, StudentQuestionHistory.question_id == Quiz.id)
            .filter(
                StudentQuestionHistory.user_id == user_id,
                Quiz.module_id == module_id,
                StudentQuestionHistory.created_at >= datetime.now() - timedelta(days=30),
            )
            .order_by(StudentQuestionHistory.created_at)
            .limit(30)
            .all()
        )
        result = []
        for history, quiz in recent:
            z = quiz.U * ability.U + quiz.A * ability.A + quiz.R * ability.R + quiz.intercept_d
            probability = 1.0 / (1.0 + pow(2.718281828, -max(-50.0, min(50.0, z))))
            result.append(
                {
                    "attempt_id": history.attempt_id,
                    "knowledge_point_id": quiz.knowledge_point_id,
                    "predicted_probability": round(probability, 4),
                    "actual_result": bool(history.is_correct),
                    "item_intercept": quiz.intercept_d,
                }
            )
        return result

    def _learning_path(self, module_id: int, blind_spots: list[dict]) -> list[dict]:
        points = (
            self.db.query(KnowledgePoint)
            .filter(KnowledgePoint.module_id == module_id)
            .order_by(KnowledgePoint.sequence)
            .all()
        )
        blind_ids = {item["knowledge_point_id"] for item in blind_spots}
        return [
            {
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "prerequisites": point.prerequisites or [],
                "status": "priority_review" if point.id in blind_ids else "planned",
            }
            for point in points
        ]

    @staticmethod
    def _average_accuracy(series: list[dict]) -> float | None:
        attempts = sum(item["attempt_count"] for item in series)
        correct = sum(item["correct_count"] for item in series)
        return round(correct / attempts, 4) if attempts else None

    @staticmethod
    def _diagnosis_confidence(attempts: int, micro_events: int, memories: int) -> float:
        assessment_component = min(attempts / 8, 1.0) * 0.7
        evidence_component = min((micro_events + memories) / 5, 1.0) * 0.3
        return round(assessment_component + evidence_component, 4)

    @staticmethod
    def _recommendation_reason(
        blind_spots: list[dict],
        micro: dict,
        memory_items: list[dict],
    ) -> str:
        reasons = []
        if blind_spots:
            reasons.append(f"检测到{len(blind_spots)}个有答题证据的知识盲区")
        if micro["confirmed_event_count"]:
            reasons.append("存在已确认的犹豫或自我修正证据")
        if memory_items:
            reasons.append("长期记忆中存在相关误区或有效学习偏好")
        return "；".join(reasons) if reasons else "当前证据较少，先完成模块前测建立基线。"
# Compatibility name for code that still imports AnalysisAgent.
AnalysisAgent = LearnerInsightService
