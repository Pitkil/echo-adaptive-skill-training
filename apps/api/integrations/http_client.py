"""Small synchronous JSON client used by backend integration adapters."""

from __future__ import annotations

from typing import Any

import httpx


class IntegrationUnavailable(RuntimeError):
    """Raised when an optional integration cannot serve a request."""


class JsonHttpClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if not self.configured:
            raise IntegrationUnavailable("Integration base URL is not configured.")

        try:
            response = httpx.request(
                method=method,
                url=f"{self.base_url}/{path.lstrip('/')}",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationUnavailable(str(exc)) from exc

    def upload(
        self,
        path: str,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        data: dict[str, str],
    ) -> Any:
        if not self.configured:
            raise IntegrationUnavailable("Integration base URL is not configured.")
        try:
            response = httpx.post(
                f"{self.base_url}/{path.lstrip('/')}",
                files={"file": (filename, content, content_type)},
                data=data,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationUnavailable(str(exc)) from exc
