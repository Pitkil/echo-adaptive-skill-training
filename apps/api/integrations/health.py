"""Fast, read-only dependency probes for the ECHO system status endpoint."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

DEPENDENCY_TIMEOUT_SECONDS = 2.0


def collect_dependency_health() -> dict[str, dict[str, Any]]:
    """Probe configured external services without exposing credentials or base URLs."""

    targets = {
        "punditrag_import": os.getenv("PUNDITRAG_IMPORT_BASE_URL", "").strip(),
        "punditrag_query": os.getenv("PUNDITRAG_QUERY_BASE_URL", "").strip(),
        "simplemem": os.getenv("SIMPLEMEM_BASE_URL", "").strip(),
        "micro_representation": os.getenv("MICRO_REPRESENTATION_BASE_URL", "").strip(),
    }
    with ThreadPoolExecutor(max_workers=len(targets)) as executor:
        futures = {
            name: executor.submit(_probe, base_url)
            for name, base_url in targets.items()
        }
        return {name: future.result() for name, future in futures.items()}


def _probe(base_url: str) -> dict[str, Any]:
    if not base_url:
        return {"status": "not_configured", "detail": "服务地址未配置"}
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/health",
            timeout=DEPENDENCY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "status": "unavailable",
            "detail": _safe_error(exc),
        }
    result: dict[str, Any] = {"status": "ok"}
    if isinstance(payload, dict):
        for field in ("service", "version", "mode"):
            value = payload.get(field)
            if value is not None:
                result[field] = value
    return result


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "连接超时"
    return "无法连接"
