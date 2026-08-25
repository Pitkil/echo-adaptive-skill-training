from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_real_detector_is_loopback_only_and_has_upload_limit() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.competition.yml").read_text(
        encoding="utf-8"
    )

    assert '"127.0.0.1:${MICRO_DETECTOR_PORT:-8030}:8030"' in compose
    assert "MICRO_DETECTOR_MAX_AUDIO_BYTES: ${MICRO_DETECTOR_MAX_AUDIO_BYTES:-104857600}" in compose


def test_competition_start_requires_strong_simplemem_key() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "start_competition.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Get-EnvironmentFileValue -Path $environmentFile -Name "SIMPLEMEM_API_KEY"' in script
    assert "[Text.Encoding]::UTF8.GetByteCount($simpleMemApiKey) -lt 32" in script
    assert "Copy .env.example to .env" in script
