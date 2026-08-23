from __future__ import annotations

from datetime import date, datetime, timedelta

from database import (
    Base,
    EvidenceStatus,
    KnowledgeBase,
    KnowledgePoint,
    LearnerAbility,
    MicroDetectionJob,
    MicroRepresentationEvent,
    MirtDailyModuleStats,
    Organization,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
    TrainingProgram,
    User,
)
from MIRT.analysis_agent import LearnerInsightService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_learning_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    organization = Organization(code="ORG", name="Test Organization")
    db.add(organization)
    db.flush()
    user = User(
        organization_id=organization.id,
        username="insight-learner",
        hashed_password="not-used-in-unit-test",
    )
    knowledge_base = KnowledgeBase(
        organization_id=organization.id,
        code="KB",
        name="Test Knowledge Base",
    )
    program = TrainingProgram(
        organization_id=organization.id,
        code="PROGRAM",
        name="Semantic Kernel Training",
    )
    db.add_all([user, knowledge_base, program])
    db.flush()
    module = TrainingModule(
        program_id=program.id,
        knowledge_base_id=knowledge_base.id,
        code="M1",
        name="Kernel and plugins",
        sequence=1,
    )
    db.add(module)
    db.flush()
    weak_point = KnowledgePoint(
        module_id=module.id,
        code="M1-K1",
        name="Kernel configuration",
        sequence=1,
    )
    next_point = KnowledgePoint(
        module_id=module.id,
        code="M1-K2",
        name="Plugin invocation",
        sequence=2,
    )
    db.add_all([weak_point, next_point])
    db.flush()
    weak_quiz = Quiz(
        module_id=module.id,
        knowledge_point_id=weak_point.id,
        content="How should a Kernel be configured?",
        answer="Register the required services.",
        type="Short",
        purpose="pretest",
        difficulty="foundation",
        U=1.0,
        A=0.8,
        R=0.6,
    )
    next_quiz = Quiz(
        module_id=module.id,
        knowledge_point_id=next_point.id,
        content="How is a plugin invoked?",
        answer="Through a registered function.",
        type="Short",
        purpose="practice",
        difficulty="standard",
        U=0.6,
        A=1.0,
        R=0.8,
    )
    db.add_all([weak_quiz, next_quiz])
    db.commit()
    return db, organization, user, module, weak_point, next_point, weak_quiz, next_quiz


def test_learning_insight_has_fixed_sections_and_traceable_recommendation() -> None:
    (
        db,
        organization,
        user,
        module,
        weak_point,
        next_point,
        weak_quiz,
        next_quiz,
    ) = make_learning_context()
    now = datetime.now()
    db.add(
        LearnerAbility(
            user_id=user.id,
            module_id=module.id,
            U=0.2,
            A=-0.8,
            R=0.4,
            attempt_count=3,
        )
    )
    db.add_all(
        [
            StudentQuestionHistory(
                attempt_id="weak-attempt-1",
                user_id=user.id,
                question_id=weak_quiz.id,
                submitted_answer="wrong",
                is_correct=False,
                score=0.0,
                created_at=now - timedelta(days=1),
            ),
            StudentQuestionHistory(
                attempt_id="weak-attempt-2",
                user_id=user.id,
                question_id=weak_quiz.id,
                submitted_answer="still wrong",
                is_correct=False,
                score=0.0,
                created_at=now,
            ),
            StudentQuestionHistory(
                attempt_id="next-attempt-1",
                user_id=user.id,
                question_id=next_quiz.id,
                submitted_answer="correct",
                is_correct=True,
                score=1.0,
                created_at=now - timedelta(days=8),
            ),
            MirtDailyModuleStats(
                user_id=user.id,
                module_id=module.id,
                stat_date=date.today(),
                attempt_count=2,
                correct_count=0,
            ),
            MirtDailyModuleStats(
                user_id=user.id,
                module_id=module.id,
                stat_date=date.today() - timedelta(days=8),
                attempt_count=1,
                correct_count=1,
            ),
        ]
    )
    job = MicroDetectionJob(
        id="job-insight-1",
        organization_id=organization.id,
        learner_id=user.id,
        module_id=module.id,
        knowledge_point_id=weak_point.id,
        source_type="learner_voice",
        audio_uri="private://recording/1",
        consent_granted=True,
    )
    event = MicroRepresentationEvent(
        id="event-insight-1",
        job_id=job.id,
        organization_id=organization.id,
        learner_id=user.id,
        module_id=module.id,
        knowledge_point_id=weak_point.id,
        source_type="learner_voice",
        event_type="hesitation",
        start_ms=100,
        end_ms=900,
        confidence=0.92,
        evidence_status=EvidenceStatus.CONFIRMED.value,
    )
    db.add_all([job, event])
    db.commit()

    profile = LearnerInsightService(db).build_profile(
        user.id,
        module.id,
        memory_items=[
            {
                "memory_id": "memory-1",
                "organization_id": organization.id,
                "user_id": user.id,
                "program_id": module.program_id,
                "module_id": module.id,
                "memory_type": "learning_preference",
                "content": "Short steps with explicit checkpoints work well.",
                "occurred_at": now.isoformat(),
            }
        ],
    )

    assert set(profile["views"]) == {
        "ability_and_trend",
        "evidence_and_blind_spots",
        "path_and_resources",
    }
    ability_view = profile["views"]["ability_and_trend"]
    assert ability_view["accuracy_trend"]["direction"] == "declined"
    assert ability_view["ability_trend"]["A"]["direction"] == "insufficient_evidence"

    evidence_view = profile["views"]["evidence_and_blind_spots"]
    assert len(evidence_view["knowledge_blind_spots"]) == 1
    blind_spot = evidence_view["knowledge_blind_spots"][0]
    assert blind_spot["knowledge_point_id"] == weak_point.id
    assert {item["attempt_id"] for item in blind_spot["evidence"]} == {
        "weak-attempt-1",
        "weak-attempt-2",
    }
    assert all(item["occurred_at"] for item in blind_spot["evidence"])

    path_view = profile["views"]["path_and_resources"]
    assert path_view["learner_profile"]["type"] == "P1"
    assert path_view["learner_profile"]["evidence_status"] == "supported"
    assert path_view["recommended_difficulty"] == "foundation"
    assert path_view["next_knowledge_point"]["knowledge_point_id"] == weak_point.id
    assert path_view["recommended_content_format"] == "practice_guide"
    assert path_view["recommended_tutoring_method"] == "step_by_step_with_checkpoints"
    assert path_view["primary_content_decision"]["action"] == "generate_resource"
    assert path_view["primary_content_decision"]["resource_type"] == "practice_guide"
    assert path_view["primary_content_decision"]["resource_count"] == 1
    assert (
        path_view["primary_content_decision"]["selection_policy"]
        == "single_most_needed"
    )
    assert {item["source_type"] for item in path_view["evidence_sources"]} >= {
        "scored_attempt",
        "confirmed_micro_event",
        "long_term_memory",
        "curriculum",
    }

    assert profile["narrative_report"]["source"] == "deterministic_template"
    assert "知识盲区" in profile["narrative_report"]["evidence_and_blind_spots"]
    assert "P1（基础巩固型）" in profile["narrative_report"]["path_and_resources"]
    assert next_point.id != path_view["next_knowledge_point"]["knowledge_point_id"]


