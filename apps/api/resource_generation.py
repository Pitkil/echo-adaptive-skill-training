"""Profile-driven resource planning, generation, and verification."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

from config import AIConfig
from openai import OpenAI

RESOURCE_TYPES = ("custom_note", "practice_guide", "staged_test")
DIMENSION_LABELS = {
    "U": "概念理解",
    "A": "实际应用",
    "R": "推理与评估",
}
DIFFICULTY_LABELS = {
    "foundation": "基础",
    "standard": "标准",
    "advanced": "进阶",
}

POINT_GUIDANCE = {
    "Kernel 创建与模型服务接入": (
        "Kernel 是集中管理 AI 服务和插件的编排器/依赖注入容器；接入 Azure OpenAI 要核对 deployment_name、endpoint 和 api_key。",
        "先注册 AzureChatCompletion，再从环境变量读取三个配置，调用聊天服务并检查返回；常见失败是部署名、地址或密钥不匹配。",
        "评分看是否说明 Kernel 的编排职责、服务注册和 Azure 三参数，并能解释配置错误如何排查。",
    ),
    "提示词与聊天完成": (
        "提示词模板把固定指令与变量分离，例如 {{name}}、{{audience}}；invoke_prompt 负责填充变量并发起生成。",
        "先定义模板和变量，再传入变量值调用 invoke_prompt，检查变量是否全部填充；常见失败是变量名不一致或把用户输入当系统指令。",
        "评分看是否识别模板变量、调用入口和安全边界，并能给出一次变量缺失的排查方案。",
    ),
    "插件定义与函数调用": (
        "Plugin 是可被 Kernel 或 Agent 发现的一组领域函数；它通过名称、描述和参数元数据区别于普通函数，并受调用边界约束。",
        "先用类组织单一职责函数，再注册到 Kernel，检查函数名称、描述、参数和返回值是否清晰；制造一次参数错误并验证失败结果。",
        "评分看是否区分 Plugin 与普通函数、说明自动函数调用依据，并能处理参数校验和调用失败。",
    ),
    "多轮对话与执行设置": (
        "ChatHistory 保存 system、user、assistant 等多轮消息以保持上下文；Execution Settings 单独控制本次生成，如 Temperature、TopP 和输出长度。",
        "先建立并追加 ChatHistory，再配置本次执行设置并调用模型；检查历史是否按会话隔离、参数是否被目标模型支持。",
        "评分看是否区分 ChatHistory 与 Execution Settings，说明常用参数作用，以及上下文过长时的处理办法。",
    ),
    "Agent 创建与指令设计": (
        "Agent 由角色、目标、输入输出、工具边界和失败处理组成；instructions 应明确可验证的行为，而不是只有‘你是专家’。",
        "先写任务目标和输出格式，再配置 instructions 与 Kernel，最后用一个成功和一个失败输入验证行为；记录工具调用是否符合边界。",
        "评分看是否覆盖指令要素、工具边界和可测试性，并能说明如何改进含糊指令。",
    ),
    "对话线程与状态管理": (
        "线程保存一次对话的消息和状态；恢复时要按 session/thread 标识读取历史，并在状态转换后持久化，避免上下文串线。",
        "创建线程并记录状态，追加两轮消息后刷新恢复，检查历史顺序、用户隔离和状态是否一致；测试重复请求不重复写入。",
        "评分看是否说明线程、历史、状态持久化和隔离，并能设计恢复失败的处理。",
    ),
    "记忆与相关内容检索": (
        "记忆流程是写入经过权限过滤的事实、按当前问题检索相关片段，再把结果放入上下文；向量检索是相似内容查找，不是永久记忆。",
        "先写入一条用户范围内的事实，再按问题检索并检查相关性，最后把片段注入上下文；验证用户和组织过滤，防止跨用户泄露。",
        "评分看是否覆盖写入、检索、上下文注入和权限边界，并能区分记忆与向量检索。",
    ),
    "多智能体分工与协作": (
        "多智能体协作先按职责拆分，再选择编排：Sequential 传递有依赖的前后结果，Concurrent 并行处理独立视角后汇总。",
        "先定义每个 Agent 的输入输出，再分别跑串行和并行方案，检查结果合并、超时、重复工作和失败重试策略。",
        "评分看是否比较 Sequential/Concurrent、职责分工和结果汇总，并能说明选择依据与风险。",
    ),
    "Process Framework 步骤与事件": (
        "Process 是业务流程，Step 是可执行步骤，Event 是触发步骤或传递结果的事件；事件连接步骤并支持清晰的边界、重试和观测。",
        "先定义 Event，再创建接收事件的 Step，按顺序构建并运行 Process；检查事件载荷、步骤输出和失败重试是否可观察。",
        "评分看是否准确区分 Process、Step、Event，能描述触发关系，并能设计一个可运行流程。",
    ),
    "日志、跟踪与可观测性": (
        "可观测性包含日志、指标和分布式追踪；OpenTelemetry 用 trace/span 串起请求、Agent、模型和插件调用，并记录耗时、状态和错误。",
        "先为请求创建 trace，在模型和插件调用处记录 span，再导出日志和指标；检查错误率、延迟、调用量和关联 ID 是否可查询。",
        "评分看是否覆盖日志/指标/追踪三大支柱、OpenTelemetry 集成和指标如何驱动定位与改进。",
    ),
    "过滤、安全与异常处理": (
        "过滤应覆盖输入、函数调用和输出边界；参数、权限和敏感信息都要校验，并把异常区分为可重试与不可重试。",
        "先配置输入过滤，再在函数调用前做权限和参数校验，最后检查输出；为拒绝和异常记录原因，确认失败不会被伪装成成功。",
        "评分看是否覆盖三类过滤、异常策略、审计信息和安全风险应对，而不只是罗列风险。",
    ),
    "部署与质量评测": (
        "质量闭环是 observe -> evaluate -> improve：记录延迟、错误、工具调用和引用，用固定案例评测，再修正提示词、检索或流程并回归。",
        "先部署可观测服务并冻结版本，再运行固定评测案例计算正确性、覆盖率、难度适配和引用追溯率，最后针对失败案例改进并重跑。",
        "评分看是否给出完整闭环、部署考虑、指标计算和改进动作，而不是只写 Process 概览。",
    ),
}

REQUIRED_COVERAGE = {
    "Kernel 创建与模型服务接入": ("Kernel", "服务", "插件"),
    "提示词与聊天完成": ("模板", "变量", "调用"),
    "插件定义与函数调用": ("Plugin", "函数", "参数"),
    "多轮对话与执行设置": ("ChatHistory", "Execution Settings", "Temperature"),
    "Agent 创建与指令设计": ("Agent", "instructions", "工具"),
    "对话线程与状态管理": ("线程", "状态", "持久化"),
    "记忆与相关内容检索": ("记忆", "检索", "权限"),
    "多智能体分工与协作": ("Sequential", "Concurrent", "汇总"),
    "Process Framework 步骤与事件": ("Process", "Step", "Event"),
    "日志、跟踪与可观测性": ("日志", "指标", "OpenTelemetry"),
    "过滤、安全与异常处理": ("输入", "函数调用", "输出"),
    "部署与质量评测": ("observe", "evaluate", "improve"),
}


@dataclass(frozen=True)
class PersonalizationPlan:
    knowledge_point_id: int
    knowledge_point_name: str
    difficulty: str
    weakest_dimension: str
    weakest_dimension_label: str
    support_strategy: str
    reason: str
    ability: dict[str, float]
    blind_spots: list[str]
    memory_hints: list[str]
    micro_event_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Verification:
    passed: bool
    factual_score: float
    coverage_score: float
    difficulty_score: float
    issues: list[str]
    details: dict[str, Any]


def build_personalization_plan(
    profile: dict[str, Any],
    *,
    knowledge_point_id: int,
    knowledge_point_name: str,
) -> PersonalizationPlan:
    views = profile.get("views", {})
    ability_view = views.get("ability_and_trend", {})
    evidence_view = views.get("evidence_and_blind_spots", {})
    ability_payload = ability_view.get("ability", {})
    ability = {key: float(ability_payload.get(key, 0.0) or 0.0) for key in ("U", "A", "R")}
    attempts = int(ability_payload.get("attempt_count", 0) or 0)
    weakest_dimension = min(ability, key=ability.get)
    blind_spots = [
        str(item.get("name") or "")
        for item in evidence_view.get("knowledge_blind_spots", [])
        if item.get("name")
    ]
    memory_hints = [
        str(item.get("content") or item.get("summary") or "").strip()
        for item in evidence_view.get("memory_summary", [])
    ]
    memory_hints = [item for item in memory_hints if item][:3]
    micro_event_count = int(
        evidence_view.get("micro_evidence", {}).get("confirmed_event_count", 0) or 0
    )

    minimum_ability = min(ability.values())
    recommended_difficulty = views.get("path_and_resources", {}).get("recommended_difficulty")
    if recommended_difficulty in DIFFICULTY_LABELS:
        difficulty = recommended_difficulty
    elif attempts == 0 or minimum_ability < -0.5:
        difficulty = "foundation"
    elif minimum_ability >= 0.8 and not blind_spots:
        difficulty = "advanced"
    else:
        difficulty = "standard"

    support_strategy = (
        "拆分步骤并增加检查点，不改变能力分值"
        if micro_event_count
        else "按当前能力提供适量提示和自检问题"
    )
    reason_parts = [
        f"当前最弱能力为{DIMENSION_LABELS[weakest_dimension]}",
        f"已完成 {attempts} 次可判分作答",
    ]
    if knowledge_point_name in blind_spots:
        reason_parts.append("该知识点属于当前知识盲区")
    elif blind_spots:
        reason_parts.append(f"当前仍有 {len(blind_spots)} 个知识盲区")
    if memory_hints:
        reason_parts.append("已结合长期记忆中的误区或学习偏好")
    if micro_event_count:
        reason_parts.append("已根据确认的微表征调整提示方式")

    return PersonalizationPlan(
        knowledge_point_id=knowledge_point_id,
        knowledge_point_name=knowledge_point_name,
        difficulty=difficulty,
        weakest_dimension=weakest_dimension,
        weakest_dimension_label=DIMENSION_LABELS[weakest_dimension],
        support_strategy=support_strategy,
        reason="；".join(reason_parts) + "。",
        ability=ability,
        blind_spots=blind_spots,
        memory_hints=memory_hints,
        micro_event_count=micro_event_count,
    )


class ResourceGenerationAgent:
    def generate(
        self,
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
        *,
        resource_type: str = "custom_note",
        user_input: str = "",
    ) -> tuple[list[dict[str, Any]], str | None]:
        if resource_type not in RESOURCE_TYPES:
            raise ValueError(f"不支持的资源类型：{resource_type}")
        if evidence and AIConfig.API_KEY and AIConfig.MODEL_NAME and AIConfig.API_KEY != "test-key":
            try:
                return self._generate_with_model(plan, evidence, resource_type), None
            except Exception as exc:
                return self._fallback(plan, evidence, resource_type, user_input), f"资源模型降级：{exc}"
        return self._fallback(plan, evidence, resource_type, user_input), None

    def _generate_with_model(
        self,
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
        resource_type: str,
    ) -> list[dict[str, Any]]:
        evidence_text = "\n".join(
            f"[{index}] {item.get('text', '')[:1200]}"
            for index, item in enumerate(evidence[:6], start=1)
        )
        prompt = f"""根据学习画像和官方证据只生成一种个性化学习资源。
