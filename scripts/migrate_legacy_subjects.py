"""One-time migration from legacy school categories to training modules.

This script is intentionally excluded from the runtime application. It reads a
legacy SQLite database, applies an explicit mapping file, and writes only the
new module-scoped quiz and MIRT records.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPOSITORY_ROOT / "apps" / "api"
sys.path.insert(0, str(API_DIR))

from database import (  # noqa: E402
    KnowledgePoint,
    LearnerAbility,
    Quiz,
    SessionLocal,
    TrainingModule,
    User,
    init_db,
)


def rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return []
    cursor = connection.execute(f'SELECT * FROM "{table}"')  # noqa: S608
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, values, strict=True)) for values in cursor.fetchall()]


def migrate(legacy_db: Path, mapping_path: Path, dry_run: bool) -> dict:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Mapping must be a non-empty JSON object.")
    legacy = sqlite3.connect(legacy_db)
    init_db()
    db = SessionLocal()
    report = {"quizzes": 0, "abilities": 0, "skipped": []}
    try:
        modules = {row.code: row for row in db.query(TrainingModule).all()}
        users = {row.id for row in db.query(User.id).all()}
        first_points = {
            module.id: db.query(KnowledgePoint)
            .filter_by(module_id=module.id)
            .order_by(KnowledgePoint.sequence)
            .first()
            for module in modules.values()
        }
        for item in rows(legacy, "quizzes"):
            legacy_category = str(item.get("subject") or "").strip()
            module = modules.get(mapping.get(legacy_category))
            point = first_points.get(module.id) if module else None
            if not module or not point:
                report["skipped"].append(
                    {"table": "quizzes", "id": item.get("id"), "reason": "unmapped category"}
                )
                continue
            db.add(
                Quiz(
                    module_id=module.id,
                    knowledge_point_id=point.id,
                    content=item.get("content") or "",
                    answer=item.get("answer") or "",
                    type=item.get("type") or "Short",
                    intercept_d=float(item.get("intercept_d") or item.get("d") or 0.0),
                    U=float(item.get("U") or 1.0),
                    A=float(item.get("A") or 1.0),
                    R=float(item.get("R") or 1.0),
                    parameter_source="legacy_migration",
                )
            )
            report["quizzes"] += 1

        for item in rows(legacy, "student_states"):
            user_id = int(item.get("user_id") or 0)
            module = modules.get(mapping.get(str(item.get("subject") or "").strip()))
            if user_id not in users or not module:
                report["skipped"].append(
                    {
                        "table": "student_states",
                        "id": item.get("id"),
                        "reason": "missing user or unmapped category",
                    }
                )
                continue
            ability = (
                db.query(LearnerAbility)
                .filter_by(user_id=user_id, module_id=module.id)
                .first()
                or LearnerAbility(user_id=user_id, module_id=module.id)
            )
            ability.U = float(item.get("U") or 0.0)
            ability.A = float(item.get("A") or 0.0)
            ability.R = float(item.get("R") or 0.0)
            ability.attempt_count = int(item.get("attempt_count") or 0)
            db.add(ability)
            report["abilities"] += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
        return report
    finally:
        db.close()
        legacy.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-db", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.legacy_db, args.mapping, args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
