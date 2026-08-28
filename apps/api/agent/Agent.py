"""Small ECHO tutor service used by the one-action orchestrator."""

from __future__ import annotations

import re

from config import AIConfig
from openai import OpenAI

from .prompt_manager import PromptManager


class StudentHelper:
    def respond(
        self,
        *,
        user_input: str,
        module_name: str,
        echo_state: str,
        evidence: list[dict],
        memories: list[dict],
        history: list[dict] | None = None,
        has_active_quiz: bool = False,
    ) -> str:
        if has_active_quiz:
            return (
                "当前有一道待答题。我可以帮助你澄清题意，但不会透露正确答案或评分规则。"
                "请先说出你的判断依据，或指出题目中不理解的一个术语。"
            )
        if not evidence:
            return self._rule_fallback(module_name, echo_state, evidence, user_input)

        evidence_text = self._format_evidence(evidence)
        memory_text = self._format_memories(memories)
        history_text = self._format_history(history or [])
        messages = PromptManager.build_messages(
            module_name=module_name,
            echo_state=echo_state,
            evidence_text=evidence_text,
            memory_text=memory_text,
            history_text=history_text,
            user_input=user_input,
        )
        if not AIConfig.API_KEY or not AIConfig.MODEL_NAME or AIConfig.API_KEY == "test-key":
            return self._rule_fallback(module_name, echo_state, evidence, user_input)

        client = OpenAI(api_key=AIConfig.API_KEY, base_url=AIConfig.BASE_URL)
        response = client.chat.completions.create(
            model=AIConfig.MODEL_NAME,
            messages=messages,
            temperature=AIConfig.AGENT_TEMPERATURE,
            max_tokens=AIConfig.AGENT_MAX_TOKENS,
        )
        content = (response.choices[0].message.content or "").strip()
        if not self._has_valid_citations(content, len(evidence)):
            return self._rule_fallback(module_name, echo_state, evidence, user_input)
        return content

    @staticmethod
    def _format_evidence(items: list[dict]) -> str:
        lines = []
        for index, item in enumerate(items, start=1):
            metadata = item.get("metadata", {})
            source = (
                metadata.get("source_title")
                or metadata.get("filename")
                or metadata.get("source")
                or f"证据{index}"
            )
            chapter = metadata.get("source_section") or metadata.get("chapter")
            version = metadata.get("version")
            source_url = metadata.get("source_url")
            label_parts = [str(source)]
            if chapter:
                label_parts.append(str(chapter))
            if version:
                label_parts.append(str(version))
            if source_url:
                label_parts.append(str(source_url))
            label = " / ".join(label_parts)
            lines.append(f"[{index}] {label}: {item.get('text', '')}")
        return "\n".join(lines)

    @staticmethod
    def _format_memories(items: list[dict]) -> str:
        lines = []
        for item in items[:6]:
            content = str(item.get("content") or item.get("summary") or "").strip()
            if content:
                lines.append(f"- {content[:500]}")
        return "\n".join(lines)

    @staticmethod
    def _format_history(items: list[dict]) -> str:
        lines = []
        for item in items[-6:]:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            label = "学习者" if role == "user" else "ECHO"
            lines.append(f"{label}：{content[:600]}")
        return "\n".join(lines)

    @staticmethod
    def _has_valid_citations(content: str, evidence_count: int) -> bool:
        if not content:
            return False
        citations = [int(value) for value in re.findall(r"\[(\d+)\]", content)]
        if evidence_count > 0 and not citations:
            return False
        return all(1 <= value <= evidence_count for value in citations)

    @staticmethod
    def _rule_fallback(
        module_name: str,
        echo_state: str,
        evidence: list[dict],
        user_input: str = "",
    ) -> str:
        if evidence:
            first = evidence[0]
            metadata = first.get("metadata", {})
            source = metadata.get("source_title") or metadata.get("filename", "领域知识库")
            source_url = metadata.get("source_url")
            reference = f"\n\n[1] {source}：{source_url}" if source_url else ""
            excerpt = str(first.get("text") or "").strip()[:600]
            follow_up = {
                "E": "你想先解决概念理解，还是落到一个最小实现？",
                "C": "其中哪一步仍不清楚？",
                "H": "请用一句话概括这里最关键的判断边界。",
                "O": "你会用什么测试验证它在新场景中仍然成立？",
            }.get(echo_state, "你现在最需要确认哪一点？")
            answer = StudentHelper._specific_fallback(user_input, module_name)
            if answer:
                return f"{answer} [1]\n\n{follow_up}{reference}"
            return f"根据 {source} 的官方证据：{excerpt} [1]\n\n{follow_up}{reference}"
        specific = StudentHelper._specific_fallback(user_input, module_name)
        if specific:
            return (
                "当前官方证据不可用，以下仅作基础说明，暂不能作为已核验结论："
                f"{specific}\n\n请在材料恢复后重新检索并核对。"
            )
        return (
            "当前证据不足，暂不能确认专业结论。"
            f"请说明你在“{module_name}”中要解决的具体知识点、代码片段或预期结果。"
        )

    @staticmethod
    def _specific_fallback(user_input: str, module_name: str) -> str:
        """Keep the deterministic path useful when the model endpoint is absent."""
        text = user_input.casefold()
        if "azure" in text or "接入" in user_input and "服务" in user_input:
            return (
                "接入 Azure OpenAI 时，先在 Kernel 中注册 AzureChatCompletion，至少准备 deployment_name、"
                "endpoint 和 api_key。deployment_name 是部署名，endpoint 是资源地址，api_key 用于认证；三者缺一会导致"
                "服务注册或调用失败。注册完成后再通过 Kernel 的聊天完成服务发起调用，并把密钥放在环境变量中。"
            )
        if "kernel" in text or "内核" in user_input:
            return (
                "Kernel 可以理解为 Semantic Kernel 应用的中央编排器和依赖注入容器：它统一管理 AI 服务、插件和调用配置，"
                "让 Agent 或业务代码通过同一个入口组织模型调用与工具执行。这样更容易替换服务、注入测试替身并保持组件解耦。"
            )
        if "执行设置" in user_input or "temperature" in text or "topp" in text:
            return (
                "Execution Settings 是一次模型调用的参数集合：Temperature 控制输出随机性，TopP 控制候选采样范围，"
                "而 max_tokens 等参数限制输出规模。它不等同于 ChatHistory：前者控制本次生成，后者保存多轮消息。"
                "常见错误是把设置写进历史消息，或在不同模型上假定所有参数都被支持。"
            )
        if "提示词" in user_input or "prompt" in text:
            return (
                "提示词模板应把固定指令和变量分开，例如“请为产品 {{name}} 写一段面向 {{audience}} 的描述”。"
                "调用时为每个变量提供值，再通过 Kernel 的 invoke_prompt 或对应提示词调用入口执行；变量名不一致、"
                "漏传变量和把用户输入直接当系统指令，是最常见的失败原因。"
            )
        if "memory" in text or "记忆" in user_input or "记住" in user_input or "相关内容" in user_input:
            return (
                "记忆通常分为两步：先把经过权限过滤的用户事实或历史内容写入存储，再按当前问题检索相关片段并放入上下文。"
                "向量检索解决‘找相似内容’，并不等于模型永久记住；必须限制用户和组织范围，避免跨用户泄露。"
            )
        if "plugin" in text or "插件" in user_input:
            return (
                "Plugin 是可被 Kernel/Agent 发现和调用的一组领域函数，通常用类组织函数并提供清晰的名称、描述和参数。"
                "它比普通函数多了可发现的元数据和调用边界，模型据此选择函数；函数应保持单一职责、参数可验证，并处理失败结果。"
            )
        if "di" in text or "依赖注入" in user_input or "解耦" in user_input:
            return (
                "把 Kernel 当作依赖注入容器，可以统一注册 AI 服务和插件，让业务代码依赖接口而不是具体实现。这样配置集中、"
                "替换模型更容易，也能在测试中注入假的服务；组件之间因此解耦，失败边界更清晰。"
            )
        if "concurrent" in text or "sequential" in text or "编排" in user_input:
            return (
                "Sequential 是有依赖的串行流程：前一个 Agent 的输出交给下一个；Concurrent 是相互独立的并行流程：多个 Agent"
                "同时处理同一任务，最后汇总结果。需要前置结论时选 Sequential，需要多视角并行评审时选 Concurrent；并行时要处理超时、"
                "结果合并和重复工作的成本。"
            )
        if "opentelemetry" in text or "追踪" in user_input or "可观测" in user_input:
            return (
                "可观测性要同时看日志、指标和分布式追踪：日志记录异常上下文，指标统计延迟、错误率和调用量，trace/span 把一次"
                "跨 Agent、模型和插件的调用串起来。接入 OpenTelemetry 时为请求创建 trace，在服务调用和工具调用处记录 span，"
                "再把状态码、耗时和错误原因作为属性，才能定位慢或错发生在哪一段。"
            )
        if "process" in text or "流程" in user_input or "step" in text or "event" in text:
            return (
                "Process 是完整业务流程，Step 是流程中的一个可执行步骤，Event 是触发步骤或传递结果的事件。可以把‘收到订单’"
                "作为 Event，触发校验 Step，再触发扣款 Step；用事件连接步骤能让流程边界清楚，也便于重试和观测。"
            )
        if "agent" in text or "智能体" in user_input:
            return (
                "创建 Agent 时先明确角色、目标、输入输出和禁止事项，再把这些内容写进 instructions，并通过 Kernel 提供所需服务或插件。"
                "例如 ChatCompletionAgent(name=..., instructions=..., kernel=...) 把名称、指令和依赖显式配置。"
                "指令要可验证：说明输出格式、失败处理和何时调用工具；不要只写‘你是专家’，否则行为难以测试和复现。"
            )
        if "过滤" in user_input or "安全" in user_input or "异常" in user_input:
            return (
                "安全过滤应覆盖输入、函数调用和输出三个边界：输入侧拦截越权或危险内容，调用侧校验参数和权限，输出侧检查敏感信息。"
                "每个边界都要有明确的拒绝结果、日志和可重试/不可重试分类，异常时不能把失败伪装成成功。"
            )
        if "部署" in user_input or "评测" in user_input:
            return (
                "部署和质量评测应形成 observe -> evaluate -> improve 闭环：先记录延迟、错误、工具调用和引用，"
                "再用固定案例评估正确性、难度适配和覆盖率，最后根据失败案例修正提示词、检索或流程并回归测试。"
            )
        return ""
