"""Offline WavLM prototype detector used by the ECHO micro service.

Only frozen inference artifacts are read from ``MICRO_MODEL_ROOT``. The module
never downloads a model and builds its tiny FAISS prototype index in memory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

WINDOW_SECONDS = 1.5
STRIDE_SECONDS = 0.5
FRAMES_PER_SECOND = 50
MERGE_GAP_SECONDS = 0.3
MIN_EVENT_SECONDS = 0.15
REQUIRED_LABELS = {"犹豫", "猜测", "思考停顿"}

_model: Any | None = None
_processor: Any | None = None
_device: str | None = None


def model_root() -> Path:
    """Return the configured directory containing frozen inference artifacts."""

    default = Path(__file__).resolve().parents[2] / "models" / "micro_detector"
    return Path(os.getenv("MICRO_MODEL_ROOT", str(default))).resolve()


def required_artifacts() -> tuple[Path, ...]:
    root = model_root()
    return (
        root / "wavlm-base-plus" / "config.json",
        root / "wavlm-base-plus" / "preprocessor_config.json",
        root / "wavlm-base-plus" / "model.safetensors",
        root / "behavior_prototypes.pt",
    )


def missing_artifacts() -> list[Path]:
    """List absent or empty model artifacts without importing heavy libraries."""

    missing = [
        path for path in required_artifacts() if not path.is_file() or path.stat().st_size == 0
    ]
    weight_path = model_root() / "wavlm-base-plus" / "model.safetensors"
    if weight_path.is_file() and weight_path.stat().st_size < 300 * 1024 * 1024:
        missing.append(weight_path)
    return list(dict.fromkeys(missing))


def _load_model() -> tuple[Any, Any, str]:
    global _device, _model, _processor
    if _model is not None and _processor is not None and _device is not None:
        return _model, _processor, _device

    missing = missing_artifacts()
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"micro detector artifacts unavailable: {names}")

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    import torch
    from transformers import Wav2Vec2FeatureExtractor, WavLMModel

    if torch.cuda.is_available():
        _device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        _device = "mps"
    else:
        _device = "cpu"

    wavlm_root = model_root() / "wavlm-base-plus"
    _processor = Wav2Vec2FeatureExtractor.from_pretrained(
        wavlm_root,
        local_files_only=True,
    )
    _model = WavLMModel.from_pretrained(
        wavlm_root,
        local_files_only=True,
        use_safetensors=True,
    )
    _model.to(_device)
    _model.eval()
    return _model, _processor, _device


def _aggregate_windows(frame_embeddings: Any) -> Any | None:
    import torch

    window_frames = int(WINDOW_SECONDS * FRAMES_PER_SECOND)
    stride_frames = int(STRIDE_SECONDS * FRAMES_PER_SECOND)
    if frame_embeddings.shape[0] < window_frames:
        return None
    windows = []
    for start in range(0, frame_embeddings.shape[0] - window_frames + 1, stride_frames):
        chunk = frame_embeddings[start : start + window_frames]
        windows.append(torch.cat([chunk.mean(dim=0), chunk.std(dim=0)]))
    return torch.stack(windows)


def extract_embeddings_batch(
    audio_paths: list[Path],
    output_dir: Path,
    batch_size: int = 4,
) -> dict[str, Path]:
    """Extract frame-level embeddings from 16 kHz audio without network access."""

    import soundfile
    import torch

    model, processor, device = _load_model()
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}

    for batch_start in range(0, len(audio_paths), batch_size):
        batch_paths = audio_paths[batch_start : batch_start + batch_size]
        waveforms = []
        for audio_path in batch_paths:
            samples, sample_rate = soundfile.read(str(audio_path))
            if sample_rate != 16_000:
                raise RuntimeError(f"{audio_path.name}: expected 16000 Hz, got {sample_rate}")
            if samples.ndim > 1:
                samples = samples.mean(axis=1)
            waveforms.append(samples)

        inputs = processor(
            waveforms,
            sampling_rate=16_000,
            return_attention_mask=True,
            return_tensors="pt",
            padding=True,
        )
        sample_lengths = inputs["attention_mask"].sum(dim=-1)
        device_inputs = {name: value.to(device) for name, value in inputs.items()}
        with torch.no_grad():
            outputs = model(**device_inputs)
        feature_lengths = model._get_feat_extract_output_lengths(sample_lengths).tolist()

        for index, audio_path in enumerate(batch_paths):
            embedding = outputs.last_hidden_state[index, : feature_lengths[index], :].cpu()
            destination = output_dir / f"{audio_path.stem}.pt"
            torch.save(embedding, destination)
            results[audio_path.name] = destination
    return results


def _load_prototypes() -> dict[str, Any]:
    import torch

    prototype_path = model_root() / "behavior_prototypes.pt"
    prototypes = torch.load(prototype_path, map_location="cpu", weights_only=True)
    if not isinstance(prototypes, dict) or not REQUIRED_LABELS.issubset(prototypes):
        raise RuntimeError("behavior prototype file has invalid labels")
    return prototypes


def _merge_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []
    events.sort(key=lambda event: (event["file"], event["label"], event["start"]))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        groups.setdefault((event["file"], event["label"]), []).append(event)

    merged = []
    for group in groups.values():
        current: dict[str, Any] | None = None
        for event in group:
            if current is None:
                current = event.copy()
            elif event["start"] - current["end"] <= MERGE_GAP_SECONDS:
                current["end"] = event["end"]
                current["score"] = max(current["score"], event["score"])
            else:
                if current["end"] - current["start"] >= MIN_EVENT_SECONDS:
                    merged.append(current)
                current = event.copy()
        if current and current["end"] - current["start"] >= MIN_EVENT_SECONDS:
            merged.append(current)
    return merged


def run_detection(
    embedding_dir: Path,
    threshold: float,
    _: Path | None = None,
) -> list[dict[str, Any]]:
    """Yield progress-compatible prototype matching results."""

    import faiss
    import numpy as np
    import torch

    prototypes = _load_prototypes()
    labels = sorted(REQUIRED_LABELS)
    prototype_matrix = torch.stack([prototypes[label] for label in labels])
    prototype_matrix = torch.nn.functional.normalize(prototype_matrix, p=2, dim=1)
    index = faiss.IndexFlatIP(prototype_matrix.shape[1])
    index.add(prototype_matrix.numpy().astype(np.float32))

    raw_events = []
    for embedding_path in sorted(embedding_dir.glob("*.pt")):
        frame_embeddings = torch.load(embedding_path, map_location="cpu", weights_only=True)
        window_embeddings = _aggregate_windows(frame_embeddings)
        if window_embeddings is None:
            continue
        normalized = torch.nn.functional.normalize(window_embeddings, p=2, dim=1)
        scores, indices = index.search(normalized.numpy().astype(np.float32), len(labels))
        for window_index in range(scores.shape[0]):
            for result_index in range(scores.shape[1]):
                score = float(scores[window_index, result_index])
                if score <= threshold:
                    continue
                raw_events.append(
                    {
                        "file": f"{embedding_path.stem}.wav",
                        "label": labels[int(indices[window_index, result_index])],
                        "start": round(window_index * STRIDE_SECONDS, 2),
                        "end": round(window_index * STRIDE_SECONDS + WINDOW_SECONDS, 2),
                        "score": round(score, 4),
                    }
                )
    return _merge_events(raw_events)


def merge_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _merge_events(events)
