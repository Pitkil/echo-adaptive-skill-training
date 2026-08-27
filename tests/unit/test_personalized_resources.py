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
    TurnExecution,
    Upload,
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
    requests = []

    def search(self, request):
        self.requests.append(request)
        return [
            {
                "content": "The learner benefits from short steps and explicit checkpoints.",
                "memory_type": "learning_preference",
            }
        ]

    def upsert(self, record):
        return {
            "status": "created",
            "memory_id": f"memory-{record.user_id}-{record.module_id}",
            "idempotency_key": record.idempotency_key,
            "conflict_memory_ids": [],
        }


class FakePunditRAGClient:
    configured = True

    def search(
        self,
        query,
        knowledge_base_id,
        module_id,
        *,
        external_knowledge_base_id=None,
        external_document_ids=None,
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
                    "external_document_id": "pundit-document-1",
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
    assert len(resources) == 1
    assert resources[0]["resource_type"] == "custom_note"
    assert all("[1]" not in item["content"] for item in resources)
    assert all(
        not ContentVerificationAgent().verify(item, plan, []).passed
        for item in resources
    )


def test_resource_generation_uses_profile_memory_and_blind_spot(monkeypatch) -> None:
    FakeMemoryClient.requests.clear()
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
    module.knowledge_base.external_ref = "pundit-kb-1"
    db.add(
        Upload(
            user_id=learner.id,
            module_id=module.id,
            knowledge_base_id=module.knowledge_base_id,
            filename="semantic-kernel.md",
            filepath="data/test/semantic-kernel.md",
            file_type="text/markdown",
            file_size=128,
            source_title="Microsoft Learn Semantic Kernel",
            source_url="https://learn.microsoft.com/semantic-kernel/overview/",
            source_section="Overview",
            source_version="2026-08-19",
            external_document_id="pundit-document-1",
            external_task_id="pundit-task-1",
            index_status="completed",
        )
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
    assert len(payload["items"]) == 1
    assert payload["items"][0]["resource_type"] == "practice_guide"
    assert payload["items"][0]["status"] == "pending_review"
    assert all(item["verification_passed"] for item in payload["items"])

    resources = db.query(GeneratedResource).filter_by(user_id=learner.id).all()
    assert len(resources) == 1
    assert all(item.knowledge_point_id == point.id for item in resources)
    assert all(item.difficulty == "foundation" for item in resources)
    assert all(point.name in item.content for item in resources)
    execution = db.query(TurnExecution).filter_by(user_id=learner.id).one()
    assert execution.primary_action == "GENERATE_RESOURCE"
    assert set(execution.result["agent_records"]) == {
        "analysis",
        "generation",
        "validation",
        "next_action",
    }
    assert all(
        item["persisted_in_system"] is True
        for item in execution.result["agent_records"].values()
    )
    memory_request = FakeMemoryClient.requests[-1]
    assert str(point.id) in memory_request.query
    assert point.name in memory_request.query

    app.dependency_overrides.clear()
    db.close()


def test_failed_resource_receives_one_auditable_local_repair() -> None:
    plan = build_personalization_plan(
        {"views": {}},
        knowledge_point_id=1,
        knowledge_point_name="多智能体协作模式",
    )
    original = {
        "resource_type": "custom_note",
        "title": "简要说明",
        "content": "这是对话线程的简要说明。",
    }
    evidence = [{"text": "Official evidence", "metadata": {"document_id": "doc-1"}}]
    initial = ContentVerificationAgent().verify(original, plan, evidence)
    assert initial.passed is False

    repaired = ResourceGenerationAgent.repair_failed_resource(
        original, plan, evidence, initial.issues
    )
    final = ContentVerificationAgent().verify(repaired, plan, evidence)

    assert final.passed is True
    assert plan.knowledge_point_name in repaired["content"]
    assert "[1]" in repaired["content"]
    assert repaired["repair_issues"] == initial.issues


def _verification_fixture(resource_type: str = "custom_note") -> tuple[dict, object, list[dict]]:
    plan = build_personalization_plan(
        {"views": {}}, knowledge_point_id=1, knowledge_point_name="Kernel 插件"
    )
    evidence = [
        {
            "text": "Kernel 插件用于组织函数调用，并定义输入和输出。",
            "metadata": {
                "document_id": "doc-1",
                "source_url": "https://learn.microsoft.com/semantic-kernel/overview/",
            },
        }
    ]
    resource = {
        "resource_type": resource_type,
        "title": "Kernel 插件学习资料",
        "content": "Kernel 插件用于组织函数调用，并定义输入和输出。[1] " + "补充说明。" * 30,
        "claims": [{"text": "Kernel 插件用于组织函数调用", "evidence_refs": [1]}],
        "steps": [],
        "assessment_dimensions": [],
        "code_blocks": [],
    }
    return resource, plan, evidence


def test_verification_rejects_invalid_citation_number() -> None:
    resource, plan, evidence = _verification_fixture()
    resource["content"] = resource["content"].replace("[1]", "[2]")
    resource["claims"][0]["evidence_refs"] = [2]
    result = ContentVerificationAgent().verify(resource, plan, evidence)
    assert result.passed is False
    assert result.details["citation_numbers"] == [2]
    assert "事实声明未与证据切片对齐" in result.issues


def test_verification_rejects_invalid_python_code() -> None:
    resource, plan, evidence = _verification_fixture()
    resource["code_blocks"] = [{"language": "python", "code": "def broken(:"}]
    result = ContentVerificationAgent().verify(resource, plan, evidence)
    assert result.passed is False
    assert result.details["code_checks"][0]["passed"] is False


def test_verification_requires_practice_step_contract() -> None:
    resource, plan, evidence = _verification_fixture("practice_guide")
    resource["steps"] = [
        {"step": 1, "action": "执行"},
        {"step": 2, "action": "观察"},
        {"step": 3, "action": "复核"},
    ]
    result = ContentVerificationAgent().verify(resource, plan, evidence)
    assert result.passed is False
    assert "实操步骤缺少动作或预期结果" in result.issues


def test_verification_requires_three_staged_test_dimensions() -> None:
    resource, plan, evidence = _verification_fixture("staged_test")
    resource["assessment_dimensions"] = ["understanding"]
    result = ContentVerificationAgent().verify(resource, plan, evidence)
    assert result.passed is False
    assert "阶段测试未覆盖理解、应用、推理三个维度" in result.issues


def test_gated_evaluation_endpoint_materializes_all_three_profiles(monkeypatch) -> None:
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
    program = db.query(TrainingProgram).filter_by(organization_id=organization.id).one()
    module = (
        db.query(TrainingModule)
        .filter_by(program_id=program.id)
        .order_by(TrainingModule.sequence)
        .first()
    )
    monkeypatch.setenv("EVALUATION_PROFILE_SEED_KEY", "evaluation-test-key")
    monkeypatch.setattr(app_module, "SimpleMemClient", FakeMemoryClient)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    for profile_id, attempt_count in (("P1", 6), ("P2", 8), ("P3", 8)):
        learner = User(
            organization_id=organization.id,
            username=f"evaluation-{profile_id.lower()}",
            hashed_password="not-used",
            role=UserRole.LEARNER.value,
        )
        db.add(learner)
        db.commit()
        db.refresh(learner)
        response = client.post(
            "/v1/evaluation/learner-profile",
            json={
                "user_id": learner.id,
                "module_id": module.id,
                "profile_id": profile_id,
            },
            headers={
                "Authorization": f"Bearer {create_access_token(learner)}",
                "X-Evaluation-Key": "evaluation-test-key",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["profile_id"] == profile_id
        assert len(payload["attempt_ids"]) == attempt_count
        assert (
            payload["profile"]["views"]["path_and_resources"]["learner_profile"]["type"]
            == profile_id
        )

    app.dependency_overrides.clear()
    db.close()
