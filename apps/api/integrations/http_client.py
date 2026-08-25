"""Small synchronous JSON client used by backend integration adapters."""

from __future__ import annotations

from typing import Any, BinaryIO

import httpx


class IntegrationUnavailable(RuntimeError):
    """Raised when an optional integration cannot serve a request."""


class IntegrationTransientError(IntegrationUnavailable):
    """Raised when an integration request is safe to retry later."""


class IntegrationContractError(IntegrationUnavailable):
    """Raised when retrying the same integration request cannot succeed."""


def _raise_http_error(exc: httpx.HTTPError) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 429 or status_code >= 500:
            raise IntegrationTransientError(str(exc)) from exc
        raise IntegrationContractError(str(exc)) from exc
    raise IntegrationTransientError(str(exc)) from exc


class JsonHttpClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = dict(headers or {})

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
            raise IntegrationTransientError("Integration base URL is not configured.")

        try:
            request_options: dict[str, Any] = {
                "method": method,
                "url": f"{self.base_url}/{path.lstrip('/')}",
                "json": payload,
                "timeout": self.timeout_seconds,
            }
            if self.headers:
                request_options["headers"] = self.headers
            response = httpx.request(**request_options)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            _raise_http_error(exc)
        except ValueError as exc:
            raise IntegrationContractError(str(exc)) from exc

    def upload(
        self,
        path: str,
        *,
        field_name: str = "file",
        filename: str,
        content: BinaryIO | bytes,
        content_type: str,
        data: dict[str, str],
    ) -> Any:
        if not self.configured:
            raise IntegrationTransientError("Integration base URL is not configured.")
        try:
            upload_options: dict[str, Any] = {
                "files": {field_name: (filename, content, content_type)},
                "data": data,
                "timeout": self.timeout_seconds,
            }
            if self.headers:
                upload_options["headers"] = self.headers
            response = httpx.post(
                f"{self.base_url}/{path.lstrip('/')}",
                **upload_options,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            _raise_http_error(exc)
        except ValueError as exc:
            raise IntegrationContractError(str(exc)) from exc
