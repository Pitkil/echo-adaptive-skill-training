"""Deterministic one-action planning for each learner turn."""

from __future__ import annotations

import re
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class TurnIntent(StrEnum):
    GREETING = "GREETING"
    END_SESSION = "END_SESSION"
    LEARNING_QUERY = "LEARNING_QUERY"
    QUIZ_REQUEST = "QUIZ_REQUEST"
    ANSWER_SUBMIT = "ANSWER_SUBMIT"
    SWITCH_MODULE = "SWITCH_MODULE"
    GENERAL_CHAT = "GENERAL_CHAT"
    REJECT = "REJECT"


class PrimaryAction(StrEnum):
    RESPOND_GREETING = "RESPOND_GREETING"
    CLOSE_SESSION = "CLOSE_SESSION"
    LEARNING_DIALOGUE = "LEARNING_DIALOGUE"
    GENERATE_QUIZ = "GENERATE_QUIZ"
    GRADE_ANSWER = "GRADE_ANSWER"
    CHANGE_MODULE = "CHANGE_MODULE"
    GENERAL_RESPONSE = "GENERAL_RESPONSE"
    REJECT_REQUEST = "REJECT_REQUEST"


class TurnContext(BaseModel):
    user_id: int
    session_id: int
    program_id: int
    module_id: int
    knowledge_base_id: int
    echo_state: str = "E"
    active_quiz_id: int | None = None


class TurnPlan(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    intent: TurnIntent
    primary_action: PrimaryAction
    context: TurnContext
    use_rag: bool = False
    use_memory: bool = False
    use_micro_evidence: bool = False
    target_module_id: int | None = None
    reason: str


class TurnOrchestrator:
    """Produce exactly one primary action without modifying state."""

    _greetings = {"你好", "您好", "嗨", "在吗", "早上好", "下午好", "晚上好", "hi", "hello", "hey"}
    _farewells = {"再见", "拜拜", "退出", "结束会话", "先这样", "下次再说"}
    _quiz_phrases = {
        "出题",
        "测验",
        "测试一下",
        "来一道题",
        "开始测试",
        "前测",
        "后测",
        "阶段测试",
        "阶段测验",
    }
    _answer_prefixes = (
        "答案是",
        "我选",
        "我选择",
        "我的答案",
        "我提交的答案",
        "提交答案",
        "答对后我的答案",
        "重复提交我的答案",
    )
    _chat_phrases = {"谢谢", "好的", "知道了", "明白了"}

    @staticmethod
    def normalize(text: str) -> str:
        normalized = (text or "").strip().lower()
        normalized = re.sub(r"[\s，。！？、,.!?:：]+", "", normalized)
        return normalized

    def plan(
        self,
        text: str,
        context: TurnContext,
        *,
        requested_module_id: int | None = None,
    ) -> TurnPlan:
        normalized = self.normalize(text)
        if not normalized:
            return self._build(
                TurnIntent.REJECT,
                PrimaryAction.REJECT_REQUEST,
                context,
                "输入为空，未执行学习动作。",
            )

        if normalized in self._greetings:
            return self._build(
                TurnIntent.GREETING,
                PrimaryAction.RESPOND_GREETING,
                context,
                "识别为独立问候短句。",
            )

        if normalized in self._farewells:
            return self._build(
                TurnIntent.END_SESSION,
                PrimaryAction.CLOSE_SESSION,
                context,
                "识别为明确结束会话短句。",
            )

        if requested_module_id is not None and requested_module_id != context.module_id:
            plan = self._build(
                TurnIntent.SWITCH_MODULE,
                PrimaryAction.CHANGE_MODULE,
                context,
                "请求显式切换培训模块。",
            )
            plan.target_module_id = requested_module_id
            return plan

        if context.active_quiz_id is not None and (
            normalized.startswith(self._answer_prefixes)
            or re.fullmatch(r"[abcd]", normalized, flags=re.IGNORECASE)
        ):
            return self._build(
                TurnIntent.ANSWER_SUBMIT,
                PrimaryAction.GRADE_ANSWER,
                context,
                "当前存在待答题目且输入符合答案形式。",
            )

        if any(phrase in normalized for phrase in self._quiz_phrases):
            return self._build(
                TurnIntent.QUIZ_REQUEST,
                PrimaryAction.GENERATE_QUIZ,
                context,
                "学习者明确请求测验。",
            )

        if normalized in self._chat_phrases:
            return self._build(
                TurnIntent.GENERAL_CHAT,
                PrimaryAction.GENERAL_RESPONSE,
                context,
                "识别为不改变学习状态的简短交流。",
            )

        return TurnPlan(
            intent=TurnIntent.LEARNING_QUERY,
            primary_action=PrimaryAction.LEARNING_DIALOGUE,
            context=context,
            use_rag=True,
            use_memory=True,
            use_micro_evidence=True,
            reason="默认进入当前培训模块的 ECHO 学习对话。",
        )

    @staticmethod
    def _build(
        intent: TurnIntent,
        action: PrimaryAction,
        context: TurnContext,
        reason: str,
    ) -> TurnPlan:
        return TurnPlan(intent=intent, primary_action=action, context=context, reason=reason)
