from __future__ import annotations

from pathlib import Path

import app as app_module
from app import app, create_access_token, ensure_catalog, get_db
from database import (
    Base,
    CourseVideo,
    KnowledgePoint,
    LearnerAbility,
    MicroDetectionJob,
    Organization,
    Quiz,
    StudentQuestionHistory,
    TrainingModule,
    User,
    UserRole,
    VideoCheckpoint,
    VideoOralAttempt,
)
from fastapi.testclient import TestClient
from oral_assessment import (
    OralAssessmentResult,
    OralAssessmentUnavailable,
    _parse_result,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _build_client(tmp_path):
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
        username="oral-mentor",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    learner = User(
        organization_id=organization.id,
        username="oral-learner",
        hashed_password="not-used",
        role=UserRole.LEARNER.value,
    )
    db.add_all([mentor, learner])
    db.commit()
    module = db.query(TrainingModule).order_by(TrainingModule.sequence).first()
    point = db.query(KnowledgePoint).filter_by(module_id=module.id).first()
    video = CourseVideo(
        module_id=module.id,
        knowledge_point_id=point.id,
        title="Kernel 视频",
        filename="kernel.mp4",
        filepath=str(tmp_path / "kernel.mp4"),
        content_type="video/mp4",
        file_size=10,
        uploaded_by_user_id=mentor.id,
    )
    db.add(video)
    db.commit()
    checkpoint = VideoCheckpoint(
        video_id=video.id,
        time_offset_seconds=20,
        question="请说明 Kernel 的两个职责。",
        expected_points=["组织模型服务", "注册并调用插件"],
        official_sources=["https://learn.microsoft.com/semantic-kernel/overview/"],
        status="draft",
    )
    db.add(checkpoint)
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), db, mentor, learner, module, point, video, checkpoint


def _freeze(client, mentor, video):
    return client.post(
        f"/v1/videos/{video.id}/checkpoints/freeze",
        headers={"Authorization": f"Bearer {create_access_token(mentor)}"},
    )


