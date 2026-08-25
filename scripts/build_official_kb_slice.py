"""Build and validate a traceable Semantic Kernel knowledge-base slice.

Downloaded source files and generated chunks are runtime/delivery data and are
written under ``data/`` by default. They must not be committed blindly: review
the applicable Microsoft terms before placing source text in a submission.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs" / "member-d" / "official_materials_manifest.json"
DEFAULT_OUTPUT = ROOT / "data" / "official-kb-slice"
ALLOWED_HOSTS = {"learn.microsoft.com", "github.com"}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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
    if parsed.hostname == "github.com" and not parsed.path.startswith(
        "/microsoft/semantic-kernel"
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
        if item.get("module_id") not in {"M1", "M2", "M3"}:
            raise ValueError(f"invalid module_id for {item['material_id']}")
        if not item.get("knowledge_point_ids"):
            raise ValueError(f"missing knowledge_point_ids for {item['material_id']}")
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
    return {
        **item,
        "resolved_url": final_url,
        "http_status": status,
        "content_type": content_type,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "local_file": clean_path.relative_to(output_dir).as_posix(),
        "source_file_sha256": sha256_bytes(raw),
        "sha256": sha256_bytes(cleaned.encode("utf-8")),
        "import_status": "prepared",
    }


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:60] or "section"


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
        paragraphs = [part.strip() for part in "\n".join(lines).split("\n\n") if part.strip()]
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
                    "license_note": item.get("license_note", "Microsoft source; verify terms before redistribution"),
                }
            )
    return chunks


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(registry_path: Path, output_dir: Path, max_chars: int) -> None:
    registry = load_registry(registry_path)
    output_dir.mkdir(parents=True, exist_ok=True)
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


def validate(output_dir: Path) -> None:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    materials = manifest["materials"]
    ids = {item["material_id"] for item in materials}
    chunks = [json.loads(line) for line in (output_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    chunk_ids: set[str] = set()
    for item in materials:
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
    print(f"valid materials={len(materials)} chunks={len(chunks)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-chars", type=int, default=1600)
    args = parser.parse_args()
    if args.command == "build":
        build(args.registry.resolve(), args.output.resolve(), args.max_chars)
    else:
        validate(args.output.resolve())


if __name__ == "__main__":
    main()
