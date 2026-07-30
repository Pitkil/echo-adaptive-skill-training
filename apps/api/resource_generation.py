"""Profile-driven resource planning, generation, and verification."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

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
    if attempts == 0 or minimum_ability < -0.5:
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
    ) -> tuple[list[dict[str, str]], str | None]:
        if evidence and AIConfig.API_KEY and AIConfig.MODEL_NAME and AIConfig.API_KEY != "test-key":
            try:
                return self._generate_with_model(plan, evidence), None
            except Exception as exc:
                return self._fallback(plan, evidence), f"资源模型降级：{exc}"
        return self._fallback(plan, evidence), None

    def _generate_with_model(
        self,
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        evidence_text = "\n".join(
            f"[{index}] {item.get('text', '')[:1200]}"
            for index, item in enumerate(evidence[:6], start=1)
        )
        prompt = f"""根据学习画像和官方证据生成三种个性化学习资源。
只返回 JSON 对象，格式为：
{{"resources":[{{"resource_type":"custom_note","title":"...","content":"..."}},
{{"resource_type":"practice_guide","title":"...","content":"..."}},
{{"resource_type":"staged_test","title":"...","content":"..."}}]}}

必须满足：
1. 三种 resource_type 各出现一次。
2. 内容围绕知识点“{plan.knowledge_point_name}”。
3. 难度为{DIFFICULTY_LABELS[plan.difficulty]}，重点补强{plan.weakest_dimension_label}。
4. 提示方式：{plan.support_strategy}。
5. 只能依据下列证据，事实后用 [1]、[2] 标明出处，不得编造。
6. 阶段测试用于动态练习，不提供参考答案，不自动更新 MIRT。

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
        resources = payload.get("resources", [])
        by_type = {
            item.get("resource_type"): item
            for item in resources
            if isinstance(item, dict) and item.get("resource_type") in RESOURCE_TYPES
        }
        if set(by_type) != set(RESOURCE_TYPES):
            raise ValueError("模型没有返回完整的三类资源")
        return [
            {
                "resource_type": resource_type,
                "title": str(by_type[resource_type].get("title") or "").strip(),
                "content": str(by_type[resource_type].get("content") or "").strip(),
            }
            for resource_type in RESOURCE_TYPES
        ]

    @staticmethod
    def _fallback(
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        source_excerpt = (
            str(evidence[0].get("text") or "")[:500].strip()
            if evidence
            else "当前没有可引用的官方材料，资源只能保存为草稿。"
        )
        memory_note = "；".join(plan.memory_hints) or "暂无长期记忆提示"
        point = plan.knowledge_point_name
        difficulty = DIFFICULTY_LABELS[plan.difficulty]
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
        return [
            {
                "resource_type": "custom_note",
                "title": f"{point}个性化学习资料",
                "content": (
                    f"学习重点：{point}\n"
                    f"当前重点补强：{plan.weakest_dimension_label}\n"
                    f"推荐难度：{difficulty}\n\n"
                    f"官方材料要点：{source_excerpt}{citation}\n\n"
                    f"学习提醒：{memory_note}\n"
                    "自检：请用自己的话说明该知识点的作用、边界和一个适用场景。"
                ),
            },
            {
                "resource_type": "practice_guide",
                "title": f"{point}实操指南",
                "content": (
                    f"任务目标：在一个最小示例中完成“{point}”相关操作。\n"
                    f"支持方式：{plan.support_strategy}。\n\n"
                    f"{first_practice_step}"
                    "步骤 2：完成最小可运行实现，并记录关键配置。\n"
                    "步骤 3：制造一个常见错误，观察日志并定位原因。\n"
                    f"{fourth_practice_step}"
                    "完成标准：能够解释实现选择，并独立修复一次错误。"
                ),
            },
            {
                "resource_type": "staged_test",
                "title": f"{point}针对性阶段练习",
                "content": (
                    f"{staged_test_scope}"
                    f"1. 理解题：说明“{point}”解决的主要问题。\n"
                    "2. 应用题：给出一个最小实现方案，并标明输入、输出和检查点。\n"
                    "3. 推理题：比较两种实现方式，说明选择依据和可能风险。\n\n"
                    "本练习根据当前画像动态生成，不作为固定前后测，默认不更新 MIRT。"
                ),
            },
        ]


class ContentVerificationAgent:
    def verify(
        self,
        resource: dict[str, str],
        plan: PersonalizationPlan,
        evidence: list[dict[str, Any]],
    ) -> Verification:
        content = resource.get("content", "")
        issues: list[str] = []
        if not evidence:
            issues.append("PunditRAG 未返回可追溯证据")
        if plan.knowledge_point_name not in content:
            issues.append("内容未覆盖目标知识点")
        if len(content) < 120:
            issues.append("内容过短，无法形成完整学习资源")
        if evidence and "[1]" not in content:
            issues.append("内容没有标记证据引用")
        if plan.difficulty not in DIFFICULTY_LABELS:
            issues.append("推荐难度无效")

        factual_score = 1.0 if evidence and "[1]" in content else 0.0
        coverage_score = 1.0 if plan.knowledge_point_name in content and len(content) >= 120 else 0.5
        difficulty_score = 1.0 if plan.difficulty in DIFFICULTY_LABELS else 0.0
        return Verification(
            passed=not issues,
            factual_score=factual_score,
            coverage_score=coverage_score,
            difficulty_score=difficulty_score,
            issues=issues,
        )
