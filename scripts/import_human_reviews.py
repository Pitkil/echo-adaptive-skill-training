"""Import two completed human-review CSV files into a copied evaluation run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REVIEW_FIELDS = (
    "case_id",
    "reviewer_id",
    "reviewed_at",
    "verifiable_claim_count",
    "unsupported_claim_count",
    "content_error",
    "difficulty_match",
    "knowledge_coverage",
    "citation_required_count",
    "citation_traceable_count",
    "evidence_location",
    "notes",
)


class ReviewImportError(ValueError):
    """Raised when human-review files are incomplete or inconsistent."""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_nonnegative_int(value: str, *, field: str, case_id: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ReviewImportError(f"Case {case_id}: {field} must be an integer.") from error
    if parsed < 0:
        raise ReviewImportError(f"Case {case_id}: {field} must be non-negative.")
    return parsed


def parse_yes_no(value: str, *, field: str, case_id: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"yes", "no"}:
        raise ReviewImportError(f"Case {case_id}: {field} must be yes or no.")
    return normalized == "yes"


def load_review_file(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != REVIEW_FIELDS:
            raise ReviewImportError(f"Unexpected columns in {path.name}.")
        rows = list(reader)
    if not rows:
        raise ReviewImportError(f"No review rows found in {path.name}.")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row["case_id"] or "").strip().zfill(3)
        reviewer_id = str(row["reviewer_id"] or "").strip()
        reviewed_at = str(row["reviewed_at"] or "").strip()
        if not case_id or not reviewer_id or not reviewed_at:
            raise ReviewImportError(f"Incomplete identity fields in {path.name}.")
        claims = parse_nonnegative_int(
            row["verifiable_claim_count"], field="verifiable_claim_count", case_id=case_id
        )
        unsupported = parse_nonnegative_int(
            row["unsupported_claim_count"], field="unsupported_claim_count", case_id=case_id
        )
        required = parse_nonnegative_int(
            row["citation_required_count"], field="citation_required_count", case_id=case_id
        )
        traceable = parse_nonnegative_int(
            row["citation_traceable_count"], field="citation_traceable_count", case_id=case_id
        )
        if unsupported > claims:
            raise ReviewImportError(f"Case {case_id}: unsupported claims exceed claims.")
        if traceable > required:
            raise ReviewImportError(f"Case {case_id}: traceable citations exceed required citations.")
        normalized_rows.append(
            {
                "case_id": case_id,
                "reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "verifiable_claim_count": claims,
                "unsupported_claim_count": unsupported,
                "content_error": parse_yes_no(row["content_error"], field="content_error", case_id=case_id),
                "difficulty_match": parse_yes_no(
                    row["difficulty_match"], field="difficulty_match", case_id=case_id
                ),
                "knowledge_coverage": parse_yes_no(
                    row["knowledge_coverage"], field="knowledge_coverage", case_id=case_id
                ),
                "citation_required_count": required,
                "citation_traceable_count": traceable,
                "evidence_location": str(row["evidence_location"] or "").strip(),
                "notes": str(row["notes"] or "").strip(),
            }
        )
    reviewer_ids = {row["reviewer_id"] for row in normalized_rows}
    if len(reviewer_ids) != 1:
        raise ReviewImportError(f"Each review file must contain exactly one reviewer: {path.name}.")
    if len({row["case_id"] for row in normalized_rows}) != len(normalized_rows):
        raise ReviewImportError(f"Duplicate case_id in {path.name}.")
    return normalized_rows


def consensus_review(rows: list[dict[str, Any]], *, case_id: str) -> dict[str, Any]:
    reviewer_ids = {row["reviewer_id"] for row in rows}
    if len(rows) != 2 or len(reviewer_ids) != 2:
        raise ReviewImportError(f"Case {case_id}: exactly two distinct reviewers are required.")
    consensus_fields = (
        "verifiable_claim_count",
        "unsupported_claim_count",
        "content_error",
        "difficulty_match",
        "knowledge_coverage",
        "citation_required_count",
        "citation_traceable_count",
    )
    for field in consensus_fields:
        if len({row[field] for row in rows}) != 1:
            raise ReviewImportError(f"Case {case_id}: reviewers disagree on {field}; adjudication required.")
    return {field: rows[0][field] for field in consensus_fields}


def import_human_reviews(
    source_run_dir: Path,
    target_run_dir: Path,
    review_files: list[Path],
    *,
    expected_case_count: int = 50,
) -> Path:
    """Copy a run, validate two review files, and persist unanimous adjudication."""

    if target_run_dir.exists():
        raise ReviewImportError(f"Target run already exists: {target_run_dir}")
    result_paths = sorted((source_run_dir / "results").glob("case-*.json"))
    if len(result_paths) != expected_case_count:
        raise ReviewImportError(
            f"Expected {expected_case_count} result files, found {len(result_paths)}."
        )
    if len(review_files) != 2:
        raise ReviewImportError("Exactly two review files are required.")

    review_rows = [load_review_file(path) for path in review_files]
    reviewers = {rows[0]["reviewer_id"] for rows in review_rows}
    if len(reviewers) != 2:
        raise ReviewImportError("Review files must belong to two distinct reviewers.")
    expected_case_ids = {path.stem.removeprefix("case-") for path in result_paths}
    for rows in review_rows:
        if {row["case_id"] for row in rows} != expected_case_ids:
            raise ReviewImportError("Review case IDs do not match the evaluation results.")

    shutil.copytree(source_run_dir, target_run_dir)
    copied_review_dir = target_run_dir / "human-reviews"
    copied_review_dir.mkdir()
    source_metadata = []
    for path, rows in zip(review_files, review_rows, strict=True):
        reviewer_id = rows[0]["reviewer_id"]
        copied = copied_review_dir / f"{reviewer_id}.csv"
        shutil.copy2(path, copied)
        source_metadata.append(
            {"reviewer_id": reviewer_id, "file": copied.name, "sha256": sha256(copied)}
        )

    rows_by_case: dict[str, list[dict[str, Any]]] = {case_id: [] for case_id in expected_case_ids}
    for rows in review_rows:
        for row in rows:
            rows_by_case[row["case_id"]].append(row)

    combined_rows: list[dict[str, Any]] = []
    for result_path in sorted((target_run_dir / "results").glob("case-*.json")):
        result = read_json(result_path)
        case_id = str(result["case_id"]).zfill(3)
        case_rows = sorted(rows_by_case[case_id], key=lambda item: item["reviewer_id"])
        adjudicated = consensus_review(case_rows, case_id=case_id)
        previous_review = result.get("human_review") or {}
        result["human_review"] = {
            "status": "completed",
            "required_reviewer_count": 2,
            "reviewers": [
                {"status": "completed", "reviewer_type": "human", **row} for row in case_rows
            ],
            "adjudication": {"status": "unanimous", **adjudicated},
            "verifiable_claim_count": adjudicated["verifiable_claim_count"],
            "unsupported_claim_count": adjudicated["unsupported_claim_count"],
            "content_error": adjudicated["content_error"],
            "criteria": previous_review.get("criteria") or {},
            "note": "Imported from two user-confirmed human reviews; unanimous per case.",
        }
        flags = result.setdefault("metric_flags", {})
        flags["difficulty_match"] = adjudicated["difficulty_match"]
        flags["knowledge_coverage"] = adjudicated["knowledge_coverage"]
        flags["source_traceable"] = (
            adjudicated["citation_traceable_count"]
            == adjudicated["citation_required_count"]
        )
        evidence = result.setdefault("metric_evidence", {})
        evidence["required_citation_count"] = adjudicated["citation_required_count"]
        evidence["traceable_citation_count"] = adjudicated["citation_traceable_count"]
        write_json(result_path, result)
        combined_rows.extend(case_rows)

    combined_path = target_run_dir / "human-review-template.csv"
    with combined_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for row in sorted(combined_rows, key=lambda item: (item["case_id"], item["reviewer_id"])):
            writer.writerow(
                {
                    **row,
                    "content_error": "yes" if row["content_error"] else "no",
                    "difficulty_match": "yes" if row["difficulty_match"] else "no",
                    "knowledge_coverage": "yes" if row["knowledge_coverage"] else "no",
                }
            )

    manifest_path = target_run_dir / "run_manifest.json"
    manifest = read_json(manifest_path)
    manifest["review_import"] = {
        "status": "completed",
        "reviewed_run_id": manifest.get("run_id"),
        "reviewer_count": 2,
        "case_count": expected_case_count,
        "imported_at": datetime.now(UTC).isoformat(),
        "sources": source_metadata,
    }
    write_json(manifest_path, manifest)
    return target_run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-dir", type=Path, required=True)
    parser.add_argument("--target-run-dir", type=Path, required=True)
    parser.add_argument("--review-file", type=Path, action="append", required=True)
    args = parser.parse_args()
    target = import_human_reviews(
        args.source_run_dir.resolve(),
        args.target_run_dir.resolve(),
        [path.resolve() for path in args.review_file],
    )
    print(target)


if __name__ == "__main__":
    main()
