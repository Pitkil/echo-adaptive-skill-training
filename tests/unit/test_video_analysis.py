from __future__ import annotations

import app as app_module
import video_analysis
from app import app, create_access_token, ensure_catalog, get_db
from database import (
    Base,
    CourseVideo,
    KnowledgePoint,
    Organization,
    TrainingModule,
    User,
    UserRole,
    VideoAnalysisJob,
    VideoCheckpoint,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _build_client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    ensure_catalog(db)
    organization = db.query(Organization).filter_by(code="ECHO-DEMO").one()
    mentor = User(
        organization_id=organization.id,
        username="analysis-mentor",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    learner = User(
        organization_id=organization.id,
        username="analysis-learner",
        hashed_password="not-used",
        role=UserRole.LEARNER.value,
    )
    db.add_all([mentor, learner])
    db.commit()
    db.refresh(mentor)
    db.refresh(learner)
    module = db.query(TrainingModule).order_by(TrainingModule.sequence).first()
    point = db.query(KnowledgePoint).filter_by(module_id=module.id).first()

    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), db, mentor, learner, module, point, tmp_path


def _add_video(db, module, point, uploader, tmp_path):
    video = CourseVideo(
        module_id=module.id,
        knowledge_point_id=point.id,
        title="kernel-overview",
        filename="kernel.mp4",
        filepath=str(tmp_path / "kernel.mp4"),
        content_type="video/mp4",
        file_size=128,
        uploaded_by_user_id=uploader.id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def test_video_analysis_generates_draft_checkpoints(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, tmp_path = _build_client(monkeypatch, tmp_path)
    video = _add_video(db, module, point, mentor, tmp_path)
    job = VideoAnalysisJob(id="job-1", video_id=video.id, status="queued")
    db.add(job)
    db.commit()

    monkeypatch.setattr(
        video_analysis,
        "extract_frames",
        lambda *args, **kwargs: [
            (0.0, tmp_path / "f0.jpg"),
            (30.0, tmp_path / "f30.jpg"),
        ],
    )
    monkeypatch.setattr(
        video_analysis,
        "read_frame",
        lambda path, backend=None: {
            "text": "Kernel 负责组织模型服务与插件",
            "topic": "Kernel",
            "question": "请说明 Kernel 在应用中的作用。",
        },
    )

    video_analysis.run_video_analysis(db, "job-1")

    refreshed = db.get(VideoAnalysisJob, "job-1")
    assert refreshed.status == "completed"
    assert refreshed.frames_count == 2
    checkpoints = (
        db.query(VideoCheckpoint)
        .filter_by(video_id=video.id)
        .order_by(VideoCheckpoint.time_offset_seconds)
        .all()
    )
    assert [item.time_offset_seconds for item in checkpoints] == [0.0, 30.0]
    assert all(item.status == "draft" for item in checkpoints)
    app.dependency_overrides.clear()


def test_llm_generates_question_from_ocr_text(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, tmp_path = _build_client(monkeypatch, tmp_path)
    video = _add_video(db, module, point, mentor, tmp_path)
    job = VideoAnalysisJob(id="job-llm", video_id=video.id, status="queued")
    db.add(job)
    db.commit()

    monkeypatch.setattr(
        video_analysis,
        "extract_frames",
        lambda *args, **kwargs: [(30.0, tmp_path / "f30.jpg")],
    )
    monkeypatch.setattr(
        video_analysis,
        "read_frame",
        lambda path, backend=None: {"text": "Kernel 组织插件并调用", "topic": "", "question": ""},
    )
    monkeypatch.setattr(
        video_analysis,
        "_llm_question_from_text",
        lambda text, kp: {"question": "请说明 Kernel 如何组织插件调用。"},
    )

    video_analysis.run_video_analysis(db, "job-llm")

    checkpoint = db.query(VideoCheckpoint).filter_by(video_id=video.id).one()
    assert checkpoint.question == "请说明 Kernel 如何组织插件调用。"
    assert checkpoint.status == "draft"
    app.dependency_overrides.clear()


def test_llm_falls_back_to_template_when_unavailable(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, tmp_path = _build_client(monkeypatch, tmp_path)
    video = _add_video(db, module, point, mentor, tmp_path)
    job = VideoAnalysisJob(id="job-fb", video_id=video.id, status="queued")
    db.add(job)
    db.commit()

    def _raise_unavailable(text, kp):
        raise video_analysis.OcrUnavailable("无可用大模型")

    monkeypatch.setattr(
        video_analysis,
        "extract_frames",
        lambda *args, **kwargs: [(30.0, tmp_path / "f30.jpg")],
    )
    monkeypatch.setattr(
        video_analysis,
        "read_frame",
        lambda path, backend=None: {"text": "Kernel 组织插件", "topic": "", "question": ""},
    )
    monkeypatch.setattr(video_analysis, "_llm_question_from_text", _raise_unavailable)

    video_analysis.run_video_analysis(db, "job-fb")

    checkpoint = db.query(VideoCheckpoint).filter_by(video_id=video.id).one()
    assert "请用自己的话说明" in checkpoint.question
    assert "Kernel 组织插件" in checkpoint.question
    app.dependency_overrides.clear()


def test_video_analysis_builds_three_ratio_checkpoints_from_prior_frame_context(
    monkeypatch,
    tmp_path,
) -> None:
    client, db, mentor, learner, module, point, tmp_path = _build_client(monkeypatch, tmp_path)
    video = _add_video(db, module, point, mentor, tmp_path)
    job = VideoAnalysisJob(id="job-context", video_id=video.id, status="queued")
    db.add(job)
    db.commit()
    offsets = [float(value) for value in range(0, 100, 5)]
    monkeypatch.setattr(video_analysis, "probe_video_duration", lambda path: 100.0)
    monkeypatch.setattr(
        video_analysis,
        "extract_frames",
        lambda *args, **kwargs: [(offset, tmp_path / f"f{int(offset)}.jpg") for offset in offsets],
    )
    monkeypatch.setattr(
        video_analysis,
        "read_frame",
        lambda path, backend=None: {
            "text": f"第 {path.stem[1:]} 秒的连续课程内容",
            "topic": "Kernel",
            "question": "",
        },
    )
    contexts: list[str] = []

    def generate(context, knowledge_point_name):
        contexts.append(context)
        return "请概括截至当前的课程内容。", ["说明关键概念", "联系前文"]

    monkeypatch.setattr(video_analysis, "_generate_contextual_checkpoint", generate)

    video_analysis.run_video_analysis(db, "job-context")

    checkpoints = (
        db.query(VideoCheckpoint)
        .filter_by(video_id=video.id)
        .order_by(VideoCheckpoint.time_offset_seconds)
        .all()
    )
    assert [item.time_offset_seconds for item in checkpoints] == [25.0, 50.0, 75.0]
    assert all(item.expected_points == ["说明关键概念", "联系前文"] for item in checkpoints)
    assert "[0:00]" in contexts[0]
    assert "[0:25]" in contexts[0]
    assert "[0:30]" in contexts[0]
    assert "[0:00]" in contexts[2]
    assert "[1:15]" in contexts[2]
    app.dependency_overrides.clear()


def test_checkpoint_freeze_gates_learner_visibility(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, tmp_path = _build_client(monkeypatch, tmp_path)
    video = _add_video(db, module, point, mentor, tmp_path)
    db.add(
        VideoCheckpoint(
            video_id=video.id,
            time_offset_seconds=10.0,
            question="请说明 Kernel 的作用。",
            expected_points=["模型服务", "插件"],
            official_sources=["https://learn.microsoft.com/semantic-kernel"],
            status="draft",
        )
    )
    db.commit()

    mentor_headers = {"Authorization": f"Bearer {create_access_token(mentor)}"}
    learner_headers = {"Authorization": f"Bearer {create_access_token(learner)}"}

    learner_view = client.get(
        f"/v1/videos/{video.id}/checkpoints",
        headers=learner_headers,
    )
    assert learner_view.status_code == 200
    assert learner_view.json()["items"] == []

    frozen = client.post(
        f"/v1/videos/{video.id}/checkpoints/freeze",
        headers=mentor_headers,
    )
    assert frozen.status_code == 200
    assert frozen.json()["items"][0]["status"] == "frozen"

    learner_after = client.get(
        f"/v1/videos/{video.id}/checkpoints",
        headers=learner_headers,
    )
    assert learner_after.json()["items"][0]["question"] == "请说明 Kernel 的作用。"
    app.dependency_overrides.clear()
