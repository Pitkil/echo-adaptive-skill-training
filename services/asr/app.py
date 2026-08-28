"""Small, CPU-friendly Whisper transcription service for ECHO voice answers."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-tiny")
DEVICE = os.getenv("ASR_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "int8")
DOWNLOAD_ROOT = Path(os.getenv("ASR_DOWNLOAD_ROOT", "/models"))
MAX_AUDIO_BYTES = int(os.getenv("ASR_MAX_AUDIO_BYTES", str(100 * 1024 * 1024)))

app = FastAPI(title="ECHO ASR", version="1.0.0")
_model = None
_model_lock = asyncio.Lock()


class TranscriptionResponse(BaseModel):
    status: str
    text: str
    language: str | None = None
    duration_ms: int | None = None
    model: str


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            MODEL_ID,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            download_root=str(DOWNLOAD_ROOT),
        )
    return _model


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ready",
        "service": "asr",
        "version": "1.0.0",
        "mode": "faster-whisper",
        "model": MODEL_ID,
        "model_loaded": _model is not None,
    }


@app.post("/v1/asr/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    audio: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
) -> TranscriptionResponse:
    size = 0
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="echo-asr-", suffix=suffix, delete=False) as output:
            temporary_path = Path(output.name)
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_AUDIO_BYTES:
                    raise HTTPException(status_code=413, detail="audio exceeds ASR size limit")
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="audio is empty")
        try:
            async with _model_lock:
                model = await asyncio.to_thread(_load_model)
            segments, info = await asyncio.to_thread(
                model.transcribe,
                str(temporary_path),
                language=(language or None),
                beam_size=1,
                best_of=1,
                vad_filter=True,
            )
            text = "".join(segment.text for segment in segments).strip()
            return TranscriptionResponse(
                status="completed",
                text=text,
                language=getattr(info, "language", None),
                duration_ms=(
                    int(float(info.duration) * 1000)
                    if getattr(info, "duration", None) is not None
                    else None
                ),
                model=MODEL_ID,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"ASR model unavailable: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
