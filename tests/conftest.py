from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPOSITORY_ROOT / "apps" / "api"
TEST_RUNTIME_DIR = Path(tempfile.gettempdir()) / f"echo-competition-tests-{os.getpid()}"


def _cleanup_test_runtime() -> None:
    shutil.rmtree(TEST_RUNTIME_DIR, ignore_errors=True)


atexit.register(_cleanup_test_runtime)

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("SQLITE_PATH", str(TEST_RUNTIME_DIR / "echo.db"))
os.environ.setdefault("UPLOAD_DIR", str(TEST_RUNTIME_DIR / "uploads"))
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("APP_RELOAD", "false")
os.environ.setdefault("SECRET_KEY", "echo-test-secret-key-with-32-bytes")
