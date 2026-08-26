"""Competition evaluation loading, validation, scoring, and report export."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

EXPECTED_CASE_COUNT = 50
AGENT_NAMES = ("analysis", "generation", "validation", "next_action")
THRESHOLDS = {
    "hallucination_rate": {"operator": "lt", "value": 0.05},
    "difficulty_adaptation_rate": {"operator": "gte", "value": 0.85},
    "knowledge_coverage_rate": {"operator": "gte", "value": 0.90},
    "citation_traceability_rate": {"operator": "gte", "value": 1.0},
    "closed_loop_completeness_rate": {"operator": "gte", "value": 1.0},
}


class EvaluationDataError(ValueError):
    """Raised when frozen cases or actual results are incomplete or inconsistent."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_frozen_cases(path: Path, *, expected_count: int = EXPECTED_CASE_COUNT) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise EvaluationDataError("Frozen evaluation file must contain a cases list.")
    if len(cases) != expected_count:
        raise EvaluationDataError(
            f"Expected {expected_count} frozen cases, found {len(cases)}."
        )

    required = {
        "case_id",
        "learner_type",
        "module",
        "knowledge_point",
        "scenario_type",
        "input",
        "expected",
        "judgment",
    }
    identifiers: list[str] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise EvaluationDataError(f"Case {index} must be an object.")
        missing = sorted(required - set(case))
        if missing:
            raise EvaluationDataError(
                f"Case {case.get('case_id', index)} is missing: {', '.join(missing)}."
            )
        case_id = str(case["case_id"]).strip()
        if not case_id:
            raise EvaluationDataError(f"Case {index} has an empty case_id.")
        identifiers.append(case_id)
    duplicates = sorted({case_id for case_id in identifiers if identifiers.count(case_id) > 1})
    if duplicates:
        raise EvaluationDataError(f"Duplicate case_id values: {', '.join(duplicates)}.")
    return cases


def result_path(results_dir: Path, case_id: str) -> Path:
    return results_dir / f"case-{case_id}.json"


def pending_cases(
    cases: Iterable[dict],
    results_dir: Path,
    *,
    selected_case_ids: set[str] | None = None,
) -> list[dict]:
    selected = selected_case_ids or {str(case["case_id"]) for case in cases}
    return [
        case
        for case in cases
        if str(case["case_id"]) in selected
        and not result_path(results_dir, str(case["case_id"])).exists()
    ]


