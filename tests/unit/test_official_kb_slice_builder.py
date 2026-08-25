from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_official_kb_slice.py"
SPEC = importlib.util.spec_from_file_location("build_official_kb_slice", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_registry_is_accepted() -> None:
    registry = MODULE.load_registry(MODULE.DEFAULT_REGISTRY)
    assert registry["total_materials"] == 15


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
        "materials": [
            {
                "material_id": "MAT",
                "local_file": "files/MAT.md",
                "sha256": digest,
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
        "text": text,
        "content_sha256": MODULE.sha256_bytes(text.encode("utf-8")),
    }
    (tmp_path / "chunks.jsonl").write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    MODULE.validate(tmp_path)
    material.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        MODULE.validate(tmp_path)
