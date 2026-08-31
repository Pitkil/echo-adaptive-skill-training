from types import SimpleNamespace

import semantic_coverage as module
from coverage_rubrics import semantic_coverage_requirements


def test_dialogue_requirements_do_not_force_unasked_course_concepts() -> None:
    requirements = semantic_coverage_requirements(
        program_code="MS-SK-ENGINEERING",
        knowledge_point_name="Kernel 创建与模型服务接入",
        user_input="如何接入 Azure OpenAI 服务到 Semantic Kernel？",
        include_core_concepts=False,
    )

    assert any("deployment_name" in item for item in requirements)
    assert not any("插件" in item for item in requirements)


def test_semantic_judge_accepts_equivalent_wording(monkeypatch) -> None:
    monkeypatch.setattr(module.AIConfig, "API_KEY", "real-key")
    monkeypatch.setattr(module.AIConfig, "MODEL_NAME", "judge-model")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"passed":true,"confidence":0.94,'
                        '"factual_support_passed":true,"requirements":['
                        '{"requirement":"说明 Agent 的定义","covered":true,'
                        '"reason":"回答用执行单元解释了同一概念"}],"issues":[]}'
                    )
                )
            )
        ]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_: response)
        )
    )
    monkeypatch.setattr(module, "OpenAI", lambda **_: fake_client)

    result = module.evaluate_semantic_coverage(
        program_code="MS-SK-ENGINEERING",
        knowledge_point_name="Agent 创建与指令设计",
        user_input="Agent 是什么？",
        content="它是接收输入、依据约束使用工具并完成目标任务的执行单元。[1]",
        requirements=["说明 Agent 的定义"],
        evidence=[{"text": "An agent completes tasks using instructions and tools.", "metadata": {}}],
    )

    assert result.passed is True
    assert result.mode == "model_semantic"
    assert result.confidence == 0.94


def test_offline_fallback_is_explicitly_labeled(monkeypatch) -> None:
    monkeypatch.setattr(module.AIConfig, "API_KEY", "test-key")

    result = module.evaluate_semantic_coverage(
        program_code="MS-SK-ENGINEERING",
        knowledge_point_name="Agent 创建与指令设计",
        user_input="Agent 是什么？",
        content="这里只介绍如何创建 ChatCompletionAgent。",
        requirements=["说明 Agent 的定义"],
        evidence=[],
    )

    assert result.passed is False
    assert result.mode == "lexical_fallback:model_not_configured"
    assert result.confidence is None


def test_offline_fallback_cannot_approve_matching_keywords(monkeypatch) -> None:
    monkeypatch.setattr(module.AIConfig, "API_KEY", "test-key")

    result = module.evaluate_semantic_coverage(
        program_code="MS-SK-ENGINEERING",
        knowledge_point_name="Kernel 创建与模型服务接入",
        user_input="如何接入 Azure OpenAI 服务到 Semantic Kernel？",
        content=(
            "创建 AzureChatCompletion 时传入 deployment_name、endpoint 和 api_key。[1]"
        ),
        requirements=["deployment_name / endpoint / api_key"],
        evidence=[
            {
                "text": "AzureChatCompletion accepts deployment_name, endpoint, and api_key.",
                "metadata": {},
            }
        ],
    )

    assert result.passed is False
    assert result.mode == "lexical_fallback:model_not_configured"
    assert result.issues[0].startswith("AI 语义复核不可用")
