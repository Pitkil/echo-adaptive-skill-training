"""Build and validate a traceable Semantic Kernel knowledge-base slice.

Downloaded source files and generated chunks are runtime/delivery data and are
written under ``data/`` by default. They must not be committed blindly: review
the applicable Microsoft terms before placing source text in a submission.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs" / "member-d" / "official_materials_manifest.json"
DEFAULT_OUTPUT = ROOT / "data" / "official-kb-slice"
ALLOWED_HOSTS = {"learn.microsoft.com", "github.com"}
VALID_MODULES = {"M1", "M2", "M3"}
KNOWLEDGE_POINT_PATTERN = re.compile(r"^M([1-3])-KP([1-4])$")
MICROSOFT_LEARN_TERMS_URL = "https://learn.microsoft.com/en-us/legal/termsofuse"
SEMANTIC_KERNEL_LICENSE_URL = (
    "https://github.com/microsoft/semantic-kernel/blob/main/LICENSE"
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def clean_captured_markdown(content: str) -> str:
    """Remove known Microsoft Learn navigation/auth boilerplate from captured content."""

    ignored = {
        "Note",
        "Access to this page requires authorization. You can try signing in or changing directories .",
        "Access to this page requires authorization. You can try signing in or changing directories.",
        "Access to this page requires authorization. You can try changing directories .",
        "Access to this page requires authorization. You can try changing directories.",
    }
    lines = [line for line in content.splitlines() if line.strip() not in ignored]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned + "\n"


class LearnMainExtractor(HTMLParser):
    """Extract headings, paragraphs, lists and code from Microsoft Learn HTML."""

    BLOCKS = {"h1", "h2", "h3", "h4", "p", "li", "pre", "code"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.main_depth = 0
        self.current_tag: str | None = None
        self.buffer: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "main" or attributes.get("role") == "main":
            self.in_main = True
            self.main_depth = 1
            return
        if self.in_main:
            self.main_depth += 1
            if tag in self.BLOCKS and self.current_tag is None:
                self.current_tag = tag
                self.buffer = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_main:
            return
        if self.current_tag == tag:
            text = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
            if text:
                self.blocks.append((tag, html.unescape(text)))
            self.current_tag = None
            self.buffer = []
        self.main_depth -= 1
        if self.main_depth <= 0:
            self.in_main = False

    def handle_data(self, data: str) -> None:
        if self.in_main and self.current_tag:
            self.buffer.append(data)

    def markdown(self) -> str:
        lines: list[str] = []
        for tag, text in self.blocks:
            if tag.startswith("h"):
                lines.extend([f"{'#' * int(tag[1])} {text}", ""])
            elif tag == "li":
                lines.append(f"- {text}")
            elif tag in {"pre", "code"}:
                lines.extend(["```text", text, "```", ""])
            else:
                lines.extend([text, ""])
        return "\n".join(lines).strip() + "\n"


def validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"source URL is not allowed: {url}")
    github_repo = "/microsoft/semantic-kernel"
    if parsed.hostname == "github.com" and parsed.path.rstrip("/") != github_repo and not parsed.path.startswith(
        f"{github_repo}/"
    ):
        raise ValueError(f"GitHub source is outside microsoft/semantic-kernel: {url}")


def load_registry(path: Path) -> dict:
    registry = json.loads(path.read_text(encoding="utf-8"))
    materials = registry.get("materials")
    if not isinstance(materials, list) or not materials:
        raise ValueError("registry must contain a non-empty materials list")
    if registry.get("total_materials") != len(materials):
        raise ValueError("registry total_materials does not match materials")
    ids = [str(item.get("material_id") or "") for item in materials]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("material_id values must be non-empty and unique")
    for item in materials:
        validate_source_url(str(item.get("url") or ""))
        if item.get("module_id") not in VALID_MODULES:
            raise ValueError(f"invalid module_id for {item['material_id']}")
        knowledge_point_ids = item.get("knowledge_point_ids")
        if not isinstance(knowledge_point_ids, list) or not knowledge_point_ids:
            raise ValueError(f"missing knowledge_point_ids for {item['material_id']}")
        if len(knowledge_point_ids) != len(set(knowledge_point_ids)):
            raise ValueError(f"duplicate knowledge_point_ids for {item['material_id']}")
        for knowledge_point_id in knowledge_point_ids:
            match = KNOWLEDGE_POINT_PATTERN.fullmatch(str(knowledge_point_id))
            if not match or f"M{match.group(1)}" != item["module_id"]:
                raise ValueError(
                    f"invalid knowledge_point_id for {item['material_id']}: "
                    f"{knowledge_point_id}"
                )
        if not str(item.get("version") or "").strip():
            raise ValueError(f"missing source version for {item['material_id']}")
        if not str(item.get("section") or "").strip():
            raise ValueError(f"missing source section for {item['material_id']}")
    return registry


def fetch_material(item: dict, output_dir: Path) -> dict:
    material_id = item["material_id"]
    request = Request(
        item["url"],
        headers={"User-Agent": "ECHO-Competition-KB-Builder/1.0"},
    )
    with urlopen(request, timeout=45) as response:  # noqa: S310 - allowlisted above
        raw = response.read()
        final_url = response.geturl()
        status = response.status
        content_type = response.headers.get_content_type()
    validate_source_url(final_url)
    source_dir = output_dir / "files"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / f"{material_id}.html"
    raw_path.write_bytes(raw)
    extractor = LearnMainExtractor()
    extractor.feed(raw.decode("utf-8", errors="replace"))
    cleaned = extractor.markdown()
    if len(cleaned) < 200:
        raise ValueError(f"extracted content is unexpectedly short: {material_id}")
    clean_path = source_dir / f"{material_id}.md"
    clean_path.write_text(cleaned, encoding="utf-8", newline="\n")
    source_host = urlparse(final_url).hostname
    license_url = (
        SEMANTIC_KERNEL_LICENSE_URL
        if source_host == "github.com"
        else MICROSOFT_LEARN_TERMS_URL
    )
    return {
        **item,
        "resolved_url": final_url,
        "http_status": status,
        "content_type": content_type,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "local_file": clean_path.relative_to(output_dir).as_posix(),
        "source_file_sha256": sha256_bytes(raw),
        "sha256": sha256_bytes(cleaned.encode("utf-8")),
        "license_note": item.get("license_note")
        or "Microsoft official source; redistribution scope must be reviewed before delivery",
        "license_url": item.get("license_url") or license_url,
        "import_status": "prepared",
    }


def prepare_existing_material(
    item: dict,
    existing_dir: Path,
    output_dir: Path,
    existing_metadata: dict,
) -> dict:
    """Rebuild one material from a previously captured, hashable source pair."""

    material_id = item["material_id"]
    existing_files = existing_dir / "files"
    raw_source = existing_files / f"{material_id}.html"
    clean_source = existing_files / f"{material_id}.md"
    if not raw_source.is_file() or not clean_source.is_file():
        raise ValueError(f"existing source pair is incomplete: {material_id}")
    raw = raw_source.read_bytes()
    cleaned = clean_captured_markdown(clean_source.read_text(encoding="utf-8"))
    if not raw or len(cleaned) < 200:
        raise ValueError(f"existing source content is unexpectedly short: {material_id}")
    source_dir = output_dir / "files"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / raw_source.name
    clean_path = source_dir / clean_source.name
    shutil.copyfile(raw_source, raw_path)
    clean_path.write_text(cleaned, encoding="utf-8", newline="\n")
    resolved_url = str(existing_metadata.get("resolved_url") or item["url"])
    validate_source_url(resolved_url)
    source_host = urlparse(resolved_url).hostname
    license_url = (
        SEMANTIC_KERNEL_LICENSE_URL
        if source_host == "github.com"
        else MICROSOFT_LEARN_TERMS_URL
    )
    return {
        **item,
        "resolved_url": resolved_url,
        "http_status": existing_metadata.get("http_status", 200),
        "content_type": existing_metadata.get("content_type", "text/html"),
        "retrieved_at": existing_metadata.get("retrieved_at"),
        "local_file": clean_path.relative_to(output_dir).as_posix(),
        "source_file_sha256": sha256_bytes(raw),
        "sha256": sha256_bytes(cleaned.encode("utf-8")),
        "license_note": item.get("license_note")
        or "Microsoft official source; redistribution scope must be reviewed before delivery",
        "license_url": item.get("license_url") or license_url,
        "import_status": "prepared",
    }


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:60] or "section"


def split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Split one oversized paragraph without silently exceeding the chunk limit."""

    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", paragraph)]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[offset : offset + max_chars]
                for offset in range(0, len(sentence), max_chars)
            )
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def split_material(item: dict, output_dir: Path, max_chars: int) -> list[dict]:
    path = (output_dir / item["local_file"]).resolve()
    if output_dir.resolve() not in path.parents:
        raise ValueError(f"local_file escapes output directory: {item['material_id']}")
    text = path.read_text(encoding="utf-8")
    sections: list[tuple[str, list[str]]] = []
    section = item.get("section") or "Full article"
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and buffer:
            sections.append((section, buffer))
            section = line.lstrip("# ").strip()
            buffer = [line]
        else:
            if line.startswith("#"):
                section = line.lstrip("# ").strip()
            buffer.append(line)
    if buffer:
        sections.append((section, buffer))

    chunks: list[dict] = []
    index = 0
    for section_name, lines in sections:
        raw_paragraphs = [
            part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()
        ]
        paragraphs = [
            piece
            for paragraph in raw_paragraphs
            for piece in split_long_paragraph(paragraph, max_chars)
        ]
        current: list[str] = []
        current_length = 0
        groups: list[str] = []
        for paragraph in paragraphs:
            if current and current_length + len(paragraph) + 2 > max_chars:
                groups.append("\n\n".join(current))
                current, current_length = [], 0
            current.append(paragraph)
            current_length += len(paragraph) + 2
        if current:
            groups.append("\n\n".join(current))
        for body in groups:
            index += 1
            body_bytes = body.encode("utf-8")
            chunks.append(
                {
                    "chunk_id": f"{item['material_id']}#{slug(section_name)}#{index:04d}",
                    "material_id": item["material_id"],
                    "title": item["title"],
                    "source_url": item.get("resolved_url") or item["url"],
                    "source_section": section_name,
                    "source_version": item["version"],
                    "module_id": item["module_id"],
                    "knowledge_point_ids": item["knowledge_point_ids"],
                    "text": body,
                    "content_sha256": sha256_bytes(body_bytes),
                    "source_file_sha256": item["sha256"],
                    "license_note": item["license_note"],
                    "license_url": item["license_url"],
                }
            )
    return chunks


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clear_generated_files(output_dir: Path) -> None:
    """Remove only the generated source-file directory before rebuilding."""

    files_dir = output_dir / "files"
    if files_dir.exists() and not files_dir.is_dir():
        raise ValueError(f"generated files path is not a directory: {files_dir}")
    if files_dir.is_dir():
        shutil.rmtree(files_dir)