def test_freeze_creates_stable_quiz_and_hides_scoring_details(tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    response = _freeze(client, mentor, video)
    assert response.status_code == 200
    db.refresh(checkpoint)
    quiz = db.get(Quiz, checkpoint.quiz_id)
    assert quiz is not None
    assert quiz.purpose == "practice"
    assert quiz.counts_for_mirt is True
    assert quiz.answer == "组织模型服务 | 注册并调用插件"

    learner_view = client.get(
        f"/v1/videos/{video.id}/checkpoints",
        headers={"Authorization": f"Bearer {create_access_token(learner)}"},
    ).json()["items"][0]
    assert learner_view["expected_points"] == []
    assert learner_view["official_sources"] == []

    second_freeze = _freeze(client, mentor, video)
    assert second_freeze.status_code == 200
    assert db.query(Quiz).filter_by(id=checkpoint.quiz_id).count() == 1
    app.dependency_overrides.clear()


def test_freeze_ignores_legacy_frozen_rows_and_only_validates_new_drafts(tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    checkpoint.status = "frozen"
    checkpoint.expected_points = []
    checkpoint.official_sources = []
    new_draft = VideoCheckpoint(
        video_id=video.id,
        time_offset_seconds=40,
        question="请说明插件调用。",
        expected_points=["注册插件", "调用函数"],
        official_sources=["https://learn.microsoft.com/semantic-kernel/concepts/plugins/"],
        status="draft",
    )
    db.add(new_draft)
    db.commit()

    response = _freeze(client, mentor, video)
    assert response.status_code == 200
    db.refresh(new_draft)
    assert new_draft.status == "frozen"
    assert new_draft.quiz_id is not None
    assert checkpoint.quiz_id is None

    repeated = _freeze(client, mentor, video)
    assert repeated.status_code == 200
    assert len(repeated.json()["items"]) == 2
    app.dependency_overrides.clear()


def test_freeze_rejects_missing_approved_scoring_evidence(tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    checkpoint.expected_points = []
    checkpoint.official_sources = ["https://example.com/not-official"]
    db.commit()
    response = _freeze(client, mentor, video)
    assert response.status_code == 422
    assert db.query(Quiz).filter_by(content=checkpoint.question).count() == 0
    app.dependency_overrides.clear()


def test_confirmed_transcript_is_scored_once_and_updates_mirt(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    assert _freeze(client, mentor, video).status_code == 200
    db.refresh(checkpoint)
    job = MicroDetectionJob(
        id="oral-job",
        organization_id=learner.organization_id,
        created_by_user_id=learner.id,
        learner_id=learner.id,
        module_id=module.id,
        knowledge_point_id=point.id,
        video_checkpoint_id=checkpoint.id,
        source_type="learner_voice",
        audio_uri="file:///tmp/oral.wav",
        consent_granted=True,
        status="completed",
        transcript="Kernel 会组织模型服务，也能注册调用插件。",
        transcription_status="completed",
    )
    db.add(job)
    db.commit()
    monkeypatch.setattr(
        app_module,
        "assess_oral_answer",
        lambda **kwargs: OralAssessmentResult(
            matched_indices=[0, 1],
            feedback="两个职责均已说明。",
        ),
    )
    headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
    payload = {
        "job_id": job.id,
        "confirmed_transcript": "Kernel 会组织模型服务，也能注册调用插件。",
        "attempt_id": "oral-attempt-1",
    }
    first = client.post(
        f"/v1/video-checkpoints/{checkpoint.id}/oral-attempts",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["score"] == 1.0
    assert first.json()["is_correct"] is True
    assert first.json()["updated"] is True
    ability = db.query(LearnerAbility).filter_by(user_id=learner.id, module_id=module.id).one()
    assert ability.attempt_count == 1
    assert db.query(StudentQuestionHistory).filter_by(attempt_id="oral-attempt-1").count() == 1
    assert db.query(VideoOralAttempt).filter_by(attempt_id="oral-attempt-1").one().mirt_updated

    duplicate = client.post(
        f"/v1/video-checkpoints/{checkpoint.id}/oral-attempts",
        headers=headers,
        json=payload,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["updated"] is False
    db.refresh(ability)
    assert ability.attempt_count == 1
    app.dependency_overrides.clear()


def test_learner_audio_job_is_bound_to_frozen_checkpoint(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    assert _freeze(client, mentor, video).status_code == 200
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(app_module, "process_micro_job", lambda job_id: None)
    response = client.post(
        "/v1/micro/detection-jobs",
        headers={"Authorization": f"Bearer {create_access_token(learner)}"},
        data={
            "module_id": str(module.id),
            "knowledge_point_id": str(point.id),
            "video_checkpoint_id": str(checkpoint.id),
            "source_type": "learner_voice",
            "consent_granted": "true",
        },
        files={"audio": ("answer.wav", b"valid-audio", "audio/wav")},
    )
    assert response.status_code == 200
    assert response.json()["video_checkpoint_id"] == checkpoint.id
    job = db.get(MicroDetectionJob, response.json()["job_id"])
    assert job.video_checkpoint_id == checkpoint.id
    app.dependency_overrides.clear()


def test_ai_failure_does_not_create_attempt_or_update_mirt(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    assert _freeze(client, mentor, video).status_code == 200
    db.refresh(checkpoint)
    db.add(
        MicroDetectionJob(
            id="unavailable-job",
            organization_id=learner.organization_id,
            created_by_user_id=learner.id,
            learner_id=learner.id,
            module_id=module.id,
            knowledge_point_id=point.id,
            video_checkpoint_id=checkpoint.id,
            source_type="learner_voice",
            audio_uri="file:///tmp/oral.wav",
            consent_granted=True,
            status="completed",
            transcript="答案",
            transcription_status="completed",
        )
    )
    db.commit()

    def unavailable(**kwargs):
        raise OralAssessmentUnavailable("AI 评分暂不可用")

    monkeypatch.setattr(app_module, "assess_oral_answer", unavailable)
    response = client.post(
        f"/v1/video-checkpoints/{checkpoint.id}/oral-attempts",
        headers={"Authorization": f"Bearer {create_access_token(learner)}"},
        json={
            "job_id": "unavailable-job",
            "confirmed_transcript": "答案",
            "attempt_id": "failed-attempt",
        },
    )
    assert response.status_code == 503
    assert db.query(VideoOralAttempt).count() == 0
    assert db.query(StudentQuestionHistory).filter_by(attempt_id="failed-attempt").count() == 0
    app.dependency_overrides.clear()


def test_empty_historical_expected_points_fail_closed(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    assert _freeze(client, mentor, video).status_code == 200
    db.refresh(checkpoint)
    checkpoint.expected_points = ["", "   "]
    db.add(
        MicroDetectionJob(
            id="empty-points-job",
            organization_id=learner.organization_id,
            created_by_user_id=learner.id,
            learner_id=learner.id,
            module_id=module.id,
            knowledge_point_id=point.id,
            video_checkpoint_id=checkpoint.id,
            source_type="learner_voice",
            audio_uri="file:///tmp/empty-points.wav",
            consent_granted=True,
            status="completed",
            transcript="回答",
            transcription_status="completed",
        )
    )
    db.commit()
    called = False

    def must_not_call(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("AI grader must not receive an empty rubric")

    monkeypatch.setattr(app_module, "assess_oral_answer", must_not_call)
    response = client.post(
        f"/v1/video-checkpoints/{checkpoint.id}/oral-attempts",
        headers={"Authorization": f"Bearer {create_access_token(learner)}"},
        json={
            "job_id": "empty-points-job",
            "confirmed_transcript": "回答",
            "attempt_id": "empty-points-attempt",
        },
    )
    assert response.status_code == 409
    assert "缺少有效评分要点" in response.json()["detail"]
    assert called is False
    assert db.query(VideoOralAttempt).filter_by(attempt_id="empty-points-attempt").count() == 0
    app.dependency_overrides.clear()


def test_quiz_mirt_flag_controls_audit_and_response(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point, video, checkpoint = _build_client(tmp_path)
    assert _freeze(client, mentor, video).status_code == 200
    db.refresh(checkpoint)
    quiz = db.get(Quiz, checkpoint.quiz_id)
    quiz.counts_for_mirt = False
    db.add(
        MicroDetectionJob(
            id="non-mirt-job",
            organization_id=learner.organization_id,
            created_by_user_id=learner.id,
            learner_id=learner.id,
            module_id=module.id,
            knowledge_point_id=point.id,
            video_checkpoint_id=checkpoint.id,
            source_type="learner_voice",
            audio_uri="file:///tmp/non-mirt.wav",
            consent_granted=True,
            status="completed",
            transcript="完整回答",
            transcription_status="completed",
        )
    )
    db.commit()
    monkeypatch.setattr(
        app_module,
        "assess_oral_answer",
        lambda **kwargs: OralAssessmentResult(
            matched_indices=[0, 1],
            feedback="回答完整。",
        ),
    )
    response = client.post(
        f"/v1/video-checkpoints/{checkpoint.id}/oral-attempts",
        headers={"Authorization": f"Bearer {create_access_token(learner)}"},
        json={
            "job_id": "non-mirt-job",
            "confirmed_transcript": "完整回答",
            "attempt_id": "non-mirt-attempt",
        },
    )
    assert response.status_code == 200
    assert response.json()["counts_for_mirt"] is False
    assert response.json()["attempt_count"] == 0
    attempt = db.query(VideoOralAttempt).filter_by(attempt_id="non-mirt-attempt").one()
    assert attempt.mirt_updated is False
    app.dependency_overrides.clear()


def test_oral_assessment_parser_rejects_duplicate_or_out_of_range_indices() -> None:
    for raw in (
        '{"matched_point_indices":[0,0],"feedback":"ok"}',
        '{"matched_point_indices":[2],"feedback":"ok"}',
    ):
        try:
            _parse_result(raw, 2)
        except ValueError:
            continue
        raise AssertionError("invalid model indices must be rejected")


def test_frontend_requires_polled_job_to_match_active_checkpoint() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "apps" / "api" / "web" / "echo-app.js"
    ).read_text(encoding="utf-8")
    assert (
        "payload.video_checkpoint_id === state.videoEvidenceContext.checkpointId"
        in script
    )
