"""Development entry point for the ECHO competition backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = API_DIR.parents[1]


def _resolve_runtime_path(variable: str, default: str, is_directory: bool) -> None:
    raw_value = os.getenv(variable, default)
    if raw_value == ":memory:":
        return

    resolved = Path(raw_value)
    if not resolved.is_absolute():
        resolved = REPOSITORY_ROOT / resolved
    resolved = resolved.resolve()
    os.environ[variable] = str(resolved)

    directory = resolved if is_directory else resolved.parent
    directory.mkdir(parents=True, exist_ok=True)


def _prepare_runtime() -> None:
    load_dotenv(REPOSITORY_ROOT / ".env")
    _resolve_runtime_path("SQLITE_PATH", "data/echo.db", is_directory=False)
    _resolve_runtime_path("UPLOAD_DIR", "data/uploads", is_directory=True)
    os.chdir(API_DIR)
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))


def main() -> None:
    _prepare_runtime()

    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("APP_RELOAD", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
    )


if __name__ == "__main__":
    main()
