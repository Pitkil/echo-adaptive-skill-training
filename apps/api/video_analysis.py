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


CHECKPOINT_RATIOS = (0.25, 0.5, 0.75)
CHECKPOINT_CONTEXT_FRAMES = 24


def resolve_ffmpeg() -> str | None:
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def probe_video_duration(video_path: Path) -> float:
    """Read the real media duration without changing the extraction cadence."""

    try:
        import imageio_ffmpeg

        _, duration = imageio_ffmpeg.count_frames_and_secs(str(video_path))
    except Exception as exc:
        raise VideoAnalysisError(f"无法读取视频时长：{exc}") from exc
    if not duration or duration <= 0:
        raise VideoAnalysisError("无法读取有效视频时长")
    return float(duration)


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


def _llm_question_from_text(text: str, knowledge_point_name: str | None) -> dict:
    """Turn OCR text into an oral-practice question using an LLM."""
    api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    base_url = os.getenv("VISION_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    model = os.getenv("VISION_MODEL") or os.getenv("OPENAI_MODEL") or ""
    if not api_key or not model:
        raise OcrUnavailable("大模型未配置（缺少 VISION_* / OPENAI_* 的模型名或密钥）")
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
    subject = knowledge_point_name or "本节内容"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "你是课程口述练习的出题助手。下面是教学视频某一帧画面识别出的文字"
                    f"（可能包含 OCR 误差），对应知识点是「{subject}」。\n"
                    "请基于这些内容，拟一道适合学习者口头回答的开放式问题，"
                    "鼓励说明理解、举例子或讲步骤，不要只问定义。\n"
                    '只返回 JSON：{"topic":"画面主题","question":"口述问题"}，不要输出多余内容。\n\n'
                    f"画面文字：\n{text}"
                ),
            }
        ],
        temperature=0.4,
    )
    return _parse_model_json(response.choices[0].message.content or "")


def _generate_question(text: str, knowledge_point_name: str | None) -> str:
    """Generate an oral-practice question, falling back to a fixed template."""
    try:
        reading = _llm_question_from_text(text, knowledge_point_name)
        question = (reading.get("question") or "").strip()
        if question:
            return question
    except Exception:
        pass
    return _template_question(text, knowledge_point_name)


def _checkpoint_context(
    readings: list[tuple[float, dict]],
    target_offset: float,
) -> str:
    """Build chronological context from prior frames plus the nearest next frame."""

    previous = [item for item in readings if item[0] <= target_offset]
    following = [item for item in readings if item[0] > target_offset]
    if len(previous) > CHECKPOINT_CONTEXT_FRAMES:
        recent_count = CHECKPOINT_CONTEXT_FRAMES // 2
        older = previous[:-recent_count]
        older_count = CHECKPOINT_CONTEXT_FRAMES - recent_count
        step = max(1, len(older) // older_count)
        selected = older[::step][-older_count:] + previous[-recent_count:]
    else:
        selected = previous
    if following:
        selected.append(following[0])
    lines = []
    for offset, reading in selected:
        text = re.sub(r"\s+", " ", str(reading.get("text") or "")).strip()
        topic = re.sub(r"\s+", " ", str(reading.get("topic") or "")).strip()
        frame_question = re.sub(r"\s+", " ", str(reading.get("question") or "")).strip()
        content = text or topic or frame_question
        if content:
            lines.append(f"[{int(offset // 60)}:{int(offset % 60):02d}] {content[:500]}")
    return "\n".join(lines)


def _llm_checkpoint_from_context(context: str, knowledge_point_name: str | None) -> dict:
    """Generate one reviewable oral checkpoint from chronological frame context."""

    api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    base_url = os.getenv("VISION_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    model = os.getenv("VISION_MODEL") or os.getenv("OPENAI_MODEL") or ""
    if not api_key or not model:
        raise OcrUnavailable("大模型未配置（缺少 VISION_* / OPENAI_* 的模型名或密钥）")
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
    subject = knowledge_point_name or "本节内容"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": (
                    "你是课程口述练习的出题助手。以下内容来自同一教学视频按时间连续抽取的多帧识别结果，"
                    "最后一帧可能略晚于检查点，仅用于补足上下文。"
                    f"对应知识点是「{subject}」。\n"
                    "请结合上下文拟一道口头回答题，检查学习者是否理解截至当前的核心内容；"
                    "不要询问画面文字，不要引入上下文没有出现的事实。"
                    "同时给出 2 至 4 条简短参考要点，供讲师审核，不能包含评分比例。\n"
                    '只返回 JSON：{"question":"口述问题","expected_points":["要点1","要点2"]}。\n\n'
                    f"连续画面上下文：\n{context}"
                ),
            }
        ],
        temperature=0.2,
    )
    return _parse_model_json(response.choices[0].message.content or "")


def _generate_contextual_checkpoint(
    context: str,
    knowledge_point_name: str | None,
) -> tuple[str, list[str]]:
    try:
        payload = _llm_checkpoint_from_context(context, knowledge_point_name)
        question = str(payload.get("question") or "").strip()
        points = [
            str(item).strip()
            for item in (payload.get("expected_points") or [])
            if str(item).strip()
        ][:4]
        if question:
            return question, points
    except Exception:
        pass
    return _template_question(context, knowledge_point_name), []


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
        readings: list[tuple[float, dict]] = []
        for time_offset, frame_path in frames:
            reading = read_frame(frame_path)
            text = (reading.get("text") or "").strip()
            question = (reading.get("question") or "").strip()
            if not question and not text:
                continue
            readings.append((time_offset, reading))

        generated = 0
        try:
            duration = video.duration_seconds or probe_video_duration(Path(video.filepath))
        except VideoAnalysisError:
            duration = None
        if duration:
            video.duration_seconds = duration
            targets = [duration * ratio for ratio in CHECKPOINT_RATIOS]
            tolerance = max(2.0, duration * 0.04)
            frozen_offsets = [
                item.time_offset_seconds
                for item in db.query(VideoCheckpoint).filter_by(video_id=video.id, status="frozen").all()
            ]
            db.query(VideoCheckpoint).filter_by(video_id=video.id, status="draft").delete()
            for target in targets:
                if any(abs(target - offset) <= tolerance for offset in frozen_offsets):
                    continue
                context = _checkpoint_context(readings, target)
                if not context:
                    continue
                question, expected_points = _generate_contextual_checkpoint(
                    context,
                    knowledge_point.name if knowledge_point else None,
                )
                db.add(
                    VideoCheckpoint(
                        video_id=video.id,
                        time_offset_seconds=round(target, 1),
                        question=question,
                        expected_points=expected_points,
                        official_sources=[],
                        status="draft",
                    )
                )
                generated += 1
        else:
            # Legacy/test media without readable duration keeps the earlier draft behavior.
            for time_offset, reading in readings:
                text = (reading.get("text") or "").strip()
                question = (reading.get("question") or "").strip()
                if not question:
                    question = _generate_question(
                        text,
                        knowledge_point.name if knowledge_point else None,
                    )
                db.add(
                    VideoCheckpoint(
                        video_id=video.id,
                        time_offset_seconds=time_offset,
                        question=question,
                        expected_points=[],
                        official_sources=[],
                        status="draft",
                    )
                )
                generated += 1
        if generated == 0:
            frozen_count = db.query(VideoCheckpoint).filter_by(video_id=video.id, status="frozen").count()
            if duration and frozen_count >= len(CHECKPOINT_RATIOS):
                job.status = "completed"
                job.error = None
            else:
                job.status = "requires_manual"
                job.error = "未能从连续画面上下文生成完整的 25%、50%、75% 口述题，请人工补充。"
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
