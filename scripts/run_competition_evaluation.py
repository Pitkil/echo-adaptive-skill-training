"""Run the frozen ECHO competition cases against a live HTTP deployment.

The runner is deliberately evidence-first: it stores the request and the real
HTTP response, never copies ``expected`` into ``actual_output``, and leaves all
subjective metric decisions pending until two human reviewers complete them.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from evaluation import (  # noqa: E402
    AGENT_NAMES,
    load_actual_results,
    load_frozen_cases,
    pending_cases,
    result_path,
    sha256_file,
    utc_now,
    write_json,
)

RESOURCE_SCENARIOS = {"custom_note", "practice_guide", "staged_test"}
SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "password",
    "api_key",
    "secret",
    "token",
    "x-evaluation-key",
    "evaluation_seed_key",
}


class EvaluationRunError(RuntimeError):
    """Raised when a run cannot safely continue."""


@dataclass(frozen=True)
class TimedResponse:
    started_at: str
    finished_at: str
    status_code: int
    payload: Any


def redact(value: Any) -> Any:
    """Recursively remove credentials from an exported request or response."""

    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def requires_real_micro_signal(case: dict[str, Any]) -> bool:
    """Require detector evidence only when the frozen case contains audio."""

    input_media = case.get("input_media") or {}
    return bool(
        case.get("audio_path")
        or case.get("input_audio_path")
        or input_media.get("audio_path")
    )


def active_module_id_after_switch(initial_module_id: int, target_module_id: int | None) -> int:
    """Return the module whose state must be queried after a turn."""

    return target_module_id if target_module_id is not None else initial_module_id


def parse_ndjson(text: str) -> dict[str, Any]:
    """Combine the ECHO streaming response without losing individual events."""

    events: list[dict[str, Any]] = []
    content_parts: list[str] = []
    meta: dict[str, Any] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        events.append(event)
        if event.get("type") == "meta":
            meta.update({key: value for key, value in event.items() if key != "type"})
        elif event.get("type") == "content":
            content_parts.append(str(event.get("content") or ""))
    return {"events": events, "meta": meta, "content": "".join(content_parts)}


def normalize_idempotency_response(payload: Any) -> Any:
    """Ignore only the expected replay status marker when comparing responses."""

    if isinstance(payload, dict):
        normalized = {
            key: normalize_idempotency_response(value) for key, value in payload.items()
        }
        assessment = normalized.get("assessment")
        if isinstance(assessment, dict) and "updated" in assessment:
            assessment["updated"] = "[IDEMPOTENCY_STATUS]"
        return normalized
    if isinstance(payload, list):
        return [normalize_idempotency_response(item) for item in payload]
    if isinstance(payload, str):
        return re.sub(
            r"^(该请求已处理过，已返回原判定结果，本次重放不重复更新能力画像。|"
            r"回答正确，能力画像已更新。)",
            "[IDEMPOTENCY_STATUS]",
            payload,
        )
    return payload


def idempotency_responses_are_equivalent(first: Any, replay: Any) -> bool:
    """Compare replay business output while permitting its explicit status marker."""

    return normalize_idempotency_response(first) == normalize_idempotency_response(replay)


def safe_slug(value: str, *, limit: int = 24) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-").lower()
    return (normalized or "run")[:limit]


def git_value(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def repository_state() -> dict[str, Any]:
    is_available = git_value("rev-parse", "--is-inside-work-tree") == "true"
    if not is_available:
        return {
            "available": False,
            "commit_sha": None,
            "branch": None,
            "is_dirty": None,
            "dirty_path_count": None,
        }
    status = git_value("status", "--porcelain")
    return {
        "available": True,
        "commit_sha": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "is_dirty": bool(status),
        "dirty_path_count": len(status.splitlines()) if status else 0,
    }


def manifest_run_kind(repository: dict[str, Any]) -> str:
    is_formal_candidate = bool(
        repository.get("available")
        and repository.get("commit_sha")
        and repository.get("is_dirty") is False
    )
    return "formal_candidate" if is_formal_candidate else "candidate"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


class LiveEchoClient:
    """Minimal authenticated client for the public ECHO API surface."""

    def __init__(self, base_url: str, *, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds

    def close(self) -> None:
        return None

    def timed_request(self, method: str, path: str, **kwargs: Any) -> TimedResponse:
        started_at = iso_now()
        params = kwargs.pop("params", None) or {}
        headers = dict(kwargs.pop("headers", None) or {})
        json_payload = kwargs.pop("json", None)
        if kwargs:
            raise TypeError(f"unsupported request options: {', '.join(sorted(kwargs))}")
        query = f"?{urlencode(params)}" if params else ""
        url = urljoin(self.base_url, path.lstrip("/")) + query
        data = None
        if json_payload is not None:
            data = json.dumps(json_payload, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            response = urlopen(request, timeout=self.timeout_seconds)  # noqa: S310
            status_code = response.status
            content_type = response.headers.get("content-type", "")
            response_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            status_code = exc.code
            content_type = exc.headers.get("content-type", "")
            response_text = exc.read().decode("utf-8", errors="replace")
        except (URLError, TimeoutError, OSError) as exc:
            status_code = 0
            content_type = "application/json"
            response_text = json.dumps(
                {"error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
            )
        finished_at = iso_now()
        if "application/x-ndjson" in content_type:
            payload: Any = parse_ndjson(response_text)
        else:
            try:
                payload = json.loads(response_text)
            except json.JSONDecodeError:
                payload = {"text": response_text}
        return TimedResponse(
            started_at=started_at,
            finished_at=finished_at,
            status_code=status_code,
            # Keep credentials available only in memory so authenticated follow-up
            # requests can succeed.  Every persisted raw record is redacted at the
            # write boundary below; replacing the token here would make the runner
            # send the literal string "[REDACTED]" as a bearer token.
            payload=payload,
        )

    @staticmethod
    def require_success(response: TimedResponse, label: str) -> Any:
        if not 200 <= response.status_code < 300:
            raise EvaluationRunError(
                f"{label} failed with HTTP {response.status_code}: {response.payload}"
            )
        return response.payload


def official_citation_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_title": metadata.get("source_title") or metadata.get("title"),
        "source_url": metadata.get("source_url") or metadata.get("url"),
        "source_section": metadata.get("source_section") or metadata.get("section"),
        "source_version": metadata.get("source_version") or metadata.get("version"),
        "document_id": metadata.get("document_id") or metadata.get("external_document_id"),
        "chunk_id": metadata.get("chunk_id"),
    }


def extract_citations(chat_payload: dict[str, Any], resources: list[dict[str, Any]]) -> list[dict]:
    citations: list[dict[str, Any]] = []
    assessment_source = (
        chat_payload.get("meta", {}).get("assessment", {}).get("source")
    )
    if isinstance(assessment_source, dict):
        citations.append(official_citation_from_metadata(assessment_source))
    else:
        for item in chat_payload.get("meta", {}).get("evidence", []) or []:
            if isinstance(item, dict):
                citations.append(official_citation_from_metadata(item.get("metadata") or {}))
    for resource in resources:
        for metadata in resource.get("evidence_sources", []) or []:
            if isinstance(metadata, dict):
                citations.append(official_citation_from_metadata(metadata))
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for citation in citations:
        marker = tuple(citation.get(key) for key in citation)
        if marker not in seen:
            seen.add(marker)
            unique.append(citation)
    return unique


def pending_human_review(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "pending_two_reviewers",
        "required_reviewer_count": 2,
        "reviewers": [],
        "adjudication": None,
        "criteria": case["judgment"],
        "note": "AI 仅整理证据；内容正确性、难度和覆盖率必须由两名人工复核。",
    }


class CompetitionEvaluationRunner:
    """Execute cases sequentially and preserve every observed failure."""

    def __init__(
        self,
        *,
        client: LiveEchoClient,
        run_dir: Path,
        run_id: str,
        seed: int,
        evaluation_seed_key: str,
    ) -> None:
        self.client = client
        self.run_dir = run_dir
        self.run_id = run_id
        self.seed = seed
        self.evaluation_seed_key = evaluation_seed_key
        self.results_dir = run_dir / "results"
        self.raw_dir = run_dir / "raw"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def health(self) -> TimedResponse:
        return self.client.timed_request("GET", "/api/health")

    def register_case_user(self, case: dict[str, Any]) -> tuple[dict[str, Any], str]:
        suffix = uuid4().hex[:8]
        username = safe_slug(f"eval-{self.run_id}-{case['case_id']}-{suffix}", limit=48)
        password = f"Eval!{uuid4().hex}"
        response = self.client.timed_request(
            "POST",
            "/auth/register",
            json={"username": username, "password": password},
        )
        payload = self.client.require_success(response, "register evaluation learner")
        token = str(payload.get("access_token") or "")
        if not token:
            raise EvaluationRunError("registration response omitted access_token")
        public = {key: value for key, value in payload.items() if key != "access_token"}
        public["username"] = username
        return public, token

    def catalog(self, token: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        programs_response = self.client.timed_request("GET", "/v1/catalog/programs", headers=headers)
        programs = self.client.require_success(programs_response, "list programs")
        if not programs:
            raise EvaluationRunError("catalog has no training program")
        program = programs[0]
        modules_response = self.client.timed_request(
            "GET", f"/v1/catalog/programs/{program['id']}/modules", headers=headers
        )
        modules = self.client.require_success(modules_response, "list modules")
        module_rows: list[dict[str, Any]] = []
        for module in modules:
            points_response = self.client.timed_request(
                "GET",
                f"/v1/catalog/modules/{module['id']}/knowledge-points",
                headers=headers,
            )
            module = dict(module)
            module["knowledge_points"] = self.client.require_success(
                points_response, "list knowledge points"
            )
            module_rows.append(module)
        return {"program": program, "modules": module_rows}

    @staticmethod
    def select_module_and_point(
        case: dict[str, Any], catalog: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        module = next(
            (row for row in catalog["modules"] if row.get("code") == case["module"]),
            None,
        )
        if module is None:
            raise EvaluationRunError(f"module not found: {case['module']}")
        point = next(
            (
                row
                for row in module["knowledge_points"]
                if row.get("name") == case["knowledge_point"]
            ),
            None,
        )
        if point is None:
            raise EvaluationRunError(
                f"knowledge point not found in {case['module']}: {case['knowledge_point']}"
            )
        return module, point

    def run_case(self, case: dict[str, Any], health_payload: dict[str, Any]) -> dict[str, Any]:
        case_started = iso_now()
        failures: list[str] = []
        raw: dict[str, Any] = {"case": case, "health": health_payload}
        registration, token = self.register_case_user(case)
        headers = {"Authorization": f"Bearer {token}"}
        catalog = self.catalog(token)
        module, point = self.select_module_and_point(case, catalog)
        active_module_id = module["id"]
        user_id = int(registration["user_id"])

        if not self.evaluation_seed_key:
            raise EvaluationRunError(
                "EVALUATION_PROFILE_SEED_KEY is required to materialize P1/P2/P3 state"
            )
        initialization_headers = {
            **headers,
            "X-Evaluation-Key": self.evaluation_seed_key,
        }
        profile_initialization = self.client.timed_request(
            "POST",
            "/v1/evaluation/learner-profile",
            json={
                "user_id": user_id,
                "module_id": module["id"],
                "profile_id": case["learner_type"],
            },
            headers=initialization_headers,
        )
        raw["profile_initialization"] = profile_initialization.__dict__
        initialized = self.client.require_success(
            profile_initialization, "initialize frozen learner profile"
        )
        actual_profile_type = (
            initialized.get("profile", {})
            .get("views", {})
            .get("path_and_resources", {})
            .get("learner_profile", {})
            .get("type")
        )
        if actual_profile_type != case["learner_type"]:
            raise EvaluationRunError(
                "initialized learner profile does not match the frozen case: "
                f"expected={case['learner_type']}, actual={actual_profile_type}"
            )

        profile_before = self.client.timed_request(
            "GET",
            f"/users/{user_id}/learning-insight",
            params={"module_id": module["id"]},
            headers=headers,
        )
        if profile_before.status_code >= 400:
            failures.append(f"PROFILE_INITIALIZATION_FAILED_HTTP_{profile_before.status_code}")

        expected_action = str(case["expected"].get("primary_action") or "")
        chat_payload: dict[str, Any] = {}
        resource_response: TimedResponse | None = None
        chat_response: TimedResponse | None = None
        idempotency_proof: dict[str, Any] | None = None
        request_payload: dict[str, Any]
        expected_resource = case["expected"].get("resource_type")
        if case["scenario_type"] in RESOURCE_SCENARIOS:
            request_payload = {
                "user_id": user_id,
                "module_id": module["id"],
                "knowledge_point_id": point["id"],
                "resource_type": expected_resource,
                "user_input": case.get("input", ""),
                "request_id": f"eval-{self.run_id}-{case['case_id']}-resource",
            }
            resource_response = self.client.timed_request(
                "POST", "/v1/resources/generate", json=request_payload, headers=headers
            )
            raw["resource_generation"] = resource_response.__dict__
            if resource_response.status_code >= 400:
                failures.append(f"RESOURCE_GENERATION_HTTP_{resource_response.status_code}")
        else:
            request_id = f"eval-{self.run_id}-{case['case_id']}"
            prepared_session_id = None
            if expected_action == "GRADE_ANSWER":
                preparation_payload = {
                    "user_id": user_id,
                    "module_id": module["id"],
                    "knowledge_point_id": point["id"],
                    "source_url": case["expected"].get("source_url"),
                    "source_section": case["expected"].get("source_section"),
                    "difficulty": case["expected"].get("difficulty"),
                }
                preparation_response = self.client.timed_request(
                    "POST",
                    "/v1/evaluation/quiz-context",
                    json=preparation_payload,
                    headers=initialization_headers,
                )
                raw["quiz_preparation"] = preparation_response.__dict__
                if preparation_response.status_code >= 400:
                    failures.append(
                        f"QUIZ_PREPARATION_HTTP_{preparation_response.status_code}"
                    )
                elif isinstance(preparation_response.payload, dict):
                    prepared_session_id = preparation_response.payload.get("session_id")
                    if not preparation_response.payload.get("quiz"):
                        failures.append("QUIZ_PREPARATION_QUESTION_MISSING")
            request_payload = {
                "user_input": case["input"],
                "user_id": user_id,
                "request_id": request_id,
                "program_id": catalog["program"]["id"],
                "module_id": module["id"],
                "knowledge_point_id": point["id"],
            }
            if prepared_session_id is not None:
                request_payload["session_id"] = prepared_session_id
            if case["case_id"] == "047":
                target = next((row for row in catalog["modules"] if row.get("code") == "M3"), None)
                request_payload["requested_module_id"] = target["id"] if target else None
                active_module_id = active_module_id_after_switch(
                    active_module_id,
                    request_payload["requested_module_id"],
                )
            chat_response = self.client.timed_request(
                "POST", "/chat", json=request_payload, headers=headers
            )
            raw["chat"] = chat_response.__dict__
            if chat_response.status_code >= 400:
                failures.append(f"CHAT_HTTP_{chat_response.status_code}")
            elif isinstance(chat_response.payload, dict):
                chat_payload = chat_response.payload

            if case["case_id"] == "048" and chat_response.status_code < 400:
                after_first = self.client.timed_request(
                    "GET",
                    f"/users/{user_id}/learning-insight",
                    params={"module_id": module["id"]},
                    headers=headers,
                )
                raw["idempotency_profile_after_first"] = after_first.__dict__
                repeated = self.client.timed_request(
                    "POST", "/chat", json=request_payload, headers=headers
                )
                raw["idempotency_replay"] = repeated.__dict__
                exact_response_match = repeated.payload == chat_response.payload
                equivalent_response = idempotency_responses_are_equivalent(
                    chat_response.payload, repeated.payload
                )
                if not equivalent_response:
                    failures.append("IDEMPOTENCY_REPLAY_CHANGED_RESPONSE")
                after_replay = self.client.timed_request(
                    "GET",
                    f"/users/{user_id}/learning-insight",
                    params={"module_id": module["id"]},
                    headers=headers,
                )
                raw["idempotency_profile_after_replay"] = after_replay.__dict__
                first_ability = (
                    after_first.payload.get("views", {})
                    .get("ability_and_trend", {})
                    .get("ability", {})
                )
                replay_ability = (
                    after_replay.payload.get("views", {})
                    .get("ability_and_trend", {})
                    .get("ability", {})
                )
                stable_fields = ("U", "A", "R", "attempt_count")
                is_stable = all(
                    first_ability.get(field) == replay_ability.get(field)
                    for field in stable_fields
                )
                if not is_stable:
                    failures.append("IDEMPOTENCY_REPLAY_CHANGED_ABILITY")
                idempotency_proof = {
                    "same_request_id": True,
                    "same_response": equivalent_response,
                    "exact_response_match": exact_response_match,
                    "ability_unchanged_on_replay": is_stable,
                    "after_first": {
                        field: first_ability.get(field) for field in stable_fields
                    },
                    "after_replay": {
                        field: replay_ability.get(field) for field in stable_fields
                    },
                }

        resources_response = self.client.timed_request(
            "GET",
            "/v1/resources",
            params={"module_id": active_module_id},
            headers=headers,
        )
        resources_payload = (
            resources_response.payload if resources_response.status_code < 400 else {"items": []}
        )
        resources = list(resources_payload.get("items") or [])
        raw["resources"] = resources_response.__dict__

        session_id = chat_payload.get("meta", {}).get("session_id")
        if resource_response is not None and resource_response.status_code < 400:
            session_id = resource_response.payload.get("session_id")
        turns_response: TimedResponse | None = None
        if session_id is not None:
            turns_response = self.client.timed_request(
                "GET", f"/v1/sessions/{session_id}/turns", headers=headers
            )
            raw["turns"] = turns_response.__dict__

        profile_after = self.client.timed_request(
            "GET",
            f"/users/{user_id}/learning-insight",
            params={"module_id": active_module_id},
            headers=headers,
        )
        raw["profile_before"] = profile_before.__dict__
        raw["profile_after"] = profile_after.__dict__

        actual_action = str(chat_payload.get("meta", {}).get("primary_action") or "")
        if resource_response is not None and resource_response.status_code < 400:
            actual_action = str(resource_response.payload.get("primary_action") or "")
        if chat_response and chat_response.status_code < 400 and actual_action != expected_action:
            failures.append(
                f"PRIMARY_ACTION_MISMATCH(expected={expected_action},actual={actual_action or 'missing'})"
            )
        assessment = chat_payload.get("meta", {}).get("assessment", {})
        expected_is_correct = case["expected"].get("is_correct")
        if expected_is_correct is not None and assessment.get("is_correct") is not expected_is_correct:
            failures.append(
                "GRADING_RESULT_MISMATCH"
                f"(expected={expected_is_correct},actual={assessment.get('is_correct')})"
            )
        if (
            case["expected"].get("update_mirt") is True
            and assessment.get("updated") is not True
        ):
            failures.append("EXPECTED_MIRT_UPDATE_MISSING")

        selected_resource = next(
            (row for row in resources if row.get("resource_type") == expected_resource),
            None,
        )
        if expected_resource and selected_resource is None:
            failures.append(f"EXPECTED_RESOURCE_MISSING({expected_resource})")

        citations = extract_citations(chat_payload, resources)
        should_cite = bool(case["expected"].get("source_url")) and actual_action in {
            "LEARNING_DIALOGUE",
            "GRADE_ANSWER",
            "GENERATE_RESOURCE",
        }
        if should_cite and not citations:
            failures.append("NO_ACTUAL_OFFICIAL_CITATION")

        dependencies = health_payload.get("dependencies") or {}
        unavailable = [
            name
            for name, detail in dependencies.items()
            if isinstance(detail, dict) and detail.get("status") != "ok"
        ]
        failures.extend(f"DEPENDENCY_NOT_OK({name})" for name in unavailable)
        mock_dependencies = [
            name
            for name, detail in dependencies.items()
            if isinstance(detail, dict) and str(detail.get("mode") or "").lower() == "mock"
        ]
        micro_signal_required = requires_real_micro_signal(case)
        if micro_signal_required and mock_dependencies:
            failures.extend(f"DEPENDENCY_MOCK({name})" for name in mock_dependencies)

        profile_payload = profile_after.payload if profile_after.status_code < 400 else {}
        confirmed_micro_count = int(
            profile_payload.get("views", {})
            .get("evidence_and_blind_spots", {})
            .get("micro_evidence", {})
            .get("confirmed_event_count", 0)
            or 0
        )
        if micro_signal_required and confirmed_micro_count == 0:
            failures.append("REAL_MICRO_SIGNAL_EVIDENCE_MISSING")
        persisted_turns = (
            turns_response.payload.get("items", [])
            if turns_response and turns_response.status_code < 400
            else []
        )
        trace_id = chat_payload.get("meta", {}).get("trace_id")
        if resource_response is not None and resource_response.status_code < 400:
            trace_id = resource_response.payload.get("trace_id")
        persisted_turn = next(
            (item for item in persisted_turns if item.get("trace_id") == trace_id),
            persisted_turns[0] if persisted_turns else None,
        )
        agent_records = (
            (persisted_turn or {}).get("result", {}).get("agent_records") or {}
        )
        if any(
            name not in agent_records
            or agent_records[name].get("status") in {"not_exposed", "not_run"}
            or agent_records[name].get("persisted_in_system") is not True
            or (
                agent_records[name].get("status") == "failed"
                and not agent_records[name].get("failure_reason")
            )
            for name in AGENT_NAMES
        ):
            failures.append("FOUR_AGENT_PERSISTED_RECORDS_INCOMPLETE")

        actual_output = {
            "trace_id": trace_id,
            "session_id": session_id,
            "intent": chat_payload.get("meta", {}).get("intent"),
            "primary_action": actual_action or None,
            "echo_reply": chat_payload.get("content"),
            "degradation": chat_payload.get("meta", {}).get("degradation")
            or (resource_response.payload.get("degradation") if resource_response else []),
            "requested_resource_type": expected_resource,
            "selected_resource": selected_resource,
            "all_resource_count": len(resources),
            "profile_after": profile_payload,
            "dependency_limitations": {
                "mock_dependencies": mock_dependencies,
                "micro_dependency_is_real": not bool(mock_dependencies),
                "micro_signal_required": micro_signal_required,
                "micro_signal_evidence_present": confirmed_micro_count > 0,
                "confirmed_micro_event_count": confirmed_micro_count,
            },
            "idempotency_proof": idempotency_proof,
        }
        closed_loop_complete = not any(
            "FOUR_AGENT_PERSISTED_RECORDS_INCOMPLETE" in item for item in failures
        )
        result = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "case_id": case["case_id"],
            "learner_type": case["learner_type"],
            "module": case["module"],
            "knowledge_point": case["knowledge_point"],
            "scenario_type": case["scenario_type"],
            "status": "completed" if not failures else "completed_with_degradation",
            "started_at": case_started,
            "finished_at": iso_now(),
            "learner_profile_snapshot": profile_before.payload,
            "learner_profile_initialization": redact(profile_initialization.payload),
            "business_state": {
                "user_id": user_id,
                "session_id": session_id,
                "module_id": active_module_id,
                "knowledge_point_id": point["id"],
            },
            "request": request_payload,
            "actual_output": actual_output,
            "agent_records": agent_records,
            "citations": citations,
            "resource_record": selected_resource,
            "human_review": pending_human_review(case),
            "metric_flags": {
                "difficulty_match": None,
                "knowledge_coverage": None,
                "source_traceable": None,
                "closed_loop_complete": closed_loop_complete,
            },
            "metric_evidence": {
                "required_citation_count": 0,
                "traceable_citation_count": 0,
            },
            "failure_reasons": sorted(set(failures)),
        }
        write_json(self.raw_dir / f"case-{case['case_id']}.json", redact(raw))
        return result


def write_review_template(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        fieldnames = [
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
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            for reviewer in ("reviewer-1", "reviewer-2"):
                writer.writerow({"case_id": case["case_id"], "reviewer_id": reviewer})


def create_manifest(
    *,
    run_id: str,
    cases_path: Path,
    health_response: TimedResponse,
    seed: int,
    base_url: str,
) -> dict[str, Any]:
    repository = repository_state()
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "created_at": utc_now(),
        "run_kind": manifest_run_kind(repository),
        "repository": repository,
        "configuration": {
            "base_url": base_url,
            "random_seed": seed,
            "model_name": os.getenv("OPENAI_MODEL") or "not_exposed_to_runner",
            "temperature": 0.2,
            "request_timeout_seconds": None,
            "retry_count": 0,
        },
        "inputs": {
            "frozen_cases": str(cases_path.relative_to(REPOSITORY_ROOT)),
            "frozen_cases_sha256": sha256_file(cases_path),
            "runner_sha256": sha256_file(Path(__file__).resolve()),
        },
        "health_check": {
            "started_at": health_response.started_at,
            "finished_at": health_response.finished_at,
            "status_code": health_response.status_code,
            "response": health_response.payload,
        },
        "privacy": {
            "credentials_exported": False,
            "tokens_exported": False,
            "real_personal_information_used": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 ECHO 冻结的 50 组比赛评测案例。")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument(
        "--cases",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "member-d" / "eval_50_cases.json",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "competition-evaluation",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument(
        "--evaluation-seed-key",
        default=os.getenv("EVALUATION_PROFILE_SEED_KEY", ""),
        help="gated key used only to materialize frozen P1/P2/P3 synthetic state",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases_path = args.cases.resolve()
    cases = load_frozen_cases(cases_path)
    selected = set(args.case_ids or [str(case["case_id"]) for case in cases])
    unknown = selected - {str(case["case_id"]) for case in cases}
    if unknown:
        raise EvaluationRunError(f"unknown case_id values: {', '.join(sorted(unknown))}")

    run_dir = args.run_root.resolve() / safe_slug(args.run_id, limit=64)
    if run_dir.exists() and not args.resume:
        raise EvaluationRunError(f"run directory already exists; use --resume: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    client = LiveEchoClient(args.base_url, timeout_seconds=args.timeout_seconds)
    runner = CompetitionEvaluationRunner(
        client=client,
        run_dir=run_dir,
        run_id=args.run_id,
        seed=args.seed,
        evaluation_seed_key=args.evaluation_seed_key,
    )
    try:
        health_response = runner.health()
        write_json(run_dir / "environment-health.json", health_response.__dict__)
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            manifest = create_manifest(
                run_id=args.run_id,
                cases_path=cases_path,
                health_response=health_response,
                seed=args.seed,
                base_url=args.base_url,
            )
            manifest["configuration"]["request_timeout_seconds"] = args.timeout_seconds
            write_json(manifest_path, manifest)
            write_review_template(run_dir / "human-review-template.csv", cases)

        todo = pending_cases(cases, runner.results_dir, selected_case_ids=selected)
        for index, case in enumerate(todo, start=1):
            case_id = str(case["case_id"])
            print(f"[{index}/{len(todo)}] running case {case_id}", flush=True)
            try:
                result = runner.run_case(case, health_response.payload)
            except Exception as exc:
                result = {
                    "schema_version": "1.0",
                    "run_id": args.run_id,
                    "case_id": case_id,
                    "learner_type": case["learner_type"],
                    "module": case["module"],
                    "knowledge_point": case["knowledge_point"],
                    "scenario_type": case["scenario_type"],
                    "status": "failed",
                    "started_at": utc_now(),
                    "finished_at": utc_now(),
                    "request": {"input": case["input"]},
                    "actual_output": {"error_type": type(exc).__name__, "error": str(exc)},
                    "agent_records": {
                        name: {
                            "status": "not_run",
                            "input_summary": None,
                            "output": None,
                            "failure_reason": str(exc),
                            "started_at": None,
                            "finished_at": None,
                            "persisted_in_system": False,
                        }
                        for name in AGENT_NAMES
                    },
                    "citations": [],
                    "resource_record": None,
                    "human_review": pending_human_review(case),
                    "metric_flags": {
                        "difficulty_match": None,
                        "knowledge_coverage": None,
                        "source_traceable": None,
                        "closed_loop_complete": False,
                    },
                    "metric_evidence": {
                        "required_citation_count": 0,
                        "traceable_citation_count": 0,
                    },
                    "failure_reasons": [f"RUNNER_OR_SYSTEM_ERROR({type(exc).__name__})"],
                }
            write_json(result_path(runner.results_dir, case_id), result)
    finally:
        client.close()

    result_count = len(load_actual_results(runner.results_dir))
    print(f"run_dir={run_dir}")
    print(f"result_count={result_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
