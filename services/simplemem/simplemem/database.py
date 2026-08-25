"""SQLite persistence, scope authorization and deterministic memory retrieval."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from .schemas import MemoryIntent, MemoryRecord, MemoryScope, MemoryType


class MemoryNotFoundError(LookupError):
    pass


class MemoryForbiddenError(PermissionError):
    pass


class MemoryConflictError(ValueError):
    def __init__(self, message: str, *, memory_ids: list[str] | None = None) -> None:
        super().__init__(message)
        self.memory_ids = memory_ids or []


class ConsolidationUnavailableError(ValueError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    organization_id INTEGER NOT NULL CHECK (organization_id > 0),
    user_id INTEGER NOT NULL CHECK (user_id > 0),
    program_id INTEGER NOT NULL CHECK (program_id > 0),
    module_id INTEGER NOT NULL CHECK (module_id > 0),
    knowledge_point_id INTEGER,
    session_id INTEGER,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (
        memory_type IN ('misconception', 'learning_preference', 'intervention_outcome')
    ),
    idempotency_key TEXT NOT NULL UNIQUE,
    conflict_key TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_refs_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'merged', 'deleted')),
    merged_into_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_memories_active_conflict
ON memories(conflict_key) WHERE state = 'active';

CREATE INDEX IF NOT EXISTS ix_memories_scope
ON memories(organization_id, user_id, program_id, module_id, state);

CREATE INDEX IF NOT EXISTS ix_memories_scope_knowledge
ON memories(organization_id, user_id, program_id, module_id, knowledge_point_id, state);

CREATE TABLE IF NOT EXISTS memory_idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(memory_id)
);

CREATE INDEX IF NOT EXISTS ix_memory_idempotency_keys_memory
ON memory_idempotency_keys(memory_id);

CREATE TABLE IF NOT EXISTS memory_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    memory_id TEXT,
    organization_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    program_id INTEGER NOT NULL,
    module_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_memory_events_scope
ON memory_events(organization_id, user_id, program_id, module_id, occurred_at);
"""


class SimpleMemStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(_SCHEMA)
            connection.execute(
                """INSERT OR IGNORE INTO memory_idempotency_keys (
                       idempotency_key, memory_id, first_seen_at
                   )
                   SELECT idempotency_key, memory_id, created_at FROM memories"""
            )

    def health(self) -> None:
        with self._connection() as connection:
            connection.execute("SELECT 1").fetchone()
            connection.execute("SELECT COUNT(*) FROM memories").fetchone()

    def upsert(self, record: MemoryRecord) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT memories.* FROM memory_idempotency_keys
                   JOIN memories USING (memory_id)
                   WHERE memory_idempotency_keys.idempotency_key = ?""",
                (record.idempotency_key,),
            ).fetchone()
            if existing is not None:
                self._assert_record_identity(existing, record)
                if existing["state"] != "active":
                    conflict_ids = [existing["memory_id"]]
                    if existing["merged_into_id"]:
                        conflict_ids.append(existing["merged_into_id"])
                    raise MemoryConflictError(
                        "idempotency_key belongs to an inactive "
                        f"{existing['state']} memory",
                        memory_ids=conflict_ids,
                    )
                if existing["idempotency_key"] != record.idempotency_key:
                    raise MemoryConflictError(
                        "idempotency_key is a superseded historical key for this memory",
                        memory_ids=[existing["memory_id"]],
                    )
                if self._same_record(existing, record):
                    status = "unchanged"
                else:
                    self._update_row(connection, existing["memory_id"], record)
                    status = "updated"
                self._audit(connection, status, existing["memory_id"], record, {})
                return {
                    "status": status,
                    "memory_id": existing["memory_id"],
                    "idempotency_key": record.idempotency_key,
                    "conflict_memory_ids": [],
                }

            conflicts = connection.execute(
                "SELECT memory_id FROM memories WHERE conflict_key = ? AND state = 'active'",
                (record.conflict_key,),
            ).fetchall()
            if conflicts:
                conflict_ids = [row["memory_id"] for row in conflicts]
                self._audit(
                    connection,
                    "conflict",
                    None,
                    record,
                    {"conflict_memory_ids": conflict_ids},
                )
                return {
                    "status": "conflict",
                    "memory_id": None,
                    "idempotency_key": record.idempotency_key,
                    "conflict_memory_ids": conflict_ids,
                }

            memory_id = f"mem-{uuid4().hex}"
            self._insert_row(connection, memory_id, record)
            self._audit(connection, "created", memory_id, record, {})
            return {
                "status": "created",
                "memory_id": memory_id,
                "idempotency_key": record.idempotency_key,
                "conflict_memory_ids": [],
            }

    def authorize(self, memory_id: str, scope: MemoryScope) -> dict[str, Any]:
        with self._connection() as connection:
            row = self._authorized_row(connection, memory_id, scope)
            self._audit(connection, "authorize", memory_id, scope, {"allowed": True})
        return {"allowed": True, "memory_id": memory_id, **self._scope_from_row(row)}

    def update(self, memory_id: str, record: MemoryRecord) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._authorized_row(connection, memory_id, record)
            idempotency_owner = connection.execute(
                """SELECT memory_id FROM memory_idempotency_keys
                   WHERE idempotency_key = ?""",
                (record.idempotency_key,),
            ).fetchone()
            if (
                idempotency_owner is not None
                and idempotency_owner["memory_id"] != memory_id
            ):
                raise MemoryConflictError(
                    "idempotency_key belongs to another memory",
                    memory_ids=[idempotency_owner["memory_id"]],
                )
            if (
                idempotency_owner is not None
                and record.idempotency_key != row["idempotency_key"]
            ):
                raise MemoryConflictError(
                    "historical idempotency_key cannot replace the current key",
                    memory_ids=[memory_id],
                )
            conflict_owners = connection.execute(
                """SELECT memory_id FROM memories
                   WHERE conflict_key = ? AND state = 'active' AND memory_id <> ?""",
                (record.conflict_key, memory_id),
            ).fetchall()
            if conflict_owners:
                raise MemoryConflictError(
                    "conflicting active memory already exists",
                    memory_ids=[item["memory_id"] for item in conflict_owners],
                )
            status = "unchanged" if self._same_record(row, record) else "updated"
            if status == "updated":
                self._update_row(connection, memory_id, record)
            self._audit(connection, status, memory_id, record, {})
        return {"status": status, "memory_id": memory_id, **self._scope(record)}

    def delete(self, memory_id: str, scope: MemoryScope) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._authorized_row(connection, memory_id, scope)
            connection.execute(
                "UPDATE memories SET state = 'deleted', updated_at = ? WHERE memory_id = ?",
                (_now(), memory_id),
            )
            self._audit(connection, "deleted", memory_id, scope, {})
        return {"status": "deleted", "memory_id": memory_id, **self._scope(scope)}

    def search(
        self,
        scope: MemoryScope,
        *,
        intent: MemoryIntent,
        query: str,
        knowledge_point_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        sql = """SELECT * FROM memories
                 WHERE organization_id = ? AND user_id = ? AND program_id = ?
                   AND module_id = ? AND state = 'active'"""
        parameters: list[Any] = [
            scope.organization_id,
            scope.user_id,
            scope.program_id,
            scope.module_id,
        ]
        if knowledge_point_id is not None:
            sql += " AND knowledge_point_id = ?"
            parameters.append(knowledge_point_id)
        sql += " ORDER BY occurred_at DESC LIMIT 250"
        with self._connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
            self._audit(
                connection,
                "search",
                None,
                scope,
                {
                    "intent": intent.value,
                    "knowledge_point_id": knowledge_point_id,
                    "candidate_count": len(rows),
                },
            )
        scored = []
        for row in rows:
            score = self._retrieval_score(row, query, intent)
            if score is not None:
                scored.append((score, row))
        scored.sort(key=lambda item: (item[0], item[1]["occurred_at"]), reverse=True)
        return [self._search_item(row, score) for score, row in scored[:limit]]

    def consolidate(self, scope: MemoryScope) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT * FROM memories
                   WHERE organization_id = ? AND user_id = ? AND program_id = ?
                     AND module_id = ? AND state = 'active'
                   ORDER BY occurred_at DESC""",
                tuple(self._scope(scope).values()),
            ).fetchall()
            groups: dict[tuple[str, int | None], list[sqlite3.Row]] = defaultdict(list)
            for row in rows:
                groups[(row["memory_type"], row["knowledge_point_id"])].append(row)
            eligible = [items for items in groups.values() if len(items) >= 2]
            if not eligible:
                raise ConsolidationUnavailableError(
                    "at least two active memories of the same type and knowledge scope are required"
                )
            sources = sorted(eligible, key=len, reverse=True)[0][:20]
            source_ids = [row["memory_id"] for row in sources]
            evidence_refs = list(
                dict.fromkeys(
                    ref
                    for row in sources
                    for ref in json.loads(row["evidence_refs_json"])
                )
            )
            contents = list(dict.fromkeys(row["content"] for row in reversed(sources)))
            conflict_seed = "|".join(
                [
                    *(str(value) for value in self._scope(scope).values()),
                    sources[0]["memory_type"],
                    str(sources[0]["knowledge_point_id"] or "all"),
                    *sorted(source_ids),
                ]
            )
            conflict_key = sha256(conflict_seed.encode("utf-8")).hexdigest()
            content = "；".join(contents)
            idempotency_key = sha256(
                f"{conflict_key}|{' '.join(content.casefold().split())}".encode()
            ).hexdigest()
            occurred_at = max(row["occurred_at"] for row in sources)
            latest_session_id = next(
                (row["session_id"] for row in sources if row["session_id"] is not None),
                None,
            )
            record = MemoryRecord(
                **self._scope(scope),
                knowledge_point_id=sources[0]["knowledge_point_id"],
                session_id=latest_session_id,
                content=content,
                memory_type=sources[0]["memory_type"],
                idempotency_key=idempotency_key,
                conflict_key=conflict_key,
                confidence=sum(float(row["confidence"]) for row in sources) / len(sources),
                evidence_refs=evidence_refs,
                occurred_at=occurred_at,
                metadata={
                    "consolidated": True,
                    "source_memory_ids": source_ids,
                    "source_count": len(source_ids),
                },
            )
            merged_memory_id = f"mem-{uuid4().hex}"
            self._insert_row(connection, merged_memory_id, record)
            placeholders = ",".join("?" for _ in source_ids)
            connection.execute(
                f"""UPDATE memories SET state = 'merged', merged_into_id = ?, updated_at = ?
                    WHERE memory_id IN ({placeholders})""",
                [merged_memory_id, _now(), *source_ids],
            )
            self._audit(
                connection,
                "consolidated",
                merged_memory_id,
                scope,
                {"source_memory_ids": source_ids, "evidence_refs": evidence_refs},
            )
        return {
            "merged_memory_id": merged_memory_id,
            "source_memory_ids": source_ids,
            "evidence_refs": evidence_refs,
            **self._scope(scope),
        }

    @staticmethod
    def _authorized_row(
        connection: sqlite3.Connection,
        memory_id: str,
        scope: MemoryScope,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM memories WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        if row is None or row["state"] != "active":
            raise MemoryNotFoundError("memory not found")
        if SimpleMemStore._scope_from_row(row) != SimpleMemStore._scope(scope):
            raise MemoryForbiddenError("memory scope does not match the requested scope")
        return row

    @staticmethod
    def _assert_record_identity(row: sqlite3.Row, record: MemoryRecord) -> None:
        expected = (*SimpleMemStore._scope(record).values(), record.memory_type.value)
        actual = (*SimpleMemStore._scope_from_row(row).values(), row["memory_type"])
        if actual != expected or row["conflict_key"] != record.conflict_key:
            raise MemoryConflictError("idempotency_key was reused for a different scope or domain")

    @staticmethod
    def _insert_row(
        connection: sqlite3.Connection,
        memory_id: str,
        record: MemoryRecord,
    ) -> None:
        now = _now()
        connection.execute(
            """INSERT INTO memories (
                memory_id, organization_id, user_id, program_id, module_id,
                knowledge_point_id, session_id, content, memory_type,
                idempotency_key, conflict_key, confidence, evidence_refs_json,
                occurred_at, metadata_json, state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                memory_id,
                record.organization_id,
                record.user_id,
                record.program_id,
                record.module_id,
                record.knowledge_point_id,
                record.session_id,
                record.content,
                record.memory_type.value,
                record.idempotency_key,
                record.conflict_key,
                record.confidence,
                _json(record.evidence_refs),
                record.occurred_at.isoformat(),
                _json(record.metadata),
                now,
                now,
            ),
        )
        connection.execute(
            """INSERT INTO memory_idempotency_keys (
                   idempotency_key, memory_id, first_seen_at
               ) VALUES (?, ?, ?)""",
            (record.idempotency_key, memory_id, now),
        )

    @staticmethod
    def _update_row(
        connection: sqlite3.Connection,
        memory_id: str,
        record: MemoryRecord,
    ) -> None:
        connection.execute(
            """INSERT OR IGNORE INTO memory_idempotency_keys (
                   idempotency_key, memory_id, first_seen_at
               ) VALUES (?, ?, ?)""",
            (record.idempotency_key, memory_id, _now()),
        )
        connection.execute(
            """UPDATE memories SET
                organization_id = ?, user_id = ?, program_id = ?, module_id = ?,
                knowledge_point_id = ?, session_id = ?, content = ?, memory_type = ?,
                idempotency_key = ?, conflict_key = ?, confidence = ?,
                evidence_refs_json = ?, occurred_at = ?, metadata_json = ?, updated_at = ?
                WHERE memory_id = ?""",
            (
                record.organization_id,
                record.user_id,
                record.program_id,
                record.module_id,
                record.knowledge_point_id,
                record.session_id,
                record.content,
                record.memory_type.value,
                record.idempotency_key,
                record.conflict_key,
                record.confidence,
                _json(record.evidence_refs),
                record.occurred_at.isoformat(),
                _json(record.metadata),
                _now(),
                memory_id,
            ),
        )

    @staticmethod
    def _same_record(row: sqlite3.Row, record: MemoryRecord) -> bool:
        stored = SimpleMemStore._record_from_row(row).model_dump(mode="json")
        incoming = record.model_dump(mode="json")
        return _json(stored) == _json(incoming)

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            program_id=row["program_id"],
            module_id=row["module_id"],
            knowledge_point_id=row["knowledge_point_id"],
            session_id=row["session_id"],
            content=row["content"],
            memory_type=row["memory_type"],
            idempotency_key=row["idempotency_key"],
            conflict_key=row["conflict_key"],
            confidence=row["confidence"],
            evidence_refs=json.loads(row["evidence_refs_json"]),
            occurred_at=row["occurred_at"],
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def _search_item(row: sqlite3.Row, score: float) -> dict[str, Any]:
        record = SimpleMemStore._record_from_row(row).model_dump(mode="json")
        return {"memory_id": row["memory_id"], **record, "score": round(score, 6)}

    @staticmethod
    def _retrieval_score(
        row: sqlite3.Row,
        query: str,
        intent: MemoryIntent,
    ) -> float | None:
        normalized_query = " ".join(query.casefold().split())
        metadata_values = [
            row["knowledge_point_id"],
            *json.loads(row["metadata_json"]).values(),
        ]
        metadata_text = " ".join(
            str(value) for value in metadata_values if value is not None
        ).casefold()
        haystack = f"{row['content'].casefold()} {metadata_text}"
        query_terms = _terms(normalized_query)
        content_terms = _terms(haystack)
        matched_terms = query_terms & content_terms
        phrase = 1.0 if normalized_query in haystack else 0.0
        memory_type = MemoryType(row["memory_type"])
        allows_scope_fallback = (
            memory_type == MemoryType.LEARNING_PREFERENCE
            and intent in {MemoryIntent.ECHO_GUIDANCE, MemoryIntent.RESOURCE_GENERATION}
        ) or (
            memory_type == MemoryType.INTERVENTION_OUTCOME
            and intent == MemoryIntent.ECHO_GUIDANCE
        )
        if not matched_terms and phrase == 0.0 and not allows_scope_fallback:
            return None
        overlap = len(matched_terms) / max(1, len(query_terms))
        intent_boosts = {
            MemoryIntent.LEARNER_DIAGNOSIS: {MemoryType.MISCONCEPTION: 0.14},
            MemoryIntent.ECHO_GUIDANCE: {
                MemoryType.LEARNING_PREFERENCE: 0.12,
                MemoryType.INTERVENTION_OUTCOME: 0.12,
            },
            MemoryIntent.RESOURCE_GENERATION: {
                MemoryType.LEARNING_PREFERENCE: 0.09,
                MemoryType.MISCONCEPTION: 0.07,
            },
        }
        boost = intent_boosts[intent].get(memory_type, 0.0)
        return overlap * 0.58 + phrase * 0.2 + float(row["confidence"]) * 0.15 + boost

    @staticmethod
    def _scope(value: MemoryScope) -> dict[str, int]:
        return {
            "organization_id": value.organization_id,
            "user_id": value.user_id,
            "program_id": value.program_id,
            "module_id": value.module_id,
        }

    @staticmethod
    def _scope_from_row(row: sqlite3.Row) -> dict[str, int]:
        return {
            "organization_id": row["organization_id"],
            "user_id": row["user_id"],
            "program_id": row["program_id"],
            "module_id": row["module_id"],
        }

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        operation: str,
        memory_id: str | None,
        scope: MemoryScope,
        detail: dict[str, Any],
    ) -> None:
        connection.execute(
            """INSERT INTO memory_events (
                operation, memory_id, organization_id, user_id, program_id,
                module_id, outcome, detail_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                operation,
                memory_id,
                scope.organization_id,
                scope.user_id,
                scope.program_id,
                scope.module_id,
                operation,
                _json(detail),
                _now(),
            ),
        )


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", value.casefold()))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(UTC).isoformat()