def load_actual_results(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(results_dir.glob("case-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise EvaluationDataError(f"Actual result must be an object: {path}.")
        if not str(payload.get("case_id") or "").strip():
            raise EvaluationDataError(f"Actual result has no case_id: {path}.")
        rows.append(payload)
    identifiers = [str(row["case_id"]) for row in rows]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise EvaluationDataError(f"Duplicate actual results: {', '.join(duplicates)}.")
    return rows


def is_official_microsoft_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower().rstrip("/")
    if parsed.scheme != "https":
        return False
    if host == "learn.microsoft.com":
        return True
    return host == "github.com" and path.startswith("/microsoft/semantic-kernel")


def citation_is_traceable(citation: dict) -> bool:
    url = str(citation.get("source_url") or "").strip()
    return all(
        (
            str(citation.get("source_title") or "").strip(),
            url,
            str(citation.get("source_section") or "").strip(),
            str(citation.get("source_version") or "").strip(),
            is_official_microsoft_url(url),
        )
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _passes(metric: str, value: float | None) -> bool | None:
    if value is None:
        return None
    threshold = THRESHOLDS[metric]
    if threshold["operator"] == "lt":
        return value < threshold["value"]
    return value >= threshold["value"]


def score_results(cases: list[dict], results: list[dict]) -> dict:
    """Calculate auditable metrics without treating missing reviews as passes."""

    case_by_id = {str(case["case_id"]): case for case in cases}
    result_by_id = {str(row["case_id"]): row for row in results}
    unknown = sorted(set(result_by_id) - set(case_by_id))
    if unknown:
        raise EvaluationDataError(f"Unknown result case_id values: {', '.join(unknown)}.")

    completed_human_reviews = 0
    pending_human_reviews = 0
    verifiable_claims = 0
    unsupported_claims = 0
    reviewed_content_error_cases = 0
    reviewed_case_count = 0
    difficulty_denominator = 0
    difficulty_matches = 0
    coverage_denominator = 0
    coverage_matches = 0
    required_citations = 0
    traceable_citations = 0
    closed_loop_cases = 0
    missing_actual_output = 0

    rows: list[dict] = []
    for case in cases:
        case_id = str(case["case_id"])
        result = result_by_id.get(case_id)
        if result is None:
            rows.append({"case_id": case_id, "status": "missing"})
            continue

        actual_output = result.get("actual_output")
        if not isinstance(actual_output, dict) or not actual_output:
            missing_actual_output += 1

        review = result.get("human_review") or {}
        review_status = str(review.get("status") or "pending")
        if review_status == "completed":
            completed_human_reviews += 1
            reviewed_case_count += 1
            claims = int(review.get("verifiable_claim_count") or 0)
            unsupported = int(review.get("unsupported_claim_count") or 0)
            if claims < 0 or unsupported < 0 or unsupported > claims:
                raise EvaluationDataError(f"Invalid human claim counts for case {case_id}.")
            verifiable_claims += claims
            unsupported_claims += unsupported
            reviewed_content_error_cases += int(bool(review.get("content_error")))
        else:
            pending_human_reviews += 1

        flags = result.get("metric_flags") or {}
        difficulty = flags.get("difficulty_match")
        if isinstance(difficulty, bool):
            difficulty_denominator += 1
            difficulty_matches += int(difficulty)
        coverage = flags.get("knowledge_coverage")
        if isinstance(coverage, bool):
            coverage_denominator += 1
            coverage_matches += int(coverage)

        evidence = result.get("metric_evidence") or {}
        required = int(evidence.get("required_citation_count") or 0)
        traceable = int(evidence.get("traceable_citation_count") or 0)
        if required < 0 or traceable < 0 or traceable > required:
            raise EvaluationDataError(f"Invalid citation counts for case {case_id}.")
        required_citations += required
        traceable_citations += traceable
        closed_loop_cases += int(flags.get("closed_loop_complete") is True)

        rows.append(
            {
                "case_id": case_id,
                "status": result.get("status", "unknown"),
                "human_review_status": review_status,
                "difficulty_match": difficulty,
                "knowledge_coverage": coverage,
                "source_traceable": flags.get("source_traceable"),
                "closed_loop_complete": flags.get("closed_loop_complete"),
                "failure_reason_count": len(result.get("failure_reasons") or []),
            }
        )

    hallucination_rate = _rate(unsupported_claims, verifiable_claims)
    case_content_error_rate = _rate(reviewed_content_error_cases, reviewed_case_count)
    difficulty_rate = _rate(difficulty_matches, difficulty_denominator)
    coverage_rate = _rate(coverage_matches, coverage_denominator)
    traceability_rate = _rate(traceable_citations, required_citations)
    closed_loop_rate = _rate(closed_loop_cases, len(cases))

    metric_values = {
        "hallucination_rate": hallucination_rate,
        "difficulty_adaptation_rate": difficulty_rate,
        "knowledge_coverage_rate": coverage_rate,
        "citation_traceability_rate": traceability_rate,
        "closed_loop_completeness_rate": closed_loop_rate,
    }
    metrics = {
        name: {
            "value": value,
            "target": THRESHOLDS[name],
            "passed": _passes(name, value),
        }
        for name, value in metric_values.items()
    }
    metrics["hallucination_rate"]["numerator"] = unsupported_claims
    metrics["hallucination_rate"]["denominator"] = verifiable_claims
    metrics["case_content_error_rate"] = {
        "value": case_content_error_rate,
        "numerator": reviewed_content_error_cases,
        "denominator": reviewed_case_count,
        "target": None,
        "passed": None,
    }
    metrics["difficulty_adaptation_rate"].update(
        numerator=difficulty_matches,
        denominator=difficulty_denominator,
    )
    metrics["knowledge_coverage_rate"].update(
        numerator=coverage_matches,
        denominator=coverage_denominator,
    )
    metrics["citation_traceability_rate"].update(
        numerator=traceable_citations,
        denominator=required_citations,
    )
    metrics["closed_loop_completeness_rate"].update(
        numerator=closed_loop_cases,
        denominator=len(cases),
    )

    formal_ready = all(
        (
            len(results) == len(cases),
            missing_actual_output == 0,
            pending_human_reviews == 0,
            completed_human_reviews == len(cases),
            hallucination_rate is not None,
        )
    )
    threshold_passed = formal_ready and all(
        metrics[name]["passed"] is True for name in THRESHOLDS
    )
    return {
        "generated_at": utc_now(),
        "case_count": len(cases),
        "result_count": len(results),
        "missing_result_count": len(cases) - len(results),
        "missing_actual_output_count": missing_actual_output,
        "completed_human_review_count": completed_human_reviews,
        "pending_human_review_count": pending_human_reviews,
        "formal_ready": formal_ready,
        "all_thresholds_passed": threshold_passed,
        "metrics": metrics,
        "cases": rows,
    }


def failure_rows(results: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for result in results:
        reasons = result.get("failure_reasons") or []
        if not reasons:
            continue
        rows.append(
            {
                "case_id": result.get("case_id"),
                "module": result.get("module"),
                "scenario_type": result.get("scenario_type"),
                "failure_reasons": reasons,
                "trace_id": (result.get("actual_output") or {}).get("trace_id"),
            }
        )
    return rows


def write_score_reports(output_dir: Path, summary: dict, results: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "metrics.json", summary)
    write_json(output_dir / "failures.json", failure_rows(results))

    csv_path = output_dir / "cases.csv"
    fieldnames = [
        "case_id",
        "status",
        "human_review_status",
        "difficulty_match",
        "knowledge_coverage",
        "source_traceable",
        "closed_loop_complete",
        "failure_reason_count",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary["cases"]:
            writer.writerow({name: row.get(name) for name in fieldnames})

    labels = {
        "hallucination_rate": "幻觉率",
        "case_content_error_rate": "案例级内容错误率",
        "difficulty_adaptation_rate": "难度适配率",
        "knowledge_coverage_rate": "核心知识覆盖率",
        "citation_traceability_rate": "引用可追溯率",
        "closed_loop_completeness_rate": "闭环记录完整率",
    }
    lines = [
        "# ECHO 50 组比赛评测报告",
        "",
        f"- 生成时间：{summary['generated_at']}",
        f"- 冻结案例：{summary['case_count']}",
        f"- 实际结果：{summary['result_count']}",
        f"- 人工复核完成：{summary['completed_human_review_count']}",
        f"- 人工复核待完成：{summary['pending_human_review_count']}",
        f"- 是否具备正式报告条件：{'是' if summary['formal_ready'] else '否'}",
        "",
        "## 指标",
        "",
        "| 指标 | 结果 | 分子/分母 | 阈值 | 判定 |",
        "|---|---:|---:|---:|---|",
    ]
    for name, metric in summary["metrics"].items():
        value = metric["value"]
        value_text = "待人工复核" if value is None else f"{value:.2%}"
        numerator = metric.get("numerator", "-")
        denominator = metric.get("denominator", "-")
        threshold = metric.get("target")
        if threshold:
            symbol = "<" if threshold["operator"] == "lt" else ">="
            threshold_text = f"{symbol} {threshold['value']:.0%}"
        else:
            threshold_text = "仅报告"
        passed = metric.get("passed")
        passed_text = "待判定" if passed is None else ("通过" if passed else "未通过")
        lines.append(
            f"| {labels[name]} | {value_text} | {numerator}/{denominator} | "
            f"{threshold_text} | {passed_text} |"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            (
                "当前结果可作为正式评测报告。"
                if summary["formal_ready"]
                else "当前结果不是正式评测结论：缺少结果或人工复核时，系统不会补写或估算指标。"
            ),
            "",
            "失败详情见 `failures.json`，逐案例结构见 `cases.csv` 和 `results/`。",
        ]
    )
    (output_dir / "evaluation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
