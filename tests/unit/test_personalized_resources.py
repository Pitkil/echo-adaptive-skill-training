from __future__ import annotations

from io import BytesIO

import app as app_module
import pytest
import resource_generation as resource_generation_module
from app import _legacy_staged_resource_questions, app, create_access_token, ensure_catalog, get_db
from catalog import PROGRAM_CODE
from coverage_rubrics import request_coverage_issues
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
from docx import Document
from fastapi.testclient import TestClient
from resource_generation import (
    ContentVerificationAgent,
    ResourceGenerationAgent,
    Verification,
    build_personalization_plan,
)
from semantic_coverage import SemanticCoverageResult
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def semantic_pass(**_kwargs) -> SemanticCoverageResult:
    return SemanticCoverageResult(
        passed=True,
        issues=[],
        mode="model_semantic",
        confidence=1.0,
        requirement_results=[],
        factual_support_passed=True,
    )


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
    requests = []

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
        self.requests.append({"query": query, "knowledge_point_ids": knowledge_point_ids})
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
    assert "[1]" not in resources[0]["content"]
    assert ContentVerificationAgent().verify(resources[0], plan, []).passed is False


def test_model_payload_parser_accepts_fenced_json() -> None:
    payload = ResourceGenerationAgent._parse_model_payload(
        '```json\n{"resource":{"resource_type":"custom_note"}}\n```'
    )

    assert payload["resource"]["resource_type"] == "custom_note"


def test_model_payload_parser_rejects_incomplete_json() -> None:
    try:
        ResourceGenerationAgent._parse_model_payload('{"resource":')
    except ValueError as exc:
        assert "JSON" in str(exc)
    else:
        raise AssertionError("incomplete model JSON must be rejected")


def test_legacy_staged_resource_questions_remain_usable() -> None:
    questions = _legacy_staged_resource_questions(
        "1. 理解题：说明 Kernel 的作用。\n"
        "2. 应用题：写出输入和输出。\n"
        "3. 推理题：比较两种实现。\n\n评分标准：按覆盖项累计。"
    )

    assert questions == [
        {"dimension": "understanding", "question": "说明 Kernel 的作用。"},
        {"dimension": "application", "question": "写出输入和输出。"},
        {"dimension": "reasoning", "question": "比较两种实现。"},
    ]


def test_model_resource_exposes_claim_references_in_learner_content() -> None:
    resource = {
        "content": "Kernel 负责组织服务和插件。",
        "claims": [{"text": "Kernel 负责组织服务和插件", "evidence_refs": [1]}],
    }

    ResourceGenerationAgent._ensure_content_citation_markers(
        resource, [{"text": "Kernel 负责组织服务和插件。"}]
    )

    assert "官方证据索引：[1]" in resource["content"]


def test_request_coverage_accepts_core_terms_without_full_point_name() -> None:
    plan = build_personalization_plan(
        {"views": {}},
        knowledge_point_id=1,
        knowledge_point_name="多智能体分工与协作",
        program_code=PROGRAM_CODE,
    )
    resource = {
        "content": "多智能体按职责分工，Sequential 传递输入和输出，Concurrent 处理独立任务并汇总结果。"
    }

    ResourceGenerationAgent._assert_request_coverage(resource, plan, "")


def test_course_rubric_does_not_apply_to_another_course() -> None:
    plan = build_personalization_plan(
        {"views": {}},
        knowledge_point_id=1,
        knowledge_point_name="多智能体分工与协作",
        program_code="ANOTHER-PROGRAM",
    )
    ResourceGenerationAgent._assert_request_coverage(
        {"content": "多智能体分工与协作的课程资料。"}, plan, "多智能体协作"
    )


def test_dialogue_course_rubric_detects_missing_azure_connection_parameters() -> None:
    issues = request_coverage_issues(
        program_code=PROGRAM_CODE,
        knowledge_point_name="Kernel 创建与模型服务接入",
        user_input="如何接入 Azure OpenAI 服务到 Semantic Kernel？",
        content="先向 Kernel 添加一个聊天完成服务。",
    )

    assert issues
    assert "AzureChatCompletion" in issues[0]
    assert "deployment_name" in issues[0]


