"""Adapter for learner voice and mentor-recording detection jobs."""

from __future__ import annotations

import os
from typing import Any

from .contracts import MicroDetectionRequest, MicroRepresentationEvent
from .http_client import JsonHttpClient


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
        return self.http.request(
            "POST",
            "/v1/detection/jobs",
            request.model_dump(mode="json"),
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.http.request("GET", f"/v1/detection/jobs/{job_id}", None)

    def get_events(self, job_id: str) -> list[MicroRepresentationEvent]:
        payload = self.http.request("GET", f"/v1/detection/jobs/{job_id}/events", None)
        raw_events = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [MicroRepresentationEvent.model_validate(item) for item in raw_events]
