"""ECHO competition API: enterprise training, one action per turn."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlparse
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
    GeneratedResource,
    KnowledgeBase,
    KnowledgePoint,
    LearnerAbility,
    LearningDecision,
    Message,
    MicroDetectionJob,
    MicroRepresentationEvent,
    Organization,
    Quiz,
    SessionLocal,
    TrainingModule,
    TrainingProgram,
    TurnExecution,
    TurnStatus,
    Upload,
    User,
    UserRole,
    VerificationResult,
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
from integrations.contracts import (
    MemoryIntent,
    MemorySearchRequest,
    MicroDetectionRequest,
    MicroSource,
)
from integrations.contracts import (
    MicroRepresentationEvent as MicroEventContract,
)
from integrations.http_client import IntegrationUnavailable
from integrations.micro_representation import MicroRepresentationClient
from integrations.micro_sync import (
    apply_micro_job_creation_result,
    persist_micro_events,
    synchronize_micro_job,
)
from integrations.punditrag import PunditRAGClient
from integrations.simplemem import SimpleMemClient
from MIRT.analysis_agent import LearnerInsightService
from MIRT.mirt_daily_stats import build_daily_series
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from Quiz.AdaptiveEngine import AdaptiveEngine
from Quiz.grading import grade_quiz_answer
from Quiz.import_from_document import (
    SUPPORTED_IMPORT_EXTENSIONS,
    extract_quiz_preview,
    validate_quiz_item,
)
from resource_generation import (
    ContentVerificationAgent,
    ResourceGenerationAgent,
    build_personalization_plan,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

API_DIR = Path(__file__).resolve().parent
WEB_DIR = API_DIR / "web"
UPLOAD_DIR = Path(Config.upload.UPLOAD_DIR).resolve()
MICRO_AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".ogg", ".wav", ".webm"}
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
    requested_module_id: int | None = None


class QuizSubmit(BaseModel):
    user_id: int
    question_id: int
    answer: str = Field(min_length=1, max_length=10000)
    attempt_id: str = Field(default_factory=lambda: uuid4().hex, max_length=64)
    session_id: int | None = None
    stage: str | None = None


class ResourceRequest(BaseModel):
    user_id: int
    module_id: int
    knowledge_point_id: int | None = None


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


class MentorBatchResult(BaseModel):
    job_ids: list[str]
    accepted: int


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


@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "echo-competition",
        "version": Config.app.APP_VERSION,
        "rag_provider": "punditrag",
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


def safe_retrieve(plan, query: str) -> tuple[list[dict], str | None]:
    if not plan.use_rag:
        return [], None
    client = PunditRAGClient()
    if not client.configured:
        return [], "PunditRAG未配置"
    try:
        return (
            client.search(
                query,
                plan.context.knowledge_base_id,
                plan.context.module_id,
                trace_id=plan.trace_id,
            ),
            None,
        )
    except IntegrationUnavailable as exc:
        return [], str(exc)


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


def extract_answer(text: str) -> str:
    normalized = re.sub(r"^(答案是|我的答案是|我选|提交答案)[:：]?", "", text.strip())
    return normalized.strip()


def requested_quiz_purpose(text: str) -> Literal[
    "pretest", "posttest", "stage_test", "practice"
]:
    normalized = TurnOrchestrator.normalize(text)
    if "前测" in normalized:
        return "pretest"
    if "后测" in normalized:
        return "posttest"
    if "练习" in normalized:
        return "practice"
    return "stage_test"


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
        purpose = requested_quiz_purpose(request.user_input)
        quiz = AdaptiveEngine(db).get_adaptive_question(
            user.id,
            session.module_id,
            purpose=purpose,
        )
        if quiz is None:
            purpose_label = {
                "pretest": "前测",
                "posttest": "后测",
                "stage_test": "阶段测验",
                "practice": "练习",
            }[purpose]
            content = f"当前模块还没有可用的{purpose_label}题目，请先导入对应用途的固定题库。"
        else:
            session.active_quiz_id = quiz.id
            payload["quiz"] = public_quiz_payload(quiz)
            content = quiz.content
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
        payload["assessment"] = {
            "is_correct": grade.is_correct,
            "score": grade.score,
            "grading_mode": grade.grading_mode,
            "counts_for_mirt": quiz.counts_for_mirt,
            "updated": updated,
            "ability": {"U": ability.U, "A": ability.A, "R": ability.R},
        }
        if grade.is_correct:
            content = (
                "回答正确，能力画像已更新。"
                if quiz.counts_for_mirt
                else "回答正确，本次结果已记录，不更新能力画像。"
            )
        else:
            content = f"本题需要巩固。参考要点：{quiz.answer}"
    elif action is PrimaryAction.LEARNING_DIALOGUE:
        evidence, rag_error = safe_retrieve(plan, request.user_input)
        memories, memory_error = safe_memories(plan, user, request.user_input)
        if rag_error:
            degradation.append(rag_error)
        if memory_error:
            degradation.append(memory_error)
        content = StudentHelper().respond(
            user_input=request.user_input,
            module_name=session.module.name,
            echo_state=session.echo_state,
            evidence=evidence,
            memories=memories,
        )
        fsm = EchoFSM(session.echo_stage_counts)
        proposed = "C" if session.echo_state == "E" else session.echo_state
        transition = fsm.update(request.user_input, proposed, session.echo_state)
        session.echo_state = transition["normalized_state"]
        session.echo_stage_counts = transition["rounds"]
        payload["echo_transition"] = transition
        payload["evidence"] = evidence
    elif action is PrimaryAction.GENERAL_RESPONSE:
        content = "收到。当前学习状态保持不变，可以继续提问或请求阶段测验。"
    else:
        content = "本轮没有执行学习动作，请提供具体问题、测验请求或模块切换目标。"

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
    execution.status = TurnStatus.COMPLETED.value
    execution.result = result
    execution.finished_at = datetime.now()
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
    if existing and existing.status == TurnStatus.COMPLETED.value:
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


@app.get("/v1/quizzes/next")
def next_fixed_quiz(
    module_id: int,
    purpose: Literal["pretest", "posttest", "stage_test", "practice"] = "stage_test",
    knowledge_point_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    accessible_module(db, user, module_id)
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
    if client.configured:
        try:
            memories = client.search(
                MemorySearchRequest(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    program_id=module.program_id,
                    module_id=module.id,
                    intent=MemoryIntent.LEARNER_DIAGNOSIS,
                    query="当前模块相关的误区、学习偏好和历史干预效果",
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


def submit_micro_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(MicroDetectionJob).filter_by(id=job_id).first()
        if job is None:
            return
        client = MicroRepresentationClient()
        if not client.configured:
            job.status = "awaiting_detector"
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
            except IntegrationUnavailable as exc:
                job.events_sync_status = "failed"
                job.events_sync_error = str(exc)
        except (IntegrationUnavailable, ValueError) as exc:
            job.status = "failed"
            job.error_message = str(exc)
        db.commit()
    finally:
        db.close()


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
) -> tuple[MicroDetectionJob, bool, int]:
    if db.query(TrainingModule.id).filter_by(id=module_id).first() is None:
        raise HTTPException(status_code=404, detail="培训模块不存在")
    job_id = uuid4().hex
    destination, audio_sha256, audio_size = save_audio_file(job_id, audio)
    existing = (
        db.query(MicroDetectionJob)
        .filter_by(
            organization_id=user.organization_id,
            created_by_user_id=user.id,
            learner_id=learner_id,
            session_id=session_id,
            module_id=module_id,
            knowledge_point_id=knowledge_point_id,
            source_type=source_type.value,
            audio_sha256=audio_sha256,
        )
        .order_by(MicroDetectionJob.created_at)
        .first()
    )
    if existing is not None:
        destination.unlink(missing_ok=True)
        return existing, False, audio_size
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
    )
    db.add(job)
    db.flush()
    return job, True, audio_size


@app.post("/v1/micro/detection-jobs")
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
    if source_type is MicroSource.LEARNER_VOICE:
        learner_id = user.id
    elif user.role not in {UserRole.MENTOR.value, UserRole.SYSTEM_ADMIN.value}:
        raise HTTPException(status_code=403, detail="只有讲师/导师可以上传培训录音")
    job, is_created, _ = create_micro_job_record(
        db,
        user=user,
        module_id=module_id,
        source_type=source_type,
        audio=audio,
        learner_id=learner_id,
        session_id=session_id,
        knowledge_point_id=knowledge_point_id,
    )
    db.commit()
    if is_created:
        background_tasks.add_task(submit_micro_job, job.id)
    return {"job_id": job.id, "status": job.status, "source_type": job.source_type}


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
    bound_learner_id = learner_id if speaker_mapping_confirmed else None
    if not audio_files:
        raise HTTPException(status_code=422, detail="at least one audio file is required")
    if len(audio_files) > 20:
        raise HTTPException(status_code=413, detail="mentor batch exceeds 20 files")
    jobs: list[MicroDetectionJob] = []
    created_jobs: list[MicroDetectionJob] = []
    total_size = 0
    try:
        for audio in audio_files:
            job, is_created, audio_size = create_micro_job_record(
                db,
                user=user,
                module_id=module_id,
                source_type=MicroSource.MENTOR_RECORDING,
                audio=audio,
                learner_id=bound_learner_id,
                session_id=session_id,
                knowledge_point_id=knowledge_point_id,
            )
            jobs.append(job)
            total_size += audio_size
            if is_created:
                created_jobs.append(job)
            if total_size > Config.upload.MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="mentor batch exceeds total size limit")
    except (HTTPException, OSError):
        db.rollback()
        for created_job in created_jobs:
            parsed = urlparse(created_job.audio_uri)
            path = Path(url2pathname(unquote(parsed.path)))
            if os.name == "nt" and str(path).startswith("/"):
                path = Path(str(path)[1:])
            path.unlink(missing_ok=True)
        raise
    db.commit()
    for job in created_jobs:
        background_tasks.add_task(submit_micro_job, job.id)
    return MentorBatchResult(job_ids=[job.id for job in jobs], accepted=len(jobs))


@app.get("/v1/micro/detection-jobs/{job_id}")
def get_micro_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.query(MicroDetectionJob).filter_by(id=job_id, organization_id=user.organization_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="检测任务不存在")
    require_micro_job_access(job, user)
    degradation = None
    should_sync = job.status not in {"completed", "failed"} or (
        job.status == "completed" and job.events_sync_status != "synced"
    )
    if job.external_job_id and should_sync:
        client = MicroRepresentationClient()
        if client.configured:
            try:
                synchronize_micro_job(db, job, client)
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
        "error_message": job.error_message,
        "degradation": degradation,
    }


@app.post("/v1/micro/detection-jobs/{job_id}/events")
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
    try:
        accepted = persist_micro_events(
            db,
            job,
            batch.items,
            expected_event_job_id=job.external_job_id or "",
        )
    except IntegrationUnavailable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job.status = "completed"
    job.events_sync_status = "synced"
    job.events_sync_error = None
    job.events_synced_at = datetime.now(UTC)
    db.commit()
    return {"accepted": accepted, "status": job.status}


@app.get("/v1/sessions/{session_id}/micro-events")
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
                "started_at": row.started_at.isoformat(),
                "error_message": row.error_message,
            }
            for row in rows
        ]
    }


@app.post("/v1/knowledge-bases/{knowledge_base_id}/documents")
def upload_knowledge_document(
    knowledge_base_id: int,
    module_id: Annotated[int, Form()],
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
    )
    db.add(upload)
    db.flush()
    status = "stored"
    degradation = None
    client = PunditRAGClient()
    if client.configured:
        try:
            client.ingest_document(
                knowledge_base_id=knowledge_base_id,
                module_id=module.id,
                filename=upload.filename,
                content=content,
                content_type=upload.file_type,
                trace_id=trace_id,
            )
            status = "indexed"
        except IntegrationUnavailable as exc:
            degradation = str(exc)
    else:
        degradation = "PunditRAG 未配置，文件已保存但尚未建立索引"
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
    query = db.query(Upload).filter_by(
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
    )
    if module_id is not None:
        query = query.filter(Upload.module_id == module_id)
    rows = query.order_by(Upload.uploaded_at.desc()).all()
    return {
        "items": [
            {
                "id": row.id,
                "module_id": row.module_id,
                "filename": row.filename,
                "file_type": row.file_type,
                "file_size": row.file_size,
                "uploaded_at": row.uploaded_at.isoformat(),
            }
            for row in rows
        ]
    }


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
    return {
        "items": [
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
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


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
                    query="当前模块的稳定误区、学习偏好和有效干预方式",
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
        point = (
            db.query(KnowledgePoint)
            .filter_by(id=request.knowledge_point_id, module_id=module.id)
            .first()
        )
    else:
        blind_spots = evidence_view["knowledge_blind_spots"]
        mastered_ids = {
            item["knowledge_point_id"]
            for item in evidence_view["mastered_knowledge_points"]
        }
        preferred_id = blind_spots[0]["knowledge_point_id"] if blind_spots else None
        point_query = (
            db.query(KnowledgePoint)
            .filter_by(module_id=module.id)
            .order_by(KnowledgePoint.sequence)
        )
        points = point_query.all()
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

    plan = build_personalization_plan(
        profile,
        knowledge_point_id=point.id,
        knowledge_point_name=point.name,
    )
    evidence: list[dict] = []
    rag_client = PunditRAGClient()
    if rag_client.configured:
        try:
            evidence = rag_client.search(
                f"{point.name} {plan.weakest_dimension_label}",
                module.knowledge_base_id,
                module.id,
                knowledge_point_ids=[point.id],
            )
        except IntegrationUnavailable as exc:
            degradation.append(f"PunditRAG：{exc}")
    else:
        degradation.append("PunditRAG未配置")

    sources = [item.get("metadata", {}) for item in evidence]
    generated, generation_error = ResourceGenerationAgent().generate(plan, evidence)
    if generation_error:
        degradation.append(generation_error)

    resources = []
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
        result = verifier.verify(item, plan, evidence)
        verification_record = VerificationResult(
            id=uuid4().hex,
            resource_id=resource.id,
            passed=result.passed,
            factual_score=result.factual_score,
            coverage_score=result.coverage_score,
            difficulty_score=result.difficulty_score,
            issues=result.issues,
        )
        db.add(verification_record)
        if result.passed:
            resource.status = "verified"
        resources.append(
            {
                "resource_id": resource.id,
                "resource_type": resource.resource_type,
                "title": resource.title,
                "status": resource.status,
                "verification_passed": result.passed,
                "issues": result.issues,
            }
        )
    db.commit()
    return {
        "items": resources,
        "plan": plan.to_dict(),
        "degradation": degradation,
    }
