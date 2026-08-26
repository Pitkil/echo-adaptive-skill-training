"""Enterprise training data model for the ECHO competition application."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from config import Config
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


class UserRole(StrEnum):
    LEARNER = "learner"
    MENTOR = "mentor"
    SYSTEM_ADMIN = "system_admin"


class MicroSourceType(StrEnum):
    LEARNER_VOICE = "learner_voice"
    MENTOR_RECORDING = "mentor_recording"


class EvidenceStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class TurnStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    COMPLETED_WITH_DEGRADATION = "completed_degraded"
    FAILED = "failed"


SQLALCHEMY_DATABASE_URL = Config.database.get_database_url()
engine_options: dict = {
    "pool_pre_ping": Config.database.POOL_PRE_PING,
}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options.update(
        pool_size=Config.database.POOL_SIZE,
        max_overflow=Config.database.MAX_OVERFLOW,
        pool_recycle=Config.database.POOL_RECYCLE,
    )

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    role = Column(String(30), nullable=False, default=UserRole.LEARNER.value)
    status = Column(String(20), nullable=False, default="active")
    reset_code = Column(String(10), nullable=True)
    reset_code_expiry = Column(DateTime, nullable=True)

    organization = relationship("Organization")
    sessions = relationship("ChatSession", back_populates="owner")
    uploads = relationship("Upload", back_populates="owner")


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(120), nullable=False)
    provider = Column(String(30), nullable=False, default="punditrag")
    external_ref = Column(String(200), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_kb_organization_code"),
    )


class TrainingProgram(Base):
    __tablename__ = "training_programs"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_program_organization_code"),
    )


class TrainingModule(Base):
    __tablename__ = "training_modules"

    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("training_programs.id"), nullable=False, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    code = Column(String(20), nullable=False)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    sequence = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="active")
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="uq_module_program_code"),
        UniqueConstraint("program_id", "sequence", name="uq_module_program_sequence"),
    )

    program = relationship("TrainingProgram")
    knowledge_base = relationship("KnowledgeBase")


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id = Column(Integer, primary_key=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    prerequisites = Column(JSON, nullable=False, default=list)
    sequence = Column(Integer, nullable=False, default=1)
    __table_args__ = (
        UniqueConstraint("module_id", "code", name="uq_knowledge_point_module_code"),
    )

    module = relationship("TrainingModule")


class ChatSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("training_programs.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    title = Column(String(100), default="新学习会话")
    active_quiz_id = Column(Integer, ForeignKey("quizzes.id"), nullable=True)
    echo_state = Column(String(10), nullable=False, default="E")
    echo_stage_counts = Column(JSON, nullable=False, default=lambda: {"E": 0, "C": 0, "H": 0, "O": 0})
    context_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    owner = relationship("User", back_populates="sessions")
    program = relationship("TrainingProgram")
    module = relationship("TrainingModule")
    knowledge_base = relationship("KnowledgeBase")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    thought_content = Column(Text, nullable=True)
    msg_type = Column(String(20), nullable=False, default="text")
    echo_state = Column(String(10), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now)

    owner = relationship("User")
    session = relationship("ChatSession", back_populates="messages")


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=False)
    source_title = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_section = Column(String(255), nullable=True)
    source_version = Column(String(120), nullable=True)
    external_document_id = Column(String(128), nullable=True, index=True)
    external_task_id = Column(String(128), nullable=True, index=True)
    index_status = Column(String(30), nullable=False, default="stored")
    index_error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.now)

    owner = relationship("User", back_populates="uploads")


class CourseVideo(Base):
    __tablename__ = "course_videos"

    id = Column(Integer, primary_key=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False, default="video/mp4")
    file_size = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.now)

    module = relationship("TrainingModule")
    knowledge_point = relationship("KnowledgePoint")


class VideoProgress(Base):
    __tablename__ = "video_progress"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    video_id = Column(Integer, ForeignKey("course_videos.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    current_time = Column(Float, nullable=False, default=0.0)
    duration = Column(Float, nullable=False, default=0.0)
    completed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_video_progress_user_video"),
    )


class VideoCheckpoint(Base):
    __tablename__ = "video_checkpoints"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("course_videos.id"), nullable=False, index=True)
    time_offset_seconds = Column(Float, nullable=False)
    question = Column(Text, nullable=False)
    expected_points = Column(JSON, nullable=False, default=list)
    official_sources = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    video = relationship("CourseVideo")


class VideoAnalysisJob(Base):
    __tablename__ = "video_analysis_jobs"

    id = Column(String(64), primary_key=True)
    video_id = Column(Integer, ForeignKey("course_videos.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued")
    frames_count = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    video = relationship("CourseVideo")


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default="MCQ")
    intercept_d = Column(Float, nullable=False, default=0.0)
    U = Column(Float, nullable=False, default=1.0)
    A = Column(Float, nullable=False, default=1.0)
    R = Column(Float, nullable=False, default=1.0)
    parameter_source = Column(String(30), nullable=False, default="expert_anchor")
    purpose = Column(String(30), nullable=False, default="practice")
    difficulty = Column(String(20), nullable=False, default="standard")
    scoring_method = Column(Text, nullable=True)
    source_title = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_section = Column(String(255), nullable=True)
    counts_for_mirt = Column(Boolean, nullable=False, default=True)

    module = relationship("TrainingModule")
    knowledge_point = relationship("KnowledgePoint")


class LearnerAbility(Base):
    __tablename__ = "learner_abilities"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    U = Column(Float, nullable=False, default=0.0)
    A = Column(Float, nullable=False, default=0.0)
    R = Column(Float, nullable=False, default=0.0)
    attempt_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("user_id", "module_id", name="uq_learner_ability_user_module"),
    )


class KnowledgePointReviewState(Base):
    __tablename__ = "knowledge_point_review_states"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False, index=True)
    stability_hours = Column(Float, nullable=False, default=0.1)
    due_at = Column(DateTime, nullable=True)
    last_result = Column(Boolean, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_point_id", name="uq_review_user_knowledge_point"),
    )


class StudentQuestionHistory(Base):
    __tablename__ = "student_question_history"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    question_id = Column(Integer, ForeignKey("quizzes.id"), nullable=False, index=True)
    submitted_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=False)
    score = Column(Float, nullable=False, default=0.0)
    stage = Column(String(10), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class MirtDailyModuleStats(Base):
    __tablename__ = "mirt_daily_module_stats"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    stat_date = Column(Date, nullable=False, default=date.today, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("user_id", "module_id", "stat_date", name="uq_mirt_daily_user_module_date"),
    )


class MicroDetectionJob(Base):
    __tablename__ = "micro_detection_jobs"

    id = Column(String(64), primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    learner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, index=True)
    source_type = Column(String(30), nullable=False)
    audio_uri = Column(String(500), nullable=False)
    consent_granted = Column(Boolean, nullable=False, default=False)
    status = Column(String(30), nullable=False, default="queued")
    external_job_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    events_sync_status = Column(String(20), nullable=False, default="pending")
    events_sync_error = Column(Text, nullable=True)
    events_synced_at = Column(DateTime, nullable=True)
    audio_duration_ms = Column(Integer, nullable=True)
    audio_sha256 = Column(String(64), nullable=True, index=True)
    dedupe_key = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_micro_detection_job_dedupe_key"),
    )


class MicroMentorBatch(Base):
    __tablename__ = "micro_mentor_batches"

    id = Column(String(64), primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class MicroMentorBatchJob(Base):
    __tablename__ = "micro_mentor_batch_jobs"

    batch_id = Column(
        String(64),
        ForeignKey("micro_mentor_batches.id"),
        primary_key=True,
    )
    job_id = Column(
        String(64),
        ForeignKey("micro_detection_jobs.id"),
        primary_key=True,
    )
    sequence = Column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("batch_id", "sequence", name="uq_micro_batch_job_sequence"),
    )


class MicroRepresentationEvent(Base):
    __tablename__ = "micro_representation_events"

    id = Column(String(100), primary_key=True)
    job_id = Column(String(64), ForeignKey("micro_detection_jobs.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    learner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, index=True)
    source_type = Column(String(30), nullable=False)
    event_type = Column(String(40), nullable=False)
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)
    transcript = Column(Text, nullable=True)
    evidence_uri = Column(String(500), nullable=True)
    speaker_ref = Column(String(100), nullable=True)
    speaker_mapping_confirmed = Column(Boolean, nullable=False, default=False)
    evidence_status = Column(String(20), nullable=False, default=EvidenceStatus.PENDING.value)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class TurnExecution(Base):
    __tablename__ = "turn_executions"

    id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False)
    trace_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    intent = Column(String(30), nullable=False)
    primary_action = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default=TurnStatus.PLANNED.value)
    plan = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    __table_args__ = (
        UniqueConstraint("session_id", "request_id", name="uq_turn_session_request"),
    )


class GeneratedResource(Base):
    __tablename__ = "generated_resources"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, index=True)
    resource_type = Column(String(30), nullable=False)
    difficulty = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    personalization_reason = Column(Text, nullable=False)
    evidence_sources = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id = Column(String(64), primary_key=True)
    resource_id = Column(String(64), ForeignKey("generated_resources.id"), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    factual_score = Column(Float, nullable=False)
    coverage_score = Column(Float, nullable=False)
    difficulty_score = Column(Float, nullable=False)
    issues = Column(JSON, nullable=False, default=list)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class LearningDecision(Base):
    __tablename__ = "learning_decisions"

    id = Column(String(64), primary_key=True)
    trace_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("training_modules.id"), nullable=False, index=True)
    knowledge_point_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=True, index=True)
    action = Column(String(40), nullable=False)
    reason = Column(Text, nullable=False)
    evidence_refs = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


def init_db() -> None:
    """Create a clean competition schema.

    Existing school-oriented databases must be migrated with the one-time
    migration script before this schema is used.
    """

    Base.metadata.create_all(bind=engine)
    _ensure_quiz_metadata_columns()
    _ensure_quiz_history_columns()
    _ensure_micro_job_columns()
    _ensure_micro_event_columns()
    _ensure_upload_rag_columns()


def _ensure_quiz_metadata_columns() -> None:
    """Add quiz-import metadata to existing competition databases in place."""

    inspector = inspect(engine)
    if "quizzes" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("quizzes")}
    additions = {
        "purpose": "VARCHAR(30) DEFAULT 'practice'",
        "difficulty": "VARCHAR(20) DEFAULT 'standard'",
        "scoring_method": "TEXT",
        "source_title": "VARCHAR(255)",
        "source_url": "VARCHAR(500)",
        "source_section": "VARCHAR(255)",
        "counts_for_mirt": "BOOLEAN DEFAULT 1",
    }
    with engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name not in existing:
                connection.execute(
                    text(f"ALTER TABLE quizzes ADD COLUMN {column_name} {definition}")
                )


def _ensure_quiz_history_columns() -> None:
    """Add auditable answer fields to existing competition databases."""

    inspector = inspect(engine)
    if "student_question_history" not in inspector.get_table_names():
        return
    existing = {
        column["name"] for column in inspector.get_columns("student_question_history")
    }
    additions = {
        "submitted_answer": "TEXT",
        "score": "FLOAT DEFAULT 0.0",
    }
    with engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name not in existing:
                connection.execute(
                    text(
                        "ALTER TABLE student_question_history "
                        f"ADD COLUMN {column_name} {definition}"
                    )
                )


def _ensure_micro_job_columns() -> None:
    """Add synchronization and ownership fields to existing micro jobs."""

    inspector = inspect(engine)
    if "micro_detection_jobs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("micro_detection_jobs")}
    additions = {
        "created_by_user_id": "INTEGER",
        "events_sync_status": "VARCHAR(20) DEFAULT 'pending' NOT NULL",
        "events_sync_error": "TEXT",
        "events_synced_at": "DATETIME",
        "audio_duration_ms": "INTEGER",
        "audio_sha256": "VARCHAR(64)",
        "dedupe_key": "VARCHAR(64)",
    }
    with engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name not in existing:
                connection.execute(
                    text(
                        "ALTER TABLE micro_detection_jobs "
                        f"ADD COLUMN {column_name} {definition}"
                    )
                )
    inspector = inspect(engine)
    unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("micro_detection_jobs")
    }
    index_names = {
        index["name"] for index in inspector.get_indexes("micro_detection_jobs")
    }
    if "uq_micro_detection_job_dedupe_key" not in unique_names | index_names:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_micro_detection_job_dedupe_key "
                    "ON micro_detection_jobs (dedupe_key)"
                )
            )


def _ensure_micro_event_columns() -> None:
    """Keep micro event identity and speaker fields compatible with the v1 contract."""

    inspector = inspect(engine)
    if "micro_representation_events" not in inspector.get_table_names():
        return
    existing = {
        column["name"] for column in inspector.get_columns("micro_representation_events")
    }
    if "speaker_mapping_confirmed" not in existing:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE micro_representation_events "
                    "ADD COLUMN speaker_mapping_confirmed BOOLEAN DEFAULT 0 NOT NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE micro_representation_events "
                    "SET speaker_mapping_confirmed = 1 WHERE learner_id IS NOT NULL"
                )
            )
    if engine.dialect.name == "mysql":
        id_column = next(
            column
            for column in inspect(engine).get_columns("micro_representation_events")
            if column["name"] == "id"
        )
        if getattr(id_column["type"], "length", None) != 100:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE micro_representation_events "
                        "MODIFY COLUMN id VARCHAR(100) NOT NULL"
                    )
                )


def _ensure_upload_rag_columns() -> None:
    """Add traceable PunditRAG fields to existing upload records."""

    inspector = inspect(engine)
    if "uploads" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("uploads")}
    additions = {
        "source_title": "VARCHAR(255)",
        "source_url": "VARCHAR(500)",
        "source_section": "VARCHAR(255)",
        "source_version": "VARCHAR(120)",
        "external_document_id": "VARCHAR(128)",
        "external_task_id": "VARCHAR(128)",
        "index_status": "VARCHAR(30) DEFAULT 'stored'",
        "index_error": "TEXT",
    }
    with engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name not in existing:
                connection.execute(
                    text(f"ALTER TABLE uploads ADD COLUMN {column_name} {definition}")
                )
