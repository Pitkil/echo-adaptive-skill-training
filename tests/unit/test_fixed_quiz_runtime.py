from __future__ import annotations

import app as app_module
from app import app, create_access_token, ensure_catalog, get_db
from database import (
    Base,
    KnowledgePoint,
    Organization,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
    TrainingProgram,
    User,
    UserRole,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_fixed_quiz_is_selected_by_purpose_and_scored_on_server() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    ensure_catalog(db)
    organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
    learner = User(
        organization_id=organization.id,
        username="fixed-quiz-learner",
        hashed_password="not-used",
        role=UserRole.LEARNER.value,
    )
    db.add(learner)
    db.flush()
    program = db.query(TrainingProgram).filter_by(organization_id=organization.id).one()
    module = (
        db.query(TrainingModule)
        .filter_by(program_id=program.id)
        .order_by(TrainingModule.sequence)
        .first()
    )
    point = (
        db.query(KnowledgePoint)
        .filter_by(module_id=module.id)
        .order_by(KnowledgePoint.sequence)
        .first()
    )
    pretest = Quiz(
        module_id=module.id,
        knowledge_point_id=point.id,
        content="Kernel 的主要作用是？\nA. 管理界面\nB. 组织模型服务与插件",
        answer="B",
        type="MCQ",
        purpose="pretest",
        difficulty="foundation",
        scoring_method="选择 B 得 1 分。",
        source_title="Understanding the kernel",
        source_url="https://learn.microsoft.com/semantic-kernel/concepts/kernel",
        source_section="The kernel is at the center",
        counts_for_mirt=True,
    )
    stage_test = Quiz(
        module_id=module.id,
        knowledge_point_id=point.id,
        content="这是一道阶段题。",
        answer="阶段答案",
        type="Open",
        purpose="stage_test",
        counts_for_mirt=False,
    )
    db.add_all([pretest, stage_test])
    db.commit()
    db.refresh(learner)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
    client = TestClient(app)

    question_response = client.get(
        f"/v1/quizzes/next?module_id={module.id}&purpose=pretest",
        headers=headers,
    )
    assert question_response.status_code == 200
    question = question_response.json()
    assert question["question_id"] == pretest.id
    assert question["purpose"] == "pretest"
    assert "answer" not in question
    assert "scoring_method" not in question

    submit_response = client.post(
        "/quiz/submit",
        json={
            "user_id": learner.id,
            "question_id": pretest.id,
            "answer": "B",
            "attempt_id": "fixed-pretest-001",
        },
        headers=headers,
    )
    assert submit_response.status_code == 200
    result = submit_response.json()
    assert result["is_correct"] is True
    assert result["score"] == 1.0
    assert result["counts_for_mirt"] is True

    history = db.query(StudentQuestionHistory).filter_by(attempt_id="fixed-pretest-001").one()
    assert history.submitted_answer == "B"
    assert history.is_correct is True
    assert history.score == 1.0

    forged_response = client.post(
        "/quiz/submit",
        json={
            "user_id": learner.id,
            "question_id": stage_test.id,
            "is_correct": True,
            "attempt_id": "forged-result",
        },
        headers=headers,
    )
    assert forged_response.status_code == 422
    assert db.query(StudentQuestionHistory).filter_by(attempt_id="forged-result").count() == 0

    app.dependency_overrides.clear()
    db.close()


def test_requested_quiz_purpose_defaults_to_fixed_stage_test() -> None:
    assert app_module.requested_quiz_purpose("开始当前模块前测") == "pretest"
    assert app_module.requested_quiz_purpose("请给我一道阶段测验") == "stage_test"
    assert app_module.requested_quiz_purpose("开始当前模块后测") == "posttest"
    assert app_module.requested_quiz_purpose("来一道练习题") == "practice"
