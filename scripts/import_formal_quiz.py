"""Validate and import the frozen 63-question competition quiz bank."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from catalog import seed_question  # noqa: E402
from database import (  # noqa: E402
    ChatSession,
    KnowledgePoint,
    Quiz,
    SessionLocal,
    StudentQuestionHistory,
    TrainingModule,
)
from Quiz.import_from_document import extract_quiz_preview, validate_quiz_item  # noqa: E402

EXPECTED_DISTRIBUTION = Counter({"pretest": 27, "posttest": 27, "practice": 9})
COMPARABLE_FIELDS = (
    "purpose",
    "difficulty",
    "source_title",
    "source_url",
    "source_section",
    "counts_for_mirt",
)
DIFFICULTY_INTERCEPTS = {"foundation": 0.8, "standard": 0.0, "advanced": -0.8}


def load_formal_items(data_root: Path) -> list[dict]:
    """Return manifest-aligned quiz items after validating every source document."""
    manifest_path = data_root / "quiz_formal_manifest.json"
    quiz_root = data_root / "quiz"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("questions", [])
    if manifest.get("total_questions") != 63 or len(records) != 63:
        raise ValueError("正式题库清单不是冻结的 63 道题版本")

    parsed_files: dict[str, list[dict]] = {}
    result: list[dict] = []
    for record in records:
        relative_path = str(record["file_path"])
        if relative_path not in parsed_files:
            source_path = quiz_root / relative_path
            if not source_path.is_file():
                raise ValueError(f"找不到题库源文件：{relative_path}")
            _, parsed_files[relative_path] = extract_quiz_preview(source_path)

        index = int(record["question_index"]) - 1
        try:
            item = parsed_files[relative_path][index]
        except IndexError as exc:
            raise ValueError(f"题目序号超出文件范围：{relative_path}#{index + 1}") from exc
        issues = validate_quiz_item(item)
        if issues:
            raise ValueError(f"题目不完整：{relative_path}#{index + 1}（{'；'.join(issues)}）")
        mismatched = [field for field in COMPARABLE_FIELDS if record[field] != item[field]]
        if mismatched:
            raise ValueError(
                f"题目与正式清单不一致：{relative_path}#{index + 1}（{','.join(mismatched)}）"
            )
        result.append({**item, "module_code": record["module"], "point_name": record["knowledge_point"]})

    distribution = Counter(item["purpose"] for item in result)
    if distribution != EXPECTED_DISTRIBUTION:
        raise ValueError(f"题库用途分布异常：{dict(distribution)}")
    return result


def remove_unused_demo_seeds(db) -> int:
    """Remove only untouched catalog smoke-test questions before formal import."""
    removed = 0
    points = (
        db.query(KnowledgePoint)
        .join(TrainingModule, KnowledgePoint.module_id == TrainingModule.id)
        .all()
    )
    for point in points:
        content, answer = seed_question(point.name)
        seeds = (
            db.query(Quiz)
            .filter_by(
                module_id=point.module_id,
                knowledge_point_id=point.id,
                content=content,
                answer=answer,
            )
            .all()
        )
        for seed in seeds:
            has_history = (
                db.query(StudentQuestionHistory.id).filter_by(question_id=seed.id).first() is not None
            )
            is_active = (
                db.query(ChatSession.id).filter_by(active_quiz_id=seed.id).first() is not None
            )
            if has_history or is_active:
                raise ValueError(f"占位题 {seed.id} 已被使用，拒绝删除")
            db.delete(seed)
            removed += 1
    return removed


def import_formal_items(data_root: Path, *, apply: bool, replace_demo_seeds: bool) -> dict:
    """Import validated items idempotently and return a count-only report."""
    items = load_formal_items(data_root)
    db = SessionLocal()
    try:
        modules = {module.code: module for module in db.query(TrainingModule).all()}
        points = {
            (module.code, point.name): point
            for module in modules.values()
            for point in db.query(KnowledgePoint).filter_by(module_id=module.id).all()
        }
        missing_points = sorted(
            {(item["module_code"], item["point_name"]) for item in items} - points.keys()
        )
        if missing_points:
            raise ValueError(f"运行数据库缺少知识点：{missing_points}")

        removed = remove_unused_demo_seeds(db) if replace_demo_seeds else 0
        imported = 0
        skipped = 0
        for item in items:
            module = modules[item["module_code"]]
            point = points[(item["module_code"], item["point_name"])]
            duplicate = (
                db.query(Quiz)
                .filter_by(
                    module_id=module.id,
                    knowledge_point_id=point.id,
                    content=item["content"],
                )
                .first()
            )
            if duplicate is not None:
                skipped += 1
                continue
            db.add(
                Quiz(
                    module_id=module.id,
                    knowledge_point_id=point.id,
                    content=item["content"],
                    answer=item["answer"],
                    type=item["type"],
                    intercept_d=DIFFICULTY_INTERCEPTS[item["difficulty"]],
                    U=1.0,
                    A=1.0,
                    R=1.0,
                    parameter_source="document_import",
                    purpose=item["purpose"],
                    difficulty=item["difficulty"],
                    scoring_method=item["scoring_method"],
                    source_title=item["source_title"],
                    source_url=item["source_url"],
                    source_section=item["source_section"],
                    counts_for_mirt=item["counts_for_mirt"],
                )
            )
            imported += 1

        if apply:
            db.commit()
        else:
            db.rollback()
        return {
            "mode": "apply" if apply else "dry-run",
            "validated": len(items),
            "removed_demo_seeds": removed,
            "imported": imported,
            "skipped_duplicates": skipped,
            "expected_distribution": dict(EXPECTED_DISTRIBUTION),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "member-d",
        help="包含 quiz_formal_manifest.json 与 quiz/ 的目录",
    )
    parser.add_argument("--apply", action="store_true", help="通过验证后提交数据库事务")
    parser.add_argument(
        "--replace-demo-seeds",
        action="store_true",
        help="删除从未作答或下发的 12 道目录占位题",
    )
    args = parser.parse_args()
    report = import_formal_items(
        args.data_root.resolve(),
        apply=args.apply,
        replace_demo_seeds=args.replace_demo_seeds,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
