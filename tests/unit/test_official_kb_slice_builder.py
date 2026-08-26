from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_official_kb_slice.py"
RETRIEVAL_CASES = ROOT / "docs" / "member-d" / "retrieval-cases.json"
SPEC = importlib.util.spec_from_file_location("build_official_kb_slice", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_registry_is_accepted() -> None:
    registry = MODULE.load_registry(MODULE.DEFAULT_REGISTRY)
    assert registry["total_materials"] == 15


def test_retrieval_cases_cover_every_knowledge_point() -> None:
    payload = json.loads(RETRIEVAL_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) == 15
    assert len({case["case_id"] for case in cases}) == 15
    covered = {case["knowledge_point_id"] for case in cases if "knowledge_point_id" in case}
    assert covered == {
        f"M{module}-KP{knowledge_point}"
        for module in range(1, 4)
        for knowledge_point in range(1, 5)
    }
    assert payload["rules"]["enable_web_search"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://learn.microsoft.com/en-us/semantic-kernel",
        "https://example.com/semantic-kernel",
        "https://github.com/another-owner/semantic-kernel",
    ],
)
def test_unapproved_sources_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        MODULE.validate_source_url(url)


def test_generated_slice_validation_detects_tampering(tmp_path: Path) -> None:
    files = tmp_path / "files"
    files.mkdir()
    material = files / "MAT.md"
    material.write_text("# Kernel\n\nOfficial content", encoding="utf-8")
    digest = MODULE.sha256_bytes(material.read_bytes())
    manifest = {
        "prepared_materials": 1,
        "failed_materials": [],
        "duplicate_sources": [],
        "materials": [
            {
                "material_id": "MAT",
                "url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
                "resolved_url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
                "http_status": 200,
                "import_status": "prepared",
                "retrieved_at": "2026-08-26T00:00:00+00:00",
                "local_file": "files/MAT.md",
                "sha256": digest,
                "module_id": "M1",
                "knowledge_point_ids": ["M1-KP1"],
            }
        ]
    }
    MODULE.write_json(tmp_path / "manifest.json", manifest)
    text = "Official content"
    chunk = {
        "chunk_id": "MAT#kernel#0001",
        "material_id": "MAT",
        "source_url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
        "source_section": "Kernel",
        "source_version": "accessed-test",
        "module_id": "M1",
        "knowledge_point_ids": ["M1-KP1"],
        "text": text,
        "content_sha256": MODULE.sha256_bytes(text.encode("utf-8")),
        "source_file_sha256": digest,
        "license_note": "Microsoft official source",
        "license_url": "https://learn.microsoft.com/en-us/legal/termsofuse",
    }
    (tmp_path / "chunks.jsonl").write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    checksummed = [tmp_path / "manifest.json", material, tmp_path / "chunks.jsonl"]
    (tmp_path / "SHA256SUMS.txt").write_text(
        "\n".join(
            f"{MODULE.sha256_bytes(path.read_bytes())}  {path.relative_to(tmp_path).as_posix()}"
            for path in sorted(checksummed)
        )
        + "\n",
        encoding="utf-8",
    )
    MODULE.validate(tmp_path)
    material.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.validate(tmp_path)


def test_registry_rejects_cross_module_knowledge_point(tmp_path: Path) -> None:
    registry = {
        "total_materials": 1,
        "materials": [
            {
                "material_id": "MAT",
                "url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
                "module_id": "M1",
                "knowledge_point_ids": ["M2-KP1"],
                "version": "accessed-2026-08-26",
                "section": "Kernel",
            }
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid knowledge_point_id"):
        MODULE.load_registry(path)


def test_long_paragraph_is_split_to_maximum_size() -> None:
    pieces = MODULE.split_long_paragraph("A" * 950, 400)
    assert "".join(pieces) == "A" * 950
    assert max(map(len, pieces)) <= 400


def test_captured_markdown_boilerplate_is_removed() -> None:
    cleaned = MODULE.clean_captured_markdown(
        "Note\n\nAccess to this page requires authorization. You can try signing in or changing directories .\n\n# Kernel\n\nOfficial text\n"
    )
    assert cleaned == "# Kernel\n\nOfficial text\n"


def test_validation_detects_checksum_tampering(tmp_path: Path) -> None:
    files = tmp_path / "files"
    files.mkdir()
    material = files / "MAT.md"
    material.write_text("official", encoding="utf-8")
    digest = MODULE.sha256_bytes(material.read_bytes())
    MODULE.write_json(
        tmp_path / "manifest.json",
        {
            "prepared_materials": 1,
            "failed_materials": [],
            "duplicate_sources": [],
            "materials": [
                {
                    "material_id": "MAT",
                    "url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
                    "resolved_url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
                    "http_status": 200,
                    "import_status": "prepared",
                    "retrieved_at": "2026-08-26T00:00:00+00:00",
                    "local_file": "files/MAT.md",
                    "sha256": digest,
                    "module_id": "M1",
                    "knowledge_point_ids": ["M1-KP1"],
                }
            ],
        },
    )
    chunk_text = "official"
    chunk = {
        "chunk_id": "MAT#kernel#0001",
        "material_id": "MAT",
        "source_url": "https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel",
        "source_section": "Kernel",
        "source_version": "accessed-test",
        "module_id": "M1",
        "knowledge_point_ids": ["M1-KP1"],
        "text": chunk_text,
        "content_sha256": MODULE.sha256_bytes(chunk_text.encode()),
        "source_file_sha256": digest,
        "license_note": "Microsoft official source",
        "license_url": "https://learn.microsoft.com/en-us/legal/termsofuse",
    }
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    paths = [tmp_path / "manifest.json", chunks_path, material]
    (tmp_path / "SHA256SUMS.txt").write_text(
        "\n".join(
            f"{MODULE.sha256_bytes(path.read_bytes())}  {path.relative_to(tmp_path).as_posix()}"
            for path in sorted(paths)
        )
        + "\n",
        encoding="utf-8",
    )
    chunks_path.write_text(json.dumps({**chunk, "title": "changed"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256SUMS mismatch"):
        MODULE.validate(tmp_path)
