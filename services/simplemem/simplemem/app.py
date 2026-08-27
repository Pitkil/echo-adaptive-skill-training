"""FastAPI entry point for the deployable ECHO SimpleMem service."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .database import (
    ConsolidationUnavailableError,
    MemoryConflictError,
    MemoryForbiddenError,
    MemoryNotFoundError,
    SimpleMemStore,
)
from .schemas import (
    HealthResponse,
    MemoryAuthorizationResponse,
    MemoryConsolidationResult,
    MemoryMutationResponse,
    MemoryRecord,
    MemoryScope,
    MemorySearchRequest,
    MemoryUpsertResponse,
)

SERVICE_VERSION = "1.0.0"


def create_app(
    database_path: str | Path | None = None,
    *,
    api_key: str | None = None,
    allow_insecure_dev: bool | None = None,
) -> FastAPI:
    configured_path = Path(
        database_path or os.getenv("SIMPLEMEM_DB_PATH", "data/simplemem.db")
    )
    configured_api_key = (
        os.getenv("SIMPLEMEM_API_KEY", "") if api_key is None else api_key
    ).strip()
    configured_host = os.getenv("SIMPLEMEM_HOST", "127.0.0.1").strip().casefold()
    configured_allow_insecure_dev = (
        _environment_flag("SIMPLEMEM_ALLOW_INSECURE_DEV", default=False)
        if allow_insecure_dev is None
        else allow_insecure_dev
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if not configured_api_key and not configured_allow_insecure_dev:
            raise RuntimeError(
                "SIMPLEMEM_API_KEY must be non-empty unless "
                "SIMPLEMEM_ALLOW_INSECURE_DEV=true is explicitly enabled"
            )
        if (
            not configured_api_key
            and configured_allow_insecure_dev
            and configured_host not in {"127.0.0.1", "localhost", "::1"}
        ):
            raise RuntimeError(
                "unauthenticated SimpleMem development must bind SIMPLEMEM_HOST "
                "to a loopback address"
            )
        application.state.store = SimpleMemStore(configured_path)
        yield

    application = FastAPI(
        title="ECHO SimpleMem",
        description="Scope-isolated persistent long-term memory service for ECHO.",
        version=SERVICE_VERSION,
        lifespan=lifespan,
    )
    application.state.store = None
    application.state.api_key = configured_api_key
    application.state.allow_insecure_dev = configured_allow_insecure_dev

    @application.exception_handler(MemoryNotFoundError)
    async def memory_not_found(_request: Request, exc: MemoryNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @application.exception_handler(MemoryForbiddenError)
    async def memory_forbidden(_request: Request, exc: MemoryForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    @application.exception_handler(MemoryConflictError)
    async def memory_conflict(_request: Request, exc: MemoryConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc), "conflict_memory_ids": exc.memory_ids},
        )

    @application.exception_handler(ConsolidationUnavailableError)
    async def consolidation_unavailable(
        _request: Request,
        exc: ConsolidationUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @application.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        _store(request).health()
        return HealthResponse(version=SERVICE_VERSION)

    protected = [Depends(_require_api_key)]

    @application.post(
        "/v1/memories",
        response_model=MemoryUpsertResponse,
        dependencies=protected,
    )
    def upsert_memory(record: MemoryRecord, request: Request) -> dict:
        return _store(request).upsert(record)

    @application.post("/v1/memories/search", dependencies=protected)
    def search_memories(payload: MemorySearchRequest, request: Request) -> dict:
        items = _store(request).search(
            payload,
            intent=payload.intent,
            query=payload.query,
            knowledge_point_id=payload.knowledge_point_id,
            limit=payload.limit,
        )
        return {"items": items}

    @application.post(
        "/v1/memories/{memory_id}/authorize",
        response_model=MemoryAuthorizationResponse,
        dependencies=protected,
    )
    def authorize_memory(
        memory_id: str,
        scope: MemoryScope,
        request: Request,
    ) -> dict:
        return _store(request).authorize(memory_id, scope)

    @application.patch(
        "/v1/memories/{memory_id}",
        response_model=MemoryMutationResponse,
        dependencies=protected,
    )
    def update_memory(
        memory_id: str,
        record: MemoryRecord,
        request: Request,
    ) -> dict:
        return _store(request).update(memory_id, record)

    @application.delete(
        "/v1/memories/scope",
        dependencies=protected,
    )
    def purge_memories(scope: MemoryScope, request: Request) -> dict:
        return _store(request).purge_scope(scope)

    @application.delete(
        "/v1/memories/{memory_id}",
        response_model=MemoryMutationResponse,
        dependencies=protected,
    )
    def delete_memory(
        memory_id: str,
        scope: MemoryScope,
        request: Request,
    ) -> dict:
        return _store(request).delete(memory_id, scope)

    @application.post(
        "/v1/memories/consolidate",
        response_model=MemoryConsolidationResult,
        dependencies=protected,
    )
    def consolidate_memories(scope: MemoryScope, request: Request) -> dict:
        return _store(request).consolidate(scope)

    return application


def _store(request: Request) -> SimpleMemStore:
    store = request.app.state.store
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SimpleMem database is not ready",
        )
    return store


def _require_api_key(
    request: Request,
    x_simplemem_api_key: str | None = Header(default=None),
) -> None:
    expected = request.app.state.api_key
    if expected and (
        x_simplemem_api_key is None or not compare_digest(x_simplemem_api_key, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid SimpleMem API key",
        )


def _environment_flag(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value")


app = create_app()
