"""Verify real PunditRAG retrieval coverage for all twelve ECHO knowledge points.

The verifier calls the live query service, keeps the unmodified response, maps
each returned document id back to ECHO's Upload row, and only passes a knowledge
point when at least one cited source belongs to a manifest material explicitly
assigned to that knowledge point.  It never substitutes expected text for a
missing retrieval result.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPOSITORY_ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app import ensure_catalog, is_official_microsoft_source_url  # noqa: E402
from catalog import KNOWLEDGE_BASE_CODE  # noqa: E402
from database import KnowledgeBase, SessionLocal, Upload, init_db  # noqa: E402

QUERY_CASES = (
    ("M1-KP1", "M1", "How do I create a Semantic Kernel and add an AI chat completion service?"),
    ("M1-KP2", "M1", "How does Semantic Kernel prompt template syntax reference variables and functions?"),
    ("M1-KP3", "M1", "How should native code plugins and their functions be defined for Semantic Kernel agents?"),
    ("M1-KP4", "M1", "How do I create and manage a ChatHistory object for a multi-turn Semantic Kernel conversation?"),
    ("M2-KP1", "M2", "What are the responsibilities and core properties of a Semantic Kernel Agent?"),
    ("M2-KP2", "M2", "How does Semantic Kernel maintain agent conversation threads and state?"),
    ("M2-KP3", "M2", "How do Semantic Kernel vector stores support memory and relevant-content retrieval?"),
    ("M2-KP4", "M2", "When should Semantic Kernel agents use sequential or concurrent orchestration?"),
    ("M3-KP1", "M3", "How do steps and events work in the Semantic Kernel Process Framework?"),
    ("M3-KP2", "M3", "How are logs, metrics, and distributed traces added for Semantic Kernel observability?"),
    ("M3-KP3", "M3", "How do Semantic Kernel filters support security checks and exception handling?"),
    ("M3-KP4", "M3", "What observability and process evidence should be used to evaluate a deployed Semantic Kernel application?"),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"query request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("PunditRAG query response must be a JSON object")
    return result


def verify(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(args.manifest)
    materials = manifest.get("materials") or []
    material_by_url = {str(item["url"]): item for item in materials}
    expected_by_point: dict[str, set[str]] = {}
    for material in materials:
        for point_id in material.get("knowledge_point_ids") or []:
            expected_by_point.setdefault(str(point_id), set()).add(
                str(material["material_id"])
            )
    missing_assignments = [
        point_id for point_id, _, _ in QUERY_CASES if not expected_by_point.get(point_id)
    ]
    if missing_assignments:
        raise ValueError(
            "manifest does not assign formal material to: " + ", ".join(missing_assignments)
        )

    init_db()
    db = SessionLocal()
    try:
        ensure_catalog(db)
        knowledge_base = db.query(KnowledgeBase).filter_by(code=KNOWLEDGE_BASE_CODE).one()
        if not knowledge_base.external_ref:
            raise ValueError("formal knowledge base has no PunditRAG external reference")
        uploads = (
            db.query(Upload)
            .filter(
                Upload.knowledge_base_id == knowledge_base.id,
                Upload.index_status == "completed",
            )
            .all()
        )
        upload_by_document_id = {
            str(row.external_document_id): row
            for row in uploads
            if row.external_document_id
        }

        report: dict[str, Any] = {
            "schema_version": "1.0",
            "run_id": args.run_id,
            "started_at": utc_now(),
            "manifest_version": manifest.get("version"),
            "manifest_path": str(args.manifest),
            "query_base_url": args.query_base_url,
            "knowledge_base": {
                "id": knowledge_base.id,
                "code": knowledge_base.code,
                "external_ref": knowledge_base.external_ref,
                "completed_upload_count": len(uploads),
            },
            "checks": [],
        }
        for index, (point_id, module_id, query) in enumerate(QUERY_CASES, start=1):
            print(f"[{index}/{len(QUERY_CASES)}] {point_id}", flush=True)
            request_payload = {
                "query": query,
                "session_id": f"{args.run_id}-{point_id}-{uuid4().hex[:8]}",
                "scope_mode": "knowledge_base",
                "kb_ids": [knowledge_base.external_ref],
                # Match ECHO's publishable retrieval path: stale or unregistered
                # vectors in the external KB must not enter the evidence set.
                "document_ids": sorted(upload_by_document_id),
                "is_stream": False,
                "enable_web_search": False,
            }
            started_at = utc_now()
            started = time.monotonic()
            try:
                response = post_json(
                    f"{args.query_base_url.rstrip('/')}/query",
                    request_payload,
                    args.timeout_seconds,
                )
                error = None
            except Exception as exc:
                response = {}
                error = f"{type(exc).__name__}: {exc}"
            elapsed_seconds = round(time.monotonic() - started, 3)
            mapped_sources = []
            matched_material_ids: set[str] = set()
            for source in response.get("sources") or []:
                document_id = str(source.get("document_id") or "")
                upload = upload_by_document_id.get(document_id)
                material = material_by_url.get(str(upload.source_url)) if upload else None
                material_id = str(material.get("material_id")) if material else None
                if material_id in expected_by_point[point_id]:
                    matched_material_ids.add(material_id)
                mapped_sources.append(
                    {
                        "source": source,
                        "echo_upload_id": upload.id if upload else None,
                        "source_title": upload.source_title if upload else None,
                        "source_url": upload.source_url if upload else None,
                        "source_section": upload.source_section if upload else None,
                        "source_version": upload.source_version if upload else None,
                        "material_id": material_id,
                        "official_microsoft_url": bool(
                            upload
                            and upload.source_url
                            and is_official_microsoft_source_url(upload.source_url)
                        ),
                    }
                )
            publishable_sources = [
                item
                for item in mapped_sources
                if item["echo_upload_id"] is not None and item["official_microsoft_url"]
            ]
            filtered_unregistered_count = len(mapped_sources) - len(publishable_sources)
            passed = bool(matched_material_ids) and bool(publishable_sources)
            check = {
                "knowledge_point_id": point_id,
                "module_id": module_id,
                "query": query,
                "expected_material_ids": sorted(expected_by_point[point_id]),
                "started_at": started_at,
                "finished_at": utc_now(),
                "elapsed_seconds": elapsed_seconds,
                "request": request_payload,
                "response": response,
                "mapped_sources": mapped_sources,
                "filtered_unregistered_count": filtered_unregistered_count,
                "matched_material_ids": sorted(matched_material_ids),
                "status": "passed" if passed else "failed",
                "failure_reason": error
                or (None if passed else "no cited source mapped to an assigned official material"),
            }
            report["checks"].append(check)
            print(
                f"  status={check['status']} sources={len(mapped_sources)} "
                f"matched={','.join(check['matched_material_ids']) or '-'} "
                f"elapsed={elapsed_seconds}s",
                flush=True,
            )
        passed_count = sum(item["status"] == "passed" for item in report["checks"])
        report["finished_at"] = utc_now()
        report["summary"] = {
            "total_knowledge_points": len(QUERY_CASES),
            "passed": passed_count,
            "failed": len(QUERY_CASES) - passed_count,
            "coverage_rate": round(passed_count / len(QUERY_CASES), 4),
            "all_passed": passed_count == len(QUERY_CASES),
        }
        return report
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify twelve-knowledge-point official retrieval coverage."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "member-d" / "official_materials_manifest.json",
    )
    parser.add_argument("--query-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.manifest = args.manifest.resolve()
    args.output = args.output.resolve()
    report = verify(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"output={args.output}")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
