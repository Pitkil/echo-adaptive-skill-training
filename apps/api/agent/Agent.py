"""Small ECHO tutor service used by the one-action orchestrator."""

from __future__ import annotations

import re

from config import AIConfig
from openai import APIError, OpenAI

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
        coverage_requirements: list[str] | None = None,
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
            coverage_requirements=coverage_requirements,
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

    def repair_response(
        self,
        *,
        user_input: str,
        module_name: str,
        evidence: list[dict],
        original_response: str,
        coverage_issues: list[str],
        echo_state: str,
    ) -> str:
        """Ask the model to repair an incomplete evidence-grounded answer once."""

        if (
            not evidence
            or not AIConfig.API_KEY
            or not AIConfig.MODEL_NAME
            or AIConfig.API_KEY == "test-key"
        ):
            return self._rule_fallback(module_name, echo_state, evidence, user_input)
        messages = PromptManager.build_repair_messages(
            module_name=module_name,
            evidence_text=self._format_evidence(evidence),
            user_input=user_input,
            original_response=original_response,
            coverage_issues=coverage_issues,
        )
        try:
            client = OpenAI(api_key=AIConfig.API_KEY, base_url=AIConfig.BASE_URL)
            response = client.chat.completions.create(
                model=AIConfig.MODEL_NAME,
                messages=messages,
                temperature=0,
                max_tokens=AIConfig.AGENT_MAX_TOKENS,
            )
            content = (response.choices[0].message.content or "").strip()
        except (APIError, ValueError, TypeError, KeyError):
            return self._rule_fallback(module_name, echo_state, evidence, user_input)
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
            return f"根据 {source} 的官方证据：{excerpt} [1]\n\n{follow_up}{reference}"
        return (
            "当前证据不足，暂不能确认专业结论。"
            f"请说明你在“{module_name}”中要解决的具体知识点、代码片段或预期结果。"
        )
