"""Deterministic server-side grading for fixed quiz-bank questions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from database import Quiz

OBJECTIVE_TYPES = {
    "choice",
    "mcq",
    "truefalse",
    "singlechoice",
    "multiplechoice",
    "判断题",
    "选择题",
}


@dataclass(frozen=True)
class QuizGrade:
    is_correct: bool
    score: float
    grading_mode: str


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return re.sub(r"[\s，。！？、；：,.!?;:\"'“”‘’（）()\[\]]+", "", normalized)


def _choice_token(value: str) -> str | None:
    match = re.match(r"^\s*([a-h])(?:\s*[\.\、:：)]|\s*$)", value or "", re.IGNORECASE)
    return match.group(1).casefold() if match else None


def grade_quiz_answer(quiz: Quiz, submitted_answer: str) -> QuizGrade:
    """Grade without trusting a client-provided correctness flag."""

    submitted = submitted_answer.strip()
    if not submitted:
        raise ValueError("Answer is empty.")

    references = [item.strip() for item in quiz.answer.split("|") if item.strip()]
    quiz_type = (quiz.type or "").replace("_", "").replace("-", "").casefold()
    if quiz_type in OBJECTIVE_TYPES:
        submitted_choice = _choice_token(submitted)
        correct = any(
            (
                submitted_choice is not None
                and submitted_choice == _choice_token(reference)
            )
            or _normalize(submitted) == _normalize(reference)
            for reference in references
        )
        return QuizGrade(is_correct=correct, score=float(correct), grading_mode="exact")

    normalized_submission = _normalize(submitted)
    correct = any(
        normalized_submission == normalized_reference
        or (
            len(normalized_reference) >= 4
            and normalized_reference in normalized_submission
        )
        for reference in references
        if (normalized_reference := _normalize(reference))
    )
    return QuizGrade(is_correct=correct, score=float(correct), grading_mode="reference_match")
