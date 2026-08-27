"""Expose the offline WavLM detector through the ECHO v1 HTTP contract."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

SERVICE_VERSION = "echo-wavlm-prototype-v2"
DEFAULT_JOB_STORE = Path(__file__).resolve().parents[2] / "data" / "micro-detector-real" / "jobs.json"
SEGMENT_DURATION_SECONDS = 30
DEFAULT_MAX_AUDIO_BYTES = 100 * 1024 * 1024
LABEL_MAP = {
    "犹豫": "hesitation",
    "猜测": "guessing",
    "思考停顿": "thinking_pause",
}


class DetectionJob(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    status: Literal["queued", "processing", "completed", "failed"]
    error_message: str | None = None
    audio_duration_ms: int | None = Field(default=None, gt=0)


class DetectionEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    job_id: str = Field(min_length=1, max_length=100)
    organization_id: int
    learner_id: int | None = None
    session_id: int | None = None
    module_id: int
    knowledge_point_id: int | None = None
    source_type: Literal["learner_voice", "mentor_recording"]
    event_type: Literal["hesitation", "guessing", "thinking_pause"]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    evidence_uri: str | None = None
    speaker_mapping_confirmed: bool = False


class StoredJob(BaseModel):
    result: DetectionJob
    scope: dict[str, Any]
    events: list[DetectionEvent] = Field(default_factory=list)


_jobs: dict[str, StoredJob] = {}
_jobs_lock = threading.Lock()


def _job_store_path() -> Path:
    return Path(os.getenv("MICRO_DETECTOR_JOB_STORE", str(DEFAULT_JOB_STORE))).resolve()


def _max_audio_bytes() -> int:
    raw_value = os.getenv("MICRO_DETECTOR_MAX_AUDIO_BYTES", str(DEFAULT_MAX_AUDIO_BYTES))
    try:
        max_audio_bytes = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("MICRO_DETECTOR_MAX_AUDIO_BYTES must be a positive integer") from exc
    if max_audio_bytes <= 0:
        raise RuntimeError("MICRO_DETECTOR_MAX_AUDIO_BYTES must be a positive integer")
    return max_audio_bytes


def _persist_jobs_locked() -> None:
    """Atomically persist detector results without storing raw audio."""

    destination = _job_store_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    payload = {
        "schema_version": "1.0",
        "detector_version": SERVICE_VERSION,
        "jobs": {
            job_id: stored.model_dump(mode="json")
            for job_id, stored in sorted(_jobs.items())
        },
    }
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _restore_jobs() -> None:
    """Restore completed jobs and fail interrupted work explicitly after restart."""

    source = _job_store_path()
    with _jobs_lock:
        _jobs.clear()
        if not source.is_file():
            return
        payload = json.loads(source.read_text(encoding="utf-8"))
        raw_jobs = payload.get("jobs")
        if not isinstance(raw_jobs, dict):
            raise RuntimeError("micro detector job store has invalid jobs payload")
        for job_id, raw in raw_jobs.items():
            stored = StoredJob.model_validate(raw)
            if stored.result.job_id != job_id:
                raise RuntimeError("micro detector job store contains mismatched job_id")
            if stored.result.status in {"queued", "processing"}:
                stored.result = stored.result.model_copy(
                    update={
                        "status": "failed",
                        "error_message": "detector restarted before job completion; resubmit safely",
                    }
                )
            _jobs[job_id] = stored
        _persist_jobs_locked()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _restore_jobs()
    yield


app = FastAPI(
    title="ECHO Offline WavLM Micro Detector",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


def _load_detector_dependencies() -> tuple[Any, Any, Any]:
    if os.getenv("MICRO_DETECTOR_OFFLINE_MODE", "true").casefold() == "true":
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from services.micro_detector_real.detector import (
        extract_embeddings_batch,
        merge_events,
        run_detection,
    )

    return extract_embeddings_batch, run_detection, merge_events


def _segment_audio(input_path: Path, output_dir: Path) -> list[tuple[Path, int]]:
    """Convert audio to 16 kHz WAV segments and retain original time offsets."""

    output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None:
        return _segment_pcm_wav(input_path, output_dir)
    output_pattern = output_dir / "segment_%04d.wav"
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-sample_fmt",
        "s16",
        "-f",
        "segment",
        "-segment_time",
        str(SEGMENT_DURATION_SECONDS),
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        reason = (result.stderr or "ffmpeg audio conversion failed").strip()
        raise RuntimeError(reason[:500])
    segments = sorted(output_dir.glob("segment_*.wav"))
    if not segments:
        raise RuntimeError("audio conversion produced no segments")
    return [
        (segment, index * SEGMENT_DURATION_SECONDS * 1000)
        for index, segment in enumerate(segments)
    ]


def _segment_pcm_wav(input_path: Path, output_dir: Path) -> list[tuple[Path, int]]:
    """Segment an already-normalized PCM WAV when ffmpeg is unavailable."""

    if input_path.suffix.casefold() != ".wav":
        raise RuntimeError("ffmpeg is unavailable; real detector accepts 16 kHz PCM WAV only")
    try:
        with wave.open(str(input_path), "rb") as source:
            if (
                source.getframerate() != 16_000
                or source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getcomptype() != "NONE"
            ):
                raise RuntimeError(
                    "ffmpeg is unavailable; WAV must be mono 16 kHz signed 16-bit PCM"
                )
            frames_per_segment = SEGMENT_DURATION_SECONDS * source.getframerate()
            parameters = source.getparams()
            segments: list[tuple[Path, int]] = []
            index = 0
            while frames := source.readframes(frames_per_segment):
                destination = output_dir / f"segment_{index:04d}.wav"
                with wave.open(str(destination), "wb") as target:
                    target.setparams(parameters)
                    target.writeframes(frames)
                segments.append((destination, index * SEGMENT_DURATION_SECONDS * 1000))
                index += 1
    except (EOFError, wave.Error) as exc:
        raise RuntimeError(f"invalid PCM WAV: {exc}") from exc
    if not segments:
        raise RuntimeError("audio conversion produced no segments")
    return segments


def _restore_original_timeline(
    raw_results: list[dict[str, Any]],
    segment_offsets: dict[str, int],
    merge_events: Any,
    source_name: str,
) -> list[dict[str, Any]]:
    """Translate segment-local event times back to the original recording."""

    restored = []
    for raw in raw_results:
        segment_name = str(raw.get("file", ""))
        if segment_name not in segment_offsets:
            raise RuntimeError(f"detector returned an unknown audio segment: {segment_name}")
        offset_seconds = segment_offsets[segment_name] / 1000
        restored.append(
            {
                **raw,
                "file": source_name,
                "start": float(raw["start"]) + offset_seconds,
                "end": float(raw["end"]) + offset_seconds,
            }
        )
    return merge_events(restored)


def _run_time_aligned_pipeline(input_path: Path) -> tuple[list[dict[str, Any]], int]:
    """Detect events while preserving offsets across long-recording segments."""

    extract_embeddings_batch, run_detection, merge_events = _load_detector_dependencies()
    with tempfile.TemporaryDirectory(prefix="echo-micro-analysis-") as temp_name:
        work_dir = Path(temp_name)
        segments = _segment_audio(input_path, work_dir / "segments")
        segment_durations = [_wav_duration_ms(segment) for segment, _ in segments]
        if any(duration is None for duration in segment_durations):
            raise RuntimeError("converted audio segment duration is unavailable")
        audio_duration_ms = sum(duration for duration in segment_durations if duration is not None)
        embedding_dir = work_dir / "embeddings"
        extract_embeddings_batch(
            [segment for segment, _ in segments],
            embedding_dir,
            batch_size=4,
        )
        raw_results = run_detection(embedding_dir, 0.51, input_path)
        offsets = {segment.name: offset for segment, offset in segments}
        return (
            _restore_original_timeline(
                raw_results,
                offsets,
                merge_events,
                input_path.name,
            ),
            audio_duration_ms,
        )


def _wav_duration_ms(path: Path) -> int | None:
    if path.suffix.casefold() != ".wav":
        return None
    try:
        with wave.open(str(path), "rb") as audio:
            duration = round(audio.getnframes() / audio.getframerate() * 1000)
    except (EOFError, wave.Error, ZeroDivisionError):
        return None
    return duration if duration > 0 else None


def _update_job(job_id: str, **changes: Any) -> None:
    with _jobs_lock:
        stored = _jobs[job_id]
        stored.result = stored.result.model_copy(update=changes)
        _persist_jobs_locked()


def _detect(job_id: str, audio_path: Path) -> None:
    try:
        _update_job(job_id, status="processing", error_message=None)
        with _jobs_lock:
            scope = dict(_jobs[job_id].scope)
        raw_results, audio_duration_ms = _run_time_aligned_pipeline(audio_path)

        events = []
        for index, raw in enumerate(raw_results, start=1):
            event_type = LABEL_MAP.get(str(raw.get("label")))
            if event_type is None:
                continue
            start_ms = max(0, round(float(raw["start"]) * 1000))
            end_ms = min(round(float(raw["end"]) * 1000), audio_duration_ms)
            if end_ms <= start_ms:
                continue
            events.append(
                DetectionEvent(
                    event_id=f"{job_id}-event-{index}",
                    job_id=job_id,
                    organization_id=scope["organization_id"],
                    learner_id=scope.get("learner_id"),
                    session_id=scope.get("session_id"),
                    module_id=scope["module_id"],
                    knowledge_point_id=scope.get("knowledge_point_id"),
                    source_type=scope["source_type"],
                    event_type=event_type,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    confidence=float(raw["score"]),
                    evidence_uri=f"detector://{job_id}/{index}",
                    speaker_mapping_confirmed=scope["speaker_mapping_confirmed"],
                )
            )
        with _jobs_lock:
            stored = _jobs[job_id]
            stored.events = events
            stored.result = stored.result.model_copy(
                update={
                    "status": "completed",
                    "error_message": None,
                    "audio_duration_ms": audio_duration_ms,
                }
            )
            _persist_jobs_locked()
    except (ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        try:
            _update_job(job_id, status="failed", error_message=str(exc)[:500])
        except (KeyError, OSError):
            pass
    finally:
        audio_path.unlink(missing_ok=True)


@app.get("/health")
def health() -> dict[str, str]:
    from services.micro_detector_real.detector import missing_artifacts

    missing = missing_artifacts()
    if missing:
        names = ", ".join(path.name for path in missing)
        raise HTTPException(
            status_code=503,
            detail=f"offline detector artifacts unavailable: {names}",
        )
    audio_mode = "all_supported_formats" if shutil.which("ffmpeg") else "pcm_wav_only"
    return {
        "status": "ok",
        "mode": "real",
        "detector_version": SERVICE_VERSION,
        "audio_mode": audio_mode,
    }


@app.post("/v1/detection/jobs", response_model=DetectionJob)
async def create_job(
    background_tasks: BackgroundTasks,
    audio: Annotated[UploadFile, File()],
    trace_id: Annotated[str, Form(min_length=1, max_length=64)],
    organization_id: Annotated[int, Form(gt=0)],
    program_id: Annotated[int, Form(gt=0)],
    module_id: Annotated[int, Form(gt=0)],
    source_type: Annotated[Literal["learner_voice", "mentor_recording"], Form()],
    consent_granted: Annotated[bool, Form()],
    learner_id: Annotated[int | None, Form(gt=0)] = None,
    session_id: Annotated[int | None, Form(gt=0)] = None,
    knowledge_point_id: Annotated[int | None, Form(gt=0)] = None,
    speaker_mapping_confirmed: Annotated[bool, Form()] = False,
) -> DetectionJob:
    if not consent_granted:
        raise HTTPException(status_code=422, detail="consent_granted must be true")
    if source_type == "learner_voice" and learner_id is None:
        raise HTTPException(status_code=422, detail="learner voice requires learner_id")
    if source_type == "mentor_recording" and speaker_mapping_confirmed != (learner_id is not None):
        raise HTTPException(
            status_code=422,
            detail="mentor learner_id requires confirmed speaker mapping",
        )

    suffix = Path(audio.filename or "recording.wav").suffix.casefold()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}:
        raise HTTPException(status_code=415, detail="unsupported audio format")
    temp_root = Path(tempfile.gettempdir()) / "echo-micro-detector"
    temp_root.mkdir(parents=True, exist_ok=True)
    audio_path = temp_root / f"{uuid.uuid4().hex}{suffix}"
    received_bytes = 0
    try:
        with audio_path.open("wb") as target:
            while chunk := await audio.read(1024 * 1024):
                received_bytes += len(chunk)
                if received_bytes > _max_audio_bytes():
                    raise HTTPException(status_code=413, detail="audio file is too large")
                target.write(chunk)
    except (HTTPException, OSError, RuntimeError):
        audio_path.unlink(missing_ok=True)
        raise
    finally:
        await audio.close()
    if received_bytes == 0:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="audio file is empty")

    job_id = f"speech-{uuid.uuid4().hex}"
    result = DetectionJob(
        job_id=job_id,
        status="queued",
        audio_duration_ms=_wav_duration_ms(audio_path),
    )
    scope = {
        "trace_id": trace_id,
        "organization_id": organization_id,
        "learner_id": learner_id,
        "session_id": session_id,
        "module_id": module_id,
        "program_id": program_id,
        "knowledge_point_id": knowledge_point_id,
        "source_type": source_type,
        "speaker_mapping_confirmed": speaker_mapping_confirmed,
    }
    try:
        with _jobs_lock:
            _jobs[job_id] = StoredJob(result=result, scope=scope)
            _persist_jobs_locked()
    except OSError as exc:
        with _jobs_lock:
            _jobs.pop(job_id, None)
        audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="failed to persist detection job") from exc
    background_tasks.add_task(_detect, job_id, audio_path)
    return result


@app.get("/v1/detection/jobs/{job_id}", response_model=DetectionJob)
def get_job(job_id: str) -> DetectionJob:
    with _jobs_lock:
        stored = _jobs.get(job_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="detection job not found")
        return stored.result.model_copy(deep=True)


@app.get("/v1/detection/jobs/{job_id}/events")
def get_events(job_id: str) -> dict[str, list[DetectionEvent]]:
    with _jobs_lock:
        stored = _jobs.get(job_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="detection job not found")
        if stored.result.status != "completed":
            raise HTTPException(status_code=409, detail="detection job is not completed")
        return {"items": [event.model_copy(deep=True) for event in stored.events]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8030)
