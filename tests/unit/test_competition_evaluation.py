from __future__ import annotations

import csv
import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from evaluation import (
    EvaluationDataError,
    completed_human_review,
    has_complete_persisted_agent_records,
    load_frozen_cases,
    pending_cases,
    result_path,
)

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "run_competition_evaluation.py"
SPEC = importlib.util.spec_from_file_location("run_competition_evaluation", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def test_frozen_competition_cases_are_exactly_fifty_and_unique() -> None:
    cases = load_frozen_cases(ROOT / "docs" / "member-d" / "eval_50_cases.json")
    assert len(cases) == 50
    assert len({case["case_id"] for case in cases}) == 50


def test_frozen_case_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    source = json.loads(
        (ROOT / "docs" / "member-d" / "eval_50_cases.json").read_text(encoding="utf-8")
    )
    source["cases"][1]["case_id"] = source["cases"][0]["case_id"]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(EvaluationDataError, match="Duplicate case_id"):
        load_frozen_cases(path)


def test_pending_cases_supports_resume_without_overwriting(tmp_path: Path) -> None:
    cases = load_frozen_cases(ROOT / "docs" / "member-d" / "eval_50_cases.json")
    first_id = cases[0]["case_id"]
    result_path(tmp_path, first_id).write_text(
        json.dumps({"case_id": first_id}), encoding="utf-8"
    )
    todo = pending_cases(cases, tmp_path)
    assert len(todo) == 49
    assert first_id not in {case["case_id"] for case in todo}


def test_ndjson_parser_preserves_meta_and_content() -> None:
    payload = RUNNER.parse_ndjson(
        '\n'.join(
            [
                json.dumps({"type": "meta", "trace_id": "t1", "primary_action": "LEARNING_DIALOGUE"}),
                json.dumps({"type": "content", "content": "第一段"}, ensure_ascii=False),
                json.dumps({"type": "content", "content": "第二段"}, ensure_ascii=False),
            ]
        )
    )
    assert payload["meta"]["trace_id"] == "t1"
    assert payload["content"] == "第一段第二段"
    assert len(payload["events"]) == 3


def test_redaction_removes_nested_credentials() -> None:
    cleaned = RUNNER.redact(
        {
            "access_token": "secret-token",
            "request": {"password": "secret-password", "username": "learner"},
            "items": [{"api_key": "secret-key"}],
        }
    )
    serialized = json.dumps(cleaned)
    assert "secret-token" not in serialized
    assert "secret-password" not in serialized
    assert "secret-key" not in serialized
    assert cleaned["request"]["username"] == "learner"


def test_live_client_keeps_token_in_memory_until_export(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200
        headers = {"content-type": "application/json"}

        def read(self) -> bytes:
            return BytesIO(b'{"access_token":"live-token"}').read()

    monkeypatch.setattr(RUNNER, "urlopen", lambda *_args, **_kwargs: Response())
    client = RUNNER.LiveEchoClient("http://echo.invalid", timeout_seconds=1)
    response = client.timed_request("POST", "/auth/register", json={"username": "u"})
    assert response.payload["access_token"] == "live-token"
    assert RUNNER.redact(response.payload)["access_token"] == "[REDACTED]"


def test_human_review_template_requires_two_reviewers(tmp_path: Path) -> None:
    cases = load_frozen_cases(ROOT / "docs" / "member-d" / "eval_50_cases.json")
    path = tmp_path / "review.csv"
    RUNNER.write_review_template(path, cases)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 100
    assert {row["reviewer_id"] for row in rows} == {"reviewer-1", "reviewer-2"}
    assert all(not row["reviewed_at"] for row in rows)


def test_pending_review_does_not_pretend_ai_is_a_human_reviewer() -> None:
    cases = load_frozen_cases(ROOT / "docs" / "member-d" / "eval_50_cases.json")
    review = RUNNER.pending_human_review(cases[0])
    assert review["status"] == "pending_two_reviewers"
    assert review["reviewers"] == []
    assert review["required_reviewer_count"] == 2
    assert completed_human_review(review) is False


def test_text_only_hesitation_case_does_not_require_audio_evidence() -> None:
    cases = load_frozen_cases(ROOT / "docs" / "member-d" / "eval_50_cases.json")
    case = next(item for item in cases if item["case_id"] == "044")

    assert RUNNER.requires_real_micro_signal(case) is False
    assert RUNNER.requires_real_micro_signal(
        {**case, "input_media": {"audio_path": "audio/case-044.wav"}}
    ) is True


def test_profile_queries_use_target_module_after_switch() -> None:
    assert RUNNER.active_module_id_after_switch(2, 3) == 3
    assert RUNNER.active_module_id_after_switch(2, None) == 2


def test_manifest_is_not_formal_when_git_metadata_is_unavailable() -> None:
    assert (
        RUNNER.manifest_run_kind(
            {
                "available": False,
                "commit_sha": None,
                "is_dirty": None,
            }
        )
        == "candidate"
    )
    assert (
        RUNNER.manifest_run_kind(
            {
                "available": True,
                "commit_sha": "abc123",
                "is_dirty": False,
            }
        )
        == "formal_candidate"
    )


def test_formal_review_requires_two_distinct_humans() -> None:
    one_reviewer = {
        "status": "completed",
        "reviewers": [
            {"reviewer_id": "r1", "reviewer_type": "human", "status": "completed"},
        ],
    }
    assert completed_human_review(one_reviewer) is False
    one_reviewer["reviewers"].append(
        {"reviewer_id": "r2", "reviewer_type": "human", "status": "completed"}
    )
    assert completed_human_review(one_reviewer) is True


def test_closed_loop_requires_persisted_records_for_all_agents() -> None:
    result = {
        "actual_output": {"primary_action": "LEARNING_DIALOGUE", "echo_reply": "answer"},
        "agent_records": {
            name: {
                "status": "observed",
                "output": {},
                "started_at": "2026-08-26T00:00:00Z",
                "finished_at": "2026-08-26T00:00:01Z",
                "persisted_in_system": True,
            }
            for name in ("analysis", "generation", "validation", "next_action")
        },
    }
    assert has_complete_persisted_agent_records(result) is True
    result["agent_records"]["validation"]["persisted_in_system"] = False
    assert has_complete_persisted_agent_records(result) is False


def test_closed_loop_preserves_a_persisted_validation_failure() -> None:
    result = {
        "actual_output": {"primary_action": "LEARNING_DIALOGUE", "echo_reply": "answer"},
        "agent_records": {
            name: {
                "status": "completed",
                "output": {},
                "failure_reason": None,
                "started_at": "2026-08-26T00:00:00Z",
                "finished_at": "2026-08-26T00:00:01Z",
                "persisted_in_system": True,
            }
            for name in ("analysis", "generation", "validation", "next_action")
        },
    }
    result["agent_records"]["validation"].update(
        status="failed",
        failure_reason="official evidence was unavailable",
        output={"passed": False},
    )

    assert has_complete_persisted_agent_records(result) is True


def test_citation_uses_external_document_id_when_internal_alias_is_absent() -> None:
    citation = RUNNER.official_citation_from_metadata(
        {
            "source_title": "Microsoft Learn",
            "source_url": "https://learn.microsoft.com/example",
            "external_document_id": "pundit-doc-1",
        }
    )
    assert citation["document_id"] == "pundit-doc-1"


def test_extract_citations_includes_fixed_quiz_source() -> None:
    citations = RUNNER.extract_citations(
        {
            "meta": {
                "assessment": {
                    "source": {
                        "source_title": "Observability in Semantic Kernel",
                        "source_url": "https://learn.microsoft.com/example",
                        "source_section": "Deployment",
                        "source_version": "2026-08-27",
                        "document_id": "doc-1",
                        "evidence_origin": "fixed_quiz_source",
                    }
                }
            }
        },
        [],
    )

    assert len(citations) == 1
    assert citations[0]["source_title"] == "Observability in Semantic Kernel"
    assert citations == [
        {
            "source_title": "Observability in Semantic Kernel",
            "source_url": "https://learn.microsoft.com/example",
            "source_section": "Deployment",
            "source_version": "2026-08-27",
            "document_id": "doc-1",
            "chunk_id": None,
        }
    ]


def test_extract_citations_prefers_fixed_quiz_source_over_rag_hits() -> None:
    citations = RUNNER.extract_citations(
        {
            "meta": {
                "evidence": [
                    {
                        "metadata": {
                            "source_title": "Unrelated RAG hit",
                            "source_url": "https://learn.microsoft.com/unrelated",
                        }
                    }
                ],
                "assessment": {
                    "source": {
                        "source_title": "Fixed question source",
                        "source_url": "https://learn.microsoft.com/fixed",
                    }
                },
            }
        },
        [],
    )

    assert [item["source_title"] for item in citations] == ["Fixed question source"]
