"""Run the frozen ECHO detector over the controlled labeled dataset.

This script reuses precomputed embeddings, so it does not need to re-encode
audio. It produces raw interval predictions plus clip/type observations that
``evaluate_micro_detection.py`` can score reproducibly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.micro_detector_real.detector import (  # noqa: E402
    STRIDE_SECONDS,
    WINDOW_SECONDS,
    _aggregate_windows,
    _load_prototypes,
    _merge_events,
)

LABEL_MAP = {
    "犹豫": "hesitation",
    "猜测": "guessing",
    "思考停顿": "thinking_pause",
}
EVENT_TYPES = tuple(LABEL_MAP.values())


def run_detection(
    dataset_root: Path,
    model_root: Path,
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return raw predictions and clip/type binary observations."""

    import torch

    os.environ["MICRO_MODEL_ROOT"] = str(model_root.resolve())
    labels_payload = json.loads(
        (dataset_root / "labels" / "ground_truth.json").read_text(encoding="utf-8")
    )
    prototypes = _load_prototypes()
    predictions: list[dict[str, Any]] = []

    for sample in labels_payload["samples"]:
        audio_path = Path(sample["audio_path"])
        embedding_path = next(
            (dataset_root / "embeddings").rglob(f"{audio_path.stem}.pt"),
            None,
        )
        if embedding_path is None:
            raise FileNotFoundError(f"embedding not found for {audio_path.name}")
        frame_embeddings = torch.load(embedding_path, map_location="cpu", weights_only=True)
        window_embeddings = _aggregate_windows(frame_embeddings)
        if window_embeddings is None:
            continue
        raw_events = []
        for raw_label, prototype in prototypes.items():
            event_type = LABEL_MAP.get(raw_label)
            if event_type is None:
                continue
            similarities = torch.cosine_similarity(
                window_embeddings,
                prototype.unsqueeze(0),
                dim=-1,
            )
            for index in (similarities > threshold).nonzero(as_tuple=True)[0]:
                raw_events.append(
                    {
                        "file": sample["sample_id"],
                        "label": event_type,
                        "start": round(index.item() * STRIDE_SECONDS, 2),
                        "end": round(index.item() * STRIDE_SECONDS + WINDOW_SECONDS, 2),
                        "score": round(similarities[index].item(), 4),
                    }
                )
        for event in _merge_events(raw_events):
            predictions.append(
                {
                    "sample_id": sample["sample_id"],
                    "event_type": event["label"],
                    "start_ms": round(event["start"] * 1000),
                    "end_ms": round(event["end"] * 1000),
                    "confidence": event["score"],
                }
            )

    by_sample: dict[str, list[dict[str, Any]]] = {}
    for prediction in predictions:
        by_sample.setdefault(prediction["sample_id"], []).append(prediction)
    observations = []
    for sample in labels_payload["samples"]:
        expected_events = sample["events"]
        predicted_events = by_sample.get(sample["sample_id"], [])
        for event_type in EVENT_TYPES:
            expected_match = next(
                (event for event in expected_events if event["event_type"] == event_type),
                None,
            )
            predicted_match = next(
                (event for event in predicted_events if event["event_type"] == event_type),
                None,
            )
            evidence = expected_match or predicted_match or {"start_ms": 0, "end_ms": 30_000}
            observations.append(
                {
                    "observation_id": f"{sample['sample_id']}:{event_type}",
                    "case_id": sample["sample_id"],
                    "event_type": event_type,
                    "expected": expected_match is not None,
                    "predicted": predicted_match is not None,
                    "source_ref": sample["audio_path"],
                    "start_ms": evidence["start_ms"],
                    "end_ms": evidence["end_ms"],
                }
            )
    return predictions, observations


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the frozen real ECHO detector evaluation")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/micro-evaluation"),
    )
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("models/micro_detector"),
    )
    parser.add_argument("--threshold", type=float, default=0.51)
    args = parser.parse_args()
    if not 0 < args.threshold < 1:
        parser.error("threshold must be between 0 and 1")

    predictions, observations = run_detection(
        args.dataset_root,
        args.model_root,
        args.threshold,
    )
    predictions_dir = args.dataset_root / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    (predictions_dir / "echo-wavlm-v2-events.json").write_text(
        json.dumps({"threshold": args.threshold, "items": predictions}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    evaluation_input = {
        "dataset_version": "micro-evaluation-130-v1",
        "detector_version": "echo-wavlm-prototype-v2",
        "detector_mode": "real-precomputed-embeddings",
        "methodology": "binary presence per 30-second sample and event type",
        "threshold": args.threshold,
        "sample_duration_seconds": 30,
        "observations": observations,
    }
    input_path = predictions_dir / "echo-wavlm-v2-observations.json"
    input_path.write_text(
        json.dumps(evaluation_input, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"predictions={len(predictions)} observations={len(observations)}")
    print(input_path)


if __name__ == "__main__":
    main()
