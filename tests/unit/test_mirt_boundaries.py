from __future__ import annotations

from database import (
    Base,
    EvidenceStatus,
    KnowledgeBase,
    KnowledgePoint,
    MicroDetectionJob,
    MicroRepresentationEvent,
    Organization,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
    TrainingProgram,
    User,
)
from Quiz.AdaptiveEngine import AdaptiveEngine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_training_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    organization = Organization(code="ORG", name="Test Organization")
    session.add(organization)
    session.flush()
    user = User(
        organization_id=organization.id,
        username="learner",
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
        name="Enterprise RAG",
    )
    session.add_all([user, knowledge_base, program])
    session.flush()
    module = TrainingModule(
        program_id=program.id,
        knowledge_base_id=knowledge_base.id,
        code="M1",
        name="Enterprise Knowledge Base",
        sequence=1,
    )
    session.add(module)
    session.flush()
    point = KnowledgePoint(module_id=module.id, code="KP1", name="Chunking", sequence=1)
    session.add(point)
    session.flush()
    quiz = Quiz(
        module_id=module.id,
        knowledge_point_id=point.id,
        content="What is semantic chunking?",
        answer="Meaning-aware segmentation",
        type="Short",
        U=1.0,
        A=0.8,
        R=0.6,
    )
    session.add(quiz)
    session.commit()
    return session, organization, user, module, point, quiz


def test_duplicate_attempt_does_not_update_mirt_twice() -> None:
    db, _, user, _, _, quiz = make_training_context()
    engine = AdaptiveEngine(db)

    first, first_updated = engine.update_student_state(
        user_id=user.id,
        question_id=quiz.id,
        is_correct=True,
        attempt_id="attempt-001",
    )
    first_values = (first.U, first.A, first.R, first.attempt_count)
    second, second_updated = engine.update_student_state(
        user_id=user.id,
        question_id=quiz.id,
        is_correct=True,
        attempt_id="attempt-001",
    )

    assert first_updated is True
    assert second_updated is False
    assert (second.U, second.A, second.R, second.attempt_count) == first_values
    assert db.query(StudentQuestionHistory).count() == 1


def test_micro_representation_event_does_not_modify_mirt_ability() -> None:
    db, organization, user, module, point, quiz = make_training_context()
    ability, _ = AdaptiveEngine(db).update_student_state(
        user_id=user.id,
        question_id=quiz.id,
        is_correct=False,
        attempt_id="attempt-002",
    )
    before = (ability.U, ability.A, ability.R)
    job = MicroDetectionJob(
        id="job-001",
        organization_id=organization.id,
        learner_id=user.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type="learner_voice",
        audio_uri="file:///test.webm",
        consent_granted=True,
    )
    event = MicroRepresentationEvent(
        id="event-001",
        job_id=job.id,
        organization_id=organization.id,
        learner_id=user.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        source_type="learner_voice",
        event_type="hesitation",
        start_ms=100,
        end_ms=900,
        confidence=0.91,
        evidence_status=EvidenceStatus.CONFIRMED.value,
    )
    db.add_all([job, event])
    db.commit()
    db.refresh(ability)

    assert (ability.U, ability.A, ability.R) == before


def test_question_marked_without_mirt_update_only_records_attempt() -> None:
    db, _, user, _, _, quiz = make_training_context()
    quiz.counts_for_mirt = False
    db.commit()

    ability, updated = AdaptiveEngine(db).update_student_state(
        user_id=user.id,
        question_id=quiz.id,
        is_correct=True,
        attempt_id="attempt-no-mirt",
    )

    assert updated is True
    assert (ability.U, ability.A, ability.R, ability.attempt_count) == (0.0, 0.0, 0.0, 0)
    assert db.query(StudentQuestionHistory).filter_by(attempt_id="attempt-no-mirt").count() == 1
