from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_compose_starts_persistent_simplemem_with_echo() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "  simplemem:" in compose
    assert "context: services/simplemem" in compose
    assert "SIMPLEMEM_BASE_URL: ${SIMPLEMEM_DOCKER_BASE_URL:-http://simplemem:8020}" in compose
    assert "SIMPLEMEM_DB_PATH: /data/simplemem.db" in compose
    assert "simplemem-data:/data" in compose
    assert "condition: service_healthy" in compose


def test_simplemem_image_has_non_root_runtime_healthcheck_and_start_command() -> None:
    dockerfile = (
        REPOSITORY_ROOT / "services" / "simplemem" / "Dockerfile"
    ).read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "EXPOSE 8020" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'CMD ["python", "-m", "simplemem"]' in dockerfile


def test_local_simplemem_start_entry_and_configuration_are_documented() -> None:
    environment = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")
    start_script = (
        REPOSITORY_ROOT / "scripts" / "start_simplemem.ps1"
    ).read_text(encoding="utf-8")

    assert "SIMPLEMEM_PORT=8020" in environment
    assert "SIMPLEMEM_DB_PATH=data/simplemem.db" in environment
    assert "SIMPLEMEM_API_KEY=" in environment
    assert "$env:PYTHONPATH = $ServiceRoot" in start_script
    assert "& $Python -m simplemem" in start_script