def test_dialogue_course_rubric_accepts_agent_definition_and_process_event() -> None:
    assert (
        request_coverage_issues(
            program_code=PROGRAM_CODE,
            knowledge_point_name="Agent 创建与指令设计",
            user_input="Agent 是什么？",
            content="Agent 可以参与对话，并执行有明确目标的任务。",
        )
        == []
    )
    assert (
        request_coverage_issues(
            program_code=PROGRAM_CODE,
            knowledge_point_name="Process Framework 步骤与事件",
            user_input="请解释 Process Framework 的三个核心概念",
            content="Process 是流程，Step 是步骤，Event 负责触发和传递结果。",
        )
        == []
    )


def test_dialogue_course_rubric_rejects_required_term_in_insufficiency_paragraph() -> None:
    issues = request_coverage_issues(
        program_code=PROGRAM_CODE,
        knowledge_point_name="Process Framework 步骤与事件",
        user_input="请解释 Process Framework 的三个核心概念",
        content=(
            "Process 是完整流程，Step 是可执行步骤。\n\n关于 Event，当前证据不足，暂不能确认。"
        ),
    )

    assert issues
    assert "Event" in issues[0]


def test_dialogue_course_rubric_rejects_parameter_list_followed_by_disclaimer() -> None:
    issues = request_coverage_issues(
        program_code=PROGRAM_CODE,
        knowledge_point_name="Kernel 创建与模型服务接入",
        user_input="如何接入 Azure OpenAI 服务到 Semantic Kernel？",
        content=(
            "使用 AzureChatCompletion。\n\n"
            "关于 deployment_name、endpoint 和 api_key，当前证据没有列出，暂不能确认。"
        ),
    )

    assert issues
    assert "deployment_name" in issues[0]