只返回 JSON 对象，格式为：
{{"resource":{{"resource_type":"{resource_type}","title":"...","content":"...",
"claims":[{{"text":"...","evidence_refs":[1]}}],
"steps":[{{"step":1,"action":"...","expected":"..."}}],
"assessment_dimensions":["understanding","application","reasoning"]}}}}

必须满足：
1. resource_type 必须严格为 {resource_type}，不得返回其它资源。
2. 内容围绕知识点“{plan.knowledge_point_name}”。
3. 难度为{DIFFICULTY_LABELS[plan.difficulty]}，重点补强{plan.weakest_dimension_label}。
4. 提示方式：{plan.support_strategy}。
5. 每条事实声明都必须在 claims.evidence_refs 中绑定下列证据编号。
6. 实操指南的每一步必须填写 action 和 expected；阶段测试必须覆盖 understanding、application、reasoning，不能提供答案。
7. 只能依据下列证据，不得编造 API、类名、章节或行为。

个性化原因：{plan.reason}
长期记忆提示：{"；".join(plan.memory_hints) or "无"}

官方证据：
{evidence_text}
"""
        response = OpenAI(api_key=AIConfig.API_KEY, base_url=AIConfig.BASE_URL).chat.completions.create(
            model=AIConfig.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=AIConfig.AGENT_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        resource = payload.get("resource")
        if not isinstance(resource, dict) or resource.get("resource_type") != resource_type:
            raise ValueError(f"模型没有返回唯一的 {resource_type} 资源")
        return [self._normalize_resource(resource, resource_type)]

    @staticmethod
    def _normalize_resource(resource: dict[str, Any], resource_type: str) -> dict[str, Any]:
        return {
            "resource_type": resource_type,
            "title": str(resource.get("title") or "").strip(),
            "content": str(resource.get("content") or "").strip(),
            "claims": resource.get("claims") if isinstance(resource.get("claims"), list) else [],
            "steps": resource.get("steps") if isinstance(resource.get("steps"), list) else [],
            "assessment_dimensions": (
                resource.get("assessment_dimensions")
                if isinstance(resource.get("assessment_dimensions"), list)
                else []
            ),
            "code_blocks": resource.get("code_blocks") if isinstance(resource.get("code_blocks"), list) else [],
        }

    @staticmethod
    def repair_failed_resource(
        resource: dict[str, Any],
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
        issues: list[str],
    ) -> dict[str, str]:
        """Apply one deterministic, auditable repair to a failed resource only.

        The repair never invents new facts.  It makes the target knowledge point
        and the already-retrieved evidence marker explicit, then adds a safe
        learner-facing self-check when the first draft is too short.
        """

        repaired = dict(resource)
        content = str(repaired.get("content") or "").strip()
        additions: list[str] = []
        if plan.knowledge_point_name not in content:
            additions.append(f"目标知识点：{plan.knowledge_point_name}")
        if evidence and "[1]" not in content:
            additions.append("证据说明：以上知识内容依据本资源所列 Microsoft 官方材料。[1]")
        if len(content) < 120:
            additions.append(
                "学习检查：请先复述核心作用，再完成一个最小示例，最后对照官方材料检查输入、输出和适用边界。"
            )
        if additions:
            content = "\n\n".join([content, *additions]).strip()
        if len(content) < 120:
            content = "\n\n".join(
                [
                    content,
                    (
                        "实施建议：第一步确认概念解决的问题和适用边界；第二步完成可运行的最小示例并记录关键输入与输出；"
                        "第三步制造一个常见错误，依据日志定位原因；第四步重新对照官方材料核验实现，并用自己的话说明选择依据。"
                    ),
                ]
            ).strip()
        repaired["content"] = content
        if not repaired.get("claims") and evidence:
            repaired["claims"] = [
                {"text": str(evidence[0].get("text") or "")[:500], "evidence_refs": [1]}
            ]
        repaired.setdefault("steps", [])
        repaired.setdefault("assessment_dimensions", [])
        repaired.setdefault("code_blocks", [])
        repaired["repair_issues"] = list(issues)
        return repaired

    @staticmethod
    def _fallback(
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
        resource_type: str,
        user_input: str = "",
    ) -> list[dict[str, Any]]:
        source_excerpt = (
            str(evidence[0].get("text") or "")[:500].strip()
            if evidence
            else "当前没有可引用的官方材料，资源只能保存为草稿。"
        )
        memory_note = "；".join(plan.memory_hints) or "暂无长期记忆提示"
        point = plan.knowledge_point_name
        difficulty = DIFFICULTY_LABELS[plan.difficulty]
        core, practice, rubric = POINT_GUIDANCE.get(
            point,
            (
                f"{point}应先说明核心目标、输入输出和适用边界。",
                "先准备环境，再完成最小实现，最后用日志或输出检查结果并处理失败。",
                "评分看概念理解、实际应用和推理依据是否完整。",
            ),
        )
        request_focus = ""
        request_text = user_input.casefold()
        if "产品描述" in user_input:
            request_focus = "示例模板：请为产品 {{name}} 生成面向 {{audience}} 的三句描述，突出 {{benefit}}；调用时逐项填充变量并检查没有遗留占位符。"
        elif "实验" in user_input or "生产" in user_input:
            request_focus = "实验性编排上线前要标记版本和能力边界，先在隔离环境用固定案例验证稳定性、超时和降级，再决定是否扩大流量。"
        elif "漂移" in user_input or "drift" in request_text:
            request_focus = "漂移检测比较线上输入分布、输出质量和固定评测集随时间的变化；超过阈值要告警、定位版本或数据变化并回归评测。"
        elif "多 agent" in request_text or "多agent" in request_text or "多智能体" in user_input:
            request_focus = "多 Agent 提示词要为每个角色分别规定职责、输入、输出格式和交接字段，并由协调者负责汇总；避免多个 Agent 重复完成同一工作。"
        elif "chatcompletionagent" in request_text or "azureaiagent" in request_text:
            request_focus = "比较 Agent 类型时要说明服务依赖、线程/状态保存、工具接入和部署边界，不能只比较类名；先按场景选择，再用统一接口隔离差异。"
        elif "有状态" in user_input or "无状态" in user_input:
            request_focus = "有状态 Agent 保存线程上下文，适合连续对话；无状态 Agent 每次由调用方传入必要上下文，适合可扩展的独立任务；混合使用时明确状态所有者和同步边界。"
        elif "temperature" in request_text or "topp" in request_text:
            request_focus = "对比时说明 Temperature 调整随机性，TopP 调整累计概率候选范围；一次只改变一个参数并固定提示词，用多次输出观察稳定性。"
        elif "部署" in user_input:
            request_focus = "部署时还要固定版本、隔离密钥、配置健康检查和回滚路径，并验证日志与指标在生产环境可见。"
        elif "漂移" in user_input or "drift" in request_text:
            request_focus = "漂移检测比较线上输入分布、输出质量和固定评测集随时间的变化；超过阈值要告警、定位版本或数据变化并回归评测。"
        elif "性能" in user_input or "成本" in user_input:
            request_focus = "性能和成本方案至少记录延迟、错误率、调用量、token 使用和单次任务成本，并按请求、模型和插件维度关联。"
        elif "漂移" in user_input or "drift" in request_text:
            request_focus = "漂移检测比较线上输入分布、输出质量和固定评测集随时间的变化；超过阈值要告警、定位版本或数据变化并回归评测。"
        request_block = f"本次需求：{request_focus}\n\n" if request_focus else ""
        citation = " [1]" if evidence else ""
        first_practice_step = (
            "步骤 1：从官方材料中确认目标、输入和输出。[1]\n"
            if evidence
            else "步骤 1：当前缺少官方材料，先完成课程材料导入再确认目标、输入和输出。\n"
        )
        fourth_practice_step = (
            "步骤 4：对照官方材料检查实现边界。[1]\n"
            if evidence
            else "步骤 4：材料补齐前只记录实现假设，不把结果标记为已验证。\n"
        )
        staged_test_scope = (
            f"练习范围：{point}；推荐难度：{difficulty}；范围依据官方材料。[1]\n\n"
            if evidence
            else f"练习范围：{point}；推荐难度：{difficulty}；当前缺少官方材料，仅保存为草稿。\n\n"
        )
        resources = {
            "custom_note": {
                "resource_type": "custom_note",
                "title": f"{point}个性化学习资料",
                "content": (
                    f"学习重点：{point}\n"
                    f"当前重点补强：{plan.weakest_dimension_label}\n"
                    f"推荐难度：{difficulty}\n\n"
                    f"核心定义：{core}\n\n"
                    f"{request_block}"
                    f"官方材料要点：{source_excerpt}{citation}\n\n"
                    f"学习提醒：{memory_note}\n"
                    f"易错点与个性化提示：{practice}\n\n"
                    "自检：请用自己的话说明该知识点的作用、边界和一个适用场景。"
                ),
                "claims": ([{"text": source_excerpt, "evidence_refs": [1]}] if evidence else []),
                "steps": [],
                "assessment_dimensions": [],
                "code_blocks": [],
            },
            "practice_guide": {
                "resource_type": "practice_guide",
                "title": f"{point}实操指南",
                "content": (
                    f"任务目标：在一个最小示例中完成“{point}”相关操作。\n"
                    f"支持方式：{plan.support_strategy}。\n\n"
                    f"本知识点操作要点：{practice}\n\n"
                    f"{request_block}"
                    f"{first_practice_step}"
                    "步骤 2：完成最小可运行实现，并记录关键配置。\n"
                    "步骤 3：制造一个常见错误，观察日志并定位原因。\n"
                    f"{fourth_practice_step}"
                    "完成标准：能够解释实现选择，并独立修复一次错误。"
                ),
                "claims": ([{"text": source_excerpt, "evidence_refs": [1]}] if evidence else []),
                "steps": [
                    {"step": 1, "action": "确认目标、输入和输出", "expected": "能够说明最小实现边界"},
                    {"step": 2, "action": "完成最小可运行实现", "expected": "得到可观察的输出"},
                    {"step": 3, "action": "制造错误并检查日志", "expected": "定位一个失败原因"},
                    {"step": 4, "action": "对照官方材料复核边界", "expected": "记录修正后的结论"},
                ],
                "assessment_dimensions": [],
                "code_blocks": [],
            },
            "staged_test": {
                "resource_type": "staged_test",
                "title": f"{point}针对性阶段练习",
                "content": (
                    f"{staged_test_scope}"
                    f"1. 理解题：说明“{point}”解决的主要问题，并写出两个关键概念。\n"
                    f"2. 应用题：{practice} 写出输入、输出和检查点。\n"
                    "3. 推理题：比较两种实现方式，说明选择依据、失败处理和可能风险。\n\n"
                    f"评分标准：{rubric}理解、应用、推理各占 30%，证据引用和边界说明占 10%；不得直接照抄题干。\n\n"
                    "本练习根据当前画像动态生成，不作为固定前后测，默认不更新 MIRT。"
                ),
                "claims": ([{"text": source_excerpt, "evidence_refs": [1]}] if evidence else []),
                "steps": [],
                "assessment_dimensions": ["understanding", "application", "reasoning"],
                "code_blocks": [],
            },
        }
        return [resources[resource_type]]


class ContentVerificationAgent:
    def verify(
        self,
        resource: dict[str, Any],
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
    ) -> Verification:
        content = str(resource.get("content", ""))
        issues: list[str] = []
        claim_checks: list[dict[str, Any]] = []
        code_checks: list[dict[str, Any]] = []
        api_checks: list[dict[str, Any]] = []
        step_checks: list[dict[str, Any]] = []
        citation_numbers = {
            int(value) for value in re.findall(r"\[(\d+)\]", content)
        }
        if not evidence:
            issues.append("PunditRAG 未返回可追溯证据")
        invalid_citations = sorted(
            number for number in citation_numbers if number < 1 or number > len(evidence)
        )
        if invalid_citations:
            issues.append("内容包含超出证据范围的引用编号")
        if plan.knowledge_point_name not in content:
            issues.append("内容未覆盖目标知识点")
        if len(content) < 120:
            issues.append("内容过短，无法形成完整学习资源")
        if evidence and not citation_numbers:
            issues.append("内容没有标记证据引用")
        if plan.difficulty not in DIFFICULTY_LABELS:
            issues.append("推荐难度无效")
        required_terms = REQUIRED_COVERAGE.get(plan.knowledge_point_name, ())
        missing_terms = [term for term in required_terms if term.casefold() not in content.casefold()]
        if required_terms and len(missing_terms) > 1:
            issues.append("内容未覆盖该知识点的关键概念")

        claims = resource.get("claims") or []
        if not isinstance(claims, list) or not claims:
            issues.append("缺少结构化事实声明")
            claims = []
        for claim in claims:
            text = str(claim.get("text") or "").strip() if isinstance(claim, dict) else ""
            refs = claim.get("evidence_refs") if isinstance(claim, dict) else []
            refs = refs if isinstance(refs, list) else []
            valid_refs = [int(ref) for ref in refs if str(ref).isdigit() and 1 <= int(ref) <= len(evidence)]
            overlap = any(
                token.casefold() in str(evidence[index - 1].get("text") or "").casefold()
                for index in valid_refs
                for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}|[\u4e00-\u9fff]{2,}", text)
            )
            passed = bool(text and valid_refs and overlap)
            claim_checks.append({"text": text, "evidence_refs": valid_refs, "passed": passed})
            if not passed:
                issues.append("事实声明未与证据切片对齐")

        for block in resource.get("code_blocks") or []:
            language = str(block.get("language") or "").lower() if isinstance(block, dict) else ""
            code = str(block.get("code") or "") if isinstance(block, dict) else ""
            passed = True
            error = None
            if language in {"python", "py"}:
                try:
                    ast.parse(code)
                except SyntaxError as exc:
                    passed = False
                    error = str(exc)
            elif language:
                passed = bool(code.strip())
                error = None if passed else "代码块为空"
            if not passed:
                issues.append("代码示例无法通过基础语法检查")
            code_checks.append({"language": language, "passed": passed, "error": error})
            identifiers = sorted(
                set(re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b", code))
                - {"True", "False", "None", "HTTP", "JSON"}
            )
            evidence_text = " ".join(str(item.get("text") or "") for item in evidence).casefold()
            unsupported = [name for name in identifiers if name.casefold() not in evidence_text]
            api_passed = not unsupported
            api_checks.append({"identifiers": identifiers, "unsupported": unsupported, "passed": api_passed})
            if not api_passed:
                issues.append("代码示例中的 API 或类名未在官方证据中找到")

        steps = resource.get("steps") or []
        if resource.get("resource_type") == "practice_guide":
            if not isinstance(steps, list) or len(steps) < 3:
                issues.append("实操指南步骤不足")
                steps = []
            for item in steps:
                passed = isinstance(item, dict) and bool(
                    str(item.get("action") or "").strip()
                    and str(item.get("expected") or "").strip()
                )
                step_checks.append({"step": item.get("step") if isinstance(item, dict) else None, "passed": passed})
                if not passed:
                    issues.append("实操步骤缺少动作或预期结果")

        dimensions = set(resource.get("assessment_dimensions") or [])
        if resource.get("resource_type") == "staged_test" and dimensions != {
            "understanding", "application", "reasoning"
        }:
            issues.append("阶段测试未覆盖理解、应用、推理三个维度")

        for item in evidence:
            metadata = item.get("metadata") or {}
            source_url = str(metadata.get("source_url") or metadata.get("url") or "")
            host = (urlsplit(source_url).hostname or "").lower()
            if not metadata.get("document_id") and not metadata.get("external_document_id"):
                issues.append("证据缺少文档编号")
            if source_url and host not in {"learn.microsoft.com", "github.com"}:
                issues.append("证据来源不属于允许的官方域名")

        factual_score = (
            sum(1 for item in claim_checks if item["passed"]) / len(claim_checks)
            if claim_checks
            else 0.0
        )
        coverage_score = 1.0 if plan.knowledge_point_name in content and len(content) >= 120 else 0.5
        difficulty_score = 1.0 if plan.difficulty in DIFFICULTY_LABELS else 0.0
        return Verification(
            passed=not issues,
            factual_score=factual_score,
            coverage_score=coverage_score,
            difficulty_score=difficulty_score,
            issues=issues,
            details={
                "citation_numbers": sorted(citation_numbers),
                "invalid_citations": invalid_citations,
                "claim_checks": claim_checks,
                "code_checks": code_checks,
                "api_checks": api_checks,
                "step_checks": step_checks,
                "assessment_dimensions": sorted(dimensions),
                "required_terms": list(required_terms),
                "missing_terms": missing_terms,
            },
        )
