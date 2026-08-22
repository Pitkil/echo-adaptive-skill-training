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
    methodology = _optional_text(payload, "methodology")
    threshold = _optional_probability(payload, "threshold")
    sample_duration_seconds = _optional_positive_number(
        payload, "sample_duration_seconds"
    )

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
        "methodology": methodology,
        "threshold": threshold,
        "sample_duration_seconds": sample_duration_seconds,
        "case_ids": sorted(case_ids),
        "observation_count": len(observations),
        "micro_average": _metrics(totals),
        "macro_average": _macro_metrics(by_type),
        "overall": _metrics(totals),
        "by_event_type": {
            event_type: _metrics(counts)
            for event_type, counts in sorted(by_type.items())
        },
        "failure_summary": _failure_summary(failures),
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
        "sample_count": total,
        "expected_positive_count": tp + fn,
        "predicted_positive_count": tp + fp,
        "accuracy": _ratio(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _macro_metrics(by_type: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Average event-type metrics, treating undefined positive predictions as zero."""

    metrics = [_metrics(counts) for counts in by_type.values()]
    return {
        "event_type_count": len(metrics),
        "accuracy": _mean([item["accuracy"] for item in metrics]),
        "precision": _mean([item["precision"] or 0.0 for item in metrics]),
        "recall": _mean([item["recall"] or 0.0 for item in metrics]),
        "f1": _mean([item["f1"] or 0.0 for item in metrics]),
        "undefined_precision_treated_as_zero": True,
    }


def _mean(values: list[float | None]) -> float | None:
    defined = [value for value in values if value is not None]
    return round(sum(defined) / len(defined), 4) if defined else None


def _failure_summary(failures: list[dict[str, Any]]) -> dict[str, Any]:
    by_failure_type: dict[str, int] = defaultdict(int)
    by_event_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for failure in failures:
        failure_type = failure["failure_type"]
        event_type = failure["event_type"]
        by_failure_type[failure_type] += 1
        by_event_type[event_type][failure_type] += 1
    return {
        "total": len(failures),
        "by_failure_type": dict(sorted(by_failure_type.items())),
        "by_event_type": {
            event_type: dict(sorted(counts.items()))
            for event_type, counts in sorted(by_event_type.items())
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    """Render a deidentified, reproducible review report from evaluation results."""

    labels = {
        "hesitation": "hesitation（犹豫）",
        "guessing": "guessing（猜测）",
        "thinking_pause": "thinking_pause（思考停顿）",
    }
    lines = [
        "# 成员 B 微表征真实识别效果报告",
        "",
        "## 1. 评测信息",
        "",
        f"- 数据版本：`{result['dataset_version']}`",
        f"- 检测器版本：`{result['detector_version']}`",
        f"- 检测模式：`{result['detector_mode']}`（真实输出，不是 Mock）",
        f"- 二元观察数：{result['observation_count']}",
        f"- 脱敏录音案例数：{len(result['case_ids'])}",
        f"- 评测口径：{result.get('methodology') or '未提供'}",
        f"- 单段录音时长：{_display_metadata(result.get('sample_duration_seconds'), ' 秒')}",
        f"- 检测阈值：{_display_metadata(result.get('threshold'))}",
        "",
        "## 2. 总体指标",
        "",
        "| 汇总方式 | Accuracy | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: | ---: |",
        _metric_row("Micro", result["micro_average"]),
        _metric_row("Macro", result["macro_average"]),
        "",
        "Macro 中没有预测正例的类别，其 Precision 按 0 计入平均，避免隐藏模型完全漏检的小类别。",
        "",
        "## 3. 分类型混淆矩阵与指标",
        "",
        "| 类型 | 样本数 | 正样本 | TP | TN | FP | FN | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for event_type, metrics in result["by_event_type"].items():
        lines.append(
            "| {label} | {sample_count} | {expected_positive_count} | {true_positive} | "
            "{true_negative} | {false_positive} | {false_negative} | {precision} | "
            "{recall} | {f1} |".format(
                label=labels.get(event_type, event_type),
                **{key: _display_metric(value) for key, value in metrics.items()},
            )
        )
    summary = result["failure_summary"]
    false_positive_types = _failure_event_types(summary, "false_positive")
    false_negative_types = _failure_event_types(summary, "false_negative")
    lines.extend(
        [
            "",
            "## 4. 误检与漏检事实",
            "",
            f"共 {summary['total']} 个错误观察："
            f"FP {summary['by_failure_type'].get('false_positive', 0)}，"
            f"FN {summary['by_failure_type'].get('false_negative', 0)}。",
            "",
            f"实际误检类别：{_display_event_types(false_positive_types)}；"
            f"实际漏检类别：{_display_event_types(false_negative_types)}。"
            "未观察到的类别不会写成常见错误。",
            "",
            "### 可复查失败样例",
            "",
            "| 类型 | 失败 | 脱敏案例 | 时间范围 |",
            "| --- | --- | --- | ---: |",
        ]
    )
    examples = _balanced_failure_examples(result["failures"], limit_per_group=3)
    for item in examples:
        lines.append(
            f"| {item['event_type']} | {item['failure_type']} | `{item['case_id']}` | "
            f"{item['start_ms']}–{item['end_ms']} ms |"
        )
    lines.extend(
        [
            "",
            "## 5. 原因分析",
            "",
            "以下是待验证假设，不是由当前统计直接证明的事实：",
            "",
            "1. 当前检测阈值可能无法同时保证召回率和误检率，需要在独立验证集检查，不能用本评测集调参。",
            "2. 检测器版本与评测数据可能存在分布差异，需要模型负责人核对训练来源和 embedding 版本。",
            "3. 片段级“是否出现”口径会隐藏事件边界误差；应另用事件级匹配评测定位该问题。",
            "",
            "## 6. 验收结论",
            "",
            "真实检测链路和评测脚本可复现，但当前 Recall 与 F1 明显不足。Accuracy 受大量负样本影响，"
            "不能单独作为达标证据。成员 B 不重新训练模型；模型负责人应使用独立验证集检查版本和阈值，"
            "冻结新版本后再用本数据复测。",
            "",
        ]
    )
    return "\n".join(lines)


def _metric_row(label: str, metrics: dict[str, Any]) -> str:
    return "| {} | {} | {} | {} | {} |".format(
        label,
        _display_metric(metrics.get("accuracy")),
        _display_metric(metrics.get("precision")),
        _display_metric(metrics.get("recall")),
        _display_metric(metrics.get("f1")),
    )


def _display_metric(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _display_metadata(value: Any, suffix: str = "") -> str:
    return "未提供" if value is None else f"{value}{suffix}"


def _balanced_failure_examples(
    failures: list[dict[str, Any]],
    *,
    limit_per_group: int,
) -> list[dict[str, Any]]:
    selected = []
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for failure in failures:
        key = (failure["failure_type"], failure["event_type"])
        if counts[key] >= limit_per_group:
            continue
        selected.append(failure)
        counts[key] += 1
    return selected


def _failure_event_types(summary: dict[str, Any], failure_type: str) -> list[str]:
    return [
        event_type
        for event_type, counts in summary["by_event_type"].items()
        if counts.get(failure_type, 0) > 0
    ]


def _display_event_types(event_types: list[str]) -> str:
    return "、".join(f"`{event_type}`" for event_type in event_types) or "无"


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _required_text(item: dict[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(item: dict[str, Any], field: str) -> str | None:
    value = item.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string when provided")
    return value.strip()


def _optional_probability(item: dict[str, Any], field: str) -> float | None:
    value = item.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
        raise ValueError(f"{field} must be a number between 0 and 1 when provided")
    return float(value)


def _optional_positive_number(item: dict[str, Any], field: str) -> float | int | None:
    value = item.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field} must be a positive number when provided")
    return value


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
    parser.add_argument("--markdown-output", type=Path, help="Optional deidentified Markdown report")
    args = parser.parse_args()

    result = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(result), encoding="utf-8")


if __name__ == "__main__":
    main()
