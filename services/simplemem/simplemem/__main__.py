"""Run SimpleMem with `python -m simplemem`."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "simplemem.app:app",
        host=os.getenv("SIMPLEMEM_HOST", "127.0.0.1"),
        port=int(os.getenv("SIMPLEMEM_PORT", "8020")),
        log_level=os.getenv("SIMPLEMEM_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
