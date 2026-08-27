from __future__ import annotations

from pathlib import Path

from integrations.asr import ASRClient


def test_asr_client_validates_and_returns_transcription(monkeypatch, tmp_path: Path) -> None:
    audio = tmp_path / "answer.webm"
    audio.write_bytes(b"audio")
    client = ASRClient(base_url="http://asr:8040")

    monkeypatch.setattr(
        client.http,
        "upload",
        lambda *args, **kwargs: {
            "status": "completed",
            "text": "Kernel 可以调用插件",
            "language": "zh",
            "duration_ms": 1200,
            "model": "Systran/faster-whisper-tiny",
        },
    )

    result = client.transcribe_file(audio)

    assert result["text"] == "Kernel 可以调用插件"
    assert result["language"] == "zh"
    assert result["duration_ms"] == 1200


def test_asr_client_rejects_invalid_response(monkeypatch, tmp_path: Path) -> None:
    audio = tmp_path / "answer.wav"
    audio.write_bytes(b"audio")
    client = ASRClient(base_url="http://asr:8040")
    monkeypatch.setattr(client.http, "upload", lambda *args, **kwargs: {"status": "failed"})

    try:
        client.transcribe_file(audio)
    except Exception as exc:  # noqa: BLE001 - assert adapter contract boundary
        assert "invalid ASR response" in str(exc)
    else:
        raise AssertionError("invalid ASR payload should be rejected")
