from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _load_service():
    service_path = Path(__file__).parents[2] / "services" / "asr" / "app.py"
    spec = importlib.util.spec_from_file_location("echo_asr_service", service_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_asr_health_does_not_download_model() -> None:
    service = _load_service()
    response = TestClient(service.app).get("/health")
    assert response.status_code == 200
    assert response.json()["model"] == "Systran/faster-whisper-tiny"
    assert response.json()["model_loaded"] is False


def test_asr_transcribes_with_lazy_model(monkeypatch) -> None:
    service = _load_service()

    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return iter([SimpleNamespace(text="  语音答案  ")]), SimpleNamespace(
                language="zh", duration=1.5
            )

    monkeypatch.setattr(service, "_load_model", lambda: FakeModel())
    with TestClient(service.app) as client:
        response = client.post(
            "/v1/asr/transcribe",
            files={"audio": ("answer.wav", b"wav", "audio/wav")},
            data={"language": "zh"},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "语音答案"
    assert response.json()["language"] == "zh"
    assert response.json()["duration_ms"] == 1500
