"""Persistent SQLite/WAL Idempotency Ledger for Track 3.2.

Provides durable deduplication and execution attempt tracking across process restarts,
preventing redundant side-effects and ensuring idempotent re-evaluation of commands.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

from jarvis_agent.execution.models.idempotency_record import (
    IdempotencyRecord,
    IdempotencyState,
)
from jarvis_agent.orchestration.models.command import ExecutionCommand

logger = logging.getLogger(__name__)


class IdempotencyLedger:
    """Thread-safe SQLite/WAL backed ledger for tracking execution idempotency."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
            isolation_level=None,  # Autocommit mode; transactions managed explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema with WAL mode and indices."""
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_records (
                idempotency_key TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                plan_revision INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                attempt_id INTEGER NOT NULL,
                command_id TEXT NOT NULL,
                arguments_hash TEXT NOT NULL,
                capability_target TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                execution_result_json TEXT,
                error_message TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_idem_task_node
            ON idempotency_records (task_id, node_id);
            """
        )
        cur.close()

    def get(self, idempotency_key: str) -> IdempotencyRecord | None:
        """Retrieve existing idempotency record by key."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM idempotency_records WHERE idempotency_key = ?;",
            (idempotency_key,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        return self._row_to_record(row)

    def reserve(self, command: ExecutionCommand) -> tuple[bool, IdempotencyRecord]:
        """Attempt to reserve execution for a command.

        Returns:
            (True, new_record) if successfully reserved for execution (first seen).
            (False, existing_record) if already seen, in-progress, completed, or failed.
        """
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute(
                "SELECT * FROM idempotency_records WHERE idempotency_key = ?;",
                (command.idempotency_key,),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute("COMMIT;")
                return False, self._row_to_record(existing)

            # Insert new IN_PROGRESS record
            cur.execute(
                """
                INSERT INTO idempotency_records (
                    idempotency_key, task_id, plan_id, plan_revision,
                    node_id, attempt_id, command_id, arguments_hash,
                    capability_target, state, created_at_utc, updated_at_utc,
                    execution_result_json, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL);
                """,
                (
                    command.idempotency_key,
                    command.task_id,
                    command.plan_id,
                    command.plan_revision,
                    command.node_id,
                    command.attempt_id,
                    command.command_id,
                    command.arguments_hash,
                    command.capability_target,
                    IdempotencyState.IN_PROGRESS.value,
                    now_str,
                    now_str,
                ),
            )
            cur.execute("COMMIT;")

            new_record = IdempotencyRecord(
                idempotency_key=command.idempotency_key,
                task_id=command.task_id,
                plan_id=command.plan_id,
                plan_revision=command.plan_revision,
                node_id=command.node_id,
                attempt_id=command.attempt_id,
                command_id=command.command_id,
                arguments_hash=command.arguments_hash,
                capability_target=command.capability_target,
                state=IdempotencyState.IN_PROGRESS,
                created_at_utc=now_str,
                updated_at_utc=now_str,
            )
            return True, new_record
        except Exception:
            try:
                cur.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            cur.close()

    def record_terminal(
        self,
        idempotency_key: str,
        state: IdempotencyState,
        execution_result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an idempotency record to a terminal state with result payload."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        res_json = json.dumps(execution_result) if execution_result is not None else None
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute(
                """
                UPDATE idempotency_records
                SET state = ?,
                    updated_at_utc = ?,
                    execution_result_json = ?,
                    error_message = ?
                WHERE idempotency_key = ?;
                """,
                (state.value, now_str, res_json, error_message, idempotency_key),
            )
            cur.execute("COMMIT;")
        except Exception:
            try:
                cur.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            cur.close()

    def _row_to_record(self, row: sqlite3.Row) -> IdempotencyRecord:
        res_json = row["execution_result_json"]
        parsed_res = json.loads(res_json) if res_json else None
        return IdempotencyRecord(
            idempotency_key=row["idempotency_key"],
            task_id=row["task_id"],
            plan_id=row["plan_id"],
            plan_revision=row["plan_revision"],
            node_id=row["node_id"],
            attempt_id=row["attempt_id"],
            command_id=row["command_id"],
            arguments_hash=row["arguments_hash"],
            capability_target=row["capability_target"],
            state=IdempotencyState(row["state"]),
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
            execution_result=parsed_res,
            error_message=row["error_message"],
        )

    def close(self) -> None:
        """Close SQLite database connection cleanly."""
        try:
            self._conn.close()
        except Exception:
            pass


__all__ = ["IdempotencyLedger"]
