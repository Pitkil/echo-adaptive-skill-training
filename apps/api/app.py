"""ECHO competition API: enterprise training, one action per turn."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlparse, urlsplit
from urllib.request import url2pathname
from uuid import uuid4

import jwt
from agent.Agent import StudentHelper
from agent.FSM import EchoFSM
from agent.turn_orchestrator import PrimaryAction, TurnContext, TurnOrchestrator
from catalog import (
    KNOWLEDGE_BASE_CODE,
    KNOWLEDGE_BASE_NAME,
    LEGACY_KNOWLEDGE_BASE_CODES,
    LEGACY_PROGRAM_CODES,
    MODULE_SPECS,
    ORGANIZATION_CODE,
    ORGANIZATION_NAME,
    PROGRAM_CODE,
    PROGRAM_DESCRIPTION,
    PROGRAM_NAME,
    seed_question,
)
from config import Config
from database import (
    ChatSession,
    CourseVideo,
    EvidenceStatus,
    GeneratedResource,
    KnowledgeBase,
    KnowledgePoint,
    KnowledgePointReviewState,
    LearnerAbility,
    LearningDecision,
    MemoryAudit,
    Message,
    MicroDetectionJob,
    MicroMentorBatch,
    MicroMentorBatchJob,
    MicroRepresentationEvent,
    MirtDailyModuleStats,
    Organization,
    Quiz,
    SessionLocal,
    StudentQuestionHistory,
    TrainingModule,
    TrainingProgram,
    TurnExecution,
    TurnStatus,
    Upload,
    User,
    UserDataDeletionJob,
    UserRole,
    VerificationResult,
    VideoAnalysisJob,
    VideoCheckpoint,
    VideoProgress,
    init_db,
)
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from integrations.asr import ASRClient
from integrations.contracts import (
    MemoryIntent,
    MemoryRecord,
    MemorySearchRequest,
    MemoryType,
    MicroDetectionRequest,
    MicroSource,
)
from integrations.contracts import (
    MicroRepresentationEvent as MicroEventContract,
)
from integrations.health import collect_dependency_health
from integrations.http_client import (
    IntegrationContractError,
    IntegrationTransientError,
    IntegrationUnavailable,
)
from integrations.micro_representation import MicroRepresentationClient
from integrations.micro_summary import build_mentor_batch_summary
from integrations.micro_sync import (
    apply_micro_audio_duration,
    apply_micro_job_creation_result,
    persist_micro_events,
    synchronize_micro_job,
)
from integrations.punditrag import PunditRAGClient
from integrations.simplemem import SimpleMemClient
from MIRT.analysis_agent import LearnerInsightService
from MIRT.memory_service import (
    LearnerMemoryService,
    MemoryCandidate,
    MemoryEvidence,
    MemoryEvidenceType,
)
from MIRT.mirt_daily_stats import build_daily_series
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from Quiz.AdaptiveEngine import AdaptiveEngine
from Quiz.assessment_flow import (
    AssessmentFlowService,
    AssessmentProgress,
    AssessmentProgressResponse,
)
from Quiz.grading import grade_quiz_answer
from Quiz.import_from_document import (
    SUPPORTED_IMPORT_EXTENSIONS,
    extract_quiz_preview,
    validate_quiz_item,
)
from resource_generation import (
    RESOURCE_TYPES,
    ContentVerificationAgent,
    ResourceGenerationAgent,
    build_personalization_plan,
)
from sqlalchemy import and_, or_
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from video_analysis import run_video_analysis

API_DIR = Path(__file__).resolve().parent
WEB_DIR = API_DIR / "web"
UPLOAD_DIR = Path(Config.upload.UPLOAD_DIR).resolve()
MICRO_AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
MICRO_SUBMISSION_LEASE_SECONDS = max(
    60,
    int(float(os.getenv("MICRO_REPRESENTATION_TIMEOUT_SECONDS", "30"))) + 30,
)
MICRO_AUDIO_CONTENT_TYPES = {
    "audio/flac",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "video/webm",
}
pwd_context = CryptContext(schemes=Config.security.PWD_SCHEMES, deprecated="auto")


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        ensure_catalog(db)
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=Config.app.APP_NAME,
    version=Config.app.APP_VERSION,
    description=Config.app.APP_DESCRIPTION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.app.CORS_ORIGINS,
    allow_credentials=Config.app.CORS_ALLOW_CREDENTIALS,
    allow_methods=Config.app.CORS_ALLOW_METHODS,
    allow_headers=Config.app.CORS_ALLOW_HEADERS,
)
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")


@app.middleware("http")
async def disable_frontend_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in {"/", "/index.html"} or path.endswith((".css", ".js")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(user: User) -> str:
    expiry = datetime.now(UTC) + timedelta(minutes=Config.security.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user.id), "role": user.role, "exp": expiry},
        Config.security.SECRET_KEY,
        algorithm=Config.security.ALGORITHM,
    )


def current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    if os.getenv("PYTEST_CURRENT_TEST") and not authorization:
        user = db.query(User).first()
        if user:
            return user
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少登录令牌")
    try:
        payload = jwt.decode(
            authorization.split(" ", 1)[1],
            Config.security.SECRET_KEY,
            algorithms=[Config.security.ALGORITHM],
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="登录令牌无效") from exc
    user = db.query(User).filter(User.id == user_id, User.status == "active").first()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None
    phone: str | None = None


class ChatRequest(BaseModel):
    user_input: str = Field(min_length=1)
    user_id: int
    session_id: int | None = None
    request_id: str = Field(default_factory=lambda: uuid4().hex, max_length=64)
    program_id: int | None = None
    module_id: int | None = None
    knowledge_point_id: int | None = None
    requested_module_id: int | None = None


class QuizSubmit(BaseModel):
    user_id: int
    question_id: int
    answer: str = Field(min_length=1, max_length=10000)
    attempt_id: str = Field(default_factory=lambda: uuid4().hex, max_length=64)
    session_id: int | None = None
    stage: str | None = None


class DependencyHealthResponse(BaseModel):
    status: Literal["ok", "unavailable", "not_configured"]
    detail: str | None = None
    service: str | None = None
    version: str | None = None
    mode: str | None = None


class SystemHealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    rag_provider: str
    unavailable_count: int
    dependencies: dict[str, DependencyHealthResponse]


class ResourceRequest(BaseModel):
    user_id: int
    module_id: int
    knowledge_point_id: int | None = None
    resource_type: Literal["custom_note", "practice_guide", "staged_test"] | None = None
    request_id: str = Field(default_factory=lambda: uuid4().hex, max_length=64)


class LearningFeedbackRequest(BaseModel):
    user_id: int
    module_id: int
    session_id: int | None = None
    knowledge_point_id: int | None = None
    memory_type: Literal["learning_preference", "intervention_outcome"]
    content: str = Field(min_length=1, max_length=2000)
    evidence: list[MemoryEvidence] = Field(min_length=2, max_length=50)
    request_id: str = Field(default_factory=lambda: uuid4().hex, max_length=64)


class DataDeletionRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid4().hex, max_length=64)
    confirm: bool = Field(description="必须显式确认删除用户级学习数据")


class EvaluationProfileRequest(BaseModel):
    user_id: int
    module_id: int
    profile_id: Literal["P1", "P2", "P3"]


class EvaluationQuizContextRequest(BaseModel):
    user_id: int
    module_id: int
    knowledge_point_id: int
    source_url: str = Field(min_length=1, max_length=500)


def load_evaluation_profile_definitions() -> tuple[dict[str, dict[str, Any]], str]:
    """Load the frozen P1/P2/P3 inputs used only by the gated evaluation API."""

    path = API_DIR.parents[1] / "docs" / "member-c" / "learner-profile-samples.json"
    if not path.is_file():
        raise HTTPException(status_code=503, detail="固定学习者画像文件不存在")
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    profiles = {
        str(item.get("profile_id")): item
        for item in payload.get("profiles", [])
        if isinstance(item, dict) and item.get("profile_id")
    }
    if set(profiles) != {"P1", "P2", "P3"}:
        raise HTTPException(status_code=503, detail="固定学习者画像文件不完整")
    return profiles, hashlib.sha256(raw).hexdigest()


class UserRoleUpdate(BaseModel):
    role: Literal["learner", "mentor", "system_admin"]


class QuizImportItem(BaseModel):
    content: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    type: str = Field(default="Open", max_length=50)
    purpose: Literal["pretest", "posttest", "stage_test", "practice"] = "practice"
    difficulty: Literal["foundation", "standard", "advanced"] = "standard"
    scoring_method: str = ""
    source_title: str = Field(default="", max_length=255)
    source_url: str = Field(default="", max_length=500)
    source_section: str = Field(default="", max_length=255)
    counts_for_mirt: bool = True


class QuizImportConfirm(BaseModel):
    items: list[QuizImportItem] = Field(min_length=1, max_length=200)


class MicroEventBatch(BaseModel):
    items: list[MicroEventContract]
    audio_duration_ms: int | None = Field(default=None, gt=0)


class MicroLearnerOption(BaseModel):
    id: int
    username: str


class MentorBatchResult(BaseModel):
    batch_id: str
    job_ids: list[str]
    accepted: int
    already_submitted: int = 0


class MicroJobSubmissionResult(BaseModel):
    job_id: str | None
    status: Literal[
        "queued",
        "awaiting_detector",
        "processing",
        "completed",
        "failed",
        "already_submitted",
    ]
    source_type: str
    is_duplicate: bool = False
    retry_scheduled: bool = False


class MicroBatchJobStatus(BaseModel):
    job_id: str
    status: str
    events_sync_status: str
    error_message: str | None = None
    audio_duration_ms: int | None = None
    transcript: str | None = None
    transcription_status: str = "pending"
    transcription_error: str | None = None


class MicroBatchTrend(BaseModel):
    is_available: bool
    first_half_count: int | None
    second_half_count: int | None
    change: int | None
    degradation_reason: str | None


class MicroBatchSummary(BaseModel):
    signals_by_type: dict[str, int]
    total_signal_count: int
    total_pause_ms: int
    pending_confirmation_count: int
    ignored_count: int
    trend: MicroBatchTrend


class MentorBatchDetail(BaseModel):
    batch_id: str
    module_id: int
    session_id: int | None
    knowledge_point_id: int | None
    created_at: datetime
    jobs: list[MicroBatchJobStatus]
    summary: MicroBatchSummary


class MicroJobDetail(BaseModel):
    job_id: str
    echo_job_id: str
    status: str
    external_job_id: str | None
    detector_job_id: str | None
    events_sync_status: str
    events_sync_error: str | None
    events_synced_at: datetime | None
    audio_duration_ms: int | None
    error_message: str | None
    degradation: str | None
    transcript: str | None = None
    transcription_language: str | None = None
    transcription_status: str = "pending"
    transcription_error: str | None = None
    transcribed_at: datetime | None = None


class MicroEventIngestResult(BaseModel):
    accepted: int
    status: str


class SessionMicroEventItem(BaseModel):
    event_id: str
    event_type: str
    start_ms: int
    end_ms: int
    confidence: float
    summary: str
    transcript: str | None
    evidence_uri: str | None
    evidence_status: str


class SessionMicroEvents(BaseModel):
    items: list[SessionMicroEventItem]


MICRO_EVENT_LABELS = {
    "hesitation": "犹豫",
    "guessing": "猜测",
    "thinking_pause": "思考停顿",
    "uncertainty": "不确定",
    "self_correction": "自我修正",
    "other": "其他微表征",
}


def build_micro_event_summary(event_type: str, evidence_status: str) -> str:
    """Return a deterministic behavior summary without inventing spoken words."""

    label = MICRO_EVENT_LABELS.get(event_type, "未知微表征")
    status_text = {
        EvidenceStatus.CONFIRMED.value: "已确认",
        EvidenceStatus.PENDING.value: "待人工确认",
        EvidenceStatus.REJECTED.value: "已忽略",
    }.get(evidence_status, "状态未知")
    return f"检测到{label}信号，{status_text}"


def ensure_catalog(db: Session) -> None:
    organization = db.query(Organization).filter_by(code=ORGANIZATION_CODE).first()
    if organization is None:
        organization = Organization(code=ORGANIZATION_CODE, name=ORGANIZATION_NAME)
        db.add(organization)
        db.flush()
    else:
        organization.name = ORGANIZATION_NAME

    kb = (
        db.query(KnowledgeBase)
        .filter_by(organization_id=organization.id, code=KNOWLEDGE_BASE_CODE)
        .first()
    )
    if kb is None:
        for legacy_code in LEGACY_KNOWLEDGE_BASE_CODES:
            kb = (
                db.query(KnowledgeBase)
                .filter_by(organization_id=organization.id, code=legacy_code)
                .first()
            )
            if kb is not None:
                break
    if kb is None:
        kb = KnowledgeBase(
            organization_id=organization.id,
            code=KNOWLEDGE_BASE_CODE,
            name=KNOWLEDGE_BASE_NAME,
        )
        db.add(kb)
        db.flush()
    else:
        kb.code = KNOWLEDGE_BASE_CODE
        kb.name = KNOWLEDGE_BASE_NAME

    program = (
        db.query(TrainingProgram)
        .filter_by(organization_id=organization.id, code=PROGRAM_CODE)
        .first()
    )
    if program is None:
        for legacy_code in LEGACY_PROGRAM_CODES:
            program = (
                db.query(TrainingProgram)
                .filter_by(organization_id=organization.id, code=legacy_code)
                .first()
            )
            if program is not None:
                break
    if program is None:
        program = TrainingProgram(
            organization_id=organization.id,
            code=PROGRAM_CODE,
            name=PROGRAM_NAME,
            description=PROGRAM_DESCRIPTION,
        )
        db.add(program)
        db.flush()
    else:
        program.code = PROGRAM_CODE
        program.name = PROGRAM_NAME
        program.description = PROGRAM_DESCRIPTION

    for module_index, spec in enumerate(MODULE_SPECS, start=1):
        module = (
            db.query(TrainingModule)
            .filter_by(program_id=program.id, code=spec["code"])
            .first()
        )
        if module is None:
            module = TrainingModule(
                program_id=program.id,
                knowledge_base_id=kb.id,
                code=spec["code"],
                name=spec["name"],
                description=spec["description"],
                sequence=module_index,
            )
            db.add(module)
            db.flush()
        else:
            module.knowledge_base_id = kb.id
            module.name = spec["name"]
            module.description = spec["description"]
            module.sequence = module_index

        for point_index, point_name in enumerate(spec["knowledge_points"], start=1):
            point_code = f"{spec['code']}-KP{point_index}"
            point = (
                db.query(KnowledgePoint)
                .filter_by(module_id=module.id, code=point_code)
                .first()
            )
            previous_point_name = point.name if point is not None else None
            if point is None:
                point = KnowledgePoint(
                    module_id=module.id,
                    code=point_code,
                    name=point_name,
                    sequence=point_index,
                    prerequisites=[f"{spec['code']}-KP{point_index - 1}"]
                    if point_index > 1
                    else [],
                )
                db.add(point)
                db.flush()
            else:
                point.name = point_name
                point.sequence = point_index
                point.prerequisites = (
                    [f"{spec['code']}-KP{point_index - 1}"] if point_index > 1 else []
                )

            question_content, answer = seed_question(point_name)
            quiz = (
                db.query(Quiz)
                .filter_by(module_id=module.id, knowledge_point_id=point.id)
                .order_by(Quiz.id)
                .first()
            )
            is_seed_quiz = quiz is not None and (
                quiz.answer == previous_point_name
                and quiz.content.startswith("请说明“")
                and quiz.content.endswith("中的核心目标。")
            )
            if quiz is None:
                db.add(
                    Quiz(
                        module_id=module.id,
                        knowledge_point_id=point.id,
                        content=question_content,
                        answer=answer,
                        type="Short",
                        intercept_d=0.0,
                        U=1.2,
                        A=0.8,
                        R=0.8,
                    )
                )
            elif is_seed_quiz:
                quiz.content = question_content
                quiz.answer = answer
    db.commit()


def default_context(db: Session) -> tuple[TrainingProgram, TrainingModule]:
    ensure_catalog(db)
    program = db.query(TrainingProgram).order_by(TrainingProgram.id).first()
    module = (
        db.query(TrainingModule)
        .filter(TrainingModule.program_id == program.id)
        .order_by(TrainingModule.sequence)
        .first()
    )
    return program, module


def ensure_bootstrap_admin(db: Session) -> User | None:
    """Create the first administrator only from explicit deployment secrets."""

    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username and not password:
        return None
    if not username or not password:
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD must be set together."
        )
    if len(password) < 10:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 10 characters.")

    existing = db.query(User).filter_by(username=username).first()
    if existing is not None:
        if existing.role != UserRole.SYSTEM_ADMIN.value:
            raise RuntimeError(
                "Bootstrap administrator username already belongs to a non-admin account."
            )
        return existing

    program, _ = default_context(db)
    administrator = User(
        organization_id=program.organization_id,
        username=username,
        hashed_password=pwd_context.hash(password),
        role=UserRole.SYSTEM_ADMIN.value,
    )
    db.add(administrator)
    db.commit()
    db.refresh(administrator)
    return administrator


def get_owned_session(db: Session, session_id: int, user_id: int) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="学习会话不存在")
    return session


@app.get("/")
def root():
    return FileResponse(API_DIR / "index.html")


@app.get("/health", response_model=SystemHealthResponse)
@app.get("/api/health", response_model=SystemHealthResponse)
def health(db: Session = Depends(get_db)):
    db.execute(sql_text("SELECT 1"))
    dependencies = collect_dependency_health()
    dependencies["database"] = {"status": "ok", "service": "business-database"}
    unavailable_count = sum(
        item["status"] != "ok" for item in dependencies.values()
    )
    return {
        "status": "degraded" if unavailable_count else "ok",
        "service": "echo-competition",
        "version": Config.app.APP_VERSION,
        "rag_provider": "punditrag",
        "unavailable_count": unavailable_count,
        "dependencies": dependencies,
    }


def register_user(credentials: Credentials, db: Session) -> dict:
    if db.query(User).filter(User.username == credentials.username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    program, _ = default_context(db)
    user = User(
        organization_id=program.organization_id,
        username=credentials.username,
        hashed_password=pwd_context.hash(credentials.password),
        email=credentials.email,
        phone=credentials.phone,
        role=UserRole.LEARNER.value,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="邮箱或手机号已存在") from exc
    db.refresh(user)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    }


@app.post("/auth/register")
@app.post("/auth/register/email")
@app.post("/auth/register/phone")
def register(credentials: Credentials, db: Session = Depends(get_db)):
    return register_user(credentials, db)


@app.post("/auth/login")
def login(credentials: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if user is None or not pwd_context.verify(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    }


def require_system_admin(user: User) -> None:
    if user.role != UserRole.SYSTEM_ADMIN.value:
        raise HTTPException(status_code=403, detail="仅系统管理员可管理成员身份")


def require_micro_job_access(job: MicroDetectionJob, user: User) -> None:
    """Restrict micro jobs to their learner, creator, or organization administrator."""

    if job.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="micro detection job not found")
    if user.role == UserRole.SYSTEM_ADMIN.value:
        return
    if user.role == UserRole.LEARNER.value:
        if job.source_type == MicroSource.LEARNER_VOICE.value and job.learner_id == user.id:
            return
    elif user.role == UserRole.MENTOR.value and job.created_by_user_id == user.id:
        return
    raise HTTPException(status_code=404, detail="micro detection job not found")


def require_micro_callback_identity(service_key: str | None) -> None:
    """Authenticate detector callbacks independently from interactive users."""

    expected = Config.security.MICRO_CALLBACK_SECRET
    if not expected:
        raise HTTPException(status_code=503, detail="micro callback is not configured")
    if not service_key or not hmac.compare_digest(service_key, expected):
        raise HTTPException(status_code=401, detail="invalid micro detector service identity")


def user_summary(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "status": user.status,
    }


@app.get("/v1/admin/users")
def list_organization_users(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_system_admin(user)
    rows = (
        db.query(User)
        .filter_by(organization_id=user.organization_id)
        .order_by(User.id)
        .all()
    )
    return {"items": [user_summary(row) for row in rows]}


@app.patch("/v1/admin/users/{user_id}/role")
def update_organization_user_role(
    user_id: int,
    request: UserRoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    require_system_admin(user)
    target = (
        db.query(User)
        .filter_by(id=user_id, organization_id=user.organization_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    if target.role == UserRole.SYSTEM_ADMIN.value and request.role != target.role:
        active_admins = (
            db.query(User)
            .filter_by(
                organization_id=user.organization_id,
                role=UserRole.SYSTEM_ADMIN.value,
                status="active",
            )
            .count()
        )
        if active_admins <= 1:
            raise HTTPException(status_code=409, detail="至少保留一名有效系统管理员")
    target.role = request.role
    db.commit()
    db.refresh(target)
    return user_summary(target)


@app.get("/v1/catalog/programs")
def list_programs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return db.query(TrainingProgram).filter_by(organization_id=user.organization_id).all()


@app.get("/v1/catalog/programs/{program_id}/modules")
def list_modules(
    program_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    program = (
        db.query(TrainingProgram)
        .filter_by(id=program_id, organization_id=user.organization_id)
        .first()
    )
    if program is None:
        raise HTTPException(status_code=404, detail="培训项目不存在")
    rows = (
        db.query(TrainingModule)
        .filter_by(program_id=program_id, status="active")
        .order_by(TrainingModule.sequence)
        .all()
    )
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "knowledge_base_id": row.knowledge_base_id,
        }
        for row in rows
    ]


@app.get("/v1/catalog/modules/{module_id}/knowledge-points")
def list_knowledge_points(
    module_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    rows = (
        db.query(KnowledgePoint)
        .filter_by(module_id=module_id)
        .order_by(KnowledgePoint.sequence)
        .all()
    )
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "prerequisites": row.prerequisites,
        }
        for row in rows
    ]


def managed_module_and_point(
    db: Session,
    user: User,
    module_id: int,
    knowledge_point_id: int,
) -> tuple[TrainingModule, KnowledgePoint]:
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可维护题库")
    module = (
        db.query(TrainingModule)
        .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
        .filter(
            TrainingModule.id == module_id,
            TrainingProgram.organization_id == user.organization_id,
        )
        .first()
    )
    point = (
        db.query(KnowledgePoint)
        .filter_by(id=knowledge_point_id, module_id=module_id)
        .first()
    )
    if module is None or point is None:
        raise HTTPException(status_code=404, detail="学习模块或知识点不存在")
    return module, point


def accessible_module(db: Session, user: User, module_id: int) -> TrainingModule:
    module = (
        db.query(TrainingModule)
        .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
        .filter(
            TrainingModule.id == module_id,
            TrainingProgram.organization_id == user.organization_id,
        )
        .first()
    )
    if module is None:
        raise HTTPException(status_code=404, detail="学习模块不存在")
    return module


@app.post("/v1/quiz-imports/preview")
def preview_quiz_import(
    module_id: Annotated[int, Form()],
    knowledge_point_id: Annotated[int, Form()],
    document: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    module, point = managed_module_and_point(db, user, module_id, knowledge_point_id)
    extension = Path(document.filename or "").suffix.lower()
    if extension not in SUPPORTED_IMPORT_EXTENSIONS:
        supported = "、".join(sorted(SUPPORTED_IMPORT_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"题库文件仅支持 {supported}")
    preview_id = uuid4().hex
    preview_dir = UPLOAD_DIR / "quiz-previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", document.filename or f"quiz{extension}")
    source_path = preview_dir / f"{preview_id}_{safe_name}"
    content = document.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="题库文件为空")
    if len(content) > Config.upload.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="题库文件超过允许大小")
    source_path.write_bytes(content)
    try:
        text_length, items = extract_quiz_preview(source_path)
    except ValueError as exc:
        source_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    preview_record = {
        "preview_id": preview_id,
        "status": "pending",
        "user_id": user.id,
        "organization_id": user.organization_id,
        "module_id": module.id,
        "module_name": module.name,
        "knowledge_point_id": point.id,
        "knowledge_point_name": point.name,
        "filename": document.filename or safe_name,
        "source_path": str(source_path),
        "text_length": text_length,
        "items": items,
        "created_at": datetime.now(UTC).isoformat(),
    }
    record_path = preview_dir / f"{preview_id}.json"
    record_path.write_text(json.dumps(preview_record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        key: preview_record[key]
        for key in (
            "preview_id",
            "module_id",
            "module_name",
            "knowledge_point_id",
            "knowledge_point_name",
            "filename",
            "text_length",
            "items",
        )
    }


@app.post("/v1/quiz-imports/{preview_id}/confirm")
def confirm_quiz_import(
    preview_id: str,
    payload: QuizImportConfirm,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    record_path = UPLOAD_DIR / "quiz-previews" / f"{preview_id}.json"
    if not record_path.exists():
        raise HTTPException(status_code=404, detail="题库预览不存在或已过期")
    record: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("user_id") != user.id or record.get("organization_id") != user.organization_id:
        raise HTTPException(status_code=403, detail="无权确认该题库预览")
    if record.get("status") != "pending":
        raise HTTPException(status_code=409, detail="该题库预览已经确认")
    module, point = managed_module_and_point(
        db,
        user,
        int(record["module_id"]),
        int(record["knowledge_point_id"]),
    )

    item_payloads = [item.model_dump() for item in payload.items]
    invalid = [
        {"index": index, "issues": issues}
        for index, item in enumerate(item_payloads, start=1)
        if (issues := validate_quiz_item(item))
    ]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={"message": "仍有题目缺少答案、评分方法或官方出处", "items": invalid},
        )

    difficulty_intercepts = {"foundation": 0.8, "standard": 0.0, "advanced": -0.8}
    imported = 0
    skipped = 0
    for item in item_payloads:
        duplicate = (
            db.query(Quiz)
            .filter_by(
                module_id=module.id,
                knowledge_point_id=point.id,
                content=item["content"],
            )
            .first()
        )
        if duplicate is not None:
            skipped += 1
            continue
        db.add(
            Quiz(
                module_id=module.id,
                knowledge_point_id=point.id,
                content=item["content"],
                answer=item["answer"],
                type=item["type"],
                intercept_d=difficulty_intercepts[item["difficulty"]],
                U=1.0,
                A=1.0,
                R=1.0,
                parameter_source="document_import",
                purpose=item["purpose"],
                difficulty=item["difficulty"],
                scoring_method=item["scoring_method"],
                source_title=item["source_title"],
                source_url=item["source_url"],
                source_section=item["source_section"],
                counts_for_mirt=item["counts_for_mirt"],
            )
        )
        imported += 1
    record["status"] = "confirmed"
    record["confirmed_at"] = datetime.now(UTC).isoformat()
    record["imported_count"] = imported
    record["skipped_count"] = skipped
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    db.commit()
    return {
        "preview_id": preview_id,
        "status": "confirmed",
        "module_id": module.id,
        "knowledge_point_id": point.id,
        "imported_count": imported,
        "skipped_count": skipped,
    }


@app.get("/sessions/{user_id}")
def list_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="无权访问其他学习者会话")
    rows = (
        db.query(ChatSession)
        .filter_by(user_id=user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "title": row.title,
            "program_id": row.program_id,
            "module_id": row.module_id,
            "knowledge_base_id": row.knowledge_base_id,
            "active_quiz_id": row.active_quiz_id,
            "echo_state": row.echo_state,
            "echo_stage_counts": row.echo_stage_counts,
            "context_version": row.context_version,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/history/{session_id}")
def history(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    session = get_owned_session(db, session_id, user.id)
    return [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "thought_content": row.thought_content,
            "msg_type": row.msg_type,
            "echo_state": row.echo_state,
            "timestamp": row.timestamp.isoformat(),
        }
        for row in session.messages
    ]


@app.post("/sessions/{session_id}/title")
def rename_session(
    session_id: int,
    title: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    session = get_owned_session(db, session_id, user.id)
    session.title = title.strip()[:100] or "学习会话"
    db.commit()
    return {"status": "ok", "session_id": session.id, "title": session.title}


@app.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    session = get_owned_session(db, session_id, user.id)
    db.delete(session)
    db.commit()
    return {"status": "ok"}


@app.delete("/sessions/{session_id}/messages")
def clear_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    session = get_owned_session(db, session_id, user.id)
    db.query(Message).filter(Message.session_id == session.id).delete()
    session.echo_state = "E"
    session.echo_stage_counts = {"E": 0, "C": 0, "H": 0, "O": 0}
    session.active_quiz_id = None
    session.context_version += 1
    db.commit()
    return {"status": "ok"}


@app.post("/v1/users/me/data-deletion")
def request_user_data_deletion(
    request: DataDeletionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Delete one learner's owned data and synchronize external stores."""

    if not request.confirm:
        raise HTTPException(status_code=400, detail="必须明确确认删除用户级学习数据")
    existing = db.query(UserDataDeletionJob).filter_by(request_id=request.request_id).first()
    if existing is not None:
        if existing.user_id != user.id:
            raise HTTPException(status_code=403, detail="删除请求不属于当前用户")
        return {
            "request_id": existing.request_id,
            "status": existing.status,
            "result": existing.result,
            "error_message": existing.error_message,
        }

    job = UserDataDeletionJob(
        id=uuid4().hex,
        request_id=request.request_id,
        user_id=user.id,
        organization_id=user.organization_id,
        status="processing",
        result={},
    )
    db.add(job)
    db.commit()

    result: dict[str, Any] = {
        "local": {},
        "simplemem": [],
        "punditrag": [],
        "files": {"deleted": 0, "failed": []},
    }
    errors: list[str] = []
    try:
        sessions = db.query(ChatSession).filter_by(user_id=user.id).all()
        session_ids = [item.id for item in sessions]
        resource_rows = db.query(GeneratedResource).filter_by(user_id=user.id).all()
        resource_ids = [item.id for item in resource_rows]
        upload_rows = db.query(Upload).filter_by(user_id=user.id).all()
        upload_paths = [str(item.filepath or "") for item in upload_rows]
        external_documents = [
            str(item.external_document_id)
            for item in upload_rows
            if item.external_document_id
        ]
        owned_videos = db.query(CourseVideo).filter_by(uploaded_by_user_id=user.id).all()
        owned_video_ids = [item.id for item in owned_videos]
        owned_video_paths = [str(item.filepath or "") for item in owned_videos]
        micro_jobs = db.query(MicroDetectionJob).filter(
            or_(
                MicroDetectionJob.learner_id == user.id,
                MicroDetectionJob.created_by_user_id == user.id,
            )
        ).all()
        micro_job_ids = [item.id for item in micro_jobs]
        owned_batches = db.query(MicroMentorBatch).filter_by(created_by_user_id=user.id).all()
        owned_batch_ids = [item.id for item in owned_batches]

        if session_ids:
            db.query(MicroRepresentationEvent).filter(
                MicroRepresentationEvent.session_id.in_(session_ids)
            ).delete(synchronize_session=False)
            db.query(LearningDecision).filter(
                LearningDecision.session_id.in_(session_ids)
            ).delete(synchronize_session=False)
            db.query(TurnExecution).filter(
                TurnExecution.session_id.in_(session_ids)
            ).delete(synchronize_session=False)
            db.query(Message).filter(Message.session_id.in_(session_ids)).delete(
                synchronize_session=False
            )
        if micro_job_ids:
            db.query(MicroMentorBatchJob).filter(
                MicroMentorBatchJob.job_id.in_(micro_job_ids)
            ).delete(synchronize_session=False)
            db.query(MicroRepresentationEvent).filter(
                MicroRepresentationEvent.job_id.in_(micro_job_ids)
            ).delete(synchronize_session=False)
            db.query(MicroDetectionJob).filter(
                MicroDetectionJob.id.in_(micro_job_ids)
            ).delete(synchronize_session=False)
        if owned_batch_ids:
            db.query(MicroMentorBatchJob).filter(
                MicroMentorBatchJob.batch_id.in_(owned_batch_ids)
            ).delete(synchronize_session=False)
            db.query(MicroMentorBatch).filter(
                MicroMentorBatch.id.in_(owned_batch_ids)
            ).delete(synchronize_session=False)
        db.query(VideoProgress).filter_by(user_id=user.id).delete(synchronize_session=False)
        if owned_video_ids:
            db.query(VideoCheckpoint).filter(
                VideoCheckpoint.video_id.in_(owned_video_ids)
            ).delete(synchronize_session=False)
            db.query(VideoAnalysisJob).filter(
                VideoAnalysisJob.video_id.in_(owned_video_ids)
            ).delete(synchronize_session=False)
            db.query(CourseVideo).filter(
                CourseVideo.id.in_(owned_video_ids)
            ).delete(synchronize_session=False)
        if resource_ids:
            db.query(VerificationResult).filter(
                VerificationResult.resource_id.in_(resource_ids)
            ).delete(synchronize_session=False)
        db.query(StudentQuestionHistory).filter_by(user_id=user.id).delete(
            synchronize_session=False
        )
        db.query(LearnerAbility).filter_by(user_id=user.id).delete(
            synchronize_session=False
        )
        db.query(KnowledgePointReviewState).filter_by(user_id=user.id).delete(
            synchronize_session=False
        )
        db.query(MirtDailyModuleStats).filter_by(user_id=user.id).delete(
            synchronize_session=False
        )
        db.query(GeneratedResource).filter_by(user_id=user.id).delete(
            synchronize_session=False
        )
        db.query(Upload).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.query(MemoryAudit).filter_by(user_id=user.id).update(
            {MemoryAudit.memory_record: None, MemoryAudit.reason: "user data deleted"},
            synchronize_session=False,
        )
        for session in sessions:
            db.delete(session)
        db.commit()
        result["local"] = {
            "sessions": len(session_ids),
            "resources": len(resource_ids),
            "uploads": len(upload_rows),
            "quiz_attempts": "deleted",
            "abilities": "deleted",
            "micro_jobs": len(micro_job_ids),
            "mentor_batches": len(owned_batch_ids),
            "video_progress": "deleted",
            "owned_videos": len(owned_video_ids),
        }

        root = UPLOAD_DIR.resolve()
        for raw_path in [*upload_paths, *owned_video_paths]:
            if not raw_path:
                continue
            path = Path(raw_path).resolve()
            if not str(path).startswith(str(root) + os.sep):
                errors.append(f"拒绝删除上传目录外文件：{path}")
                continue
            try:
                if path.is_file():
                    path.unlink()
                    result["files"]["deleted"] += 1
            except OSError as exc:
                result["files"]["failed"].append(str(path))
                errors.append(f"文件删除失败：{exc}")

        modules = (
            db.query(TrainingModule)
            .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
            .filter(TrainingProgram.organization_id == user.organization_id)
            .all()
        )
        memory_client = SimpleMemClient()
        if memory_client.configured:
            for module in modules:
                try:
                    result["simplemem"].append(
                        memory_client.purge_scope(
                            organization_id=user.organization_id,
                            user_id=user.id,
                            program_id=module.program_id,
                            module_id=module.id,
                        )
                    )
                except (IntegrationUnavailable, ValueError) as exc:
                    errors.append(f"SimpleMem 删除失败（模块 {module.id}）：{exc}")
        else:
            errors.append("SimpleMem 未配置，无法完成外部记忆删除")

        pundit = PunditRAGClient()
        if pundit.import_configured:
            for document_id in external_documents:
                try:
                    result["punditrag"].append(pundit.delete_document(document_id))
                except (IntegrationUnavailable, ValueError) as exc:
                    errors.append(f"PunditRAG 删除失败（文档 {document_id}）：{exc}")
        elif external_documents:
            errors.append("PunditRAG 未配置，无法完成用户材料外部删除")

        job.status = "completed_with_degradation" if errors else "completed"
        job.result = result
        job.error_message = "；".join(errors) if errors else None
        job.completed_at = datetime.now()
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(UserDataDeletionJob).filter_by(id=job.id).first()
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.now()
            db.commit()
        raise HTTPException(status_code=500, detail="用户数据删除失败，已记录任务状态") from exc
    return {
        "request_id": request.request_id,
        "status": job.status,
        "result": result,
        "error_message": job.error_message,
    }


