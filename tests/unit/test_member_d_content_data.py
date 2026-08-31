from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from Quiz.import_from_document import extract_quiz_preview

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MEMBER_D_ROOT = REPOSITORY_ROOT / "docs" / "member-d"
ALLOWED_SOURCE_HOSTS = {
    "learn.microsoft.com",
    "github.com",
}


def _load_json(name: str) -> dict:
    return json.loads((MEMBER_D_ROOT / name).read_text(encoding="utf-8"))


def _assert_official_source(url: str) -> None:
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.hostname in ALLOWED_SOURCE_HOSTS
    if parsed.hostname == "github.com":
        assert parsed.path.startswith("/microsoft/semantic-kernel")


def test_formal_quiz_manifest_matches_import_preview() -> None:
    manifest = _load_json("quiz_formal_manifest.json")
    quiz_root = MEMBER_D_ROOT / "quiz"
    records = manifest["questions"]

    assert manifest["total_questions"] == 63
    assert manifest["distribution"] == {
        "pretest": 27,
        "posttest": 27,
        "practice": 9,
    }
    assert len(records) == 63
    assert len({record["question_id"] for record in records}) == 63
    assert {record["status"] for record in records} == {"formal"}

    manifest_by_location = {
        (record["file_path"], record["question_index"]): record
        for record in records
    }
    parsed_by_location: dict[tuple[str, int], dict] = {}
    for path in sorted(quiz_root.rglob("*.md")):
        relative_path = path.relative_to(quiz_root).as_posix()
        _, items = extract_quiz_preview(path)
        for index, item in enumerate(items, start=1):
            assert item["valid"], (relative_path, index, item["issues"])
            parsed_by_location[(relative_path, index)] = item

    assert len(parsed_by_location) == 63
    assert manifest_by_location.keys() == parsed_by_location.keys()
    comparable_fields = {
        "purpose",
        "difficulty",
        "source_title",
        "source_url",
        "source_section",
        "counts_for_mirt",
    }
    for location, item in parsed_by_location.items():
        record = manifest_by_location[location]
        assert {field: record[field] for field in comparable_fields} == {
            field: item[field] for field in comparable_fields
        }
        _assert_official_source(item["source_url"])

    assert Counter(item["purpose"] for item in parsed_by_location.values()) == {
        "pretest": 27,
        "posttest": 27,
        "practice": 9,
    }


def test_official_material_registry_is_complete_and_truthful() -> None:
    registry = _load_json("official_materials_manifest.json")
    materials = registry["materials"]

    assert registry["total_materials"] == 20
    assert registry["coverage"]["total_materials"] == 20
    assert len(materials) == 20
    assert len({material["material_id"] for material in materials}) == 20
    assert Counter(material["module_id"] for material in materials) == {
        "M1": 8,
        "M2": 7,
        "M3": 5,
    }
    assert {material["import_status"] for material in materials} == {"pending"}
    assert all(not material["local_file"] for material in materials)
    assert all(not material["sha256"] for material in materials)
    for material in materials:
        _assert_official_source(material["url"])


def test_fixed_evaluation_cases_cover_all_resource_types() -> None:
    evaluation = _load_json("eval_50_cases.json")
    cases = evaluation["cases"]

    assert evaluation["total_cases"] == 50
    assert len(cases) == 50
    assert len({case["case_id"] for case in cases}) == 50
    assert Counter(case["scenario_type"] for case in cases) == {
        "explanation": 9,
        "custom_note": 9,
        "practice_guide": 9,
        "staged_test": 9,
        "dynamic": 9,
        "exception": 5,
    }

    resource_cases = [
        case for case in cases if case["scenario_type"] in {
            "custom_note",
            "practice_guide",
            "staged_test",
        }
    ]
    assert len(resource_cases) == 27
    assert {case["expected"]["resource_type"] for case in resource_cases} == {
        "custom_note",
        "practice_guide",
        "staged_test",
    }
    assert all(case["expected"]["publish_resource"] for case in resource_cases)
    assert Counter(case["learner_type"] for case in resource_cases) == {
        "P1": 9,
        "P2": 9,
        "P3": 9,
    }
    input_markers = {
        "custom_note": "定制学习资料",
        "practice_guide": "实践操作指南",
        "staged_test": "阶段测试",
    }
    assert all(
        input_markers[case["scenario_type"]] in case["input"]
        for case in resource_cases
    )
    for case in cases:
        _assert_official_source(case["expected"]["source_url"])
