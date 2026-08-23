"""Evidence-aware learner insight aggregation owned by member C."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from database import (
    EvidenceStatus,
    KnowledgePoint,
    LearnerAbility,
    MicroRepresentationEvent,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
)
from sqlalchemy.orm import Session

from MIRT.mirt_daily_stats import build_daily_series

DIMENSION_LABELS = {
    "U": "理解与知识掌握",
    "A": "应用与操作能力",
    "R": "推理与评估能力",
}
CONTENT_FORMAT_BY_DIMENSION = {
    "U": "custom_note",
    "A": "practice_guide",
    "R": "staged_test",
}
LEARNER_PROFILE_REQUIREMENTS = {
    "P1": {
        "label": "基础巩固型",
        "explanation_depth": "concept_first",
        "step_detail": "detailed",
        "support_level": "high",
    },
    "P2": {
        "label": "理论转实践型",
        "explanation_depth": "application_focused",
        "step_detail": "moderate",
        "support_level": "medium",
    },
    "P3": {
        "label": "工程进阶型",
        "explanation_depth": "architecture_and_tradeoffs",
        "step_detail": "high_level",
        "support_level": "low",
    },
}


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
        path = self._learning_path(module_id, blind_spots, mastered)
        confidence = self._diagnosis_confidence(
            ability_payload["attempt_count"],
            micro["confirmed_event_count"],
            len(memory_items or []),
        )
        recent = build_daily_series(self.db, user_id, module_id, days=30)
        average_accuracy = self._average_accuracy(recent)
        accuracy_trend = self._period_accuracy_trend(recent)
        recommendation = self._build_recommendation(
            ability_payload=ability_payload,
            average_accuracy=average_accuracy,
            blind_spots=blind_spots,
            mastered=mastered,
            learning_path=path,
            micro=micro,
            memory_items=memory_items or [],
        )
        narrative_report = self._build_fallback_report(
            ability_payload=ability_payload,
            accuracy_trend=accuracy_trend,
            blind_spots=blind_spots,
            mastered=mastered,
            recommendation=recommendation,
        )

        return {
            "module": {"id": module.id, "code": module.code, "name": module.name},
            "views": {
                "ability_and_trend": {
                    "ability": ability_payload,
                    "ability_trend": self._ability_dimension_trend(ability_payload),
                    "daily_series": recent,
                    "average_accuracy": average_accuracy,
                    "accuracy_trend": accuracy_trend,
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
                    **recommendation,
                },
            },
            "narrative_report": narrative_report,
        }

    def _knowledge_point_status(self, user_id: int, module_id: int) -> tuple[list[dict], list[dict]]:
        points = (
            self.db.query(KnowledgePoint)
            .filter(KnowledgePoint.module_id == module_id)
            .order_by(KnowledgePoint.sequence)
            .all()
        )
        attempt_rows = (
            self.db.query(StudentQuestionHistory, Quiz)
            .join(StudentQuestionHistory, StudentQuestionHistory.question_id == Quiz.id)
            .filter(
                StudentQuestionHistory.user_id == user_id,
                Quiz.module_id == module_id,
            )
            .order_by(StudentQuestionHistory.created_at)
            .all()
        )
        by_point: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for history, quiz in attempt_rows:
            by_point[quiz.knowledge_point_id].append(
                {
                    "attempt_id": history.attempt_id,
                    "question_id": quiz.id,
                    "question": quiz.content,
                    "score": round(float(history.score), 4),
                    "is_correct": bool(history.is_correct),
                    "purpose": quiz.purpose,
                    "difficulty": quiz.difficulty,
                    "counts_for_mirt": bool(quiz.counts_for_mirt),
                    "occurred_at": history.created_at.isoformat(),
                }
            )

        blind_spots: list[dict] = []
        mastered: list[dict] = []
        for point in points:
            evidence = by_point.get(point.id, [])
            total = len(evidence)
            correct = sum(1 for item in evidence if item["is_correct"])
            accuracy = correct / total if total else None
            payload = {
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "attempt_count": total,
                "accuracy": round(accuracy, 4) if accuracy is not None else None,
                "latest_attempt_at": evidence[-1]["occurred_at"] if evidence else None,
                "evidence": evidence[-10:],
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

    def _learning_path(
        self,
        module_id: int,
        blind_spots: list[dict],
        mastered: list[dict],
    ) -> list[dict]:
        points = (
            self.db.query(KnowledgePoint)
            .filter(KnowledgePoint.module_id == module_id)
            .order_by(KnowledgePoint.sequence)
            .all()
        )
        blind_ids = {item["knowledge_point_id"] for item in blind_spots}
        mastered_ids = {item["knowledge_point_id"] for item in mastered}
        return [
            {
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "prerequisites": point.prerequisites or [],
                "status": (
                    "priority_review"
                    if point.id in blind_ids
                    else "mastered"
                    if point.id in mastered_ids
                    else "planned"
                ),
            }
            for point in points
        ]

    @staticmethod
    def _average_accuracy(series: list[dict]) -> float | None:
        attempts = sum(item["attempt_count"] for item in series)
        correct = sum(item["correct_count"] for item in series)
        return round(correct / attempts, 4) if attempts else None

    @staticmethod
    def _period_accuracy_trend(series: list[dict], window_days: int = 7) -> dict:
        def summarize(items: list[dict]) -> dict:
            attempts = sum(item["attempt_count"] for item in items)
            correct = sum(item["correct_count"] for item in items)
            return {
                "attempt_count": attempts,
                "correct_count": correct,
                "accuracy": round(correct / attempts, 4) if attempts else None,
            }

        current = summarize(series[-window_days:])
        previous = summarize(series[-2 * window_days : -window_days])
        if current["accuracy"] is None or previous["accuracy"] is None:
            change = None
            direction = "insufficient_evidence"
        else:
            change = round(current["accuracy"] - previous["accuracy"], 4)
            direction = "improved" if change > 0.02 else "declined" if change < -0.02 else "stable"
        return {
            "window_days": window_days,
            "current_period": current,
            "previous_period": previous,
            "accuracy_change": change,
            "direction": direction,
        }

    @staticmethod
    def _ability_dimension_trend(ability_payload: dict) -> dict:
        reason = (
            "当前没有可更新 MIRT 的作答，能力变化暂不能判断。"
            if ability_payload["attempt_count"] == 0
            else "当前数据库未保存历史 U/A/R 快照，不能推断各维度变化。"
        )
        return {
            dimension: {
                "current": ability_payload[dimension],
                "change": None,
                "direction": "insufficient_evidence",
                "reason": reason,
            }
            for dimension in ("U", "A", "R")
        }

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

    def _build_recommendation(
        self,
        *,
        ability_payload: dict,
        average_accuracy: float | None,
        blind_spots: list[dict],
        mastered: list[dict],
        learning_path: list[dict],
        micro: dict,
        memory_items: list[dict],
    ) -> dict:
        attempts = int(ability_payload["attempt_count"])
        ability_values = {
            dimension: float(ability_payload[dimension])
            for dimension in ("U", "A", "R")
        }
        weakest_dimension = min(ability_values, key=ability_values.get) if attempts else None
        learner_profile = self._classify_learner_profile(
            attempts=attempts,
            ability_values=ability_values,
            average_accuracy=average_accuracy,
            blind_spots=blind_spots,
        )

        if attempts == 0:
            recommended_difficulty = "foundation"
            content_format = "diagnostic_pretest"
        elif min(ability_values.values()) < -0.5 or (
            average_accuracy is not None and average_accuracy < 0.6
        ):
            recommended_difficulty = "foundation"
            content_format = CONTENT_FORMAT_BY_DIMENSION[weakest_dimension]
        elif (
            min(ability_values.values()) >= 0.8
            and average_accuracy is not None
            and average_accuracy >= 0.8
            and not blind_spots
        ):
            recommended_difficulty = "advanced"
            content_format = CONTENT_FORMAT_BY_DIMENSION[weakest_dimension]
        else:
            recommended_difficulty = "standard"
            content_format = CONTENT_FORMAT_BY_DIMENSION[weakest_dimension]

        next_point = next(
            (item for item in learning_path if item["status"] == "priority_review"),
            next((item for item in learning_path if item["status"] == "planned"), None),
        )
        learning_preference = next(
            (
                item
                for item in memory_items
                if str(item.get("memory_type", "")) == "learning_preference"
            ),
            None,
        )
        if micro["confirmed_event_count"]:
            tutoring_method = "step_by_step_with_checkpoints"
        elif learning_preference is not None:
            tutoring_method = "use_recorded_learning_preference"
        else:
            tutoring_method = "guided_explanation_with_self_check"

        evidence_sources = self._recommendation_evidence_sources(
            blind_spots=blind_spots,
            mastered=mastered,
            micro=micro,
            memory_items=memory_items,
            next_point=next_point,
        )
        reason = self._recommendation_reason(blind_spots, micro, memory_items)
        if weakest_dimension is not None:
            reason += (
                f"；当前最弱维度为{DIMENSION_LABELS[weakest_dimension]}，"
                f"因此推荐 {content_format}。"
            )

        return {
            "learner_profile": learner_profile,
            "recommended_difficulty": recommended_difficulty,
            "next_knowledge_point": next_point,
            "recommended_content_format": content_format,
            "recommended_tutoring_method": tutoring_method,
            "weakest_dimension": weakest_dimension,
            "recommendation_reason": reason,
            "evidence_sources": evidence_sources,
            "primary_content_decision": {
                "action": "complete_pretest" if attempts == 0 else "generate_resource",
                "content_format": content_format,
                "resource_type": content_format if attempts else None,
                "resource_count": 0 if attempts == 0 else 1,
                "selection_policy": "single_most_needed",
                "knowledge_point_id": (
                    next_point["knowledge_point_id"] if next_point is not None else None
                ),
                "difficulty": recommended_difficulty,
            },
        }

    @staticmethod
    def _classify_learner_profile(
        *,
        attempts: int,
        ability_values: dict[str, float],
        average_accuracy: float | None,
        blind_spots: list[dict],
    ) -> dict:
        """Classify the three fixed demo profiles using scored evidence only."""

        if attempts == 0:
            return {
                "type": None,
                "label": "待完成前测",
                "reason": "尚无可判分作答，不能归入 P1、P2 或 P3。",
                "evidence_status": "insufficient",
                "content_requirements": {},
            }

        minimum_ability = min(ability_values.values())
        average_ability = sum(ability_values.values()) / len(ability_values)
        is_strong_and_stable = (
            minimum_ability >= 0.8
            and average_accuracy is not None
            and average_accuracy >= 0.8
            and not blind_spots
        )
        application_gap = ability_values["U"] - ability_values["A"]
        is_theory_to_practice = (
            ability_values["U"] >= 0.3
            and ability_values["A"] == minimum_ability
            and application_gap >= 0.3
        )

        if is_strong_and_stable:
            profile_type = "P3"
            reason = "三项能力和正确率均较高，且没有作答支持的知识盲区。"
        elif is_theory_to_practice:
            profile_type = "P2"
            reason = "理解能力已有基础，但应用能力明显较弱，需要从理论转向实践。"
        else:
            profile_type = "P1"
            reason_parts = ["当前能力仍需基础巩固"]
            if average_accuracy is not None and average_accuracy < 0.6:
                reason_parts.append("近期正确率低于 60%")
            if blind_spots:
                reason_parts.append(f"存在 {len(blind_spots)} 个有作答证据的知识盲区")
            if average_ability < 0.3:
                reason_parts.append("三项能力平均值低于 0.3")
            reason = "；".join(reason_parts) + "。"

        requirements = LEARNER_PROFILE_REQUIREMENTS[profile_type]
        return {
            "type": profile_type,
            "label": requirements["label"],
            "reason": reason,
            "evidence_status": "supported",
            "content_requirements": {
                key: value
                for key, value in requirements.items()
                if key != "label"
            },
        }

    @staticmethod
    def _recommendation_evidence_sources(
        *,
        blind_spots: list[dict],
        mastered: list[dict],
        micro: dict,
        memory_items: list[dict],
        next_point: dict | None,
    ) -> list[dict]:
        sources: list[dict] = []
        for point in [*blind_spots, *mastered]:
            for evidence in point.get("evidence", []):
                sources.append(
                    {
                        "source_type": "scored_attempt",
                        "source_id": evidence["attempt_id"],
                        "knowledge_point_id": point["knowledge_point_id"],
                        "score": evidence["score"],
                        "occurred_at": evidence["occurred_at"],
                    }
                )
        for item in micro.get("items", [])[:3]:
            sources.append(
                {
                    "source_type": "confirmed_micro_event",
                    "source_id": item["event_id"],
                    "knowledge_point_id": item.get("knowledge_point_id"),
                    "confidence": item["confidence"],
                }
            )
        for index, item in enumerate(memory_items[:3]):
            sources.append(
                {
                    "source_type": "long_term_memory",
                    "source_id": item.get("memory_id") or item.get("id") or f"memory-{index + 1}",
                    "memory_type": item.get("memory_type"),
                    "occurred_at": item.get("occurred_at"),
                }
            )
        if next_point is not None:
            sources.append(
                {
                    "source_type": "curriculum",
                    "source_id": next_point["code"],
                    "knowledge_point_id": next_point["knowledge_point_id"],
                }
            )
        return sources[:12]

    @staticmethod
    def _build_fallback_report(
        *,
        ability_payload: dict,
        accuracy_trend: dict,
        blind_spots: list[dict],
        mastered: list[dict],
        recommendation: dict,
    ) -> dict:
        attempts = int(ability_payload["attempt_count"])
        if attempts == 0:
            ability_text = "尚无可更新 MIRT 的作答，能力现状和变化趋势暂不能判断。"
            evidence_text = "尚无作答证据，已掌握知识点和知识盲区暂不能判断。"
        else:
            direction_labels = {
                "improved": "上升",
                "declined": "下降",
                "stable": "基本稳定",
                "insufficient_evidence": "暂不能判断",
            }
            ability_text = (
                f"当前 U={ability_payload['U']:.4f}、A={ability_payload['A']:.4f}、"
                f"R={ability_payload['R']:.4f}；近两期正确率变化"
                f"{direction_labels[accuracy_trend['direction']]}。"
            )
            evidence_text = (
                f"依据可追溯作答，识别出 {len(mastered)} 个已掌握知识点和 "
                f"{len(blind_spots)} 个知识盲区。"
            )
        next_point = recommendation["next_knowledge_point"]
        next_point_name = next_point["name"] if next_point is not None else "暂未确定"
        learner_profile = recommendation["learner_profile"]
        if learner_profile["type"] is None:
            profile_text = "当前尚不能确定 P1、P2 或 P3 画像。"
        else:
            profile_text = (
                f"当前画像为 {learner_profile['type']}（{learner_profile['label']}），"
                f"依据为：{learner_profile['reason']}"
            )
        path_text = (
            f"{profile_text}推荐难度为 {recommendation['recommended_difficulty']}，"
            f"下一知识点为“{next_point_name}”，"
            f"内容形式为 {recommendation['recommended_content_format']}，"
            f"辅导方式为 {recommendation['recommended_tutoring_method']}。"
        )
        return {
            "source": "deterministic_template",
            "ability_and_trend": ability_text,
            "evidence_and_blind_spots": evidence_text,
            "path_and_resources": path_text,
        }


# Compatibility name for code that still imports AnalysisAgent.
AnalysisAgent = LearnerInsightService
