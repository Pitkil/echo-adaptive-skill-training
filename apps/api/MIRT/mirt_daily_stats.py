"""Daily module-level assessment statistics."""

from __future__ import annotations

from datetime import date, timedelta

from database import MirtDailyModuleStats
from sqlalchemy.orm import Session


def upsert_mirt_daily_stat(
    db: Session,
    user_id: int,
    module_id: int,
    is_correct: bool,
) -> None:
    today = date.today()
    row = (
        db.query(MirtDailyModuleStats)
        .filter_by(user_id=user_id, module_id=module_id, stat_date=today)
        .first()
    )
    if row is None:
        row = MirtDailyModuleStats(
            user_id=user_id,
            module_id=module_id,
            stat_date=today,
            attempt_count=0,
            correct_count=0,
        )
        db.add(row)
    row.attempt_count = (row.attempt_count or 0) + 1
    if is_correct:
        row.correct_count = (row.correct_count or 0) + 1


def build_daily_series(
    db: Session,
    user_id: int,
    module_id: int,
    days: int = 30,
) -> list[dict]:
    days = max(1, min(days, 366))
    end = date.today()
    start = end - timedelta(days=days - 1)
    rows = (
        db.query(MirtDailyModuleStats)
        .filter(
            MirtDailyModuleStats.user_id == user_id,
            MirtDailyModuleStats.module_id == module_id,
            MirtDailyModuleStats.stat_date >= start,
            MirtDailyModuleStats.stat_date <= end,
        )
        .all()
    )
    indexed = {row.stat_date: row for row in rows}
    result = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        row = indexed.get(current)
        attempts = int(row.attempt_count) if row else 0
        correct = int(row.correct_count) if row else 0
        result.append(
            {
                "date": current.isoformat(),
                "attempt_count": attempts,
                "correct_count": correct,
                "accuracy": round(correct / attempts, 4) if attempts else None,
            }
        )
    return result
