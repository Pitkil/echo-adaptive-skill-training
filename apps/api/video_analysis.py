"""Frame extraction and OCR-backed drafting for video oral-practice checkpoints."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from config import Config
from database import CourseVideo, KnowledgePoint, VideoAnalysisJob, VideoCheckpoint
from sqlalchemy.orm import Session


class VideoAnalysisError(RuntimeError):
    """Base error for the video checkpoint generation pipeline."""


class OcrUnavailable(VideoAnalysisError):
    """Raised when neither a vision model nor local OCR is available."""


def resolve_ffmpeg() -> str | None:
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def extract_frames(
    video_path: Path,
    output_dir: Path,
    *,
    interval: int,
    max_frames: int,
) -> list[tuple[float, Path]]:
    """Sample frames at a fixed interval and return (time_offset, image_path) pairs."""

    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        raise VideoAnalysisError("ffmpeg 不可用，无法抽帧")
    output_dir.mkdir(parents=True, exist_ok=True)
    fps = 1.0 / max(1, interval)
    subprocess.run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "2",
            str(output_dir / "frame_%04d.jpg"),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    frames: list[tuple[float, Path]] = []
    for path in sorted(output_dir.glob("frame_*.jpg")):
        try:
            index = int(path.stem.split("_")[1])
        except (IndexError, ValueError):
            index = len(frames)
        frames.append((index * interval, path))
    return frames


def _parse_model_json(raw: str) -> dict:
    raw = (raw or "").strip()
    match = re.search(r"\{.*\}", raw, re.S)
    try:
        payload = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, AttributeError):
        return {"text": raw}
    return payload if isinstance(payload, dict) else {"text": raw}


def _vision_reading(image_path: Path) -> dict:
    api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    base_url = os.getenv("VISION_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    model = os.getenv("VISION_MODEL") or os.getenv("OPENAI_MODEL") or ""
    if not api_key or not model:
        raise OcrUnavailable("视觉模型未配置（缺少 VISION_* 或 OPENAI_*）")
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
    image_data = base64.b64encode(image_path.read_bytes()).decode()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "这是教学视频中的一帧。请只返回 JSON，字段为："
                            '{"topic":"本帧主题","question":"一条适合口述练习的开放式问题",'
                            '"text":"画面中的关键文字"}。不要输出多余内容。'
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                    },
                ],
            }
        ],
        temperature=0.2,
    )
    return _parse_model_json(response.choices[0].message.content or "")


def _tesseract_reading(image_path: Path) -> dict:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise OcrUnavailable("tesseract 不可用")
    result = subprocess.run(
        [tesseract, str(image_path), "stdout", "-l", "eng+chi_sim"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise VideoAnalysisError("tesseract 识别失败")
    return {"text": (result.stdout or "").strip(), "topic": "", "question": ""}


def read_frame(image_path: Path, backend: str | None = None) -> dict:
    backend = backend or Config.upload.VIDEO_OCR_BACKEND
    if backend == "vision":
        return _vision_reading(image_path)
    if backend == "tesseract":
        return _tesseract_reading(image_path)
    if backend in {"none", "manual"}:
        raise OcrUnavailable("已禁用 OCR，需人工填写口述题")
    vision_error: Exception | None = None
    tesseract_error: Exception | None = None
    try:
        return _vision_reading(image_path)
    except Exception as exc:  # noqa: BLE001 - fall back to local OCR
        vision_error = exc
    try:
        return _tesseract_reading(image_path)
    except Exception as exc:  # noqa: BLE001 - report a combined degradation
        tesseract_error = exc
    raise OcrUnavailable(
        f"视觉模型与 tesseract 均不可用（vision: {vision_error}; tesseract: {tesseract_error}）"
    )


def _template_question(text: str, knowledge_point_name: str | None) -> str:
    snippet = re.sub(r"\s+", " ", text).strip()
    snippet = snippet[:120] + ("…" if len(snippet) > 120 else "")
    subject = knowledge_point_name or "本节内容"
    if snippet:
        return f"请用自己的话说明「{subject}」这段画面的关键内容：{snippet}"
    return f"请用自己的话说明「{subject}」的关键内容，并举一个应用例子。"


def run_video_analysis(db: Session, job_id: str) -> None:
    """Run frame extraction + OCR and persist draft checkpoints for one job."""

    job = db.get(VideoAnalysisJob, job_id)
    if job is None:
        return
    job.status = "processing"
    job.updated_at = datetime.now()
    db.commit()
    video = db.get(CourseVideo, job.video_id)
    if video is None:
        _fail_job(db, job_id, "视频不存在")
        return
    frames_dir = Path(video.filepath).parent / f"{video.id}_frames"
    try:
        frames = extract_frames(
            Path(video.filepath),
            frames_dir,
            interval=Config.upload.VIDEO_FRAME_INTERVAL_SECONDS,
            max_frames=Config.upload.VIDEO_FRAME_MAX_COUNT,
        )
        job.frames_count = len(frames)
        knowledge_point = (
            db.get(KnowledgePoint, video.knowledge_point_id)
            if video.knowledge_point_id
            else None
        )
        generated = 0
        for time_offset, frame_path in frames:
            reading = read_frame(frame_path)
            text = (reading.get("text") or "").strip()
            question = (reading.get("question") or "").strip()
            if not question and not text:
                continue
            db.add(
                VideoCheckpoint(
                    video_id=video.id,
                    time_offset_seconds=time_offset,
                    question=question or _template_question(
                        text,
                        knowledge_point.name if knowledge_point else None,
                    ),
                    expected_points=[],
                    official_sources=[],
                    status="draft",
                )
            )
            generated += 1
        if generated == 0:
            job.status = "requires_manual"
            job.error = "未能从画面识别出有效内容，请人工填写口述题。"
        else:
            job.status = "completed"
            job.error = None
        job.updated_at = datetime.now()
        db.commit()
    except OcrUnavailable as exc:
        _fail_job(db, job_id, str(exc), status="requires_manual")
    except Exception as exc:  # noqa: BLE001 - persist the failure for the UI
        _fail_job(db, job_id, str(exc), status="failed")
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


def _fail_job(db: Session, job_id: str, message: str, *, status: str = "failed") -> None:
    db.rollback()
    job = db.get(VideoAnalysisJob, job_id)
    if job is not None:
        job.status = status
        job.error = message
        job.updated_at = datetime.now()
        db.commit()
