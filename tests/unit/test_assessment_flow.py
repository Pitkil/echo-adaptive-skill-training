from __future__ import annotations

from datetime import datetime, timedelta

from database import (
    Base,
    KnowledgeBase,
    KnowledgePoint,
    Organization,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
    TrainingProgram,
    User,
)
from Quiz.assessment_flow import AssessmentFlowService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def build_flow_data() -> tuple[Session, User, TrainingModule, list[KnowledgePoint], dict[str, Quiz]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(code="FLOW", name="Flow Test")
    db.add(organization)
    db.flush()
    knowledge_base = KnowledgeBase(
        organization_id=organization.id,
        code="FLOW-KB",
        name="Flow KB",
    )
    program = TrainingProgram(
        organization_id=organization.id,
        code="FLOW-PROGRAM",
        name="Flow Program",
    )
    learner = User(
        organization_id=organization.id,
        username="flow-learner",
        hashed_password="not-used",
        role="learner",
    )
    db.add_all([knowledge_base, program, learner])
    db.flush()
    module = TrainingModule(
        program_id=program.id,
        knowledge_base_id=knowledge_base.id,
        code="M1",
        name="Flow Module",
        sequence=1,
    )
    db.add(module)
    db.flush()
    points = [
        KnowledgePoint(module_id=module.id, code="KP1", name="Point 1", sequence=1),
        KnowledgePoint(module_id=module.id, code="KP2", name="Point 2", sequence=2),
    ]
    db.add_all(points)
    db.flush()
    quizzes = {
        "pretest": Quiz(
            module_id=module.id,
            knowledge_point_id=points[0].id,
            content="Pretest",
            answer="A",
            purpose="pretest",
        ),
        "practice_1": Quiz(
            module_id=module.id,
            knowledge_point_id=points[0].id,
            content="Practice 1",
            answer="A",
            purpose="practice",
        ),
        "practice_2": Quiz(
            module_id=module.id,
            knowledge_point_id=points[1].id,
            content="Practice 2",
            answer="A",
            purpose="practice",
        ),
        "stage_test": Quiz(
            module_id=module.id,
            knowledge_point_id=points[0].id,
            content="Stage",
            answer="A",
            purpose="stage_test",
        ),
        "posttest": Quiz(
            module_id=module.id,
            knowledge_point_id=points[1].id,
            content="Posttest",
            answer="A",
            purpose="posttest",
        ),
    }
    db.add_all(quizzes.values())
    db.commit()
    return db, learner, module, points, quizzes


def add_attempt(
    db: Session,
    *,
    learner: User,
    quiz: Quiz,
    attempt_id: str,
    score: float,
    created_at: datetime,
) -> None:
    db.add(
        StudentQuestionHistory(
            attempt_id=attempt_id,
            user_id=learner.id,
            question_id=quiz.id,
            submitted_answer="A",
            is_correct=score >= 1.0,
            score=score,
            created_at=created_at,
        )
    )
    db.commit()


def test_assessment_flow_unlocks_only_the_server_selected_next_phase() -> None:
    db, learner, module, _, quizzes = build_flow_data()
    flow = AssessmentFlowService(db, user_id=learner.id, module_id=module.id)
    started_at = datetime(2026, 1, 1, 9, 0)

    initial = flow.progress()
    assert initial.next_action == "start_pretest"
    assert flow.can_request("pretest")[0] is True
    assert flow.can_request("posttest")[0] is False

    add_attempt(
        db,
        learner=learner,
        quiz=quizzes["pretest"],
        attempt_id="pretest-1",
        score=1.0,
        created_at=started_at,
    )
    learning = flow.progress()
    assert learning.next_action == "practice"
    assert learning.practice_coverage == 0
    assert flow.can_request("stage_test")[0] is False

    for offset, key in enumerate(("practice_1", "practice_2"), start=1):
        add_attempt(
            db,
            learner=learner,
            quiz=quizzes[key],
            attempt_id=f"practice-{offset}",
            score=1.0,
            created_at=started_at + timedelta(minutes=offset),
        )
    stage_ready = flow.progress()
    assert stage_ready.next_action == "start_stage_test"
    assert stage_ready.practice_coverage == 2
    assert flow.can_request("stage_test")[0] is True

    db.close()


def test_assessment_flow_requires_remediation_before_stage_retake_and_posttest() -> None:
    db, learner, module, _, quizzes = build_flow_data()
    flow = AssessmentFlowService(db, user_id=learner.id, module_id=module.id)
    started_at = datetime(2026, 1, 2, 9, 0)
    for offset, (key, score) in enumerate(
        (
            ("pretest", 1.0),
            ("practice_1", 1.0),
            ("practice_2", 1.0),
            ("stage_test", 0.5),
        )
    ):
        add_attempt(
            db,
            learner=learner,
            quiz=quizzes[key],
            attempt_id=f"first-{key}",
            score=score,
            created_at=started_at + timedelta(minutes=offset),
        )

    remediation = flow.progress()
    assert remediation.state == "remediation"
    assert remediation.next_action == "practice"
    assert flow.can_request("stage_test")[0] is False
    assert flow.can_request("posttest")[0] is False

    add_attempt(
        db,
        learner=learner,
        quiz=quizzes["practice_1"],
        attempt_id="remediation-practice",
        score=1.0,
        created_at=started_at + timedelta(minutes=5),
    )
    assert flow.progress().next_action == "start_stage_test"

    add_attempt(
        db,
        learner=learner,
        quiz=quizzes["stage_test"],
        attempt_id="stage-pass",
        score=1.0,
        created_at=started_at + timedelta(minutes=6),
    )
    assert flow.progress().next_action == "start_posttest"
    assert flow.can_request("posttest")[0] is True

    add_attempt(
        db,
        learner=learner,
        quiz=quizzes["posttest"],
        attempt_id="posttest-pass",
        score=1.0,
        created_at=started_at + timedelta(minutes=7),
    )
    completed = flow.progress()
    assert completed.state == "completed"
    assert completed.next_action == "view_report"

    db.close()


def test_assessment_flow_reports_missing_fixed_pretest_content() -> None:
    db, learner, module, _, quizzes = build_flow_data()
    db.delete(quizzes["pretest"])
    db.commit()

    progress = AssessmentFlowService(
        db,
        user_id=learner.id,
        module_id=module.id,
    ).progress()

    assert progress.state == "content_missing"
    assert progress.button_enabled is False
    assert "前测题库" in progress.title
    db.close()