def test_resource_generation_uses_profile_memory_and_blind_spot(monkeypatch) -> None:
    FakeMemoryClient.requests.clear()
    FakePunditRAGClient.requests.clear()
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
    monkeypatch.setattr(resource_generation_module, "evaluate_semantic_coverage", semantic_pass)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
    response = TestClient(app).post(
        "/v1/resources/generate",
        json={
            "user_id": learner.id,
            "module_id": module.id,
            "user_input": "请给我一个包含变量的产品描述模板",
        },
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
    assert payload["items"][0]["status"] == "verified"
    assert all(item["verification_passed"] for item in payload["items"])

    resources = db.query(GeneratedResource).filter_by(user_id=learner.id).all()
    assert len(resources) == 1
    assert all(item.knowledge_point_id == point.id for item in resources)
    assert all(item.difficulty == "foundation" for item in resources)
    assert all(point.name in item.content for item in resources)
    download = TestClient(app).get(
        f"/v1/resources/{resources[0].id}/download",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "filename*=UTF-8''" in download.headers["content-disposition"]
    exported = Document(BytesIO(download.content))
    exported_text = "\n".join(paragraph.text for paragraph in exported.paragraphs)
    assert resources[0].title in exported_text
    assert "为什么为你推荐" in exported_text
    assert "官方出处" in exported_text
    execution = db.query(TurnExecution).filter_by(user_id=learner.id).one()
    assert execution.primary_action == "GENERATE_RESOURCE"
    assert set(execution.result["agent_records"]) == {
        "analysis",
        "generation",
        "validation",
        "next_action",
    }
    assert all(
        item["persisted_in_system"] is True for item in execution.result["agent_records"].values()
    )
    memory_request = FakeMemoryClient.requests[-1]
    assert str(point.id) in memory_request.query
    assert point.name in memory_request.query
    assert "产品描述模板" in memory_request.query
    assert "产品描述模板" in FakePunditRAGClient.requests[-1]["query"]
    assert execution.plan["learning_goal"] == "请给我一个包含变量的产品描述模板"
    assert execution.result["agent_records"]["generation"]["input_summary"]["learning_goal"]

    app.dependency_overrides.clear()
    db.close()


@pytest.mark.parametrize("repair_rounds", [0, 1, 2])
def test_final_staged_questions_match_verified_content(monkeypatch, repair_rounds) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        ensure_catalog(db)
        organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
        learner = User(
            organization_id=organization.id,
            username="repair-question-learner",
            hashed_password="not-used",
            role=UserRole.LEARNER.value,
        )
        db.add(learner)
        db.commit()
        module = db.query(TrainingModule).order_by(TrainingModule.id).first()

        def variant(index):
            return {
                "resource_type": "staged_test",
                "title": f"练习版本{index}",
                "content": f"正文版本{index}",
                "questions": [{"dimension": "understanding", "question": f"问题版本{index}"}],
            }

        inspected = []

        def verify(_self, item, *_args):
            inspected.append(item)
            passed = len(inspected) > repair_rounds
            return Verification(passed, 1.0, 1.0, 1.0, [] if passed else ["覆盖不足"], {})

        monkeypatch.setattr(app_module, "SimpleMemClient", FakeMemoryClient)
        monkeypatch.setattr(
            app_module,
            "search_official_evidence",
            lambda *_a, **_k: (
                [
                    {
                        "text": "official evidence",
                        "metadata": {"source_url": "https://learn.microsoft.com/"},
                    }
                ],
                None,
            ),
        )
        monkeypatch.setattr(
            ResourceGenerationAgent, "generate", lambda *_a, **_k: ([variant(0)], None)
        )
        monkeypatch.setattr(
            ResourceGenerationAgent,
            "regenerate_after_verification_failure",
            lambda *_a, **_k: (variant(1), None),
        )
        monkeypatch.setattr(
            ResourceGenerationAgent, "repair_failed_resource", lambda *_a, **_k: variant(2)
        )
        monkeypatch.setattr(ContentVerificationAgent, "verify", verify)

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)
            headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
            response = client.post(
                "/v1/resources/generate",
                headers=headers,
                json={
                    "user_id": learner.id,
                    "module_id": module.id,
                    "resource_type": "staged_test",
                },
            )
            assert response.status_code == 200, response.text
            resource_id = response.json()["items"][0]["resource_id"]
            db.expire_all()
            resource = db.get(GeneratedResource, resource_id)
            expected = variant(repair_rounds)
            assert resource.content == expected["content"]
            assert resource.learning_payload["questions"] == expected["questions"]
            assert inspected[-1]["questions"] == resource.learning_payload["questions"]
            listing = client.get(f"/v1/resources?module_id={module.id}", headers=headers)
            assert listing.status_code == 200
            item = next(row for row in listing.json()["items"] if row["resource_id"] == resource_id)
            assert item["learning_payload"]["questions"] == expected["questions"]
            assert item["verification_passed"] is True
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_failed_resource_receives_one_auditable_local_repair(monkeypatch) -> None:
    monkeypatch.setattr(resource_generation_module, "evaluate_semantic_coverage", semantic_pass)
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


def test_regeneration_fallback_preserves_the_failed_draft(monkeypatch) -> None:
    plan = build_personalization_plan(
        {"views": {}}, knowledge_point_id=1, knowledge_point_name="课程自定义知识点"
    )
    original = {
        "resource_type": "custom_note",
        "title": "原始标题",
        "content": "原始学习内容。",
    }
    evidence = [{"text": "Official evidence", "metadata": {"document_id": "doc-1"}}]
    monkeypatch.setattr("resource_generation.AIConfig.API_KEY", "")

    repaired, note = ResourceGenerationAgent().regenerate_after_verification_failure(
        plan,
        evidence,
        resource_type="custom_note",
        user_input="解释这个知识点",
        issues=["内容过短"],
        original_resource=original,
    )

    assert note == "模型未配置，未执行定向重生成"
    assert "原始学习内容" in repaired["content"]
    assert repaired["repair_issues"] == ["内容过短"]


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


def test_verification_rejects_staged_test_metadata_without_real_questions() -> None:
    resource, plan, evidence = _verification_fixture("staged_test")
    resource["assessment_dimensions"] = ["understanding", "application", "reasoning"]
    resource["content"] += " 本阶段测试包含三个维度和评分标准。"
    result = ContentVerificationAgent().verify(resource, plan, evidence)

    assert result.passed is False
    assert "阶段测试缺少 understanding 真实题目" in result.issues
    assert "阶段测试缺少可执行评分方法" in result.issues


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