def build(registry_path: Path, output_dir: Path, max_chars: int) -> None:
    if max_chars < 400:
        raise ValueError("max_chars must be at least 400")
    registry = load_registry(registry_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    clear_generated_files(output_dir)
    prepared: list[dict] = []
    failures: list[dict] = []
    for item in registry["materials"]:
        try:
            prepared.append(fetch_material(item, output_dir))
            print(f"prepared {item['material_id']}")
        except (OSError, ValueError) as exc:
            failures.append({"material_id": item["material_id"], "error": str(exc)})
            print(f"failed {item['material_id']}: {exc}", file=sys.stderr)
    duplicate_urls: dict[str, list[str]] = {}
    duplicate_hashes: dict[str, list[str]] = {}
    for item in prepared:
        duplicate_urls.setdefault(item["resolved_url"], []).append(item["material_id"])
        duplicate_hashes.setdefault(item["sha256"], []).append(item["material_id"])
    duplicates = [
        {"kind": "resolved_url", "value": value, "material_ids": ids}
        for value, ids in duplicate_urls.items()
        if len(ids) > 1
    ] + [
        {"kind": "content_sha256", "value": value, "material_ids": ids}
        for value, ids in duplicate_hashes.items()
        if len(ids) > 1
    ]
    if duplicates:
        for duplicate in duplicates:
            print(f"duplicate {duplicate}", file=sys.stderr)
        failures.extend(
            {"material_id": ",".join(item["material_ids"]), "error": f"duplicate {item['kind']}"}
            for item in duplicates
        )
    chunks = [chunk for item in prepared for chunk in split_material(item, output_dir, max_chars)]
    delivery_manifest = {
        "version": registry["version"],
        "source_registry": registry_path.relative_to(ROOT).as_posix(),
        "prepared_materials": len(prepared),
        "failed_materials": failures,
        "duplicate_sources": duplicates,
        "materials": prepared,
    }
    write_json(output_dir / "manifest.json", delivery_manifest)
    with (output_dir / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    sums: list[str] = []
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
        sums.append(f"{sha256_bytes(path.read_bytes())}  {path.relative_to(output_dir).as_posix()}")
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"prepared={len(prepared)} failed={len(failures)} chunks={len(chunks)}")
    if failures:
        raise SystemExit(2)


def rebuild(
    registry_path: Path,
    existing_dir: Path,
    output_dir: Path,
    max_chars: int,
) -> None:
    """Rebuild a slice from previously captured official source files."""

    if existing_dir.resolve() == output_dir.resolve():
        raise ValueError("existing and output directories must be different")
    registry = load_registry(registry_path)
    existing_manifest = json.loads(
        (existing_dir / "manifest.json").read_text(encoding="utf-8")
    )
    metadata_by_id = {
        item["material_id"]: item for item in existing_manifest.get("materials", [])
    }
    prepared: list[dict] = []
    failures: list[dict] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    clear_generated_files(output_dir)
    for item in registry["materials"]:
        try:
            prepared.append(
                prepare_existing_material(
                    item,
                    existing_dir,
                    output_dir,
                    metadata_by_id.get(item["material_id"], {}),
                )
            )
        except (OSError, ValueError) as exc:
            failures.append({"material_id": item["material_id"], "error": str(exc)})
    chunks = [
        chunk
        for item in prepared
        for chunk in split_material(item, output_dir, max_chars)
    ]
    delivery_manifest = {
        "version": registry["version"],
        "source_registry": registry_path.relative_to(ROOT).as_posix(),
        "build_mode": "rebuild_from_existing_sources",
        "existing_source_dir": existing_dir.relative_to(ROOT).as_posix(),
        "prepared_materials": len(prepared),
        "failed_materials": failures,
        "duplicate_sources": [],
        "materials": prepared,
    }
    write_json(output_dir / "manifest.json", delivery_manifest)
    with (output_dir / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    sums = [
        f"{sha256_bytes(path.read_bytes())}  {path.relative_to(output_dir).as_posix()}"
        for path in sorted(
            path
            for path in output_dir.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS.txt"
        )
    ]
    (output_dir / "SHA256SUMS.txt").write_text(
        "\n".join(sums) + "\n", encoding="utf-8"
    )
    print(f"prepared={len(prepared)} failed={len(failures)} chunks={len(chunks)}")
    if failures:
        raise SystemExit(2)


def validate(output_dir: Path) -> None:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    required_manifest = {"version", "source_registry", "prepared_materials", "failed_materials", "duplicate_sources", "materials"}
    if not required_manifest.issubset(manifest):
        missing = sorted(required_manifest - set(manifest))
        raise ValueError(f"manifest has missing required fields: {', '.join(missing)}")
    materials = manifest["materials"]
    if not isinstance(materials, list):
        raise ValueError("manifest materials must be a list")
    if manifest.get("failed_materials"):
        raise ValueError("delivery manifest contains failed materials")
    if manifest.get("duplicate_sources"):
        raise ValueError("delivery manifest contains duplicate sources")
    if manifest.get("prepared_materials") != len(materials):
        raise ValueError("prepared_materials does not match materials")
    ids = {item["material_id"] for item in materials}
    chunks = [json.loads(line) for line in (output_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    chunk_ids: set[str] = set()
    for item in materials:
        required_material = {
            "material_id",
            "title",
            "url",
            "resolved_url",
            "version",
            "section",
            "module_id",
            "knowledge_point_ids",
            "local_file",
            "sha256",
            "source_file_sha256",
            "license_note",
            "license_url",
            "retrieved_at",
            "import_status",
            "http_status",
        }
        if not required_material.issubset(item) or any(
            not str(item.get(key) or "").strip() for key in required_material - {"http_status"}
        ):
            raise ValueError(f"material has missing required metadata: {item.get('material_id')}")
        validate_source_url(item.get("resolved_url") or item["url"])
        if item.get("http_status") != 200:
            raise ValueError(f"material HTTP status is not 200: {item['material_id']}")
        if item.get("import_status") != "prepared":
            raise ValueError(f"material is not prepared: {item['material_id']}")
        if not str(item.get("retrieved_at") or "").strip():
            raise ValueError(f"material retrieval time is missing: {item['material_id']}")
        path = (output_dir / item["local_file"]).resolve()
        if output_dir.resolve() not in path.parents or not path.is_file():
            raise ValueError(f"invalid local_file for {item['material_id']}")
        if sha256_bytes(path.read_bytes()) != item["sha256"]:
            raise ValueError(f"material hash mismatch: {item['material_id']}")
    for chunk in chunks:
        validate_source_url(chunk["source_url"])
        required = {"chunk_id", "material_id", "source_section", "source_version", "text", "content_sha256"}
        if not required.issubset(chunk) or not all(chunk[key] for key in required):
            raise ValueError(f"chunk has missing required fields: {chunk.get('chunk_id')}")
        if chunk["material_id"] not in ids or chunk["chunk_id"] in chunk_ids:
            raise ValueError(f"invalid or duplicate chunk: {chunk['chunk_id']}")
        chunk_ids.add(chunk["chunk_id"])
        if sha256_bytes(chunk["text"].encode("utf-8")) != chunk["content_sha256"]:
            raise ValueError(f"chunk hash mismatch: {chunk['chunk_id']}")
        material = next(item for item in materials if item["material_id"] == chunk["material_id"])
        if chunk.get("module_id") != material.get("module_id"):
            raise ValueError(f"chunk module mismatch: {chunk['chunk_id']}")
        if chunk.get("knowledge_point_ids") != material.get("knowledge_point_ids"):
            raise ValueError(f"chunk knowledge points mismatch: {chunk['chunk_id']}")
        if chunk.get("source_file_sha256") != material.get("sha256"):
            raise ValueError(f"chunk source hash mismatch: {chunk['chunk_id']}")
        if not str(chunk.get("license_note") or "").strip():
            raise ValueError(f"chunk license note is missing: {chunk['chunk_id']}")
        validate_source_url(chunk.get("license_url") or "")

    sums_path = output_dir / "SHA256SUMS.txt"
    checksum_lines = [line for line in sums_path.read_text(encoding="utf-8").splitlines() if line]
    checked_paths: set[str] = set()
    for line in checksum_lines:
        digest, separator, relative_name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"invalid SHA256SUMS entry: {line}")
        relative_path = Path(relative_name)
        target = (output_dir / relative_path).resolve()
        if output_dir.resolve() not in target.parents or not target.is_file():
            raise ValueError(f"invalid SHA256SUMS path: {relative_name}")
        normalized_name = relative_path.as_posix()
        if normalized_name in checked_paths:
            raise ValueError(f"duplicate SHA256SUMS path: {normalized_name}")
        checked_paths.add(normalized_name)
        if sha256_bytes(target.read_bytes()) != digest:
            raise ValueError(f"SHA256SUMS mismatch: {normalized_name}")
    expected_paths = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if checked_paths != expected_paths:
        raise ValueError("SHA256SUMS file list does not match delivery files")
    print(f"valid materials={len(materials)} chunks={len(chunks)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "rebuild", "validate"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--existing",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Existing validated source directory used by the rebuild command",
    )
    parser.add_argument("--max-chars", type=int, default=1600)
    args = parser.parse_args()
    if args.command == "build":
        build(args.registry.resolve(), args.output.resolve(), args.max_chars)
    elif args.command == "rebuild":
        rebuild(
            args.registry.resolve(),
            args.existing.resolve(),
            args.output.resolve(),
            args.max_chars,
        )
    else:
        validate(args.output.resolve())


if __name__ == "__main__":
    main()