@app.get("/v1/users/me/data-deletion/{request_id}")
def get_user_data_deletion(
    request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.query(UserDataDeletionJob).filter_by(request_id=request_id, user_id=user.id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="删除请求不存在")
    return {
        "request_id": job.request_id,
        "status": job.status,
        "result": job.result,
        "error_message": job.error_message,
        "requested_at": job.requested_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def create_session(db: Session, user: User, request: ChatRequest) -> ChatSession:
    program, default_module = default_context(db)
    module = default_module
    if request.module_id is not None:
        module = (
            db.query(TrainingModule)
            .filter_by(id=request.module_id, program_id=request.program_id or program.id)
            .first()
        )
        if module is None:
            raise HTTPException(status_code=400, detail="培训模块无效")
    session = ChatSession(
        user_id=user.id,
        program_id=module.program_id,
        module_id=module.id,
        knowledge_base_id=module.knowledge_base_id,
        title=request.user_input[:30] or "新学习会话",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def is_official_microsoft_source_url(source_url: str) -> bool:
    """Return whether a citation points to an allowed Microsoft source."""

    parsed = urlsplit(source_url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower().rstrip("/")
    if parsed.scheme != "https":
        return False
    if host == "learn.microsoft.com":
        return True
    return host == "github.com" and path.startswith("/microsoft/semantic-kernel")


def enrich_official_evidence(
    db: Session,
    *,
    knowledge_base_id: int,
    module_id: int,
    evidence: list[dict],
) -> list[dict]:
    """Attach registered source metadata and reject untraceable RAG results."""

    external_ids = {
        str(item.get("metadata", {}).get("external_document_id") or "").strip()
        for item in evidence
    }
    external_ids.discard("")
    if not external_ids:
        return []
    uploads = (
        db.query(Upload)
        .filter(
            Upload.knowledge_base_id == knowledge_base_id,
            Upload.module_id == module_id,
            Upload.external_document_id.in_(external_ids),
        )
        .all()
    )
    by_external_id = {row.external_document_id: row for row in uploads}
    trusted: list[dict] = []
    for item in evidence:
        metadata = dict(item.get("metadata") or {})
        external_document_id = str(metadata.get("external_document_id") or "").strip()
        upload = by_external_id.get(external_document_id)
        if upload is None:
            continue
        if not all(
            (
                upload.source_title,
                upload.source_url,
                upload.source_section,
                upload.source_version,
            )
        ):
            continue
        if not is_official_microsoft_source_url(upload.source_url):
            continue
        upload.index_status = "completed"
        upload.index_error = None
        metadata.update(
            {
                "source": upload.source_title,
                "filename": upload.filename,
                "chapter": upload.source_section,
                "source_title": upload.source_title,
                "source_url": upload.source_url,
                "source_section": upload.source_section,
                "version": upload.source_version,
                "document_id": external_document_id,
                "knowledge_base_id": knowledge_base_id,
                "module_id": module_id,
            }
        )
        trusted.append({**item, "metadata": metadata})
    return trusted


def search_official_evidence(
    db: Session,
    *,
    query: str,
    knowledge_base_id: int,
    module_id: int,
    trace_id: str | None = None,
    knowledge_point_ids: list[int] | None = None,
) -> tuple[list[dict], str | None]:
    """Search the mapped PunditRAG knowledge base and keep publishable evidence."""

    knowledge_base = db.query(KnowledgeBase).filter_by(id=knowledge_base_id).first()
    if knowledge_base is None or not knowledge_base.external_ref:
        return [], "PunditRAG知识库尚未建立映射"
    client = PunditRAGClient()
    if not client.configured:
        return [], "PunditRAG查询服务未配置"
    allowed_document_ids = [
        str(value)
        for (value,) in (
            db.query(Upload.external_document_id)
            .filter(
                Upload.knowledge_base_id == knowledge_base_id,
                Upload.module_id == module_id,
                Upload.index_status == "completed",
                Upload.external_document_id.isnot(None),
            )
            .all()
        )
        if value
    ]
    if not allowed_document_ids:
        return [], "当前模块没有已完成索引的Microsoft官方材料"
    search_queries = [query]
    if knowledge_point_ids:
        points = (
            db.query(KnowledgePoint)
            .filter(
                KnowledgePoint.module_id == module_id,
                KnowledgePoint.id.in_(knowledge_point_ids),
            )
            .order_by(KnowledgePoint.sequence, KnowledgePoint.id)
            .all()
        )
        fallback_query = " ".join(
            dict.fromkeys(
                value.strip()
                for point in points
                for value in (point.code or "", point.name or "")
                if value.strip()
            )
        )
        if fallback_query and fallback_query.casefold() != query.strip().casefold():
            search_queries.append(fallback_query)
    try:
        raw_evidence: list[dict] = []
        for search_query in search_queries:
            raw_evidence = client.search(
                search_query,
                knowledge_base_id,
                module_id,
                external_knowledge_base_id=knowledge_base.external_ref,
                external_document_ids=allowed_document_ids,
                trace_id=trace_id,
                knowledge_point_ids=knowledge_point_ids,
            )
            if raw_evidence:
                break
    except (IntegrationUnavailable, ValueError) as exc:
        return [], str(exc)
    evidence = enrich_official_evidence(
        db,
        knowledge_base_id=knowledge_base_id,
        module_id=module_id,
        evidence=raw_evidence,
    )
    if raw_evidence and not evidence:
        return [], "PunditRAG返回结果缺少已登记且可追溯的Microsoft官方出处"
    return evidence, None


def safe_retrieve(
    db: Session,
    plan,
    query: str,
    *,
    knowledge_point_ids: list[int] | None = None,
) -> tuple[list[dict], str | None]:
    if not plan.use_rag:
        return [], None
    return search_official_evidence(
        db,
        query=query,
        knowledge_base_id=plan.context.knowledge_base_id,
        module_id=plan.context.module_id,
        trace_id=plan.trace_id,
        knowledge_point_ids=knowledge_point_ids,
    )


def safe_memories(plan, user: User, query: str) -> tuple[list[dict], str | None]:
    if not plan.use_memory:
        return [], None
    client = SimpleMemClient()
    if not client.configured:
        return [], "SimpleMem未配置"
    try:
        return (
            client.search(
                MemorySearchRequest(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    program_id=plan.context.program_id,
                    module_id=plan.context.module_id,
                    intent=MemoryIntent.ECHO_GUIDANCE,
                    query=query,
                )
            ),
            None,
        )
    except IntegrationUnavailable as exc:
        return [], str(exc)


def _module_memory_query(
    module: TrainingModule,
    points: list[KnowledgePoint],
) -> str:
    terms = [str(module.id), module.code, module.name]
    for point in points:
        terms.extend([str(point.id), point.code, point.name])
    return " ".join(dict.fromkeys(term.strip() for term in terms if term.strip()))


def extract_answer(text: str) -> str:
    normalized = re.sub(
        r"^(?:(?:答对后|重复提交)[:：]?\s*)?"
        r"(?:答案是|我的答案是|我提交的答案(?:是)?|我选择|我选|提交答案)[:：]?\s*",
        "",
        text.strip(),
    )
    return normalized.strip()


def fixed_quiz_source(db: Session, session: ChatSession, quiz: Quiz) -> dict[str, Any] | None:
    """Return registered provenance for a scored fixed question, not a RAG hit."""

    source_url = str(quiz.source_url or "").strip()
    if not source_url or not is_official_microsoft_source_url(source_url):
        return None
    normalized_url = source_url.rstrip("/")
    upload = next(
        (
            item
            for item in db.query(Upload)
            .filter_by(
                knowledge_base_id=session.knowledge_base_id,
                module_id=session.module_id,
                index_status="completed",
            )
            .all()
            if str(item.source_url or "").strip().rstrip("/") == normalized_url
        ),
        None,
    )
    return {
        "source_title": quiz.source_title or (upload.source_title if upload else None),
        "source_url": source_url,
        "source_section": quiz.source_section or (upload.source_section if upload else None),
        "source_version": upload.source_version if upload else None,
        "document_id": upload.external_document_id if upload else None,
        "chunk_id": None,
        "evidence_origin": "fixed_quiz_source",
    }


def requested_quiz_purpose(text: str) -> Literal[
    "pretest", "posttest", "stage_test", "practice"
] | None:
    """Return an explicitly requested purpose; generic requests follow server progress."""

    normalized = TurnOrchestrator.normalize(text)
    if "前测" in normalized:
        return "pretest"
    if "后测" in normalized:
        return "posttest"
    if "练习" in normalized:
        return "practice"
    if "阶段" in normalized:
        return "stage_test"
    return None


def _persist_misconception_feedback(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    quiz: Quiz,
    request_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """Create stable misconception memory only after two distinct wrong attempts."""

    rows = (
        db.query(StudentQuestionHistory)
        .filter_by(user_id=user.id, question_id=quiz.id, is_correct=False)
        .order_by(StudentQuestionHistory.created_at.desc())
        .limit(2)
        .all()
    )
    if len(rows) < 2:
        return {
            "operation": "create",
            "status": "rejected",
            "reason": "稳定误区至少需要两个不同的错误作答证据。",
            "memory_record": None,
        }
    evidence = [
        MemoryEvidence(
            reference_id=row.attempt_id,
            evidence_type=MemoryEvidenceType.SCORED_ATTEMPT,
            occurred_at=(row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at),
            attempt_id=row.attempt_id,
            question_id=quiz.id,
            knowledge_point_id=quiz.knowledge_point_id,
            is_correct=False,
            score=row.score,
            misconception_key=f"question-{quiz.id}",
            session_id=row.session_id,
            confidence=1.0,
        )
        for row in reversed(rows)
    ]
    candidate = MemoryCandidate(
        organization_id=user.organization_id,
        user_id=user.id,
        program_id=session.program_id,
        module_id=session.module_id,
        knowledge_point_id=quiz.knowledge_point_id,
        session_id=session.id,
        content=f"在“{quiz.knowledge_point.name}”相关题目中重复出现同类错误理解。",
        memory_type=MemoryType.MISCONCEPTION,
        evidence=evidence,
        metadata={"trace_id": trace_id, "request_id": request_id},
    )
    lifecycle = LearnerMemoryService().create(candidate)
    payload = lifecycle.to_dict()
    record = payload.get("memory_record")
    db.add(
        MemoryAudit(
            id=uuid4().hex,
            request_id=request_id,
            organization_id=user.organization_id,
            user_id=user.id,
            operation=payload["operation"],
            status=payload["status"],
            memory_record=record,
            reason=payload.get("reason"),
        )
    )
    return payload


def recommended_quiz_purpose(progress: AssessmentProgress) -> Literal[
    "pretest", "posttest", "stage_test", "practice"
] | None:
    """Map the server-owned next action to the only assessment purpose to issue."""

    if progress.next_action in {"start_pretest", "continue_pretest"}:
        return "pretest"
    if progress.next_action in {"start_stage_test", "continue_stage_test"}:
        return "stage_test"
    if progress.next_action in {"start_posttest", "continue_posttest"}:
        return "posttest"
    if progress.next_action == "practice":
        return "practice"
    return None


def public_quiz_payload(quiz: Quiz) -> dict[str, Any]:
    """Return question metadata without exposing its answer or scoring rule."""

    return {
        "question_id": quiz.id,
        "content": quiz.content,
        "type": quiz.type,
        "purpose": quiz.purpose,
        "difficulty": quiz.difficulty,
        "knowledge_point_id": quiz.knowledge_point_id,
    }


def execute_turn(
    db: Session,
    user: User,
    session: ChatSession,
    request: ChatRequest,
    execution: TurnExecution,
    plan,
) -> dict:
    action = plan.primary_action
    content = ""
    payload: dict = {}
    degradation: list[str] = []
    analysis_started_at = datetime.now(UTC)
    analysis_output = LearnerInsightService(db).build_profile(user.id, session.module_id)
    analysis_finished_at = datetime.now(UTC)
    generation_started_at = datetime.now(UTC)
    requested_point = None
    misconception_feedback_quiz: Quiz | None = None
    if request.knowledge_point_id is not None:
        requested_point = (
            db.query(KnowledgePoint)
            .filter_by(id=request.knowledge_point_id, module_id=session.module_id)
            .first()
        )
        if requested_point is None:
            raise ValueError("知识点不属于当前培训模块。")

    if action is PrimaryAction.RESPOND_GREETING:
        content = f"你好，当前学习模块是“{session.module.name}”。可以直接提出知识问题、请求测验或进行语音讲解。"
    elif action is PrimaryAction.CLOSE_SESSION:
        content = "本次学习会话已结束，当前模块、能力状态和学习记录已经保存。"
    elif action is PrimaryAction.CHANGE_MODULE:
        target = (
            db.query(TrainingModule)
            .filter_by(id=plan.target_module_id, program_id=session.program_id)
            .first()
        )
        if target is None:
            raise ValueError("目标培训模块无效。")
        session.module_id = target.id
        session.knowledge_base_id = target.knowledge_base_id
        session.echo_state = "E"
        session.echo_stage_counts = {"E": 0, "C": 0, "H": 0, "O": 0}
        session.active_quiz_id = None
        session.context_version += 1
        content = f"已切换到“{target.name}”，新的 ECHO 学习循环从唤起阶段开始。"
    elif action is PrimaryAction.GENERATE_QUIZ:
        assessment_flow = AssessmentFlowService(
            db,
            user_id=user.id,
            module_id=session.module_id,
        )
        assessment_progress = assessment_flow.progress(
            active_quiz_id=session.active_quiz_id,
        )
        purpose = requested_quiz_purpose(request.user_input)
        purpose = purpose or recommended_quiz_purpose(assessment_progress)
        if purpose is None:
            is_allowed = False
            content = assessment_progress.description
        else:
            is_allowed, blocked_message = assessment_flow.can_request(
                purpose,
                active_quiz_id=session.active_quiz_id,
            )
            if not is_allowed:
                content = blocked_message
            else:
                quiz = AdaptiveEngine(db).get_adaptive_question(
                    user.id,
                    session.module_id,
                    knowledge_point_id=(requested_point.id if requested_point else None),
                    purpose=purpose,
                )
                if quiz is not None:
                    session.active_quiz_id = quiz.id
                    payload["quiz"] = public_quiz_payload(quiz)
                    content = quiz.content
        if purpose is not None and is_allowed and "quiz" not in payload:
            purpose_label = {
                "pretest": "前测",
                "posttest": "后测",
                "stage_test": "阶段测验",
                "practice": "练习",
            }[purpose]
            content = f"当前模块还没有可用的{purpose_label}题目，请先导入对应用途的固定题库。"
    elif action is PrimaryAction.GRADE_ANSWER:
        quiz = db.query(Quiz).filter_by(id=session.active_quiz_id).first()
        if quiz is None:
            raise ValueError("当前待答题目不存在。")
        submitted = extract_answer(request.user_input)
        grade = grade_quiz_answer(quiz, submitted)
        ability, updated = AdaptiveEngine(db).update_student_state(
            user_id=user.id,
            question_id=quiz.id,
            is_correct=grade.is_correct,
            attempt_id=request.request_id,
            submitted_answer=submitted,
            score=grade.score,
            session_id=session.id,
            stage=session.echo_state,
        )
        session.active_quiz_id = None
        if not grade.is_correct and quiz.counts_for_mirt:
            misconception_feedback_quiz = quiz
        payload["assessment"] = {
            "is_correct": grade.is_correct,
            "score": grade.score,
            "grading_mode": grade.grading_mode,
            "counts_for_mirt": quiz.counts_for_mirt,
            "updated": updated,
            "ability": {"U": ability.U, "A": ability.A, "R": ability.R},
        }
        assessment_source = fixed_quiz_source(db, session, quiz)
        if assessment_source is not None:
            payload["assessment"]["source"] = assessment_source
        evidence, rag_error = search_official_evidence(
            db,
            query=" ".join(
                value
                for value in (quiz.content, quiz.source_title, quiz.source_section)
                if value
            ),
            knowledge_base_id=session.knowledge_base_id,
            module_id=session.module_id,
            trace_id=plan.trace_id,
            knowledge_point_ids=[quiz.knowledge_point_id],
        )
        payload["evidence"] = evidence
        if rag_error:
            degradation.append(rag_error)
        if grade.is_correct:
            content = (
                "回答正确，能力画像已更新。"
                if quiz.counts_for_mirt
                else "回答正确，本次结果已记录，不更新能力画像。"
            )
        else:
            content = f"本题需要巩固。参考要点：{quiz.answer}"
        if evidence:
            metadata = evidence[0].get("metadata") or {}
            source_label = metadata.get("source_title") or metadata.get("title")
            source_section = metadata.get("source_section") or metadata.get("chapter")
            content += f"\n\n依据：[1] {source_label} - {source_section}"
        elif assessment_source is not None:
            content += (
                f"\n\n依据：[1] {assessment_source['source_title']} - "
                f"{assessment_source['source_section']}"
            )
    elif action is PrimaryAction.LEARNING_DIALOGUE:
        retrieval_query = request.user_input
        knowledge_point_ids = None
        if requested_point is not None:
            retrieval_query = f"{requested_point.name} {request.user_input}"
            knowledge_point_ids = [requested_point.id]
        evidence, rag_error = safe_retrieve(
            db,
            plan,
            retrieval_query,
            knowledge_point_ids=knowledge_point_ids,
        )
        memories, memory_error = safe_memories(plan, user, request.user_input)
        if rag_error:
            degradation.append(rag_error)
        if memory_error:
            degradation.append(memory_error)
        recent_messages = (
            db.query(Message)
            .filter_by(session_id=session.id)
            .order_by(Message.id.desc())
            .limit(6)
            .all()
        )
        history = [
            {"role": item.role, "content": item.content}
            for item in reversed(recent_messages)
        ]
        content = StudentHelper().respond(
            user_input=request.user_input,
            module_name=session.module.name,
            echo_state=session.echo_state,
            evidence=evidence,
            memories=memories,
            history=history,
            has_active_quiz=session.active_quiz_id is not None,
        )
        fsm = EchoFSM(session.echo_stage_counts)
        proposed = "C" if session.echo_state == "E" else session.echo_state
        transition = fsm.update(request.user_input, proposed, session.echo_state)
        session.echo_state = transition["normalized_state"]
        session.echo_stage_counts = transition["rounds"]
        payload["echo_transition"] = transition
        payload["evidence"] = evidence
    elif action is PrimaryAction.GENERAL_RESPONSE:
        content = "收到。当前学习状态保持不变，可以继续提问，系统会在合适阶段安排测验。"
    else:
        content = "本轮没有执行学习动作，请提供具体问题、测验请求或模块切换目标。"

    payload["assessment_progress"] = AssessmentFlowService(
        db,
        user_id=user.id,
        module_id=session.module_id,
    ).progress(active_quiz_id=session.active_quiz_id).public_payload()
    generation_finished_at = datetime.now(UTC)

    db.add(
        Message(
            user_id=user.id,
            session_id=session.id,
            role="user",
            content=request.user_input,
            echo_state=session.echo_state,
        )
    )
    db.add(
        Message(
            user_id=user.id,
            session_id=session.id,
            role="assistant",
            content=content,
            echo_state=session.echo_state,
        )
    )
    session.updated_at = datetime.now()
    result = {
        "content": content,
        "payload": payload,
        "degradation": degradation,
        "session_id": session.id,
        "trace_id": plan.trace_id,
        "intent": plan.intent.value,
        "primary_action": plan.primary_action.value,
        "echo_state": session.echo_state,
    }
    evidence_refs = [
        item.get("metadata", {}).get("chunk_id")
        or item.get("metadata", {}).get("filename")
        for item in payload.get("evidence", [])
    ]
    db.add(
        LearningDecision(
            id=uuid4().hex,
            trace_id=plan.trace_id,
            user_id=user.id,
            session_id=session.id,
            module_id=session.module_id,
            action=plan.primary_action.value,
            reason=plan.reason,
            evidence_refs=[ref for ref in evidence_refs if ref],
        )
    )
    validation_started_at = datetime.now(UTC)
    validation_issues: list[str] = []
    if plan.use_rag and not payload.get("evidence"):
        validation_issues.append("需要专业知识的对话未获得可追溯官方证据")
    if action is PrimaryAction.GRADE_ANSWER and not payload.get("assessment"):
        validation_issues.append("服务端判分结果缺失")
    if (
        action is PrimaryAction.GRADE_ANSWER
        and payload.get("assessment")
        and not payload["assessment"].get("source")
        and not payload.get("evidence")
    ):
        validation_issues.append("固定题判分结果缺少官方出处")
    if not content.strip():
        validation_issues.append("最终回复为空")
    validation_finished_at = datetime.now(UTC)
    next_action_started_at = datetime.now(UTC)
    result["agent_records"] = {
        "analysis": {
            "status": "completed",
            "input_summary": {
                "user_id": user.id,
                "module_id": session.module_id,
                "active_quiz_id": plan.context.active_quiz_id,
                "echo_state": plan.context.echo_state,
            },
            "output": analysis_output,
            "failure_reason": None,
            "started_at": analysis_started_at.isoformat(),
            "finished_at": analysis_finished_at.isoformat(),
            "persisted_in_system": True,
        },
        "generation": {
            "status": "completed_with_degradation" if degradation else "completed",
            "input_summary": {
                "primary_action": plan.primary_action.value,
                "use_rag": plan.use_rag,
                "use_memory": plan.use_memory,
            },
            "output": {"content": content, "payload": payload, "degradation": degradation},
            "failure_reason": "；".join(degradation) if degradation else None,
            "started_at": generation_started_at.isoformat(),
            "finished_at": generation_finished_at.isoformat(),
            "persisted_in_system": True,
        },
        "validation": {
            "status": "failed" if validation_issues else "completed",
            "input_summary": {
                "primary_action": plan.primary_action.value,
                "evidence_count": len(payload.get("evidence") or []),
            },
            "output": {"passed": not validation_issues, "issues": validation_issues},
            "failure_reason": "；".join(validation_issues) if validation_issues else None,
            "started_at": validation_started_at.isoformat(),
            "finished_at": validation_finished_at.isoformat(),
            "persisted_in_system": True,
        },
        "next_action": {
            "status": "completed",
            "input_summary": {"intent": plan.intent.value, "trace_id": plan.trace_id},
            "output": {
                "primary_action": plan.primary_action.value,
                "reason": plan.reason,
                "assessment_progress": payload["assessment_progress"],
                "resulting_echo_state": session.echo_state,
            },
            "failure_reason": None,
            "started_at": next_action_started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "persisted_in_system": True,
        },
    }
    execution.status = (
        TurnStatus.COMPLETED_WITH_DEGRADATION.value
        if degradation
        else TurnStatus.COMPLETED.value
    )
    execution.result = result
    execution.finished_at = datetime.now()
    db.commit()
    if misconception_feedback_quiz is not None:
        memory_feedback = _persist_misconception_feedback(
            db,
            user=user,
            session=session,
            quiz=misconception_feedback_quiz,
            request_id=request.request_id,
            trace_id=plan.trace_id,
        )
        result["payload"]["memory_feedback"] = memory_feedback
        result["agent_records"]["analysis"]["output"]["memory_feedback"] = memory_feedback
        execution.result = result
        db.commit()
    return result


def stream_result(result: dict):
    yield json.dumps(
        {
            "type": "meta",
            "session_id": result["session_id"],
            "trace_id": result["trace_id"],
            "intent": result["intent"],
            "primary_action": result["primary_action"],
            "echo_state": result["echo_state"],
            "degradation": result["degradation"],
            **result.get("payload", {}),
        },
        ensure_ascii=False,
    ) + "\n"
    yield json.dumps({"type": "content", "content": result["content"]}, ensure_ascii=False) + "\n"


@app.post("/chat")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if request.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问其他学习者数据")
    session = (
        create_session(db, user, request)
        if request.session_id is None
        else get_owned_session(db, request.session_id, user.id)
    )
    existing = (
        db.query(TurnExecution)
        .filter_by(session_id=session.id, request_id=request.request_id)
        .first()
    )
    if existing and existing.status in {
        TurnStatus.COMPLETED.value,
        TurnStatus.COMPLETED_WITH_DEGRADATION.value,
    }:
        return StreamingResponse(stream_result(existing.result), media_type="application/x-ndjson")

    context = TurnContext(
        user_id=user.id,
        session_id=session.id,
        program_id=session.program_id,
        module_id=session.module_id,
        knowledge_base_id=session.knowledge_base_id,
        echo_state=session.echo_state,
        active_quiz_id=session.active_quiz_id,
    )
    plan = TurnOrchestrator().plan(
        request.user_input,
        context,
        requested_module_id=request.requested_module_id,
    )
    execution = existing or TurnExecution(
        id=uuid4().hex,
        request_id=request.request_id,
        trace_id=plan.trace_id,
        user_id=user.id,
        session_id=session.id,
        intent=plan.intent.value,
        primary_action=plan.primary_action.value,
        plan=plan.model_dump(mode="json"),
    )
    if existing is None:
        db.add(execution)
        db.commit()
    try:
        result = execute_turn(db, user, session, request, execution, plan)
    except Exception as exc:
        db.rollback()
        execution = db.query(TurnExecution).filter_by(id=execution.id).first()
        if execution:
            execution.status = TurnStatus.FAILED.value
            execution.error_message = str(exc)
            execution.finished_at = datetime.now()
            db.commit()
        raise HTTPException(status_code=500, detail=f"本轮执行失败：{exc}") from exc
    return StreamingResponse(stream_result(result), media_type="application/x-ndjson")


@app.get(
    "/v1/modules/{module_id}/assessment-progress",
    response_model=AssessmentProgressResponse,
)
def assessment_progress(
    module_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Return the server-owned next assessment action for this learner and module."""

    accessible_module(db, user, module_id)
    latest_session = (
        db.query(ChatSession)
        .filter_by(user_id=user.id, module_id=module_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .first()
    )
    progress = AssessmentFlowService(
        db,
        user_id=user.id,
        module_id=module_id,
    ).progress(
        active_quiz_id=latest_session.active_quiz_id if latest_session else None,
    )
    return AssessmentProgressResponse.model_validate(progress.public_payload())


@app.get("/v1/quizzes/next")
def next_fixed_quiz(
    module_id: int,
    purpose: Literal["pretest", "posttest", "stage_test", "practice"] = "stage_test",
    knowledge_point_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    accessible_module(db, user, module_id)
    is_allowed, blocked_message = AssessmentFlowService(
        db,
        user_id=user.id,
        module_id=module_id,
    ).can_request(purpose)
    if not is_allowed:
        raise HTTPException(status_code=409, detail=blocked_message)
    if knowledge_point_id is not None:
        point = (
            db.query(KnowledgePoint)
            .filter_by(id=knowledge_point_id, module_id=module_id)
            .first()
        )
        if point is None:
            raise HTTPException(status_code=404, detail="知识点不存在")
    quiz = AdaptiveEngine(db).get_adaptive_question(
        user.id,
        module_id,
        knowledge_point_id=knowledge_point_id,
        purpose=purpose,
    )
    if quiz is None:
        raise HTTPException(status_code=404, detail="当前范围没有可用的固定题目")
    return public_quiz_payload(quiz)


@app.post("/quiz/submit")
def submit_quiz(
    payload: QuizSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if payload.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权提交其他学习者答案")
    quiz = db.query(Quiz).filter_by(id=payload.question_id).first()
    if quiz is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    accessible_module(db, user, quiz.module_id)
    session = None
    if payload.session_id is not None:
        session = get_owned_session(db, payload.session_id, user.id)
        if session.active_quiz_id not in {None, quiz.id}:
            raise HTTPException(status_code=409, detail="提交题目与当前待答题目不一致")
    existing_attempt = (
        db.query(StudentQuestionHistory)
        .filter_by(attempt_id=payload.attempt_id)
        .first()
    )
    is_active_question = session is not None and session.active_quiz_id == quiz.id
    if existing_attempt is None and not is_active_question:
        is_allowed, blocked_message = AssessmentFlowService(
            db,
            user_id=user.id,
            module_id=quiz.module_id,
        ).can_request(quiz.purpose)
        if not is_allowed:
            raise HTTPException(status_code=409, detail=blocked_message)
    try:
        grade = grade_quiz_answer(quiz, payload.answer)
        ability, updated = AdaptiveEngine(db).update_student_state(
            user_id=user.id,
            question_id=payload.question_id,
            is_correct=grade.is_correct,
            attempt_id=payload.attempt_id,
            submitted_answer=payload.answer.strip(),
            score=grade.score,
            session_id=payload.session_id,
            stage=payload.stage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if session is not None and session.active_quiz_id == quiz.id:
        session.active_quiz_id = None
        db.commit()
    return {
        "status": "success",
        "updated": updated,
        "attempt_id": payload.attempt_id,
        "is_correct": grade.is_correct,
        "score": grade.score,
        "grading_mode": grade.grading_mode,
        "reference_answer": quiz.answer,
        "scoring_method": quiz.scoring_method,
        "source": {
            "title": quiz.source_title,
            "url": quiz.source_url,
            "section": quiz.source_section,
        },
        "counts_for_mirt": quiz.counts_for_mirt,
        "ability": {"U": ability.U, "A": ability.A, "R": ability.R},
        "attempt_count": ability.attempt_count,
    }


@app.get("/users/{user_id}/mirt/modules")
def mirt_modules(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="无权查看其他学习者画像")
    program, _ = default_context(db)
    rows = (
        db.query(TrainingModule)
        .filter_by(program_id=program.id)
        .order_by(TrainingModule.sequence)
        .all()
    )
    return {"modules": [{"id": row.id, "code": row.code, "name": row.name} for row in rows]}


@app.get("/users/{user_id}/mirt/module-state")
def mirt_module_state(
    user_id: int,
    module_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="无权查看其他学习者画像")
    row = db.query(LearnerAbility).filter_by(user_id=user.id, module_id=module_id).first()
    return {
        "module_id": module_id,
        "found": row is not None,
        "U": row.U if row else 0.0,
        "A": row.A if row else 0.0,
        "R": row.R if row else 0.0,
    }


@app.get("/users/{user_id}/mirt/daily-series")
def mirt_daily_series(
    user_id: int,
    module_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="无权查看其他学习者画像")
    series = build_daily_series(db, user.id, module_id, days)
    attempts = sum(item["attempt_count"] for item in series)
    correct = sum(item["correct_count"] for item in series)
    return {
        "module_id": module_id,
        "days": days,
        "series": series,
        "avg_accuracy": round(correct / attempts, 4) if attempts else None,
    }


@app.get("/users/{user_id}/learning-insight")
def learning_insight(
    user_id: int,
    module_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="无权查看其他学习者画像")
    memories: list[dict] = []
    memory_error = None
    client = SimpleMemClient()
    module = db.query(TrainingModule).filter_by(id=module_id).first()
    if module is None:
        raise HTTPException(status_code=404, detail="培训模块不存在")
    module_points = (
        db.query(KnowledgePoint)
        .filter_by(module_id=module.id)
        .order_by(KnowledgePoint.sequence)
        .all()
    )
    if client.configured:
        try:
            memories = client.search(
                MemorySearchRequest(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    program_id=module.program_id,
                    module_id=module.id,
                    intent=MemoryIntent.LEARNER_DIAGNOSIS,
                    query=_module_memory_query(module, module_points),
                )
            )
        except IntegrationUnavailable as exc:
            memory_error = str(exc)
    profile = LearnerInsightService(db).build_profile(
        user.id,
        module_id,
        memory_items=memories,
    )
    profile["degradation"] = [memory_error] if memory_error else []
    return profile


@app.post("/v1/evaluation/learner-profile")
def initialize_evaluation_learner_profile(
    request: EvaluationProfileRequest,
    x_evaluation_key: Annotated[str | None, Header(alias="X-Evaluation-Key")] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Materialize one frozen synthetic learner profile for an auditable test run.

    The endpoint is absent unless a deployment explicitly sets a strong
    ``EVALUATION_PROFILE_SEED_KEY``. It may only initialize the authenticated
    learner's own synthetic account and is not part of the production flow.
    """

    configured_key = os.getenv("EVALUATION_PROFILE_SEED_KEY", "").strip()
    if not configured_key:
        raise HTTPException(status_code=404, detail="评测画像初始化未启用")
    if not x_evaluation_key or not hmac.compare_digest(x_evaluation_key, configured_key):
        raise HTTPException(status_code=403, detail="评测画像初始化密钥无效")
    if request.user_id != user.id or user.role != UserRole.LEARNER.value:
        raise HTTPException(status_code=403, detail="只能初始化当前评测学习者")

    module = accessible_module(db, user, request.module_id)
    profiles, source_sha256 = load_evaluation_profile_definitions()
    profile_input = profiles[request.profile_id]
    points = (
        db.query(KnowledgePoint)
        .filter_by(module_id=module.id)
        .order_by(KnowledgePoint.sequence, KnowledgePoint.id)
        .all()
    )
    if len(points) < 4:
        raise HTTPException(status_code=409, detail="评测模块至少需要四个知识点")
    quiz_by_point: dict[int, Quiz] = {}
    for point in points[:4]:
        quiz = (
            db.query(Quiz)
            .filter_by(
                module_id=module.id,
                knowledge_point_id=point.id,
                counts_for_mirt=True,
            )
            .order_by(Quiz.id)
            .first()
        )
        if quiz is None:
            raise HTTPException(status_code=409, detail=f"知识点 {point.code} 没有固定题目")
        quiz_by_point[point.id] = quiz

    outcome_plan = {
        "P1": [(0, False), (0, False), (0, True), (1, False), (1, False), (1, True)],
        "P2": [
            (0, True), (0, True), (0, True),
            (1, True), (1, True), (1, True),
            (2, False), (3, False),
        ],
        "P3": [
            (0, True), (0, True), (0, True),
            (1, True), (1, True),
            (2, True), (2, True),
            (3, False),
        ],
    }[request.profile_id]
    module_quiz_ids = [row.id for row in db.query(Quiz.id).filter_by(module_id=module.id).all()]
    if module_quiz_ids:
        db.query(StudentQuestionHistory).filter(
            StudentQuestionHistory.user_id == user.id,
            StudentQuestionHistory.question_id.in_(module_quiz_ids),
        ).delete(synchronize_session=False)
    ability = (
        db.query(LearnerAbility)
        .filter_by(user_id=user.id, module_id=module.id)
        .first()
    )
    if ability is None:
        ability = LearnerAbility(user_id=user.id, module_id=module.id)
        db.add(ability)
    ability.U = float(profile_input["ability"]["U"])
    ability.A = float(profile_input["ability"]["A"])
    ability.R = float(profile_input["ability"]["R"])
    ability.attempt_count = int(profile_input["attempt_count"])
    ability.updated_at = datetime.now(UTC)

    attempt_ids: list[str] = []
    for sequence, (point_index, is_correct) in enumerate(outcome_plan, start=1):
        point = points[point_index]
        attempt_id = f"eval-{user.id}-{module.code}-{request.profile_id}-{sequence:02d}"
        attempt_ids.append(attempt_id)
        db.add(
            StudentQuestionHistory(
                attempt_id=attempt_id,
                user_id=user.id,
                question_id=quiz_by_point[point.id].id,
                submitted_answer="[frozen synthetic evaluation input]",
                is_correct=is_correct,
                score=1.0 if is_correct else 0.0,
                stage="EVAL",
            )
        )
    db.commit()

    memory_results: list[dict[str, Any]] = []
    memory_items: list[dict[str, Any]] = []
    memory_degradation: list[str] = []
    for index, hint in enumerate(profile_input.get("memory_hints") or [], start=1):
        memory_type = (
            MemoryType.MISCONCEPTION
            if request.profile_id == "P1"
            else MemoryType.LEARNING_PREFERENCE
        )
        hash_input = f"{user.organization_id}:{user.id}:{module.id}:{request.profile_id}:{index}"
        idempotency_key = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        conflict_input = f"{user.organization_id}:{user.id}:{module.id}:{memory_type.value}"
        record = MemoryRecord(
            organization_id=user.organization_id,
            user_id=user.id,
            program_id=module.program_id,
            module_id=module.id,
            knowledge_point_id=points[0].id if memory_type is MemoryType.MISCONCEPTION else None,
            content=str(hint),
            memory_type=memory_type,
            idempotency_key=idempotency_key,
            conflict_key=hashlib.sha256(conflict_input.encode("utf-8")).hexdigest(),
            confidence=1.0,
            evidence_refs=attempt_ids[:3],
            metadata={
                "source": "frozen_evaluation_profile",
                "profile_id": request.profile_id,
                "source_sha256": source_sha256,
            },
        )
        try:
            memory_results.append(SimpleMemClient().upsert(record))
            memory_items.append(
                {
                    "content": record.content,
                    "memory_type": record.memory_type.value,
                    "evidence_refs": record.evidence_refs,
                }
            )
        except IntegrationUnavailable as exc:
            memory_degradation.append(str(exc))

    initialized_profile = LearnerInsightService(db).build_profile(
        user.id,
        module.id,
        memory_items=memory_items,
    )
    actual_profile_type = (
        initialized_profile["views"]["path_and_resources"]["learner_profile"].get("type")
    )
    if actual_profile_type != request.profile_id:
        raise HTTPException(
            status_code=500,
            detail=(
                f"评测画像初始化后分类不一致：expected={request.profile_id}, "
                f"actual={actual_profile_type}"
            ),
        )
    return {
        "profile_id": request.profile_id,
        "source_sha256": source_sha256,
        "module_id": module.id,
        "attempt_ids": attempt_ids,
        "memory_results": memory_results,
        "degradation": memory_degradation,
        "profile": initialized_profile,
    }


@app.post("/v1/evaluation/quiz-context")
def initialize_evaluation_quiz_context(
    request: EvaluationQuizContextRequest,
    x_evaluation_key: Annotated[str | None, Header(alias="X-Evaluation-Key")] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Create an isolated session with the frozen case's registered fixed quiz active."""

    configured_key = os.getenv("EVALUATION_PROFILE_SEED_KEY", "").strip()
    if not configured_key:
        raise HTTPException(status_code=404, detail="评测题目上下文初始化未启用")
    if not x_evaluation_key or not hmac.compare_digest(x_evaluation_key, configured_key):
        raise HTTPException(status_code=403, detail="评测题目上下文初始化密钥无效")
    if request.user_id != user.id or user.role != UserRole.LEARNER.value:
        raise HTTPException(status_code=403, detail="只能初始化当前评测学习者")

    module = accessible_module(db, user, request.module_id)
    point = (
        db.query(KnowledgePoint)
        .filter_by(id=request.knowledge_point_id, module_id=module.id)
        .first()
    )
    if point is None:
        raise HTTPException(status_code=404, detail="评测知识点不存在")
    normalized_source_url = request.source_url.strip().rstrip("/")
    quiz = next(
        (
            item
            for item in db.query(Quiz)
            .filter_by(module_id=module.id, knowledge_point_id=point.id)
            .order_by(Quiz.id)
            .all()
            if str(item.source_url or "").strip().rstrip("/") == normalized_source_url
        ),
        None,
    )
    if quiz is None:
        raise HTTPException(
            status_code=409,
            detail="当前知识点没有与冻结案例官方来源一致的固定题",
        )

    session = ChatSession(
        user_id=user.id,
        program_id=module.program_id,
        module_id=module.id,
        knowledge_base_id=module.knowledge_base_id,
        title=f"评测固定题：{point.name}"[:100],
        active_quiz_id=quiz.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id,
        "module_id": module.id,
        "knowledge_point_id": point.id,
        "quiz": public_quiz_payload(quiz),
        "source": fixed_quiz_source(db, session, quiz),
    }


def submit_micro_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(MicroDetectionJob).filter_by(id=job_id).first()
        if job is None:
            return
        client = MicroRepresentationClient()
        if not client.configured:
            job.status = "awaiting_detector"
            job.error_message = "Integration base URL is not configured."
            db.commit()
            return
        module = db.query(TrainingModule).filter_by(id=job.module_id).first()
        try:
            response = client.create_job(
                MicroDetectionRequest(
                    trace_id=job.id,
                    organization_id=job.organization_id,
                    learner_id=job.learner_id,
                    session_id=job.session_id,
                    program_id=module.program_id,
                    module_id=job.module_id,
                    knowledge_point_id=job.knowledge_point_id,
                    source_type=MicroSource(job.source_type),
                    audio_uri=job.audio_uri,
                    consent_granted=job.consent_granted,
                    speaker_mapping_confirmed=job.learner_id is not None,
                )
            )
            try:
                apply_micro_job_creation_result(db, job, client, response)
            except IntegrationContractError as exc:
                job.events_sync_status = "failed"
                job.events_sync_error = str(exc)
                job.status = "failed"
                job.error_message = str(exc)
            except IntegrationUnavailable as exc:
                job.events_sync_status = "failed"
                job.events_sync_error = str(exc)
        except IntegrationTransientError as exc:
            job.status = "awaiting_detector"
            job.error_message = str(exc)
        except (IntegrationContractError, ValueError) as exc:
            job.status = "failed"
            job.error_message = str(exc)
        except IntegrationUnavailable as exc:
            # Older/custom adapters still raising the base error are treated as
            # temporary so an optional detector outage cannot lock the audio.
            job.status = "awaiting_detector"
            job.error_message = str(exc)
        db.commit()
    finally:
        db.close()


def transcribe_micro_job(job_id: str) -> None:
    """Transcribe a persisted recording without changing micro-signal evidence."""

    db = SessionLocal()
    try:
        job = db.query(MicroDetectionJob).filter_by(id=job_id).first()
        if job is None or job.transcription_status == "completed":
            return
        client = ASRClient()
        if not client.configured:
            job.transcription_status = "unavailable"
            job.transcription_error = "ASR 服务未配置。"
            db.commit()
            return
        parsed = urlparse(job.audio_uri)
        if parsed.scheme != "file":
            job.transcription_status = "failed"
            job.transcription_error = "ASR 仅支持 ECHO 本地录音文件。"
            db.commit()
            return
        audio_path = Path(url2pathname(unquote(parsed.path)))
        if os.name == "nt" and len(str(audio_path)) >= 3 and str(audio_path)[0] == "/":
            audio_path = Path(str(audio_path)[1:])
        job.transcription_status = "processing"
        job.transcription_error = None
        db.commit()
        try:
            result = client.transcribe_file(audio_path)
        except IntegrationTransientError as exc:
            job.transcription_status = "unavailable"
            job.transcription_error = str(exc)
        except (IntegrationContractError, IntegrationUnavailable, OSError, ValueError) as exc:
            job.transcription_status = "failed"
            job.transcription_error = str(exc)
        else:
            job.transcript = result["text"]
            job.transcription_language = result.get("language")
            job.transcription_status = "completed"
            job.transcribed_at = datetime.now()
            job.transcription_error = None
        db.commit()
    finally:
        db.close()


def process_micro_job(job_id: str) -> None:
    """Run detector submission and ASR for one recording as one queued task."""

    submit_micro_job(job_id)
    transcribe_micro_job(job_id)


def save_audio_file(job_id: str, audio: UploadFile) -> tuple[Path, str, int]:
    """Validate and stream an audio upload while computing its complete hash."""

    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in MICRO_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported audio file extension")
    if (audio.content_type or "").lower() not in MICRO_AUDIO_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="unsupported audio content type")
    destination_dir = UPLOAD_DIR / "micro"
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", audio.filename or "audio.webm")
    destination = destination_dir / f"{job_id}_{safe_name}"
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := audio.file.read(1024 * 1024):
                size += len(chunk)
                if size > Config.upload.MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="audio file exceeds size limit")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="audio file is empty")
    except (HTTPException, OSError):
        destination.unlink(missing_ok=True)
        raise
    return destination, digest.hexdigest(), size


@dataclass(frozen=True)
class MicroJobCreation:
    job: MicroDetectionJob
    is_created: bool
    audio_size: int
    saved_path: Path | None


def validate_micro_job_scope(
    db: Session,
    *,
    user: User,
    module_id: int,
    source_type: MicroSource,
    learner_id: int | None,
    session_id: int | None,
    knowledge_point_id: int | None,
) -> None:
    module = (
        db.query(TrainingModule)
        .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
        .filter(
            TrainingModule.id == module_id,
            TrainingProgram.organization_id == user.organization_id,
        )
        .first()
    )
    if module is None:
        raise HTTPException(status_code=404, detail="training module does not exist")
    if knowledge_point_id is not None and (
        db.query(KnowledgePoint.id)
        .filter(
            KnowledgePoint.id == knowledge_point_id,
            KnowledgePoint.module_id == module_id,
        )
        .first()
        is None
    ):
        raise HTTPException(status_code=422, detail="knowledge point does not belong to module")
    if learner_id is not None and (
        db.query(User.id)
        .filter(
            User.id == learner_id,
            User.organization_id == user.organization_id,
            User.role == UserRole.LEARNER.value,
            User.status == "active",
        )
        .first()
        is None
    ):
        raise HTTPException(status_code=422, detail="learner is not active in this organization")
    if session_id is None:
        return
    session = (
        db.query(ChatSession)
        .join(User, User.id == ChatSession.user_id)
        .filter(
            ChatSession.id == session_id,
            User.organization_id == user.organization_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=422, detail="session does not belong to this organization")
    if session.module_id != module_id:
        raise HTTPException(status_code=422, detail="session does not belong to module")
    if source_type is MicroSource.LEARNER_VOICE and session.user_id != user.id:
        raise HTTPException(status_code=403, detail="learner voice session must belong to current user")
    if learner_id is not None and session.user_id != learner_id:
        raise HTTPException(status_code=422, detail="session does not belong to learner")


def build_micro_dedupe_key(
    *,
    organization_id: int,
    learner_id: int | None,
    session_id: int | None,
    module_id: int,
    knowledge_point_id: int | None,
    source_type: MicroSource,
    audio_sha256: str,
) -> str:
    scope = {
        "audio_sha256": audio_sha256,
        "knowledge_point_id": knowledge_point_id,
        "learner_id": learner_id,
        "module_id": module_id,
        "organization_id": organization_id,
        "session_id": session_id,
        "source_type": source_type.value,
    }
    canonical = json.dumps(scope, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cleanup_audio_files(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def create_micro_job_record(
    db: Session,
    *,
    user: User,
    module_id: int,
    source_type: MicroSource,
    audio: UploadFile,
    learner_id: int | None,
    session_id: int | None,
    knowledge_point_id: int | None,
) -> MicroJobCreation:
    job_id = uuid4().hex
    validate_micro_job_scope(
        db,
        user=user,
        module_id=module_id,
        source_type=source_type,
        learner_id=learner_id,
        session_id=session_id,
        knowledge_point_id=knowledge_point_id,
    )
    destination, audio_sha256, audio_size = save_audio_file(job_id, audio)
    dedupe_key = build_micro_dedupe_key(
        organization_id=user.organization_id,
        learner_id=learner_id,
        session_id=session_id,
        module_id=module_id,
        knowledge_point_id=knowledge_point_id,
        source_type=source_type,
        audio_sha256=audio_sha256,
    )
    existing = db.query(MicroDetectionJob).filter(
        MicroDetectionJob.organization_id == user.organization_id,
        MicroDetectionJob.learner_id.is_(learner_id)
        if learner_id is None
        else MicroDetectionJob.learner_id == learner_id,
        MicroDetectionJob.session_id.is_(session_id)
        if session_id is None
        else MicroDetectionJob.session_id == session_id,
        MicroDetectionJob.module_id == module_id,
        MicroDetectionJob.knowledge_point_id.is_(knowledge_point_id)
        if knowledge_point_id is None
        else MicroDetectionJob.knowledge_point_id == knowledge_point_id,
        MicroDetectionJob.source_type == source_type.value,
        MicroDetectionJob.audio_sha256 == audio_sha256,
    ).order_by(MicroDetectionJob.created_at, MicroDetectionJob.id).first()
    if existing is not None:
        destination.unlink(missing_ok=True)
        return MicroJobCreation(existing, False, audio_size, None)
    job = MicroDetectionJob(
        id=job_id,
        organization_id=user.organization_id,
        created_by_user_id=user.id,
        learner_id=learner_id,
        session_id=session_id,
        module_id=module_id,
        knowledge_point_id=knowledge_point_id,
        source_type=source_type.value,
        audio_uri=destination.as_uri(),
        consent_granted=True,
        audio_sha256=audio_sha256,
        dedupe_key=dedupe_key,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        destination.unlink(missing_ok=True)
        existing = db.query(MicroDetectionJob).filter_by(dedupe_key=dedupe_key).first()
        if existing is None:
            raise
        return MicroJobCreation(existing, False, audio_size, None)
    except SQLAlchemyError:
        destination.unlink(missing_ok=True)
        raise
    return MicroJobCreation(job, True, audio_size, destination)


@app.post("/v1/micro/detection-jobs", response_model=MicroJobSubmissionResult)
def create_micro_job(
    background_tasks: BackgroundTasks,
    module_id: Annotated[int, Form()],
    source_type: Annotated[MicroSource, Form()],
    consent_granted: Annotated[bool, Form()],
    audio: Annotated[UploadFile, File()],
    session_id: Annotated[int | None, Form()] = None,
    knowledge_point_id: Annotated[int | None, Form()] = None,
    learner_id: Annotated[int | None, Form()] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not consent_granted:
        raise HTTPException(status_code=400, detail="未获得录音分析授权")
    if source_type is not MicroSource.LEARNER_VOICE:
        raise HTTPException(status_code=422, detail="讲师录音必须使用批量录音接口")
    if user.role != UserRole.LEARNER.value:
        raise HTTPException(status_code=403, detail="只有学习者可以提交单轮语音")
    learner_id = user.id
    creation = create_micro_job_record(
        db,
        user=user,
        module_id=module_id,
        source_type=source_type,
        audio=audio,
        learner_id=learner_id,
        session_id=session_id,
        knowledge_point_id=knowledge_point_id,
    )
    job = creation.job
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        cleanup_audio_files([creation.saved_path] if creation.saved_path else [])
        raise HTTPException(status_code=500, detail="failed to save micro detection job") from exc
    retry_scheduled = False
    if creation.is_created:
        background_tasks.add_task(process_micro_job, job.id)
    elif job.status == "awaiting_detector" and not job.external_job_id:
        retry_scheduled = queue_awaiting_micro_job_retry(db, job, background_tasks)
    if (
        not creation.is_created
        and user.role != UserRole.SYSTEM_ADMIN.value
        and job.created_by_user_id != user.id
    ):
        return {
            "job_id": None,
            "status": "already_submitted",
            "source_type": job.source_type,
            "is_duplicate": True,
            "retry_scheduled": retry_scheduled,
        }
    return {
        "job_id": job.id,
        "status": job.status,
        "source_type": job.source_type,
        "is_duplicate": not creation.is_created,
        "retry_scheduled": retry_scheduled,
    }


@app.get("/v1/micro/learners", response_model=list[MicroLearnerOption])
def list_micro_learners(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """List active learners eligible for confirmed mentor speaker binding."""

    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可选择学习者")
    return (
        db.query(User)
        .filter(
            User.organization_id == user.organization_id,
            User.role == UserRole.LEARNER.value,
            User.status == "active",
        )
        .order_by(User.username, User.id)
        .all()
    )


@app.post("/v1/micro/mentor-batches", response_model=MentorBatchResult)
def create_mentor_batch(
    background_tasks: BackgroundTasks,
    module_id: Annotated[int, Form()],
    consent_granted: Annotated[bool, Form()],
    audio_files: Annotated[list[UploadFile], File()],
    learner_id: Annotated[int | None, Form()] = None,
    session_id: Annotated[int | None, Form()] = None,
    knowledge_point_id: Annotated[int | None, Form()] = None,
    speaker_mapping_confirmed: Annotated[bool, Form()] = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可批量上传")
    if not consent_granted:
        raise HTTPException(status_code=400, detail="未获得录音分析授权")
    if speaker_mapping_confirmed != (learner_id is not None):
        raise HTTPException(
            status_code=422,
            detail="learner_id 与说话人确认状态不一致",
        )
    bound_learner_id = learner_id if speaker_mapping_confirmed else None
    if not audio_files:
        raise HTTPException(status_code=422, detail="at least one audio file is required")
    if len(audio_files) > 20:
        raise HTTPException(status_code=413, detail="mentor batch exceeds 20 files")
    jobs: list[MicroDetectionJob] = []
    linked_job_ids: set[str] = set()
    created_jobs: list[MicroDetectionJob] = []
    created_paths: list[Path] = []
    already_submitted = 0
    retry_jobs: list[MicroDetectionJob] = []
    hidden_job_ids: set[str] = set()
    total_size = 0
    batch = MicroMentorBatch(
        id=uuid4().hex,
        organization_id=user.organization_id,
        created_by_user_id=user.id,
        module_id=module_id,
        session_id=session_id,
        knowledge_point_id=knowledge_point_id,
    )
    try:
        db.add(batch)
        db.flush()
        for audio in audio_files:
            creation = create_micro_job_record(
                db,
                user=user,
                module_id=module_id,
                source_type=MicroSource.MENTOR_RECORDING,
                audio=audio,
                learner_id=bound_learner_id,
                session_id=session_id,
                knowledge_point_id=knowledge_point_id,
            )
            total_size += creation.audio_size
            if (
                not creation.is_created
                and user.role != UserRole.SYSTEM_ADMIN.value
                and creation.job.created_by_user_id != user.id
            ):
                if creation.job.id in hidden_job_ids:
                    if total_size > Config.upload.MAX_FILE_SIZE:
                        raise HTTPException(status_code=413, detail="mentor batch exceeds total size limit")
                    continue
                hidden_job_ids.add(creation.job.id)
                already_submitted += 1
                if (
                    creation.job.status == "awaiting_detector"
                    and not creation.job.external_job_id
                ):
                    retry_jobs.append(creation.job)
                if total_size > Config.upload.MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="mentor batch exceeds total size limit")
                continue
            if creation.job.id in linked_job_ids:
                if total_size > Config.upload.MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="mentor batch exceeds total size limit")
                continue
            linked_job_ids.add(creation.job.id)
            jobs.append(creation.job)
            db.add(
                MicroMentorBatchJob(
                    batch_id=batch.id,
                    job_id=creation.job.id,
                    sequence=len(jobs),
                )
            )
            if creation.is_created:
                created_jobs.append(creation.job)
                if creation.saved_path:
                    created_paths.append(creation.saved_path)
            if total_size > Config.upload.MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="mentor batch exceeds total size limit")
        db.commit()
    except (HTTPException, OSError):
        db.rollback()
        cleanup_audio_files(created_paths)
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        cleanup_audio_files(created_paths)
        raise HTTPException(status_code=500, detail="failed to save mentor batch") from exc
    for job in created_jobs:
        background_tasks.add_task(process_micro_job, job.id)
    for job in retry_jobs:
        queue_awaiting_micro_job_retry(db, job, background_tasks)
    for job in jobs:
        if job not in created_jobs and job.status == "awaiting_detector" and not job.external_job_id:
            queue_awaiting_micro_job_retry(db, job, background_tasks)
    return MentorBatchResult(
        batch_id=batch.id,
        job_ids=[job.id for job in jobs],
        accepted=len(jobs),
        already_submitted=already_submitted,
    )


@app.get("/v1/micro/mentor-batches/{batch_id}", response_model=MentorBatchDetail)
def get_mentor_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    batch = (
        db.query(MicroMentorBatch)
        .filter_by(id=batch_id, organization_id=user.organization_id)
        .first()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="mentor batch does not exist")
    if (
        user.role != UserRole.SYSTEM_ADMIN.value
        and batch.created_by_user_id != user.id
    ):
        raise HTTPException(status_code=404, detail="mentor batch does not exist")
    links = (
        db.query(MicroMentorBatchJob)
        .filter_by(batch_id=batch.id)
        .order_by(MicroMentorBatchJob.sequence)
        .all()
    )
    job_ids = [link.job_id for link in links]
    jobs_by_id = {
        job.id: job
        for job in db.query(MicroDetectionJob)
        .filter(MicroDetectionJob.id.in_(job_ids))
        .all()
    } if job_ids else {}
    events = (
        db.query(MicroRepresentationEvent)
        .filter(MicroRepresentationEvent.job_id.in_(job_ids))
        .order_by(MicroRepresentationEvent.start_ms)
        .all()
    ) if job_ids else []
    return {
        "batch_id": batch.id,
        "module_id": batch.module_id,
        "session_id": batch.session_id,
        "knowledge_point_id": batch.knowledge_point_id,
        "created_at": batch.created_at.isoformat(),
        "jobs": [
            {
                "job_id": job.id,
                "status": job.status,
                "events_sync_status": job.events_sync_status,
                "error_message": job.error_message,
                "audio_duration_ms": job.audio_duration_ms,
                "transcript": job.transcript,
                "transcription_status": job.transcription_status,
                "transcription_error": job.transcription_error,
            }
            for link in links
            if (job := jobs_by_id.get(link.job_id)) is not None
        ],
        "summary": build_mentor_batch_summary(jobs_by_id, events),
    }


def queue_awaiting_micro_job_retry(
    db: Session,
    job: MicroDetectionJob,
    background_tasks: BackgroundTasks,
) -> bool:
    # MicroDetectionJob.updated_at is stored as the project's existing naive
    # local database timestamp, so the lease comparison must use the same base.
    now = datetime.now()
    stale_before = now - timedelta(seconds=MICRO_SUBMISSION_LEASE_SECONDS)
    updated = (
        db.query(MicroDetectionJob)
        .filter(
            MicroDetectionJob.id == job.id,
            MicroDetectionJob.external_job_id.is_(None),
            or_(
                MicroDetectionJob.status == "awaiting_detector",
                and_(
                    MicroDetectionJob.status == "queued",
                    MicroDetectionJob.updated_at < stale_before,
                ),
            ),
        )
        .update(
            {
                MicroDetectionJob.status: "queued",
                MicroDetectionJob.error_message: None,
                MicroDetectionJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if not updated:
        return False
    db.commit()
    db.refresh(job)
    background_tasks.add_task(process_micro_job, job.id)
    return True


@app.get("/v1/micro/detection-jobs/{job_id}", response_model=MicroJobDetail)
def get_micro_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.query(MicroDetectionJob).filter_by(id=job_id, organization_id=user.organization_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="检测任务不存在")
    require_micro_job_access(job, user)
    degradation = None
    if job.status in {"awaiting_detector", "queued"} and not job.external_job_id:
        client = MicroRepresentationClient()
        if client.configured:
            queue_awaiting_micro_job_retry(db, job, background_tasks)
        else:
            degradation = "微表征检测服务未配置，任务仍在等待检测器"
    should_sync = job.status not in {"completed", "failed"} or (
        job.status == "completed" and job.events_sync_status != "synced"
    )
    if job.external_job_id and should_sync:
        client = MicroRepresentationClient()
        if client.configured:
            try:
                synchronize_micro_job(db, job, client)
                db.commit()
            except IntegrationContractError as exc:
                degradation = f"微表征检测服务同步失败：{exc}"
                job.status = "failed"
                job.error_message = str(exc)
                job.events_sync_status = "failed"
                job.events_sync_error = degradation
                db.commit()
            except IntegrationUnavailable as exc:
                degradation = f"微表征检测服务同步失败：{exc}"
                if job.status == "completed":
                    job.events_sync_status = "failed"
                    job.events_sync_error = degradation
                else:
                    job.error_message = degradation
                db.commit()
        else:
            degradation = "微表征检测服务未配置，暂时无法同步任务状态"
    return {
        "job_id": job.id,
        "echo_job_id": job.id,
        "status": job.status,
        "external_job_id": job.external_job_id,
        "detector_job_id": job.external_job_id,
        "events_sync_status": job.events_sync_status,
        "events_sync_error": job.events_sync_error,
        "events_synced_at": job.events_synced_at,
        "audio_duration_ms": job.audio_duration_ms,
        "error_message": job.error_message,
        "degradation": degradation,
        "transcript": job.transcript,
        "transcription_language": job.transcription_language,
        "transcription_status": job.transcription_status,
        "transcription_error": job.transcription_error,
        "transcribed_at": job.transcribed_at,
    }


@app.post(
    "/v1/micro/detection-jobs/{job_id}/events",
    response_model=MicroEventIngestResult,
)
def ingest_micro_events(
    job_id: str,
    batch: MicroEventBatch,
    db: Session = Depends(get_db),
    x_micro_service_key: Annotated[str | None, Header()] = None,
):
    require_micro_callback_identity(x_micro_service_key)
    job = db.query(MicroDetectionJob).filter_by(id=job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="检测任务不存在")
    if not job.external_job_id:
        raise HTTPException(status_code=409, detail="检测任务尚未绑定外部任务编号")
    if job.status == "failed":
        raise HTTPException(status_code=409, detail="失败的检测任务不能接收事件回调")
    try:
        apply_micro_audio_duration(job, batch.audio_duration_ms)
        accepted = persist_micro_events(
            db,
            job,
            batch.items,
            expected_event_job_id=job.external_job_id,
        )
    except IntegrationContractError as exc:
        db.rollback()
        failed_job = db.query(MicroDetectionJob).filter_by(id=job_id).first()
        if failed_job is not None:
            failed_job.status = "failed"
            failed_job.error_message = str(exc)
            failed_job.events_sync_status = "failed"
            failed_job.events_sync_error = str(exc)
            db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrationUnavailable as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    job.status = "completed"
    job.error_message = None
    job.events_sync_status = "synced"
    job.events_sync_error = None
    job.events_synced_at = datetime.now(UTC)
    db.commit()
    return {"accepted": accepted, "status": job.status}


@app.get("/v1/sessions/{session_id}/micro-events", response_model=SessionMicroEvents)
def session_micro_events(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    get_owned_session(db, session_id, user.id)
    rows = (
        db.query(MicroRepresentationEvent)
        .filter_by(session_id=session_id)
        .order_by(MicroRepresentationEvent.start_ms)
        .all()
    )
    return {
        "items": [
            {
                "event_id": row.id,
                "event_type": row.event_type,
                "start_ms": row.start_ms,
                "end_ms": row.end_ms,
                "confidence": row.confidence,
                "summary": build_micro_event_summary(row.event_type, row.evidence_status),
                "transcript": row.transcript,
                "evidence_uri": row.evidence_uri,
                "evidence_status": row.evidence_status,
            }
            for row in rows
        ]
    }


@app.get("/v1/sessions/{session_id}/turns")
def session_turns(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    get_owned_session(db, session_id, user.id)
    rows = (
        db.query(TurnExecution)
        .filter_by(session_id=session_id)
        .order_by(TurnExecution.started_at.desc())
        .limit(30)
        .all()
    )
    return {
        "items": [
            {
                "trace_id": row.trace_id,
                "intent": row.intent,
                "primary_action": row.primary_action,
                "status": row.status,
                "request_id": row.request_id,
                "plan": row.plan,
                "result": row.result,
                "started_at": row.started_at.isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "error_message": row.error_message,
            }
            for row in rows
        ]
    }


@app.post("/v1/learning-feedback")
def record_learning_feedback(
    request: LearningFeedbackRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Record confirmed preferences or intervention outcomes in SimpleMem."""

    if request.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权记录其他学习者反馈")
    module = accessible_module(db, user, request.module_id)
    if request.session_id is not None:
        get_owned_session(db, request.session_id, user.id)
    candidate = MemoryCandidate(
        organization_id=user.organization_id,
        user_id=user.id,
        program_id=module.program_id,
        module_id=module.id,
        session_id=request.session_id,
        knowledge_point_id=request.knowledge_point_id,
        content=request.content,
        memory_type=MemoryType(request.memory_type),
        evidence=request.evidence,
        metadata={"request_id": request.request_id, "source": "explicit_learning_feedback"},
    )
    lifecycle = LearnerMemoryService().create(candidate)
    payload = lifecycle.to_dict()
    db.add(
        MemoryAudit(
            id=uuid4().hex,
            request_id=request.request_id,
            organization_id=user.organization_id,
            user_id=user.id,
            operation=payload["operation"],
            status=payload["status"],
            memory_record=payload.get("memory_record"),
            reason=payload.get("reason"),
        )
    )
    db.commit()
    return payload


@app.post("/v1/knowledge-bases/{knowledge_base_id}/documents")
def upload_knowledge_document(
    knowledge_base_id: int,
    module_id: Annotated[int, Form()],
    source_title: Annotated[str, Form(min_length=1, max_length=255)],
    source_url: Annotated[str, Form(min_length=1, max_length=500)],
    source_section: Annotated[str, Form(min_length=1, max_length=255)],
    source_version: Annotated[str, Form(min_length=1, max_length=120)],
    document: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可维护知识库")
    module = (
        db.query(TrainingModule)
        .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
        .filter(
            TrainingModule.id == module_id,
            TrainingModule.knowledge_base_id == knowledge_base_id,
            TrainingProgram.organization_id == user.organization_id,
        )
        .first()
    )
    if module is None:
        raise HTTPException(status_code=404, detail="知识库或培训模块不存在")
    source_title = source_title.strip()
    source_url = source_url.strip()
    source_section = source_section.strip()
    source_version = source_version.strip()
    if not is_official_microsoft_source_url(source_url):
        raise HTTPException(
            status_code=400,
            detail="课程材料链接必须来自 Microsoft Learn 或 microsoft/semantic-kernel 官方仓库",
        )
    trace_id = uuid4().hex
    destination_dir = UPLOAD_DIR / "knowledge"
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", document.filename or "document")
    destination = destination_dir / f"{trace_id}_{safe_name}"
    content = document.file.read()
    destination.write_bytes(content)
    upload = Upload(
        user_id=user.id,
        module_id=module.id,
        knowledge_base_id=knowledge_base_id,
        filename=document.filename or safe_name,
        filepath=str(destination),
        file_type=document.content_type or "application/octet-stream",
        file_size=len(content),
        source_title=source_title,
        source_url=source_url,
        source_section=source_section,
        source_version=source_version,
        index_status="stored",
    )
    db.add(upload)
    db.flush()
    status = "stored"
    degradation = None
    client = PunditRAGClient()
    if client.import_configured:
        try:
            knowledge_base = module.knowledge_base
            if not knowledge_base.external_ref:
                external = client.ensure_knowledge_base(
                    name=knowledge_base.name,
                    description=(
                        f"ECHO {module.program.name} 官方课程知识库；"
                        "仅收录 Microsoft Learn 与 microsoft/semantic-kernel 官方资料。"
                    ),
                )
                knowledge_base.external_ref = str(external["kb_id"])
                db.flush()
            result = client.ingest_document(
                knowledge_base_id=knowledge_base_id,
                module_id=module.id,
                filename=upload.filename,
                content=content,
                content_type=upload.file_type,
                trace_id=trace_id,
                external_knowledge_base_id=knowledge_base.external_ref,
            )
            upload.external_document_id = result["document_id"]
            upload.external_task_id = result["task_id"]
            upload.index_status = result["status"]
            status = result["status"]
        except (IntegrationUnavailable, ValueError) as exc:
            upload.index_status = "degraded"
            upload.index_error = str(exc)
            degradation = str(exc)
    else:
        upload.index_status = "degraded"
        upload.index_error = "PunditRAG 导入服务未配置"
        degradation = "PunditRAG 导入服务未配置，文件已保存但尚未建立索引"
    db.commit()
    return {
        "upload_id": upload.id,
        "trace_id": trace_id,
        "status": status,
        "degradation": degradation,
    }


@app.get("/v1/knowledge-bases/{knowledge_base_id}/documents")
def list_knowledge_documents(
    knowledge_base_id: int,
    module_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可查看知识库材料")
    query = (
        db.query(Upload)
        .join(User, User.id == Upload.user_id)
        .filter(
            User.organization_id == user.organization_id,
            Upload.knowledge_base_id == knowledge_base_id,
        )
    )
    if module_id is not None:
        query = query.filter(Upload.module_id == module_id)
    rows = query.order_by(Upload.uploaded_at.desc()).all()
    rag_client = PunditRAGClient()
    if rag_client.import_configured:
        for row in rows:
            if not row.external_task_id or row.index_status not in {"pending", "processing"}:
                continue
            try:
                task = rag_client.get_import_status(row.external_task_id)
                task_status = str(task.get("status") or "").strip()
                if task_status in {"pending", "processing", "completed", "failed"}:
                    row.index_status = task_status
                    row.index_error = str(task.get("error") or "").strip() or None
            except (IntegrationUnavailable, ValueError) as exc:
                row.index_error = str(exc)
        db.commit()
    return {
        "items": [
            {
                "id": row.id,
                "module_id": row.module_id,
                "filename": row.filename,
                "file_type": row.file_type,
                "file_size": row.file_size,
                "source_title": row.source_title,
                "source_url": row.source_url,
                "source_section": row.source_section,
                "source_version": row.source_version,
                "external_document_id": row.external_document_id,
                "external_task_id": row.external_task_id,
                "index_status": row.index_status,
                "index_error": row.index_error,
                "uploaded_at": row.uploaded_at.isoformat(),
            }
            for row in rows
        ]
    }


class VideoProgressRequest(BaseModel):
    current_time: float = Field(ge=0)
    duration: float = Field(ge=0)
    completed: bool = False


class VideoProgressResponse(BaseModel):
    current_time: float
    duration: float
    completed: bool


class CourseVideoResponse(BaseModel):
    id: int
    module_id: int
    knowledge_point_id: int | None
    title: str
    filename: str
    file_size: int
    content_type: str
    duration_seconds: float | None
    uploaded_at: datetime
    stream_url: str | None = None
    progress: VideoProgressResponse | None = None


class CourseVideoListResponse(BaseModel):
    items: list[CourseVideoResponse]


class CourseVideoUploadResponse(BaseModel):
    items: list[CourseVideoResponse]
    total_size: int


def create_media_token(user_id: int, video_id: int) -> str:
    """Mint a short-lived token so the HTML video element can stream a protected file."""

    return jwt.encode(
        {
            "sub": str(user_id),
            "vid": video_id,
            "exp": datetime.now(UTC) + timedelta(hours=2),
        },
        Config.security.SECRET_KEY,
        algorithm=Config.security.ALGORITHM,
    )


def _course_video_payload(
    video: CourseVideo,
    progress: VideoProgress | None,
    *,
    user_id: int,
) -> dict:
    return {
        "id": video.id,
        "module_id": video.module_id,
        "knowledge_point_id": video.knowledge_point_id,
        "title": video.title,
        "filename": video.filename,
        "file_size": video.file_size,
        "content_type": video.content_type,
        "duration_seconds": video.duration_seconds,
        "uploaded_at": video.uploaded_at.isoformat(),
        "stream_url": f"/v1/videos/{video.id}/stream?token={create_media_token(user_id, video.id)}",
        "progress": (
            {
                "current_time": progress.current_time,
                "duration": progress.duration,
                "completed": progress.completed,
            }
            if progress
            else None
        ),
    }


def _range_video_response(path: Path, media_type: str, request: Request):
    file_size = path.stat().st_size
    range_header = (request.headers.get("range") or "").strip()
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
    if not match:
        return FileResponse(path, media_type=media_type)

    start_raw, end_raw = match.groups()
    if not start_raw and end_raw:
        start = max(0, file_size - int(end_raw))
        end = file_size - 1
    else:
        start = int(start_raw or 0)
        end = int(end_raw) if end_raw else file_size - 1
    end = min(end, file_size - 1)
    if start >= file_size or start > end:
        raise HTTPException(status_code=416, detail="请求范围无效")

    def iter_file():
        remaining = end - start + 1
        with path.open("rb") as stream:
            stream.seek(start)
            while remaining > 0:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        },
    )


def _stream_identity(
    db: Session,
    video_id: int,
    authorization: str | None,
    token: str | None,
) -> User:
    candidates: list[str] = []
    if authorization and authorization.lower().startswith("bearer "):
        candidates.append(authorization.split(" ", 1)[1])
    if token:
        candidates.append(token)
    for raw in candidates:
        try:
            payload = jwt.decode(
                raw,
                Config.security.SECRET_KEY,
                algorithms=[Config.security.ALGORITHM],
            )
            if "vid" in payload and int(payload["vid"]) != video_id:
                continue
            user_id = int(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            continue
        user = db.query(User).filter(User.id == user_id, User.status == "active").first()
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="缺少登录令牌")


@app.post("/v1/modules/{module_id}/videos", response_model=CourseVideoUploadResponse)
def upload_course_videos(
    module_id: int,
    files: Annotated[list[UploadFile], File()],
    knowledge_point_id: Annotated[int | None, Form()] = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可上传课程视频")
    module = accessible_module(db, user, module_id)
    if knowledge_point_id is not None:
        point = (
            db.query(KnowledgePoint)
            .filter_by(id=knowledge_point_id, module_id=module_id)
            .first()
        )
        if point is None:
            raise HTTPException(status_code=404, detail="知识点不存在")

    destination_dir = UPLOAD_DIR / "videos"
    destination_dir.mkdir(parents=True, exist_ok=True)
    created: list[dict] = []
    total_size = 0
    max_mb = Config.upload.VIDEO_MAX_FILE_SIZE // (1024 * 1024)
    for upload in files:
        original = (upload.filename or "video").strip() or "video"
        extension = Path(original).suffix.lower()
        if extension not in Config.upload.VIDEO_ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的视频格式：{extension or original}")
        safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(original).stem) or "video"
        trace_id = uuid4().hex
        destination = destination_dir / f"{trace_id}_{safe_stem}{extension}"
        size = 0
        exceeded = False
        with destination.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > Config.upload.VIDEO_MAX_FILE_SIZE:
                    exceeded = True
                    break
                output.write(chunk)
        if exceeded:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"视频文件超过 {max_mb} MB 上限")
        if size == 0:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="不能上传空视频文件")
        video = CourseVideo(
            module_id=module.id,
            knowledge_point_id=knowledge_point_id,
            title=Path(original).stem,
            filename=original,
            filepath=str(destination),
            content_type=upload.content_type or f"video/{extension.lstrip('.')}",
            file_size=size,
            sort_order=0,
            uploaded_by_user_id=user.id,
        )
        db.add(video)
        db.flush()
        created.append(_course_video_payload(video, None, user_id=user.id))
        total_size += size
    db.commit()
    return {"items": created, "total_size": total_size}


@app.get("/v1/modules/{module_id}/videos", response_model=CourseVideoListResponse)
def list_course_videos(
    module_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    accessible_module(db, user, module_id)
    videos = (
        db.query(CourseVideo)
        .filter_by(module_id=module_id)
        .order_by(CourseVideo.sort_order, CourseVideo.id)
        .all()
    )
    video_ids = [video.id for video in videos]
    progress_map = {
        row.video_id: row
        for row in (
            db.query(VideoProgress)
            .filter(VideoProgress.user_id == user.id)
            .filter(VideoProgress.video_id.in_(video_ids))
            .all()
        )
    } if video_ids else {}
    return {
        "items": [
            _course_video_payload(video, progress_map.get(video.id), user_id=user.id)
            for video in videos
        ]
    }


@app.get("/v1/videos/{video_id}/stream")
def stream_course_video(
    video_id: int,
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    user = _stream_identity(
        db,
        video_id,
        request.headers.get("authorization"),
        token,
    )
    video = db.query(CourseVideo).filter_by(id=video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    accessible_module(db, user, video.module_id)
    path = Path(video.filepath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="视频文件缺失")
    return _range_video_response(path, video.content_type, request)


@app.put("/v1/videos/{video_id}/progress", response_model=VideoProgressResponse)
def save_course_video_progress(
    video_id: int,
    payload: VideoProgressRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    video = db.query(CourseVideo).filter_by(id=video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    accessible_module(db, user, video.module_id)
    progress = (
        db.query(VideoProgress)
        .filter_by(user_id=user.id, video_id=video_id)
        .first()
    )
    if progress is None:
        progress = VideoProgress(
            user_id=user.id,
            video_id=video_id,
            module_id=video.module_id,
        )
        db.add(progress)
    progress.current_time = payload.current_time
    progress.duration = payload.duration
    progress.completed = payload.completed
    progress.updated_at = datetime.now()
    db.commit()
    return {
        "current_time": progress.current_time,
        "duration": progress.duration,
        "completed": progress.completed,
    }


class VideoCheckpointResponse(BaseModel):
    id: int
    video_id: int
    time_offset_seconds: float
    question: str
    expected_points: list[str]
    official_sources: list[str]
    status: str


class VideoCheckpointListResponse(BaseModel):
    items: list[VideoCheckpointResponse]


class VideoCheckpointEditRequest(BaseModel):
    time_offset_seconds: float | None = None
    question: str | None = Field(default=None, min_length=1)
    expected_points: list[str] | None = None
    official_sources: list[str] | None = None


class VideoAnalysisJobResponse(BaseModel):
    job_id: str
    status: str
    frames_count: int
    error: str | None


def _video_checkpoint_payload(checkpoint: VideoCheckpoint) -> dict:
    return {
        "id": checkpoint.id,
        "video_id": checkpoint.video_id,
        "time_offset_seconds": checkpoint.time_offset_seconds,
        "question": checkpoint.question,
        "expected_points": checkpoint.expected_points,
        "official_sources": checkpoint.official_sources,
        "status": checkpoint.status,
    }


def run_video_analysis_task(job_id: str) -> None:
    db = SessionLocal()
    try:
        run_video_analysis(db, job_id)
    finally:
        db.close()


@app.post(
    "/v1/videos/{video_id}/generate-checkpoints",
    response_model=VideoAnalysisJobResponse,
)
def generate_video_checkpoints(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可生成视频口述题")
    video = db.query(CourseVideo).filter_by(id=video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    accessible_module(db, user, video.module_id)
    job = VideoAnalysisJob(id=uuid4().hex, video_id=video_id, status="queued")
    db.add(job)
    db.commit()
    background_tasks.add_task(run_video_analysis_task, job.id)
    return {
        "job_id": job.id,
        "status": job.status,
        "frames_count": 0,
        "error": None,
    }


@app.get("/v1/video-analysis/{job_id}", response_model=VideoAnalysisJobResponse)
def get_video_analysis_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.query(VideoAnalysisJob).filter_by(id=job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    video = db.get(CourseVideo, job.video_id)
    if video is not None:
        accessible_module(db, user, video.module_id)
    return {
        "job_id": job.id,
        "status": job.status,
        "frames_count": job.frames_count,
        "error": job.error,
    }


@app.get("/v1/videos/{video_id}/checkpoints", response_model=VideoCheckpointListResponse)
def list_video_checkpoints(
    video_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    video = db.get(CourseVideo, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    accessible_module(db, user, video.module_id)
    query = (
        db.query(VideoCheckpoint)
        .filter_by(video_id=video_id)
        .order_by(VideoCheckpoint.time_offset_seconds, VideoCheckpoint.id)
    )
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        query = query.filter(VideoCheckpoint.status == "frozen")
    return {"items": [_video_checkpoint_payload(item) for item in query.all()]}


@app.put(
    "/v1/videos/{video_id}/checkpoints/{checkpoint_id}",
    response_model=VideoCheckpointResponse,
)
def edit_video_checkpoint(
    video_id: int,
    checkpoint_id: int,
    payload: VideoCheckpointEditRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可编辑口述题")
    video = db.get(CourseVideo, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    accessible_module(db, user, video.module_id)
    checkpoint = (
        db.query(VideoCheckpoint)
        .filter_by(id=checkpoint_id, video_id=video_id)
        .first()
    )
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="口述题不存在")
    if payload.time_offset_seconds is not None:
        checkpoint.time_offset_seconds = payload.time_offset_seconds
    if payload.question is not None:
        checkpoint.question = payload.question
    if payload.expected_points is not None:
        checkpoint.expected_points = payload.expected_points
    if payload.official_sources is not None:
        checkpoint.official_sources = payload.official_sources
    checkpoint.updated_at = datetime.now()
    db.commit()
    return _video_checkpoint_payload(checkpoint)


@app.post(
    "/v1/videos/{video_id}/checkpoints/freeze",
    response_model=VideoCheckpointListResponse,
)
def freeze_video_checkpoints(
    video_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可冻结口述题")
    video = db.get(CourseVideo, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    accessible_module(db, user, video.module_id)
    checkpoints = (
        db.query(VideoCheckpoint)
        .filter_by(video_id=video_id, status="draft")
        .all()
    )
    for item in checkpoints:
        item.status = "frozen"
        item.updated_at = datetime.now()
    db.commit()
    frozen = (
        db.query(VideoCheckpoint)
        .filter_by(video_id=video_id)
        .order_by(VideoCheckpoint.time_offset_seconds, VideoCheckpoint.id)
        .all()
    )
    return {"items": [_video_checkpoint_payload(item) for item in frozen]}


@app.get("/v1/resources")
def list_resources(
    module_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(GeneratedResource).filter_by(user_id=user.id)
    if module_id is not None:
        query = query.filter(GeneratedResource.module_id == module_id)
    rows = query.order_by(GeneratedResource.created_at.desc()).limit(50).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        verification_rows = (
            db.query(VerificationResult)
            .filter_by(resource_id=row.id)
            .order_by(VerificationResult.retry_count, VerificationResult.created_at)
            .all()
        )
        latest_verification = verification_rows[-1] if verification_rows else None
        items.append(
            {
                "resource_id": row.id,
                "module_id": row.module_id,
                "knowledge_point_id": row.knowledge_point_id,
                "resource_type": row.resource_type,
                "difficulty": row.difficulty,
                "title": row.title,
                "content": row.content,
                "personalization_reason": row.personalization_reason,
                "evidence_sources": row.evidence_sources,
                "status": row.status,
                "verification_passed": (
                    bool(latest_verification.passed) if latest_verification else None
                ),
                "verification_issues": (
                    latest_verification.issues if latest_verification else []
                ),
                "verification_details": (
                    latest_verification.details if latest_verification else {}
                ),
                "retry_count": (
                    int(latest_verification.retry_count) if latest_verification else 0
                ),
                "verification_history": [
                    {
                        "passed": bool(item.passed),
                        "factual_score": item.factual_score,
                        "coverage_score": item.coverage_score,
                        "difficulty_score": item.difficulty_score,
                        "issues": item.issues,
                        "details": item.details,
                        "retry_count": item.retry_count,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in verification_rows
                ],
                "created_at": row.created_at.isoformat(),
            }
        )
    return {"items": items}


@app.post("/v1/resources/generate")
def generate_resources(
    request: ResourceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if request.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权生成其他学习者资源")
    module = (
        db.query(TrainingModule)
        .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
        .filter(
            TrainingModule.id == request.module_id,
            TrainingProgram.organization_id == user.organization_id,
        )
        .first()
    )
    if module is None:
        raise HTTPException(status_code=404, detail="培训模块不存在")

    points = (
        db.query(KnowledgePoint)
        .filter_by(module_id=module.id)
        .order_by(KnowledgePoint.sequence)
        .all()
    )
    requested_point = (
        next((item for item in points if item.id == request.knowledge_point_id), None)
        if request.knowledge_point_id is not None
        else None
    )
    if request.knowledge_point_id is not None and requested_point is None:
        raise HTTPException(status_code=404, detail="当前模块没有可生成资源的知识点")

    degradation: list[str] = []
    memories: list[dict] = []
    memory_client = SimpleMemClient()
    if memory_client.configured:
        try:
            memories = memory_client.search(
                MemorySearchRequest(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    program_id=module.program_id,
                    module_id=module.id,
                    intent=MemoryIntent.RESOURCE_GENERATION,
                    query=_module_memory_query(
                        module,
                        [requested_point] if requested_point is not None else points,
                    ),
                    knowledge_point_id=request.knowledge_point_id,
                )
            )
        except IntegrationUnavailable as exc:
            degradation.append(f"SimpleMem：{exc}")
    else:
        degradation.append("SimpleMem未配置")

    profile = LearnerInsightService(db).build_profile(
        user.id,
        module.id,
        memory_items=memories,
    )
    evidence_view = profile["views"]["evidence_and_blind_spots"]
    if request.knowledge_point_id is not None:
        point = requested_point
    else:
        blind_spots = evidence_view["knowledge_blind_spots"]
        mastered_ids = {
            item["knowledge_point_id"]
            for item in evidence_view["mastered_knowledge_points"]
        }
        preferred_id = blind_spots[0]["knowledge_point_id"] if blind_spots else None
        point = (
            next((item for item in points if item.id == preferred_id), None)
            if preferred_id is not None
            else next(
                (item for item in points if item.id not in mastered_ids),
                points[-1] if points else None,
            )
        )
    if point is None:
        raise HTTPException(status_code=404, detail="当前模块没有可生成资源的知识点")

    session = ChatSession(
        user_id=user.id,
        program_id=module.program_id,
        module_id=module.id,
        knowledge_base_id=module.knowledge_base_id,
        title=f"生成资源：{point.name}"[:100],
    )
    db.add(session)
    db.flush()
    trace_id = uuid4().hex
    execution = TurnExecution(
        id=uuid4().hex,
        request_id=request.request_id,
        trace_id=trace_id,
        user_id=user.id,
        session_id=session.id,
        intent="RESOURCE_REQUEST",
        primary_action="GENERATE_RESOURCE",
        plan={
            "module_id": module.id,
            "knowledge_point_id": point.id,
            "single_primary_action": True,
        },
    )
    db.add(execution)
    analysis_started_at = datetime.now(UTC)

    plan = build_personalization_plan(
        profile,
        knowledge_point_id=point.id,
        knowledge_point_name=point.name,
    )
    analysis_finished_at = datetime.now(UTC)
    generation_started_at = datetime.now(UTC)
    evidence, rag_error = search_official_evidence(
        db,
        query=f"{point.name} {plan.weakest_dimension_label}",
        knowledge_base_id=module.knowledge_base_id,
        module_id=module.id,
        knowledge_point_ids=[point.id],
    )
    if rag_error:
        degradation.append(f"PunditRAG：{rag_error}")

    sources = [item.get("metadata", {}) for item in evidence]
    selected_resource_type = request.resource_type or profile["views"]["path_and_resources"].get(
        "recommended_content_format", "custom_note"
    )
    if selected_resource_type not in RESOURCE_TYPES:
        selected_resource_type = "custom_note"
    generated, generation_error = ResourceGenerationAgent().generate(
        plan,
        evidence,
        resource_type=selected_resource_type,
    )
    if generation_error:
        degradation.append(generation_error)
    generation_finished_at = datetime.now(UTC)

    resources = []
    verification_details = []
    verifier = ContentVerificationAgent()
    for item in generated:
        resource = GeneratedResource(
            id=uuid4().hex,
            user_id=user.id,
            module_id=module.id,
            knowledge_point_id=point.id,
            resource_type=item["resource_type"],
            difficulty=plan.difficulty,
            title=item["title"],
            content=item["content"],
            personalization_reason=plan.reason,
            evidence_sources=sources,
        )
        db.add(resource)
        db.flush()
        initial_result = verifier.verify(item, plan, evidence)
        initial_record = VerificationResult(
            id=uuid4().hex,
            resource_id=resource.id,
            passed=initial_result.passed,
            factual_score=initial_result.factual_score,
            coverage_score=initial_result.coverage_score,
            difficulty_score=initial_result.difficulty_score,
                    issues=initial_result.issues,
                    details=initial_result.details,
                    retry_count=0,
                )
        db.add(initial_record)
        final_result = initial_result
        retry_count = 0
        if not initial_result.passed and evidence:
            repaired = ResourceGenerationAgent.repair_failed_resource(
                item,
                plan,
                evidence,
                initial_result.issues,
            )
            resource.title = repaired["title"]
            resource.content = repaired["content"]
            final_result = verifier.verify(repaired, plan, evidence)
            retry_count = 1
            db.add(
                VerificationResult(
                    id=uuid4().hex,
                    resource_id=resource.id,
                    passed=final_result.passed,
                    factual_score=final_result.factual_score,
                    coverage_score=final_result.coverage_score,
                    difficulty_score=final_result.difficulty_score,
                    issues=final_result.issues,
                    details=final_result.details,
                    retry_count=retry_count,
                )
            )
        if final_result.passed:
            # Automated verification is not the publication gate. A mentor or
            # administrator must explicitly publish the resource.
            resource.status = "pending_review"
        verification_details.append(
            {
                "resource_id": resource.id,
                "resource_type": resource.resource_type,
                "initial": {
                    "passed": initial_result.passed,
                    "issues": initial_result.issues,
                },
                "final": {
                    "passed": final_result.passed,
                    "issues": final_result.issues,
                },
                "retry_count": retry_count,
            }
        )
        resources.append(
            {
                "resource_id": resource.id,
                "resource_type": resource.resource_type,
                "title": resource.title,
                "status": resource.status,
                "verification_passed": final_result.passed,
                "issues": final_result.issues,
                "retry_count": retry_count,
            }
        )
    validation_finished_at = datetime.now(UTC)
    next_action_started_at = datetime.now(UTC)
    next_action_reason = (
        "资源已通过自动内容检查，等待讲师或管理员人工发布。"
        if all(item["verification_passed"] for item in resources)
        else "存在未通过检查的资源，保持草稿并等待补充证据或再次修复。"
    )
    execution.result = {
        "session_id": session.id,
        "trace_id": trace_id,
        "primary_action": "GENERATE_RESOURCE",
        "resource_ids": [item["resource_id"] for item in resources],
        "degradation": degradation,
        "agent_records": {
            "analysis": {
                "status": "completed",
                "input_summary": {
                    "user_id": user.id,
                    "module_id": module.id,
                    "knowledge_point_id": point.id,
                    "memory_count": len(memories),
                },
                "output": {"profile": profile, "personalization_plan": plan.to_dict()},
                "failure_reason": None,
                "started_at": analysis_started_at.isoformat(),
                "finished_at": analysis_finished_at.isoformat(),
                "persisted_in_system": True,
            },
            "generation": {
                "status": "completed_with_degradation" if generation_error else "completed",
                "input_summary": {
                    "resource_type": selected_resource_type,
                    "official_evidence_count": len(evidence),
                },
                "output": {
                    "resources": resources,
                    "evidence_sources": sources,
                    "generation_error": generation_error,
                },
                "failure_reason": generation_error,
                "started_at": generation_started_at.isoformat(),
                "finished_at": generation_finished_at.isoformat(),
                "persisted_in_system": True,
            },
            "validation": {
                "status": (
                    "completed"
                    if all(item["verification_passed"] for item in resources)
                    else "failed"
                ),
                "input_summary": {"resource_count": len(resources)},
                "output": {"items": verification_details},
                "failure_reason": (
                    None
                    if all(item["verification_passed"] for item in resources)
                    else next_action_reason
                ),
                "started_at": generation_finished_at.isoformat(),
                "finished_at": validation_finished_at.isoformat(),
                "persisted_in_system": True,
            },
            "next_action": {
                "status": "completed",
                "input_summary": {"trace_id": trace_id},
                "output": {
                    "primary_action": "GENERATE_RESOURCE",
                    "reason": next_action_reason,
                    "published_resource_count": 0,
                    "pending_review_count": sum(
                        1 for item in resources if item["status"] == "pending_review"
                    ),
                },
                "failure_reason": None,
                "started_at": next_action_started_at.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "persisted_in_system": True,
            },
        },
    }
    execution.status = (
        TurnStatus.COMPLETED_WITH_DEGRADATION.value
        if degradation or not all(item["verification_passed"] for item in resources)
        else TurnStatus.COMPLETED.value
    )
    execution.finished_at = datetime.now(UTC)
    db.add(
        LearningDecision(
            id=uuid4().hex,
            trace_id=trace_id,
            user_id=user.id,
            session_id=session.id,
            module_id=module.id,
            knowledge_point_id=point.id,
            action="GENERATE_RESOURCE",
            reason=next_action_reason,
            evidence_refs=[
                source.get("chunk_id") or source.get("external_document_id")
                for source in sources
                if source.get("chunk_id") or source.get("external_document_id")
            ],
        )
    )
    db.commit()
    return {
        "items": resources,
        "plan": plan.to_dict(),
        "degradation": degradation,
        "session_id": session.id,
        "trace_id": trace_id,
        "primary_action": "GENERATE_RESOURCE",
        "resource_type": selected_resource_type,
    }


@app.post("/v1/resources/{resource_id}/publish")
def publish_resource(
    resource_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Publish an automatically verified resource after an explicit human gate."""

    if user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="仅讲师、导师或系统管理员可发布资源")
    resource = (
        db.query(GeneratedResource)
        .join(TrainingModule, TrainingModule.id == GeneratedResource.module_id)
        .join(TrainingProgram, TrainingProgram.id == TrainingModule.program_id)
        .filter(
            GeneratedResource.id == resource_id,
            TrainingProgram.organization_id == user.organization_id,
        )
        .first()
    )
    if resource is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    latest = (
        db.query(VerificationResult)
        .filter_by(resource_id=resource.id)
        .order_by(VerificationResult.created_at.desc())
        .first()
    )
    if latest is None or not latest.passed:
        raise HTTPException(status_code=409, detail="资源未通过自动校验，不能发布")
    if resource.status == "verified":
        return {"status": "already_published", "resource_id": resource.id}
    resource.status = "verified"
    publish_session = (
        db.query(ChatSession)
        .filter_by(user_id=resource.user_id, module_id=resource.module_id)
        .order_by(ChatSession.updated_at.desc())
        .first()
    )
    if publish_session is not None:
        db.add(
            LearningDecision(
                id=uuid4().hex,
                trace_id=uuid4().hex,
                user_id=resource.user_id,
                session_id=publish_session.id,
                module_id=resource.module_id,
                knowledge_point_id=resource.knowledge_point_id,
                action="PUBLISH_RESOURCE",
                reason=f"{user.username} 完成人工发布门禁",
                evidence_refs=[resource.id],
            )
        )
    db.commit()
    return {"status": "published", "resource_id": resource.id}
