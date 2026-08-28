"""Adapter for the optional local ECHO speech-to-text service."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .http_client import IntegrationContractError, JsonHttpClient


class TranscriptionResult(BaseModel):
    status: str = Field(pattern="^completed$")
    text: str
    language: str | None = None
    duration_ms: int | None = Field(default=None, gt=0)
    model: str = Field(min_length=1)


class ASRClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.http = JsonHttpClient(
            base_url or os.getenv("ASR_BASE_URL", ""),
            timeout_seconds=float(os.getenv("ASR_TIMEOUT_SECONDS", "120")),
        )

    @property
    def configured(self) -> bool:
        return self.http.configured

    def transcribe_file(self, path: Path, *, language: str | None = None) -> dict[str, Any]:
        if not path.is_file():
            raise IntegrationContractError(f"ASR audio file does not exist: {path.name}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = {"language": language} if language else {}
        with path.open("rb") as content:
            payload = self.http.upload(
                "/v1/asr/transcribe",
                field_name="audio",
                filename=path.name,
                content=content,
                content_type=content_type,
                data=data,
            )
        try:
            result = TranscriptionResult.model_validate(payload)
        except ValidationError as exc:
            raise IntegrationContractError(f"invalid ASR response: {exc}") from exc
        return result.model_dump(mode="json")
