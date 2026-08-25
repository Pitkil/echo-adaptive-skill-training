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
.venv/bin/python -m simplemem
```

The default address is `http://127.0.0.1:8020`. Check it with `GET /health`.

On Windows, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_simplemem.ps1
```

## Authentication

Set the same non-empty `SIMPLEMEM_API_KEY` for ECHO and this service. Protected `/v1` endpoints then
require the `X-SimpleMem-API-Key` header. `/health` remains available for orchestration health checks.
An empty key is intended only for local development.

## Persistence and retrieval

- The SQLite database path is controlled by `SIMPLEMEM_DB_PATH`.
- Deletes are tombstoned, while consolidation preserves source records and their evidence references.
- Searches always apply all four scope fields before ranking candidates.
- Ranking combines lexical overlap, exact phrase matching, confidence and intent-specific memory-type
  weights. No external model or embedding service is required.

## Docker

Build and run only this service:

```bash
docker build -t echo-simplemem services/simplemem
docker run --rm -p 8020:8020 -v echo-simplemem-data:/data echo-simplemem
```

The repository `docker-compose.yml` also starts SimpleMem with ECHO and retains its database in the
`simplemem-data` volume.