def test_learning_insight_does_not_invent_ability_or_blind_spots_without_attempts() -> None:
    db, _, user, module, first_point, _, _, _ = make_learning_context()

    profile = LearnerInsightService(db).build_profile(user.id, module.id)

    ability_view = profile["views"]["ability_and_trend"]
    evidence_view = profile["views"]["evidence_and_blind_spots"]
    path_view = profile["views"]["path_and_resources"]
    assert ability_view["ability"]["attempt_count"] == 0
    assert ability_view["ability_trend"]["U"]["direction"] == "insufficient_evidence"
    assert evidence_view["knowledge_blind_spots"] == []
    assert evidence_view["mastered_knowledge_points"] == []
    assert path_view["primary_content_decision"] == {
        "action": "complete_pretest",
        "content_format": "diagnostic_pretest",
        "resource_type": None,
        "resource_count": 0,
        "selection_policy": "single_most_needed",
        "knowledge_point_id": first_point.id,
        "difficulty": "foundation",
    }
    assert path_view["learner_profile"]["type"] is None
    assert path_view["learner_profile"]["evidence_status"] == "insufficient"
    assert "暂不能判断" in profile["narrative_report"]["ability_and_trend"]
    assert "暂不能判断" in profile["narrative_report"]["evidence_and_blind_spots"]
    assert "尚不能确定 P1、P2 或 P3" in profile["narrative_report"]["path_and_resources"]


def test_three_fixed_learner_profiles_produce_distinct_supported_requirements() -> None:
    classifier = LearnerInsightService._classify_learner_profile

    p1 = classifier(
        attempts=4,
        ability_values={"U": -0.4, "A": -0.8, "R": -0.2},
        average_accuracy=0.4,
        blind_spots=[{"knowledge_point_id": 1}],
    )
    p2 = classifier(
        attempts=6,
        ability_values={"U": 0.7, "A": 0.1, "R": 0.5},
        average_accuracy=0.7,
        blind_spots=[],
    )
    p3 = classifier(
        attempts=8,
        ability_values={"U": 1.0, "A": 0.9, "R": 0.8},
        average_accuracy=0.875,
        blind_spots=[],
    )

    assert [p1["type"], p2["type"], p3["type"]] == ["P1", "P2", "P3"]
    assert p1["content_requirements"]["support_level"] == "high"
    assert p2["content_requirements"]["explanation_depth"] == "application_focused"
    assert p3["content_requirements"]["step_detail"] == "high_level"
    assert len({p1["reason"], p2["reason"], p3["reason"]}) == 3
