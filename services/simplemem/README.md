# ECHO SimpleMem

This directory is a standalone, contract-compatible long-term memory service for ECHO.
It persists records and mutation audit events in SQLite, applies exact organization/user/program/module
scope checks, enforces idempotency and active-memory conflict rules, and provides deterministic scoped
retrieval. It does not claim embedding-based semantic search.

## Local start

From the repository root:

```bash
PYTHONPATH=services/simplemem \
SIMPLEMEM_DB_PATH=data/simplemem.db \
SIMPLEMEM_HOST=127.0.0.1 \
SIMPLEMEM_ALLOW_INSECURE_DEV=true \
.venv/bin/python -m simplemem
```

The default address is `http://127.0.0.1:8020`. Check it with `GET /health`.

On Windows, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_simplemem.ps1 -AllowInsecureDevelopment
```

Both examples explicitly enable unauthenticated loopback-only development. Without that flag,
SimpleMem refuses to start unless `SIMPLEMEM_API_KEY` is non-empty.

## Authentication

Set the same strong, non-empty `SIMPLEMEM_API_KEY` for ECHO and this service. Protected `/v1`
endpoints require the `X-SimpleMem-API-Key` header. `/health` remains available for orchestration
health checks. An empty key is rejected by default and is allowed only when
`SIMPLEMEM_ALLOW_INSECURE_DEV=true` is explicitly set for a loopback-only development process.

## Persistence and retrieval

- The SQLite database path is controlled by `SIMPLEMEM_DB_PATH`.
- Deletes are tombstoned, while consolidation preserves source records and their evidence references.
  Replaying an idempotency key owned by a deleted or merged source returns HTTP 409; retries cannot
  silently reactivate a tombstone or report an inactive source as saved.
- Searches always apply all four scope fields before ranking candidates.
- Misconceptions require lexical or exact-phrase evidence before confidence and intent boosts apply.
  Learning preferences may fall back across topics for guidance/resource generation, and intervention
  outcomes may do so for guidance. No external model or embedding service is required.

## Docker

Build and run only this service:

```bash
docker build -t echo-simplemem services/simplemem
docker run --rm -p 127.0.0.1:8020:8020 \
  -e SIMPLEMEM_API_KEY="$(openssl rand -hex 32)" \
  -v echo-simplemem-data:/data echo-simplemem
```

The repository `docker-compose.yml` also starts SimpleMem with ECHO and retains its database in the
`simplemem-data` volume. The base Compose file exposes port 8020 only to the internal container network
and requires `SIMPLEMEM_API_KEY`. For explicit loopback-only development, use the override below; it
gives ECHO and SimpleMem the same fixed development-only service key:

```bash
docker compose -f docker-compose.yml -f docker-compose.simplemem-dev.yml up --build
```
