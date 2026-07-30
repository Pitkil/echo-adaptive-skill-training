from __future__ import annotations

from agent.turn_orchestrator import PrimaryAction, TurnContext, TurnOrchestrator


def context(*, active_quiz_id: int | None = None) -> TurnContext:
    return TurnContext(
        user_id=1,
        session_id=2,
        program_id=3,
        module_id=4,
        knowledge_base_id=5,
        active_quiz_id=active_quiz_id,
    )


def test_greeting_and_farewell_require_independent_short_phrases() -> None:
    orchestrator = TurnOrchestrator()

    greeting = orchestrator.plan("你好", context())
    learning = orchestrator.plan("你好，请解释混合检索", context())
    farewell = orchestrator.plan("再见", context())
    continuing = orchestrator.plan("再见之前再讲一次重排", context())

    assert greeting.primary_action is PrimaryAction.RESPOND_GREETING
    assert learning.primary_action is PrimaryAction.LEARNING_DIALOGUE
    assert farewell.primary_action is PrimaryAction.CLOSE_SESSION
    assert continuing.primary_action is PrimaryAction.LEARNING_DIALOGUE


def test_explicit_module_switch_has_one_primary_action() -> None:
    plan = TurnOrchestrator().plan("切换模块", context(), requested_module_id=9)

    assert plan.primary_action is PrimaryAction.CHANGE_MODULE
    assert plan.target_module_id == 9
    assert plan.use_rag is False
    assert plan.use_memory is False


def test_active_quiz_accepts_only_answer_shaped_turns() -> None:
    orchestrator = TurnOrchestrator()

    answer = orchestrator.plan("答案是：B", context(active_quiz_id=12))
    question = orchestrator.plan("为什么 B 才是正确答案？", context(active_quiz_id=12))

    assert answer.primary_action is PrimaryAction.GRADE_ANSWER
    assert question.primary_action is PrimaryAction.LEARNING_DIALOGUE


def test_pretest_and_posttest_requests_are_quiz_actions() -> None:
    orchestrator = TurnOrchestrator()

    assert (
        orchestrator.plan("开始当前模块前测", context()).primary_action
        is PrimaryAction.GENERATE_QUIZ
    )
    assert (
        orchestrator.plan("开始当前模块后测", context()).primary_action
        is PrimaryAction.GENERATE_QUIZ
    )
