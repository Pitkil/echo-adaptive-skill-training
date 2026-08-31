"""Course-owned semantic coverage rules loaded from course data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RequestCoverageRule:
    markers: tuple[str, ...]
    required_concepts: tuple[tuple[str, ...], ...]
    match_all: bool = False


@dataclass(frozen=True)
class DifficultyCoverageRule:
    difficulties: tuple[str, ...]
    required_concepts: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class CoverageRubric:
    concepts: tuple[tuple[str, ...], ...]
    request_rules: tuple[RequestCoverageRule, ...] = ()
    difficulty_rules: tuple[DifficultyCoverageRule, ...] = ()


def _string_tuple(values: object) -> tuple[str, ...]:
    if not isinstance(values, list) or not all(
        isinstance(value, str) and value for value in values
    ):
        raise ValueError("coverage rule values must be non-empty strings")
    return tuple(values)


def _concepts(values: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(values, list):
        raise ValueError("coverage concepts must be a list")
    return tuple(_string_tuple(value) for value in values)


def _load_course_rubrics() -> dict[tuple[str, str], CoverageRubric]:
    data_path = Path(__file__).with_name("course_data") / "ms_sk_engineering_rubrics.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    program_code = str(payload.get("program_code") or "").strip()
    points = payload.get("knowledge_points")
    if not program_code or not isinstance(points, dict):
        raise ValueError(f"invalid course coverage data: {data_path}")
    loaded: dict[tuple[str, str], CoverageRubric] = {}
    for point_name, raw in points.items():
        if not isinstance(point_name, str) or not isinstance(raw, dict):
            raise ValueError(f"invalid knowledge-point coverage data: {point_name!r}")
        request_rules = tuple(
            RequestCoverageRule(
                markers=_string_tuple(item.get("markers")),
                required_concepts=_concepts(item.get("required_concepts")),
                match_all=bool(item.get("match_all", False)),
            )
            for item in raw.get("request_rules", [])
            if isinstance(item, dict)
        )
        difficulty_rules = tuple(
            DifficultyCoverageRule(
                difficulties=_string_tuple(item.get("difficulties")),
                required_concepts=_concepts(item.get("required_concepts")),
            )
            for item in raw.get("difficulty_rules", [])
            if isinstance(item, dict)
        )
        loaded[(program_code, point_name)] = CoverageRubric(
            concepts=_concepts(raw.get("concepts")),
            request_rules=request_rules,
            difficulty_rules=difficulty_rules,
        )
    return loaded


COURSE_COVERAGE_RUBRICS = _load_course_rubrics()


def get_coverage_rubric(
    program_code: str | None, knowledge_point_name: str
) -> CoverageRubric | None:
    if not program_code:
        return None
    return COURSE_COVERAGE_RUBRICS.get((program_code, knowledge_point_name))


def concept_present(content: str, alternatives: tuple[str, ...]) -> bool:
    """Return whether a term appears outside an insufficiency paragraph."""

    insufficiency_markers = (
        "证据不足",
        "暂不能确认",
        "不能确认",
        "无法确认",
        "没有列出",
        "未列出",
        "没有提到",
        "未提到",
        "未给出",
    )
    paragraphs = [
        paragraph.casefold().strip()
        for paragraph in content.replace("\r\n", "\n").split("\n\n")
        if paragraph.strip()
    ]
    for paragraph in paragraphs:
        if any(marker in paragraph for marker in insufficiency_markers):
            continue
        if any(term.casefold() in paragraph for term in alternatives):
            return True
    return False


def request_rule_matches(rule: RequestCoverageRule, user_input: str) -> bool:
    normalized = user_input.casefold()
    matches = [marker.casefold() in normalized for marker in rule.markers]
    return all(matches) if rule.match_all else any(matches)


def request_coverage_issues(
    *,
    program_code: str | None,
    knowledge_point_name: str,
    user_input: str,
    content: str,
) -> list[str]:
    rubric = get_coverage_rubric(program_code, knowledge_point_name)
    if rubric is None:
        return []
    issues: list[str] = []
    for rule in rubric.request_rules:
        if not request_rule_matches(rule, user_input):
            continue
        missing = [
            concept
            for concept in rule.required_concepts
            if not concept_present(content, concept)
        ]
        if missing:
            labels = ["/".join(concept) for concept in missing]
            issues.append("未直接满足学习需求：" + "、".join(labels))
    return issues


def request_coverage_requirements(
    *, program_code: str | None, knowledge_point_name: str, user_input: str
) -> list[str]:
    rubric = get_coverage_rubric(program_code, knowledge_point_name)
    if rubric is None:
        return []
    requirements: list[str] = []
    for rule in rubric.request_rules:
        if request_rule_matches(rule, user_input):
            requirements.extend("/".join(concept) for concept in rule.required_concepts)
    return list(dict.fromkeys(requirements))


def semantic_coverage_requirements(
    *,
    program_code: str | None,
    knowledge_point_name: str,
    user_input: str,
    difficulty: str | None = None,
    include_core_concepts: bool = True,
) -> list[str]:
    """Describe course expectations for a semantic judge, not a word matcher."""

    rubric = get_coverage_rubric(program_code, knowledge_point_name)
    requirements = [f"直接回答学习者关于“{knowledge_point_name}”的问题"]
    if rubric is None:
        return requirements
    if include_core_concepts:
        requirements.extend(" / ".join(concept) for concept in rubric.concepts)
    for rule in rubric.request_rules:
        if request_rule_matches(rule, user_input):
            requirements.extend(" / ".join(concept) for concept in rule.required_concepts)
    if difficulty:
        for rule in rubric.difficulty_rules:
            if difficulty in rule.difficulties:
                requirements.extend(" / ".join(concept) for concept in rule.required_concepts)
    return list(dict.fromkeys(requirements))


def difficulty_coverage_issues(
    *,
    program_code: str | None,
    knowledge_point_name: str,
    difficulty: str,
    content: str,
) -> list[str]:
    rubric = get_coverage_rubric(program_code, knowledge_point_name)
    if rubric is None:
        return []
    issues: list[str] = []
    for rule in rubric.difficulty_rules:
        if difficulty not in rule.difficulties:
            continue
        missing = [
            concept
            for concept in rule.required_concepts
            if not concept_present(content, concept)
        ]
        if missing:
            labels = ["/".join(concept) for concept in missing]
            issues.append("未达到课程难度覆盖要求：" + "、".join(labels))
    return issues
