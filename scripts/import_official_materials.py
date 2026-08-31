"""Download, register, and index the frozen Microsoft official material set.

The command is a validation-only dry run unless ``--apply`` is passed.  During an
applied run it keeps the untouched HTTP response and a retrieval-oriented HTML
copy, records both hashes, creates the ECHO Upload rows, and sends the normalized
copy through ECHO's PunditRAG adapter.  It never marks a document completed until
the external import task reports completion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
import time
from copy import deepcopy
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
from database import (  # noqa: E402
    KnowledgeBase,
    KnowledgePoint,
    SessionLocal,
    TrainingModule,
    Upload,
    User,
    UserRole,
    init_db,
)
from integrations.http_client import IntegrationUnavailable  # noqa: E402
from integrations.punditrag import PunditRAGClient  # noqa: E402

USER_AGENT = "ECHO-Competition-Material-Importer/1.0 (+official-source-archive)"
TERMINAL_IMPORT_STATES = {"completed", "failed"}
ACTIVE_IMPORT_STATES = {"pending", "processing"}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    materials = payload.get("materials")
    if not isinstance(materials, list) or not materials:
        raise ValueError("official material manifest must contain a non-empty materials list")
    if int(payload.get("total_materials") or 0) != len(materials):
        raise ValueError("official material manifest count does not match materials")

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for material in materials:
        material_id = str(material.get("material_id") or "").strip()
        source_url = str(material.get("url") or "").strip()
        download_url = str(material.get("download_url") or source_url).strip()
        module_code = str(material.get("module_id") or "").strip()
        if not material_id or material_id in seen_ids:
            raise ValueError(f"invalid or duplicated material_id: {material_id!r}")
        if not source_url or source_url in seen_urls:
            raise ValueError(f"invalid or duplicated source URL: {source_url!r}")
        if not is_official_microsoft_source_url(source_url):
            raise ValueError(f"material is outside the allowed Microsoft sources: {source_url}")
        if not is_official_microsoft_source_url(download_url):
            raise ValueError(
                f"material download is outside the allowed Microsoft sources: {download_url}"
            )
        if module_code not in {"M1", "M2", "M3"}:
            raise ValueError(f"invalid module_id for {material_id}: {module_code}")
        seen_ids.add(material_id)
        seen_urls.add(source_url)
    return payload


def download_official_content(url: str, *, timeout_seconds: float) -> tuple[bytes, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/markdown,text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            content = response.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise ValueError(f"official page exceeds 20 MiB limit: {url}")
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"failed to download {url}: {exc}") from exc
    if len(content) < 2_000:
        raise ValueError(f"official page response is unexpectedly short: {url}")
    if content_type not in {"text/html", "application/xhtml+xml", "text/markdown", "text/plain"}:
        raise ValueError(f"official page returned unsupported content type {content_type}: {url}")
    return content, final_url, content_type


def normalize_official_html(raw_html: bytes, material: dict[str, Any]) -> bytes:
    """Keep the article body and add explicit immutable source metadata."""

    from lxml import etree, html

    parser = html.HTMLParser(encoding="utf-8", recover=True)
    document = html.fromstring(raw_html, parser=parser)
    candidates = document.xpath(
        "//main[@id='main'] | //main | //article | //*[@role='main']"
    )
    article = deepcopy(candidates[0] if candidates else document)
    for unwanted in article.xpath(
        ".//script | .//style | .//noscript | .//nav | .//header | .//footer | "
        ".//form | .//button | .//svg | .//iframe"
    ):
        parent = unwanted.getparent()
        if parent is not None:
            parent.remove(unwanted)

    body = etree.Element("body")
    metadata = etree.SubElement(body, "section")
    metadata.set("data-echo-source-metadata", "true")
    title = etree.SubElement(metadata, "h1")
    title.text = str(material["title"])
    fields = [
        ("Material ID", material["material_id"]),
        ("Official source URL", material["url"]),
        ("Source version/date", material["version"]),
        ("ECHO module", material["module_id"]),
        ("Knowledge points", ", ".join(material.get("knowledge_point_ids") or [])),
        ("Registered section", material.get("section") or "全文"),
    ]
    for label, value in fields:
        paragraph = etree.SubElement(metadata, "p")
        strong = etree.SubElement(paragraph, "strong")
        strong.text = f"{label}: "
        strong.tail = str(value)
    body.append(article)

    root = etree.Element("html")
    head = etree.SubElement(root, "head")
    charset = etree.SubElement(head, "meta")
    charset.set("charset", "utf-8")
    root.append(body)
    normalized = html.tostring(root, encoding="utf-8", method="html", pretty_print=True)
    if len(" ".join(article.itertext()).strip()) < 500:
        raise ValueError(f"official page has too little article text: {material['url']}")
    return normalized


def normalize_official_markdown(raw_markdown: bytes, material: dict[str, Any]) -> bytes:
    """Convert official Markdown into retrieval-friendly semantic HTML."""

    from lxml import etree, html

    markdown_text = raw_markdown.decode("utf-8", errors="replace").strip()
    if len(markdown_text) < 500:
        raise ValueError(f"official Markdown has too little text: {material['url']}")
    body = etree.Element("body")
    metadata = etree.SubElement(body, "section")
    metadata.set("data-echo-source-metadata", "true")
    title = etree.SubElement(metadata, "h1")
    title.text = str(material["title"])
    for label, value in (
        ("Material ID", material["material_id"]),
        ("Official source URL", material["url"]),
        ("Source version/date", material["version"]),
        ("ECHO module", material["module_id"]),
        ("Knowledge points", ", ".join(material.get("knowledge_point_ids") or [])),
        ("Registered section", material.get("section") or "全文"),
    ):
        paragraph = etree.SubElement(metadata, "p")
        strong = etree.SubElement(paragraph, "strong")
        strong.text = f"{label}: "
        strong.tail = str(value)
    article = etree.SubElement(body, "article")
    fenced_blocks = re.findall(
        r"```([^\n]*)\n(.*?)```", markdown_text, flags=re.DOTALL
    )
    highlight_groups = material.get("highlight_term_groups") or []
    if highlight_groups:
        highlights = etree.SubElement(body, "section")
        highlights.set("data-echo-retrieval-highlights", "true")
        highlight_title = etree.SubElement(highlights, "h2")
        highlight_title.text = "Official retrieval highlights"
        for raw_group in highlight_groups:
            terms = [str(term).strip() for term in raw_group if str(term).strip()]
            matched_block = next(
                (
                    (language, block)
                    for language, block in fenced_blocks
                    if all(term.casefold() in block.casefold() for term in terms)
                ),
                None,
            )
            if matched_block is None:
                raise ValueError(
                    f"official Markdown is missing configured highlight terms for "
                    f"{material['material_id']}: {terms}"
                )
            language, block = matched_block
            # PunditRAG may omit pre/code blocks from returned source snippets.
            # Keep the verbatim official block as plain text too so generated
            # facts remain traceable to a visible retrieval result.
            paragraph = etree.SubElement(highlights, "p")
            language_label = f" ({language.strip()})" if language.strip() else ""
            paragraph.text = f"Official code excerpt{language_label}:\n{block.strip()}"
    code_lines: list[str] = []
    code_language = ""
    in_code_block = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            if in_code_block:
                preformatted = etree.SubElement(article, "pre")
                code = etree.SubElement(preformatted, "code")
                if code_language:
                    code.set("data-language", code_language)
                code.text = "\n".join(code_lines).strip()
                code_lines = []
                code_language = ""
                in_code_block = False
            else:
                code_language = line.lstrip()[3:].strip()
                in_code_block = True
            continue
        if in_code_block:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            continue
        heading_level = len(stripped) - len(stripped.lstrip("#"))
        if 1 <= heading_level <= 6 and stripped[heading_level:].startswith(" "):
            heading = etree.SubElement(article, f"h{heading_level}")
            heading.text = stripped[heading_level:].strip()
            continue
        paragraph = etree.SubElement(article, "p")
        paragraph.text = stripped
    if code_lines:
        preformatted = etree.SubElement(article, "pre")
        code = etree.SubElement(preformatted, "code")
        if code_language:
            code.set("data-language", code_language)
        code.text = "\n".join(code_lines).strip()
    root = etree.Element("html")
    head = etree.SubElement(root, "head")
    charset = etree.SubElement(head, "meta")
    charset.set("charset", "utf-8")
    root.append(body)
    return html.tostring(root, encoding="utf-8", method="html", pretty_print=True)


def choose_import_user(db, username: str | None) -> User:
    query = db.query(User)
    if username:
        user = query.filter_by(username=username).first()
        if user is None:
            raise ValueError(f"import user does not exist: {username}")
        if user.role not in {UserRole.SYSTEM_ADMIN.value, UserRole.MENTOR.value}:
            raise ValueError("import user must be a system administrator or mentor")
        return user
    user = query.filter_by(role=UserRole.SYSTEM_ADMIN.value).order_by(User.id).first()
    if user is None:
        user = query.filter_by(role=UserRole.MENTOR.value).order_by(User.id).first()
    if user is None:
        raise ValueError("no system administrator or mentor is available for material import")
    return user


def get_module(db, *, module_code: str, organization_id: int) -> TrainingModule:
    module = (
        db.query(TrainingModule)
        .join(TrainingModule.program)
        .filter(
            TrainingModule.code == module_code,
            TrainingModule.program.has(organization_id=organization_id),
        )
        .first()
    )
    if module is None:
        raise ValueError(f"training module is missing: {module_code}")
    return module


def wait_for_import(
    client: PunditRAGClient,
    task_id: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] = {"task_id": task_id, "status": "pending"}
    while time.monotonic() < deadline:
        payload = client.get_import_status(task_id)
        last_payload = payload
        status = str(payload.get("status") or "").strip()
        if status in TERMINAL_IMPORT_STATES:
            return payload
        if status not in ACTIVE_IMPORT_STATES:
            raise ValueError(f"PunditRAG returned unknown import state: {status!r}")
        time.sleep(poll_seconds)
    return {
        **last_payload,
        "status": "processing",
        "error": f"polling exceeded {timeout_seconds:g} seconds; task may still be running",
    }


def existing_upload(db, module: TrainingModule, source_url: str) -> Upload | None:
    return (
        db.query(Upload)
        .filter(
            Upload.knowledge_base_id == module.knowledge_base_id,
            Upload.module_id == module.id,
            Upload.source_url == source_url,
        )
        .order_by(Upload.id.desc())
        .first()
    )


def import_materials(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    init_db()
    db = SessionLocal()
    report: dict[str, Any] = {
        "run_id": args.run_id,
        "mode": "apply" if args.apply else "dry-run",
        "started_at": datetime.now(UTC).isoformat(),
        "manifest": str(args.manifest),
        "items": [],
    }
    try:
        ensure_catalog(db)
        user = choose_import_user(db, args.username)
        modules = {
            code: get_module(db, module_code=code, organization_id=user.organization_id)
            for code in ("M1", "M2", "M3")
        }
        points_by_code = {
            point.code: point
            for point in db.query(KnowledgePoint)
            .filter(KnowledgePoint.module_id.in_([module.id for module in modules.values()]))
            .all()
        }
        knowledge_base_ids = {module.knowledge_base_id for module in modules.values()}
        if len(knowledge_base_ids) != 1:
            raise ValueError("M1/M2/M3 must share one formal knowledge base")
        knowledge_base = db.get(KnowledgeBase, next(iter(knowledge_base_ids)))
        if knowledge_base is None:
            raise ValueError("formal knowledge base row is missing")

        client = PunditRAGClient()
        if args.apply and not client.import_configured:
            raise ValueError("PunditRAG import service is not configured")
        if args.apply and not knowledge_base.external_ref:
            external = client.ensure_knowledge_base(
                name=knowledge_base.name,
                description=(
                    "ECHO Semantic Kernel official competition corpus; Microsoft Learn and "
                    "microsoft/semantic-kernel sources only."
                ),
            )
            knowledge_base.external_ref = str(external["kb_id"])
            db.commit()

        run_root = args.output_root / args.run_id
        raw_root = run_root / "raw"
        normalized_root = run_root / "normalized"
        if args.apply:
            raw_root.mkdir(parents=True, exist_ok=True)
            normalized_root.mkdir(parents=True, exist_ok=True)

        material_count = len(manifest["materials"])
        for material_index, material in enumerate(manifest["materials"], start=1):
            print(
                f"[{material_index}/{material_count}] {material['material_id']} "
                f"({material['module_id']})",
                flush=True,
            )
            module = modules[str(material["module_id"])]
            mapped_point_ids = [
                points_by_code[code].id
                for code in material.get("knowledge_point_ids") or []
                if code in points_by_code
            ]
            if len(mapped_point_ids) != len(material.get("knowledge_point_ids") or []):
                raise ValueError(
                    f"material contains an unknown knowledge point: {material['material_id']}"
                )
            previous = existing_upload(db, module, str(material["url"]))
            item: dict[str, Any] = {
                "material_id": material["material_id"],
                "module_id": material["module_id"],
                "source_url": material["url"],
                "download_url": material.get("download_url") or material["url"],
                "previous_upload_id": previous.id if previous else None,
                "previous_status": previous.index_status if previous else None,
            }
            report["items"].append(item)
            if not args.apply:
                item["status"] = "validated"
                continue
            if previous and previous.index_status in {"completed", "pending", "processing"}:
                if sorted(previous.knowledge_point_ids or []) != sorted(mapped_point_ids):
                    previous.knowledge_point_ids = mapped_point_ids
                    db.commit()
                if previous.external_task_id and previous.index_status in ACTIVE_IMPORT_STATES:
                    task = wait_for_import(
                        client,
                        previous.external_task_id,
                        timeout_seconds=args.import_timeout_seconds,
                        poll_seconds=args.poll_seconds,
                    )
                    previous.index_status = str(task.get("status") or previous.index_status)
                    previous.index_error = str(task.get("error") or "").strip() or None
                    db.commit()
                item.update(
                    {
                        "status": "reused",
                        "upload_id": previous.id,
                        "document_id": previous.external_document_id,
                        "task_id": previous.external_task_id,
                        "index_status": previous.index_status,
                        "index_error": previous.index_error,
                    }
                )
                print(
                    f"  reused upload={previous.id} status={previous.index_status}",
                    flush=True,
                )
                continue

            raw, final_url, content_type = download_official_content(
                str(material.get("download_url") or material["url"]),
                timeout_seconds=args.download_timeout_seconds,
            )
            if not is_official_microsoft_source_url(final_url):
                raise ValueError(f"official page redirected outside the allowed sources: {final_url}")
            normalized = (
                normalize_official_markdown(raw, material)
                if content_type in {"text/markdown", "text/plain"}
                else normalize_official_html(raw, material)
            )
            print(
                f"  downloaded raw={len(raw)} bytes normalized={len(normalized)} bytes",
                flush=True,
            )
            raw_suffix = ".source.md" if content_type in {"text/markdown", "text/plain"} else ".source.html"
            raw_path = raw_root / f"{material['material_id']}{raw_suffix}"
            normalized_path = normalized_root / f"{material['material_id']}.html"
            raw_path.write_bytes(raw)
            normalized_path.write_bytes(normalized)

            upload = Upload(
                user_id=user.id,
                module_id=module.id,
                knowledge_base_id=module.knowledge_base_id,
                knowledge_point_ids=mapped_point_ids,
                filename=normalized_path.name,
                filepath=str(normalized_path.resolve()),
                file_type=mimetypes.guess_type(normalized_path.name)[0] or "text/html",
                file_size=len(normalized),
                source_title=str(material["title"]),
                source_url=str(material["url"]),
                source_section=str(material.get("section") or "全文"),
                source_version=str(material["version"]),
                index_status="stored",
            )
            db.add(upload)
            db.flush()
            trace_id = uuid4().hex
            try:
                result = client.ingest_document(
                    knowledge_base_id=module.knowledge_base_id,
                    module_id=module.id,
                    filename=upload.filename,
                    content=normalized,
                    content_type=upload.file_type,
                    trace_id=trace_id,
                    external_knowledge_base_id=knowledge_base.external_ref,
                )
                upload.external_document_id = result["document_id"]
                upload.external_task_id = result["task_id"]
                upload.index_status = result["status"]
                db.commit()
                task = wait_for_import(
                    client,
                    upload.external_task_id,
                    timeout_seconds=args.import_timeout_seconds,
                    poll_seconds=args.poll_seconds,
                )
                upload.index_status = str(task.get("status") or upload.index_status)
                upload.index_error = str(task.get("error") or "").strip() or None
                db.commit()
            except (IntegrationUnavailable, OSError, RuntimeError, ValueError) as exc:
                upload.index_status = "failed"
                upload.index_error = str(exc)
                db.commit()
                item["error"] = str(exc)

            item.update(
                {
                    "status": "imported" if upload.index_status == "completed" else "failed",
                    "upload_id": upload.id,
                    "document_id": upload.external_document_id,
                    "task_id": upload.external_task_id,
                    "index_status": upload.index_status,
                    "index_error": upload.index_error,
                    "final_url": final_url,
                    "http_content_type": content_type,
                    "raw_file": str(raw_path.resolve()),
                    "raw_sha256": sha256_bytes(raw),
                    "normalized_file": str(normalized_path.resolve()),
                    "normalized_sha256": sha256_bytes(normalized),
                    "raw_bytes": len(raw),
                    "normalized_bytes": len(normalized),
                }
            )
            print(
                f"  upload={upload.id} task={upload.external_task_id} "
                f"status={upload.index_status}",
                flush=True,
            )
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        completed = sum(item.get("index_status") == "completed" for item in report["items"])
        failed = sum(item.get("index_status") == "failed" for item in report["items"])
        report["summary"] = {
            "total": len(report["items"]),
            "completed": completed,
            "failed": failed,
            "not_completed": len(report["items"]) - completed,
        }
        if args.apply:
            args.output_root.mkdir(parents=True, exist_ok=True)
            report_path = args.output_root / args.run_id / "material-import-report.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            report["report_path"] = str(report_path.resolve())
        db.close()
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or import the frozen Microsoft official material set."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "member-d" / "official_materials_manifest.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "formal-materials",
    )
    parser.add_argument(
        "--run-id",
        default=f"official-materials-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
    )
    parser.add_argument("--username", help="Existing administrator or mentor account.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--download-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--import-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = import_materials(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.apply and report["summary"]["not_completed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
