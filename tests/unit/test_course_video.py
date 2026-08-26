from __future__ import annotations

import app as app_module
from app import app, create_access_token, ensure_catalog, get_db
from database import Base, KnowledgePoint, Organization, TrainingModule, User, UserRole
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
        username="video-mentor",
        hashed_password="not-used",
        role=UserRole.MENTOR.value,
    )
    learner = User(
        organization_id=organization.id,
        username="video-learner",
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
    return TestClient(app), db, mentor, learner, module, point


def test_admin_uploads_videos_and_learner_resumes_progress(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point = _build_client(monkeypatch, tmp_path)
    mentor_headers = {"Authorization": f"Bearer {create_access_token(mentor)}"}
    learner_headers = {"Authorization": f"Bearer {create_access_token(learner)}"}

    response = client.post(
        f"/v1/modules/{module.id}/videos",
        headers=mentor_headers,
        data={"knowledge_point_id": str(point.id)},
        files=[
            ("files", ("kernel.mp4", b"fake-video-bytes", "video/mp4")),
            ("files", ("plugins.webm", b"another-video", "video/webm")),
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_size"] == len(b"fake-video-bytes") + len(b"another-video")
    assert len(payload["items"]) == 2
    video_id = payload["items"][0]["id"]
    assert payload["items"][0]["knowledge_point_id"] == point.id

    list_response = client.get(
        f"/v1/modules/{module.id}/videos",
        headers=learner_headers,
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 2
    assert items[0]["progress"] is None
    stream_url = items[0]["stream_url"]
    assert f"/v1/videos/{video_id}/stream?token=" in stream_url

    stream_response = client.get(stream_url)
    assert stream_response.status_code == 200
    assert stream_response.content == b"fake-video-bytes"

    progress_response = client.put(
        f"/v1/videos/{video_id}/progress",
        headers=learner_headers,
        json={"current_time": 12.5, "duration": 30.0, "completed": False},
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["current_time"] == 12.5

    refreshed = client.get(
        f"/v1/modules/{module.id}/videos",
        headers=learner_headers,
    ).json()["items"]
    resumed = next(item for item in refreshed if item["id"] == video_id)
    assert resumed["progress"]["current_time"] == 12.5
    app.dependency_overrides.clear()


def test_learner_cannot_upload_videos(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point = _build_client(monkeypatch, tmp_path)
    learner_headers = {"Authorization": f"Bearer {create_access_token(learner)}"}
    response = client.post(
        f"/v1/modules/{module.id}/videos",
        headers=learner_headers,
        files=[("files", ("blocked.mp4", b"nope", "video/mp4"))],
    )
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_video_stream_supports_range_requests(monkeypatch, tmp_path) -> None:
    client, db, mentor, learner, module, point = _build_client(monkeypatch, tmp_path)
    mentor_headers = {"Authorization": f"Bearer {create_access_token(mentor)}"}
    upload = client.post(
        f"/v1/modules/{module.id}/videos",
        headers=mentor_headers,
        files=[("files", ("range.mp4", b"0123456789", "video/mp4"))],
    ).json()
    stream_url = upload["items"][0]["stream_url"]
    ranged = client.get(stream_url, headers={"Range": "bytes=2-5"})
    assert ranged.status_code == 206
    assert ranged.content == b"2345"
    assert ranged.headers["content-range"] == "bytes 2-5/10"
    app.dependency_overrides.clear()
