"""Frozen competition curriculum for the Microsoft Semantic Kernel demo domain."""

from __future__ import annotations

from typing import Final

ORGANIZATION_CODE: Final = "ECHO-DEMO"
ORGANIZATION_NAME: Final = "ECHO 企业培训演示组织"

KNOWLEDGE_BASE_CODE: Final = "MS-SK-OFFICIAL"
KNOWLEDGE_BASE_NAME: Final = "Microsoft Semantic Kernel 官方知识库"

PROGRAM_CODE: Final = "MS-SK-ENGINEERING"
PROGRAM_NAME: Final = "基于 Microsoft Semantic Kernel 的企业级智能体应用开发"
PROGRAM_DESCRIPTION: Final = (
    "依据 Microsoft Learn Semantic Kernel 文档和 microsoft/semantic-kernel "
    "官方仓库及示例，开展插件、智能体协作、流程、部署与质量评测训练。"
)

# Only these stable identifiers are used to migrate the earlier demo catalog in place.
LEGACY_KNOWLEDGE_BASE_CODES: Final = ("MS-AF-OFFICIAL", "RAG-KB")
LEGACY_PROGRAM_CODES: Final = ("MS-AF-ENGINEERING", "RAG-ENGINEERING")

MODULE_SPECS: Final = (
    {
        "code": "M1",
        "name": "Kernel 与插件",
        "description": "创建 Kernel、接入模型服务，并使用提示词、插件和函数调用完成对话任务。",
        "knowledge_points": (
            "Kernel 创建与模型服务接入",
            "提示词与聊天完成",
            "插件定义与函数调用",
            "多轮对话与执行设置",
        ),
    },
    {
        "code": "M2",
        "name": "Agent 与多智能体协作",
        "description": "创建 Agent、维护对话状态和记忆，并组织多个 Agent 分工协作。",
        "knowledge_points": (
            "Agent 创建与指令设计",
            "对话线程与状态管理",
            "记忆与相关内容检索",
            "多智能体分工与协作",
        ),
    },
    {
        "code": "M3",
        "name": "流程、部署与质量评测",
        "description": "使用流程框架组织任务，完成可观测、安全、部署和质量评测。",
        "knowledge_points": (
            "Process Framework 步骤与事件",
            "日志、跟踪与可观测性",
            "过滤、安全与异常处理",
            "部署与质量评测",
        ),
    },
)


def seed_question(knowledge_point_name: str) -> tuple[str, str]:
    """Return the deterministic smoke-test question for a catalog knowledge point."""
    return (
        f"请说明“{knowledge_point_name}”在 Semantic Kernel 应用开发中的核心目标。",
        knowledge_point_name,
    )
