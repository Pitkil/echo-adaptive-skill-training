from __future__ import annotations

import app as app_module
from app import app, create_access_token, ensure_catalog, get_db
from database import (
    Base,
    GeneratedResource,
    KnowledgePoint,
    LearnerAbility,
    Organization,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
    TrainingProgram,
    User,
    UserRole,
)
from fastapi.testclient import TestClient
from resource_generation import (
    ContentVerificationAgent,
    ResourceGenerationAgent,
    build_personalization_plan,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class FakeMemoryClient:
    configured = True

    def search(self, request):
        return [
            {
                "content": "The learner benefits from short steps and explicit checkpoints.",
                "memory_type": "learning_preference",
            }
        ]


class FakePunditRAGClient:
    configured = True

    def search(
        self,
        query,
        knowledge_base_id,
        module_id,
        *,
        trace_id=None,
        knowledge_point_ids=None,
        top_k=None,
    ):
        return [
            {
                "text": (
                    "Official guidance defines the target concept, its inputs and outputs, "
                    "and recommends validating the smallest runnable implementation first."
                ),
                "metadata": {
                    "source_title": "Microsoft Learn",
                    "source_url": "https://learn.microsoft.com/",
                    "source_section": "Official guidance",
                },
            }
        ]


def test_draft_resources_do_not_claim_missing_evidence() -> None:
    plan = build_personalization_plan(
        {"views": {}},
        knowledge_point_id=1,
        knowledge_point_name="Kernel setup",
    )
    resources, error = ResourceGenerationAgent().generate(plan, [])

    assert error is None
    assert len(resources) == 3
    assert all("[1]" not in item["content"] for item in resources)
    assert all(
        not ContentVerificationAgent().verify(item, plan, []).passed
        for item in resources
    )


def test_resource_generation_uses_profile_memory_and_blind_spot(monkeypatch) -> None:
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
        username="personalized-resource-learner",
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
    quiz = (
        db.query(Quiz)
        .filter_by(module_id=module.id, knowledge_point_id=point.id)
        .order_by(Quiz.id)
        .first()
    )
    db.add(
        LearnerAbility(
            user_id=learner.id,
            module_id=module.id,
            U=0.4,
            A=-1.0,
            R=0.2,
            attempt_count=2,
        )
    )
    db.add_all(
        [
            StudentQuestionHistory(
                attempt_id=f"resource-wrong-{index}",
                user_id=learner.id,
                question_id=quiz.id,
                submitted_answer="wrong",
                is_correct=False,
                score=0.0,
            )
            for index in range(2)
        ]
    )
    db.commit()
    db.refresh(learner)

    monkeypatch.setattr(app_module, "SimpleMemClient", FakeMemoryClient)
    monkeypatch.setattr(app_module, "PunditRAGClient", FakePunditRAGClient)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
    response = TestClient(app).post(
        "/v1/resources/generate",
        json={"user_id": learner.id, "module_id": module.id},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["knowledge_point_id"] == point.id
    assert payload["plan"]["weakest_dimension"] == "A"
    assert payload["plan"]["difficulty"] == "foundation"
    assert payload["plan"]["memory_hints"]
    assert len(payload["items"]) == 3
    assert all(item["verification_passed"] for item in payload["items"])

    resources = db.query(GeneratedResource).filter_by(user_id=learner.id).all()
    assert len(resources) == 3
    assert all(item.knowledge_point_id == point.id for item in resources)
    assert all(item.difficulty == "foundation" for item in resources)
    assert all(point.name in item.content for item in resources)

    app.dependency_overrides.clear()
    db.close()
