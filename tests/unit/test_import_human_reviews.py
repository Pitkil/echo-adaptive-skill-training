import csv
import json
from pathlib import Path

import pytest

from scripts.import_human_reviews import ReviewImportError, import_human_reviews

FIELDS = (
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


def write_review(path: Path, reviewer_id: str, *, difficulty: str = "yes") -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "case_id": "001",
                "reviewer_id": reviewer_id,
                "reviewed_at": "2026-08-27T20:00:00+08:00",
                "verifiable_claim_count": "2",
                "unsupported_claim_count": "0",
                "content_error": "no",
                "difficulty_match": difficulty,
                "knowledge_coverage": "yes",
                "citation_required_count": "1",
                "citation_traceable_count": "1",
                "evidence_location": "https://example.test/source",
                "notes": "reviewed",
            }
        )


def make_run(path: Path) -> None:
    (path / "results").mkdir(parents=True)
    (path / "reports").mkdir()
    (path / "run_manifest.json").write_text(
        json.dumps({"run_id": "candidate-test"}), encoding="utf-8"
    )
    result = {
        "case_id": "001",
        "human_review": {"criteria": {"difficulty_match": "check"}},
        "metric_flags": {"closed_loop_complete": True},
        "metric_evidence": {},
    }
    (path / "results" / "case-001.json").write_text(
        json.dumps(result), encoding="utf-8"
    )


def test_imports_two_unanimous_human_reviews(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    make_run(source)
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    write_review(first, "reviewer-1")
    write_review(second, "reviewer-2")

    import_human_reviews(source, target, [first, second], expected_case_count=1)

    result = json.loads((target / "results" / "case-001.json").read_text(encoding="utf-8"))
    assert result["human_review"]["status"] == "completed"
    assert len(result["human_review"]["reviewers"]) == 2
    assert result["metric_flags"]["difficulty_match"] is True
    assert result["metric_evidence"]["traceable_citation_count"] == 1
    assert len(list(csv.DictReader((target / "human-review-template.csv").open(encoding="utf-8-sig")))) == 2


def test_rejects_review_disagreement_without_adjudication(tmp_path: Path) -> None:
    source = tmp_path / "source"
    make_run(source)
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    write_review(first, "reviewer-1", difficulty="yes")
    write_review(second, "reviewer-2", difficulty="no")

    with pytest.raises(ReviewImportError, match="adjudication required"):
        import_human_reviews(
            source,
            tmp_path / "target",
            [first, second],
            expected_case_count=1,
        )
