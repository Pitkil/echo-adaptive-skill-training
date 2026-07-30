"""Module-scoped adaptive assessment and MIRT-2PL ability updates."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
from database import (
    KnowledgePointReviewState,
    LearnerAbility,
    Quiz,
    StudentQuestionHistory,
)
from MIRT.mirt_daily_stats import upsert_mirt_daily_stat
from sqlalchemy.orm import Session

MAP_PRIOR_SIGMA = 1.0
MAP_NEWTON_MAX_ITER = 25
MAP_NEWTON_TOL = 1e-5
THETA_CLIP = 4.0


class AdaptiveEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_learner_ability(self, user_id: int, module_id: int) -> LearnerAbility:
        state = (
            self.db.query(LearnerAbility)
            .filter_by(user_id=user_id, module_id=module_id)
            .first()
        )
        if state is None:
            state = LearnerAbility(user_id=user_id, module_id=module_id)
            self.db.add(state)
            self.db.flush()
        return state

    @staticmethod
    def probability_predict(ability: LearnerAbility, quiz: Quiz) -> float:
        z = quiz.U * ability.U + quiz.A * ability.A + quiz.R * ability.R + quiz.intercept_d
        z = float(np.clip(z, -50.0, 50.0))
        return 1.0 / (1.0 + math.exp(-z))

    def get_adaptive_question(
        self,
        user_id: int,
        module_id: int,
        *,
        knowledge_point_id: int | None = None,
        purpose: str | None = None,
        target_probability: float = 0.65,
    ) -> Quiz | None:
        ability = self.get_learner_ability(user_id, module_id)
        answered = {
            question_id
            for (question_id,) in self.db.query(StudentQuestionHistory.question_id)
            .filter(StudentQuestionHistory.user_id == user_id)
            .all()
        }
        query = self.db.query(Quiz).filter(Quiz.module_id == module_id)
        if knowledge_point_id is not None:
            query = query.filter(Quiz.knowledge_point_id == knowledge_point_id)
        if purpose is not None:
            query = query.filter(Quiz.purpose == purpose)
        candidates = [quiz for quiz in query.all() if quiz.id not in answered]
        if not candidates:
            candidates = query.all()
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda quiz: abs(self.probability_predict(ability, quiz) - target_probability),
        )

    def update_student_state(
        self,
        *,
        user_id: int,
        question_id: int,
        is_correct: bool,
        attempt_id: str,
        submitted_answer: str | None = None,
        score: float | None = None,
        session_id: int | None = None,
        stage: str | None = None,
    ) -> tuple[LearnerAbility, bool]:
        existing = (
            self.db.query(StudentQuestionHistory)
            .filter(StudentQuestionHistory.attempt_id == attempt_id)
            .first()
        )
        quiz = self.db.query(Quiz).filter(Quiz.id == question_id).first()
        if quiz is None:
            raise ValueError("Quiz not found.")
        if existing is not None:
            return self.get_learner_ability(user_id, quiz.module_id), False

        ability = self.get_learner_ability(user_id, quiz.module_id)
        attempt = StudentQuestionHistory(
            attempt_id=attempt_id,
            user_id=user_id,
            session_id=session_id,
            question_id=question_id,
            submitted_answer=submitted_answer,
            is_correct=is_correct,
            score=float(is_correct) if score is None else score,
            stage=stage,
        )
        if not quiz.counts_for_mirt:
            self.db.add(attempt)
            self.db.commit()
            return ability, True

        history = (
            self.db.query(StudentQuestionHistory, Quiz)
            .join(Quiz, StudentQuestionHistory.question_id == Quiz.id)
            .filter(
                StudentQuestionHistory.user_id == user_id,
                Quiz.module_id == quiz.module_id,
            )
            .order_by(StudentQuestionHistory.created_at)
            .all()
        )
        observations = [(item, 1.0 if row.is_correct else 0.0) for row, item in history]
        observations.append((quiz, 1.0 if is_correct else 0.0))
        theta = self._map_estimate_ability(
            observations,
            np.array([ability.U, ability.A, ability.R], dtype=float),
        )
        ability.U, ability.A, ability.R = map(float, theta)
        ability.attempt_count += 1
        ability.updated_at = datetime.now()

        self.db.add(attempt)
        self._update_review_state(user_id, quiz.knowledge_point_id, is_correct, ability, quiz)
        upsert_mirt_daily_stat(self.db, user_id, quiz.module_id, is_correct)
        self.db.commit()
        self.db.refresh(ability)
        return ability, True

    def _update_review_state(
        self,
        user_id: int,
        knowledge_point_id: int,
        is_correct: bool,
        ability: LearnerAbility,
        quiz: Quiz,
    ) -> None:
        state = (
            self.db.query(KnowledgePointReviewState)
            .filter_by(user_id=user_id, knowledge_point_id=knowledge_point_id)
            .first()
        )
        if state is None:
            state = KnowledgePointReviewState(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
                stability_hours=0.1,
            )
            self.db.add(state)
        if is_correct:
            predicted = self.probability_predict(ability, quiz)
            multiplier = 1.5 + 2.0 * (1.0 - predicted)
            state.stability_hours = min(
                max(state.stability_hours or 0.1, 0.1) * multiplier,
                24 * 90,
            )
        else:
            state.stability_hours = 0.5
        state.last_result = is_correct
        state.due_at = datetime.now() + timedelta(hours=state.stability_hours)
        state.updated_at = datetime.now()

    @staticmethod
    def _map_estimate_ability(
        observations: list[tuple[Quiz, float]],
        theta_init: np.ndarray,
    ) -> np.ndarray:
        theta = np.asarray(theta_init, dtype=float).reshape(3).copy()
        regularization = 1.0 / (MAP_PRIOR_SIGMA**2)

        for _ in range(MAP_NEWTON_MAX_ITER):
            gradient = regularization * theta.copy()
            hessian = regularization * np.eye(3)
            for quiz, outcome in observations:
                discrimination = np.array([quiz.U, quiz.A, quiz.R], dtype=float)
                z = float(np.clip(np.dot(discrimination, theta) + quiz.intercept_d, -50, 50))
                probability = 1.0 / (1.0 + math.exp(-z))
                gradient += (probability - outcome) * discrimination
                hessian += (
                    probability
                    * (1.0 - probability)
                    * np.outer(discrimination, discrimination)
                )
            try:
                delta = np.linalg.solve(hessian, gradient)
            except np.linalg.LinAlgError:
                delta = np.linalg.lstsq(hessian, gradient, rcond=None)[0]
            next_theta = np.clip(theta - delta, -THETA_CLIP, THETA_CLIP)
            if np.linalg.norm(next_theta - theta) < MAP_NEWTON_TOL:
                theta = next_theta
                break
            theta = next_theta
        return np.clip(theta, -THETA_CLIP, THETA_CLIP)
