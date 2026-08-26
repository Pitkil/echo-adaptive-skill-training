"""Server-owned assessment progression for one learner and training module."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from database import KnowledgePoint, Quiz, StudentQuestionHistory
from pydantic import BaseModel
from sqlalchemy.orm import Session

AssessmentPurpose = Literal["pretest", "practice", "stage_test", "posttest"]

STAGE_PASS_SCORE = 0.7


class PurposeProgressResponse(BaseModel):
    purpose: AssessmentPurpose
    status: str
    answered: int
    total: int
    accuracy: float | None
    latest_attempt_at: datetime | None


class AssessmentProgressResponse(BaseModel):
    module_id: int
    state: str
    title: str
    description: str
    next_action: str
    button_label: str
    command_text: str | None
    button_enabled: bool
    active_purpose: AssessmentPurpose | None
    practice_coverage: int
    knowledge_point_total: int
    phases: list[PurposeProgressResponse]


@dataclass(frozen=True)
class PurposeProgress:
    purpose: AssessmentPurpose
    status: str
    answered: int
    total: int
    accuracy: float | None
    latest_attempt_at: datetime | None

    def public_payload(self) -> dict:
        payload = asdict(self)
        payload["latest_attempt_at"] = (
            self.latest_attempt_at.isoformat() if self.latest_attempt_at else None
        )
        return payload


@dataclass(frozen=True)
class AssessmentProgress:
    module_id: int
    state: str
    title: str
    description: str
    next_action: str
    button_label: str
    command_text: str | None
    button_enabled: bool
    active_purpose: AssessmentPurpose | None
    practice_coverage: int
    knowledge_point_total: int
    phases: list[PurposeProgress]

    def public_payload(self) -> dict:
        return {
            "module_id": self.module_id,
            "state": self.state,
            "title": self.title,
            "description": self.description,
            "next_action": self.next_action,
            "button_label": self.button_label,
            "command_text": self.command_text,
            "button_enabled": self.button_enabled,
            "active_purpose": self.active_purpose,
            "practice_coverage": self.practice_coverage,
            "knowledge_point_total": self.knowledge_point_total,
            "phases": [item.public_payload() for item in self.phases],
        }


class AssessmentFlowService:
    """Derive a persistent assessment flow from fixed quizzes and scored history."""

    def __init__(self, db: Session, *, user_id: int, module_id: int) -> None:
        self.db = db
        self.user_id = user_id
        self.module_id = module_id

    def progress(self, *, active_quiz_id: int | None = None) -> AssessmentProgress:
        quizzes = (
            self.db.query(Quiz)
            .filter(Quiz.module_id == self.module_id)
            .order_by(Quiz.id)
            .all()
        )
        quiz_by_id = {item.id: item for item in quizzes}
        latest_by_question: dict[int, StudentQuestionHistory] = {}
        history_rows = (
            self.db.query(StudentQuestionHistory)
            .join(Quiz, Quiz.id == StudentQuestionHistory.question_id)
            .filter(
                StudentQuestionHistory.user_id == self.user_id,
                Quiz.module_id == self.module_id,
            )
            .order_by(StudentQuestionHistory.created_at, StudentQuestionHistory.id)
            .all()
        )
        for row in history_rows:
            latest_by_question[row.question_id] = row

        stats = {
            purpose: self._purpose_progress(
                purpose,
                quizzes,
                latest_by_question,
            )
            for purpose in ("pretest", "practice", "stage_test", "posttest")
        }
        knowledge_point_total = (
            self.db.query(KnowledgePoint)
            .filter(KnowledgePoint.module_id == self.module_id)
            .count()
        )
        practice_points = {
            quiz_by_id[question_id].knowledge_point_id
            for question_id in latest_by_question
            if question_id in quiz_by_id
            and quiz_by_id[question_id].purpose == "practice"
        }
        practice_coverage = len(practice_points)

        pretest = self._with_status(stats["pretest"], self._basic_status(stats["pretest"]))
        practice = self._with_status(
            stats["practice"],
            "missing" if stats["practice"].total == 0 else "available",
        )

        if pretest.status != "completed":
            stage_status = "missing" if stats["stage_test"].total == 0 else "locked"
        elif stats["stage_test"].total == 0:
            stage_status = "missing"
        elif stats["stage_test"].answered == 0:
            stage_status = (
                "available"
                if knowledge_point_total > 0 and practice_coverage >= knowledge_point_total
                else "locked"
            )
        elif stats["stage_test"].answered < stats["stage_test"].total:
            stage_status = "in_progress"
        elif (stats["stage_test"].accuracy or 0.0) >= STAGE_PASS_SCORE:
            stage_status = "completed"
        else:
            latest_practice = stats["practice"].latest_attempt_at
            latest_stage = stats["stage_test"].latest_attempt_at
            stage_status = (
                "retake_ready"
                if latest_practice and latest_stage and latest_practice > latest_stage
                else "review_required"
            )
        stage_test = self._with_status(stats["stage_test"], stage_status)

        if stats["posttest"].total == 0:
            posttest_status = "missing"
        elif stage_test.status != "completed":
            posttest_status = "locked"
        else:
            posttest_status = self._basic_status(stats["posttest"])
        posttest = self._with_status(stats["posttest"], posttest_status)

        active_purpose = None
        if active_quiz_id is not None and active_quiz_id in quiz_by_id:
            active_purpose = quiz_by_id[active_quiz_id].purpose
        phases = [pretest, practice, stage_test, posttest]
        return self._next_step(
            phases,
            active_purpose=active_purpose,
            practice_coverage=practice_coverage,
            knowledge_point_total=knowledge_point_total,
        )

    def can_request(
        self,
        purpose: AssessmentPurpose,
        *,
        active_quiz_id: int | None = None,
    ) -> tuple[bool, str]:
        progress = self.progress(active_quiz_id=active_quiz_id)
        if progress.active_purpose is not None:
            return False, "请先完成当前题目，再进入下一项学习任务。"
        phase = next(item for item in progress.phases if item.purpose == purpose)
        allowed_statuses = {
            "pretest": {"available", "in_progress"},
            "practice": {"available"},
            "stage_test": {"available", "in_progress", "retake_ready"},
            "posttest": {"available", "in_progress"},
        }
        if phase.status in allowed_statuses[purpose]:
            return True, ""
        if phase.status == "missing":
            labels = {
                "pretest": "前测",
                "practice": "练习",
                "stage_test": "阶段测验",
                "posttest": "后测",
            }
            return False, f"当前模块尚未配置{labels[purpose]}题库，请联系讲师完成导入。"
        if purpose == "pretest" and phase.status == "completed":
            return False, "当前模块前测已经完成，请按系统建议继续学习。"
        if purpose == "stage_test" and phase.status == "review_required":
            return False, "阶段测验尚未达标，请先完成系统安排的巩固练习。"
        if purpose == "posttest":
            return False, "后测尚未解锁，请先完成前测、知识点练习和阶段测验。"
        return False, "该测验阶段尚未解锁，请按当前学习路径继续。"

    @staticmethod
    def _purpose_progress(
        purpose: AssessmentPurpose,
        quizzes: list[Quiz],
        latest_by_question: dict[int, StudentQuestionHistory],
    ) -> PurposeProgress:
        purpose_quizzes = [item for item in quizzes if item.purpose == purpose]
        attempts = [
            latest_by_question[item.id]
            for item in purpose_quizzes
            if item.id in latest_by_question
        ]
        accuracy = (
            sum(float(item.score) for item in attempts) / len(attempts)
            if attempts
            else None
        )
        latest_attempt_at = max((item.created_at for item in attempts), default=None)
        return PurposeProgress(
            purpose=purpose,
            status="available",
            answered=len(attempts),
            total=len(purpose_quizzes),
            accuracy=accuracy,
            latest_attempt_at=latest_attempt_at,
        )

    @staticmethod
    def _basic_status(progress: PurposeProgress) -> str:
        if progress.total == 0:
            return "missing"
        if progress.answered == 0:
            return "available"
        if progress.answered < progress.total:
            return "in_progress"
        return "completed"

    @staticmethod
    def _with_status(progress: PurposeProgress, status: str) -> PurposeProgress:
        return PurposeProgress(
            purpose=progress.purpose,
            status=status,
            answered=progress.answered,
            total=progress.total,
            accuracy=progress.accuracy,
            latest_attempt_at=progress.latest_attempt_at,
        )

    def _next_step(
        self,
        phases: list[PurposeProgress],
        *,
        active_purpose: AssessmentPurpose | None,
        practice_coverage: int,
        knowledge_point_total: int,
    ) -> AssessmentProgress:
        by_purpose = {item.purpose: item for item in phases}
        common = {
            "module_id": self.module_id,
            "active_purpose": active_purpose,
            "practice_coverage": practice_coverage,
            "knowledge_point_total": knowledge_point_total,
            "phases": phases,
        }
        if active_purpose is not None:
            return AssessmentProgress(
                state="answering",
                title="完成当前题目",
                description="本轮只处理当前答案，提交后系统会重新安排下一步。",
                next_action="answer_active",
                button_label="等待作答",
                command_text=None,
                button_enabled=False,
                **common,
            )

        pretest = by_purpose["pretest"]
        if pretest.status == "missing":
            return AssessmentProgress(
                state="content_missing",
                title="前测题库待配置",
                description="仍可进行对话学习，但正式能力基线需要讲师先导入前测题。",
                next_action="await_content",
                button_label="前测题库待配置",
                command_text=None,
                button_enabled=False,
                **common,
            )
        if pretest.status != "completed":
            continuing = pretest.status == "in_progress"
            return AssessmentProgress(
                state="pretest",
                title="先建立本模块能力基线",
                description=f"已完成 {pretest.answered}/{pretest.total} 道前测题。系统将逐题判分并更新能力画像。",
                next_action="continue_pretest" if continuing else "start_pretest",
                button_label="继续前测" if continuing else "开始入门诊断",
                command_text="继续当前模块前测" if continuing else "开始当前模块前测",
                button_enabled=True,
                **common,
            )

        stage_test = by_purpose["stage_test"]
        practice = by_purpose["practice"]
        if stage_test.status == "in_progress":
            return AssessmentProgress(
                state="stage_test",
                title="继续阶段检查",
                description=f"已完成 {stage_test.answered}/{stage_test.total} 道阶段题。完成后系统会判断是否进入后测。",
                next_action="continue_stage_test",
                button_label="继续阶段检查",
                command_text="继续当前模块阶段测验",
                button_enabled=True,
                **common,
            )
        if stage_test.status == "review_required":
            return AssessmentProgress(
                state="remediation",
                title="先巩固，再重新检查",
                description=f"阶段正确率为 {round((stage_test.accuracy or 0) * 100)}%，低于 70% 达标线。系统将安排针对性练习。",
                next_action="practice",
                button_label="开始巩固练习",
                command_text="来一道当前模块练习题" if practice.total else None,
                button_enabled=practice.total > 0,
                **common,
            )
        if stage_test.status == "retake_ready":
            return AssessmentProgress(
                state="stage_test",
                title="可以重新进行阶段检查",
                description="已完成新的巩固练习，系统将使用阶段题重新确认掌握情况。",
                next_action="start_stage_test",
                button_label="重新阶段检查",
                command_text="开始当前模块阶段测验",
                button_enabled=True,
                **common,
            )
        if stage_test.status in {"locked", "missing"}:
            coverage_complete = (
                knowledge_point_total > 0 and practice_coverage >= knowledge_point_total
            )
            if stage_test.status == "missing" and coverage_complete:
                return AssessmentProgress(
                    state="content_missing",
                    title="阶段题库待配置",
                    description="知识点练习已覆盖，但讲师尚未导入阶段测验题。",
                    next_action="await_content",
                    button_label="阶段题库待配置",
                    command_text=None,
                    button_enabled=False,
                    **common,
                )
            return AssessmentProgress(
                state="learning",
                title="继续覆盖当前模块知识点",
                description=f"练习已覆盖 {practice_coverage}/{knowledge_point_total} 个知识点，覆盖完成后系统自动解锁阶段检查。",
                next_action="practice",
                button_label="继续知识点练习",
                command_text="来一道当前模块练习题" if practice.total else None,
                button_enabled=practice.total > 0,
                **common,
            )
        if stage_test.status == "available":
            return AssessmentProgress(
                state="stage_test",
                title="知识点覆盖完成",
                description="现在进行阶段检查，系统会根据结果决定巩固或进入后测。",
                next_action="start_stage_test",
                button_label="开始阶段检查",
                command_text="开始当前模块阶段测验",
                button_enabled=True,
                **common,
            )

        posttest = by_purpose["posttest"]
        if posttest.status == "missing":
            return AssessmentProgress(
                state="content_missing",
                title="后测题库待配置",
                description="阶段检查已经达标，但讲师尚未导入模块后测题。",
                next_action="await_content",
                button_label="后测题库待配置",
                command_text=None,
                button_enabled=False,
                **common,
            )
        if posttest.status != "completed":
            continuing = posttest.status == "in_progress"
            return AssessmentProgress(
                state="posttest",
                title="完成模块学习效果验证",
                description=f"已完成 {posttest.answered}/{posttest.total} 道后测题，结果将与前测基线对比。",
                next_action="continue_posttest" if continuing else "start_posttest",
                button_label="继续结业测验" if continuing else "开始结业测验",
                command_text="继续当前模块后测" if continuing else "开始当前模块后测",
                button_enabled=True,
                **common,
            )
        return AssessmentProgress(
            state="completed",
            title="本模块学习闭环已完成",
            description="前测、知识点学习、阶段检查和后测均已完成，可以查看能力变化与学习报告。",
            next_action="view_report",
            button_label="查看学习报告",
            command_text=None,
            button_enabled=True,
            **common,
        )
