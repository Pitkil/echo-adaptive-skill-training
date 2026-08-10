from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from app import (
    require_micro_callback_identity,
    require_micro_job_access,
    save_audio_file,
)
from config import Config
from database import UserRole
from fastapi import HTTPException, UploadFile
from integrations.contracts import MicroSource
from starlette.datastructures import Headers


def make_user(user_id: int, role: str, organization_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=role, organization_id=organization_id)


def make_job(**overrides: object) -> SimpleNamespace:
    values = {
        "organization_id": 1,
        "source_type": MicroSource.LEARNER_VOICE.value,
        "learner_id": 7,
        "created_by_user_id": 7,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_audio(content: bytes, filename: str = "turn.wav") -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": "audio/wav"}),
    )


def test_learner_cannot_read_another_learners_job() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_micro_job_access(
            make_job(learner_id=8, created_by_user_id=8),
            make_user(7, UserRole.LEARNER.value),
        )
    assert exc_info.value.status_code == 404


def test_mentor_can_only_read_a_job_they_created() -> None:
    require_micro_job_access(
        make_job(created_by_user_id=10),
        make_user(10, UserRole.MENTOR.value),
    )
    with pytest.raises(HTTPException) as exc_info:
        require_micro_job_access(
            make_job(created_by_user_id=11),
            make_user(10, UserRole.MENTOR.value),
        )
    assert exc_info.value.status_code == 404


def test_callback_requires_independent_service_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config.security, "MICRO_CALLBACK_SECRET", "service-secret")
    require_micro_callback_identity("service-secret")
    with pytest.raises(HTTPException) as exc_info:
        require_micro_callback_identity("ordinary-user-token")
    assert exc_info.value.status_code == 401


def test_audio_is_streamed_hashed_and_size_limited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(Config.upload, "MAX_FILE_SIZE", 8)

    with pytest.raises(HTTPException) as exc_info:
        save_audio_file("too-large", make_audio(b"123456789"))
    assert exc_info.value.status_code == 413
    assert not list(tmp_path.rglob("too-large*"))

    path, digest, size = save_audio_file("valid", make_audio(b"12345678"))
    assert size == 8
    assert len(digest) == 64
    assert path.read_bytes() == b"12345678"


def test_audio_extension_and_content_type_are_validated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    with pytest.raises(HTTPException) as exc_info:
        save_audio_file("invalid", make_audio(b"audio", filename="turn.exe"))
    assert exc_info.value.status_code == 415
