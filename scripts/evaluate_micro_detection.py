"""Calculate reproducible micro-representation detection metrics from labeled data."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

EVENT_TYPES = {
    "hesitation",
    "guessing",
    "thinking_pause",
    "uncertainty",
    "self_correction",
    "other",
}


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate labeled binary observations and return overall and per-type metrics."""

    dataset_version = _required_text(payload, "dataset_version")
    detector_version = _required_text(payload, "detector_version")
    detector_mode = _required_text(payload, "detector_mode")
    if detector_mode.casefold() == "mock":
        raise ValueError("mock detector output cannot be used for detection metrics")

    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must be a non-empty list")

    totals = _empty_counts()
    by_type: dict[str, dict[str, int]] = defaultdict(_empty_counts)
    seen_ids: set[str] = set()
    failures: list[dict[str, Any]] = []
    case_ids: set[str] = set()

    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("each observation must be an object")
        observation_id = _required_text(item, "observation_id")
        if observation_id in seen_ids:
            raise ValueError(f"duplicate observation_id: {observation_id}")
        seen_ids.add(observation_id)
        case_id = _required_text(item, "case_id")
        case_ids.add(case_id)
        event_type = _required_text(item, "event_type")
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported event_type: {event_type}")
        expected = _required_bool(item, "expected")
        predicted = _required_bool(item, "predicted")
        _validate_evidence_location(item)

        bucket = _classification_bucket(expected, predicted)
        totals[bucket] += 1
        by_type[event_type][bucket] += 1
        if expected != predicted:
            failures.append(
                {
                    "observation_id": observation_id,
                    "case_id": case_id,
                    "event_type": event_type,
                    "failure_type": "false_negative" if expected else "false_positive",
                    "source_ref": item["source_ref"],
                    "start_ms": item["start_ms"],
                    "end_ms": item["end_ms"],
                }
            )

    return {
        "dataset_version": dataset_version,
        "detector_version": detector_version,
        "detector_mode": detector_mode,
        "case_ids": sorted(case_ids),
        "observation_count": len(observations),
        "overall": _metrics(totals),
        "by_event_type": {
            event_type: _metrics(counts)
            for event_type, counts in sorted(by_type.items())
        },
        "failures": failures,
    }


def _empty_counts() -> dict[str, int]:
    return {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0}


def _classification_bucket(expected: bool, predicted: bool) -> str:
    if expected and predicted:
        return "true_positive"
    if not expected and not predicted:
        return "true_negative"
    if predicted:
        return "false_positive"
    return "false_negative"


def _metrics(counts: dict[str, int]) -> dict[str, Any]:
    tp = counts["true_positive"]
    tn = counts["true_negative"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    total = tp + tn + fp + fn
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = _ratio(2 * tp, 2 * tp + fp + fn)
    return {
        **counts,
        "accuracy": _ratio(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _required_text(item: dict[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _required_bool(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _validate_evidence_location(item: dict[str, Any]) -> None:
    _required_text(item, "source_ref")
    start_ms = item.get("start_ms")
    end_ms = item.get("end_ms")
    if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
        raise ValueError("start_ms must be a non-negative integer")
    if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms <= start_ms:
        raise ValueError("end_ms must be an integer greater than start_ms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate Accuracy, Precision, Recall and F1 for labeled micro events."
    )
    parser.add_argument("input", type=Path, help="UTF-8 JSON labeled observation file")
    parser.add_argument("--output", type=Path, help="Optional UTF-8 JSON report path")
    args = parser.parse_args()

    result = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
