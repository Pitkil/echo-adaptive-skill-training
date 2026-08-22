from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate_micro_detection import evaluate, render_markdown

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
        "methodology": "binary presence per sample and event type",
        "threshold": 0.51,
        "sample_duration_seconds": 30,
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
        "sample_count": 4,
        "expected_positive_count": 2,
        "predicted_positive_count": 2,
        "accuracy": 0.5,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert [item["failure_type"] for item in result["failures"]] == [
        "false_negative",
        "false_positive",
    ]
    assert result["micro_average"] == result["overall"]
    assert result["macro_average"]["f1"] == 0.5
    assert result["failure_summary"]["total"] == 2


def test_markdown_report_contains_deidentified_metrics_and_failure_examples() -> None:
    result = evaluate(
        payload(
            [
                observation("o1", event_type="hesitation", expected=True, predicted=False),
                observation("o2", event_type="guessing", expected=False, predicted=True),
            ]
        )
    )

    report = render_markdown(result)

    assert "Micro" in report
    assert "Macro" in report
    assert "binary presence per sample and event type" in report
    assert "检测阈值：0.51" in report
    assert "B-MICRO-01" in report
    assert "authorized-audio-01.wav" not in report
    assert "实际误检类别：`guessing`" in report
    assert "实际漏检类别：`hesitation`" in report
    assert "待验证假设" in report


def test_evaluation_rejects_mock_results() -> None:
    with pytest.raises(ValueError, match="mock detector"):
        evaluate(
            payload(
                [observation("o1", event_type="hesitation", expected=True, predicted=True)],
                detector_mode="mock",
            )
        )

    with pytest.raises(ValueError, match="mock detector"):
        evaluate(
            payload(
                [observation("o2", event_type="hesitation", expected=True, predicted=True)],
                detector_mode="Mock",
            )
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("threshold", 1.0, "threshold must be a number between 0 and 1"),
        ("threshold", True, "threshold must be a number between 0 and 1"),
        ("sample_duration_seconds", 0, "sample_duration_seconds must be a positive number"),
        ("methodology", " ", "methodology must be a non-empty string"),
    ],
)
def test_evaluation_rejects_invalid_metadata(field, value, message) -> None:
    candidate = payload(
        [observation("o1", event_type="hesitation", expected=True, predicted=True)]
    )
    candidate[field] = value

    with pytest.raises(ValueError, match=message):
        evaluate(candidate)


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

    assert manifest["version"] == "b-micro-cases-v2"
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

    required_fields = {
        "consent_granted",
        "speaker_status",
        "input_events",
        "expected_retained_events",
        "expected_filtered_events",
        "enters_personal_profile",
        "evidence_to_c",
        "summary_to_a",
        "expected_failure_reason",
        "retryable",
        "coverage_tags",
    }
    for case in cases:
        assert required_fields <= case.keys()
        assert isinstance(case["consent_granted"], bool)
        assert isinstance(case["enters_personal_profile"], bool)
        assert isinstance(case["retryable"], bool)
        assert case["speaker_status"] in {
            "learner_self",
            "confirmed",
            "unconfirmed",
        }
        for event in case["input_events"]:
            assert 0 <= event["confidence"] <= 1
            assert 0 <= event["start_ms"] < event["end_ms"]
        expected_pause_ms = sum(
            event["end_ms"] - event["start_ms"]
            for event in case["input_events"]
            if event["event_type"] in {"hesitation", "thinking_pause"}
        )
        assert case["summary_to_a"]["total_pause_ms"] == expected_pause_ms

    for field in ("learner_profile", "module"):
        values = {case[field] for case in cases}
        assert min(sum(case[field] == value for case in cases) for value in values) >= 3

    tags = {tag for case in cases for tag in case["coverage_tags"]}
    assert {
        "unauthorized",
        "low_confidence",
        "speaker_unconfirmed",
        "service_unavailable",
        "legal_empty_result",
        "missing_duration",
        "time_change",
    } <= tags
