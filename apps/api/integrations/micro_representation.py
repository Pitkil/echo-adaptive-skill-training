"""Adapter for learner voice and mentor-recording detection jobs."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, unquote, urlparse
from urllib.request import url2pathname

from pydantic import ValidationError

from .contracts import (
    MicroDetectionJobResult,
    MicroDetectionRequest,
    MicroRepresentationEvent,
)
from .http_client import IntegrationUnavailable, JsonHttpClient

_AUDIO_CONTENT_TYPES = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


class MicroRepresentationClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.http = JsonHttpClient(
            base_url or os.getenv("MICRO_REPRESENTATION_BASE_URL", ""),
            timeout_seconds=float(os.getenv("MICRO_REPRESENTATION_TIMEOUT_SECONDS", "30")),
        )

    @property
    def configured(self) -> bool:
        return self.http.configured

    def create_job(self, request: MicroDetectionRequest) -> dict[str, Any]:
        parsed_uri = urlparse(request.audio_uri)
        if parsed_uri.scheme == "file":
            payload = self._upload_local_audio(request, parsed_uri)
        elif parsed_uri.scheme in {"http", "https"}:
            payload = self.http.request(
                "POST",
                "/v1/detection/jobs",
                request.model_dump(mode="json"),
            )
        else:
            raise IntegrationUnavailable(
                "micro-representation audio_uri must use file, http, or https."
            )
        return self._validate_job_result(payload)

    def get_job(self, job_id: str) -> dict[str, Any]:
        payload = self.http.request("GET", f"/v1/detection/jobs/{job_id}", None)
        result = self._validate_job_result(payload)
        if result["job_id"] != job_id:
            raise IntegrationUnavailable("detection job response job_id does not match request.")
        return result

    def get_events(self, job_id: str) -> list[MicroRepresentationEvent]:
        payload = self.http.request("GET", f"/v1/detection/jobs/{job_id}/events", None)
        raw_events = payload.get("items", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_events, list):
            raise IntegrationUnavailable("invalid micro-representation event response: items must be a list.")
        try:
            events = [MicroRepresentationEvent.model_validate(item) for item in raw_events]
        except ValidationError as exc:
            raise IntegrationUnavailable(f"invalid micro-representation event response: {exc}") from exc
        if any(event.job_id != job_id for event in events):
            raise IntegrationUnavailable("micro-representation event job_id does not match request.")
        return events

    def _upload_local_audio(
        self,
        request: MicroDetectionRequest,
        parsed_uri: ParseResult,
    ) -> Any:
        if parsed_uri.netloc not in {"", "localhost"}:
            raise IntegrationUnavailable("remote file audio_uri is not allowed.")
        local_path = Path(url2pathname(unquote(parsed_uri.path)))
        if os.name == "nt" and len(str(local_path)) >= 3 and str(local_path)[0] == "/":
            local_path = Path(str(local_path)[1:])
        if not local_path.is_file():
            raise IntegrationUnavailable(
                f"micro-representation audio file does not exist: {local_path.name}"
            )

        form_data = {
            key: self._form_value(value)
            for key, value in request.model_dump(mode="json", exclude={"audio_uri"}).items()
            if value is not None
        }
        content_type = _AUDIO_CONTENT_TYPES.get(
            local_path.suffix.lower(),
            mimetypes.guess_type(local_path.name)[0] or "application/octet-stream",
        )
        with local_path.open("rb") as content:
            return self.http.upload(
                "/v1/detection/jobs",
                field_name="audio",
                filename=local_path.name,
                content=content,
                content_type=content_type,
                data=form_data,
            )

    @staticmethod
    def _form_value(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    @staticmethod
    def _validate_job_result(payload: Any) -> dict[str, Any]:
        try:
            result = MicroDetectionJobResult.model_validate(payload)
        except ValidationError as exc:
            raise IntegrationUnavailable(f"invalid detection job response: {exc}") from exc
        return result.model_dump(mode="json", exclude_none=True)
