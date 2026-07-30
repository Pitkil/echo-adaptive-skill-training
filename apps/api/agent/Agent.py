"""Small ECHO tutor service used by the one-action orchestrator."""

from __future__ import annotations

from config import AIConfig
from openai import OpenAI

from .FSM import EchoFSM
from .prompt_manager import PromptManager


class StudentHelper:
    def __init__(self) -> None:
        self.fsm = EchoFSM()

    def respond(
        self,
        *,
        user_input: str,
        module_name: str,
        echo_state: str,
        evidence: list[dict],
        memories: list[dict],
    ) -> str:
        evidence_text = self._format_evidence(evidence)
        memory_text = self._format_memories(memories)
        prompt = PromptManager.build(
            module_name=module_name,
            echo_state=echo_state,
            evidence_text=evidence_text,
            memory_text=memory_text,
            user_input=user_input,
        )
        if not AIConfig.API_KEY or not AIConfig.MODEL_NAME or AIConfig.API_KEY == "test-key":
            return self._rule_fallback(user_input, module_name, echo_state, evidence)

        client = OpenAI(api_key=AIConfig.API_KEY, base_url=AIConfig.BASE_URL)
        response = client.chat.completions.create(
            model=AIConfig.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=AIConfig.AGENT_TEMPERATURE,
            max_tokens=AIConfig.AGENT_MAX_TOKENS,
        )
        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _format_evidence(items: list[dict]) -> str:
        lines = []
        for index, item in enumerate(items, start=1):
            metadata = item.get("metadata", {})
            source = metadata.get("filename") or metadata.get("source") or f"证据{index}"
            chapter = metadata.get("chapter")
            label = f"{source} / {chapter}" if chapter else source
            lines.append(f"[{index}] {label}: {item.get('text', '')}")
        return "\n".join(lines)

    @staticmethod
    def _format_memories(items: list[dict]) -> str:
        return "\n".join(
            f"- {item.get('content') or item.get('summary') or ''}" for item in items
        )

    @staticmethod
    def _rule_fallback(
        user_input: str,
        module_name: str,
        echo_state: str,
        evidence: list[dict],
    ) -> str:
        if evidence:
            first = evidence[0]
            source = first.get("metadata", {}).get("filename", "领域知识库")
            return (
                f"当前在“{module_name}”模块。根据 {source} 的证据，"
                f"{first.get('text', '')}\n\n"
                f"请结合你的问题“{user_input}”说明其中最关键的判断依据，"
                "我再根据你的解释决定是补充基础示例还是进入实践任务。"
            )
        return (
            f"当前在“{module_name}”模块，现有知识库没有返回足够证据。"
            "为了避免凭空给出专业结论，请补充具体知识点、代码片段或期望完成的实践任务。"
        )
