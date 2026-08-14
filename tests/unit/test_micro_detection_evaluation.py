from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate_micro_detection import evaluate

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def observation(
    observation_id: str,
    *,
    event_type: str,
    expected: bool,
    predicted: bool,
) -> dict:
    return {
        "observation_id": observation_id,
        "case_id": "B-MICRO-01",
        "event_type": event_type,
        "expected": expected,
        "predicted": predicted,
        "source_ref": "authorized-audio-01.wav",
        "start_ms": 100,
        "end_ms": 400,
    }


def payload(items: list[dict], *, detector_mode: str = "real") -> dict:
    return {
        "dataset_version": "annotated-v1",
        "detector_version": "detector-v1",
        "detector_mode": detector_mode,
        "observations": items,
    }


def test_evaluation_calculates_metrics_and_reports_failures() -> None:
    result = evaluate(
        payload(
            [
                observation("o1", event_type="hesitation", expected=True, predicted=True),
                observation("o2", event_type="hesitation", expected=True, predicted=False),
                observation("o3", event_type="hesitation", expected=False, predicted=True),
                observation("o4", event_type="hesitation", expected=False, predicted=False),
            ]
        )
    )

    assert result["overall"] == {
        "true_positive": 1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 1,
        "accuracy": 0.5,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert [item["failure_type"] for item in result["failures"]] == [
        "false_negative",
        "false_positive",
    ]


def test_evaluation_rejects_mock_results() -> None:
    with pytest.raises(ValueError, match="mock detector"):
        evaluate(
            payload(
                [observation("o1", event_type="hesitation", expected=True, predicted=True)],
                detector_mode="mock",
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_ref", "", "source_ref"),
        ("start_ms", -1, "start_ms"),
        ("end_ms", 100, "end_ms"),
    ],
)
def test_evaluation_requires_traceable_audio_locations(
    field: str,
    value: object,
    message: str,
) -> None:
    item = observation("o1", event_type="hesitation", expected=True, predicted=True)
    item[field] = value
    with pytest.raises(ValueError, match=message):
        evaluate(payload([item]))


def test_evaluation_rejects_duplicate_observation_ids() -> None:
    item = observation("o1", event_type="hesitation", expected=True, predicted=True)
    with pytest.raises(ValueError, match="duplicate observation_id"):
        evaluate(payload([item, item.copy()]))


def test_frozen_difference_cases_cover_profiles_modules_and_boundaries() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "docs/member-b/micro-difference-cases.json").read_text(
            encoding="utf-8"
        )
    )
    cases = manifest["cases"]

    assert len(cases) == 10
    assert len({case["case_id"] for case in cases}) == 10
    assert {case["learner_profile"] for case in cases} == {"P1", "P2", "P3"}
    assert {case["module"] for case in cases} == {"M1", "M2", "M3"}
    assert {case["source_type"] for case in cases} == {
        "learner_voice",
        "mentor_recording",
    }
    scenarios = " ".join(case["scenario"] for case in cases)
    assert "未授权" in scenarios
    assert "重复" in scenarios
    assert "缺少audio_duration_ms" in scenarios
