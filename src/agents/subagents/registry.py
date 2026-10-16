"""src.agents.subagents.registry
Canonical subagent registry and lifecycle tracking.

Matches OpenClaw parity:
- src/agents/subagents/registry/subagent-registry.ts
- src/agents/subagents/registry/subagent-registry.types.ts
- src/agents/subagents/registry/subagent-registry.store.sqlite.ts
- src/agents/subagents/registry/subagent-control.ts
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from .types import SubagentRole, SubagentRunRecord, SubagentSpawnContextMode, SubagentStatus


def _resolve_default_db_path() -> Path:
    """Locate the shared state database path (~/.jarvis/state/jarvis.sqlite)."""
    state_dir = os.environ.get("JARVIS_STATE_DIR")
    if state_dir:
        base = Path(state_dir)
    else:
        base = Path.home() / ".jarvis" / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "jarvis.sqlite"


class SubagentRegistry:
    """Singleton registry managing active and historical subagent execution runs."""

    _instance: SubagentRegistry | None = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _resolve_default_db_path()
        self._lock = threading.RLock()
        self._table_initialized = False

        # In-memory indexes
        self._runs_by_id: dict[str, SubagentRunRecord] = {}
        self._runs_by_session_key: dict[str, SubagentRunRecord] = {}
        self._runs_by_parent_key: dict[str, list[str]] = {}

    @classmethod
    def get_instance(cls, db_path: Path | str | None = None) -> SubagentRegistry:
        """Obtain the singleton SubagentRegistry instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(db_path=db_path)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for test isolation)."""
        with cls._instance_lock:
            cls._instance = None

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        """Ensure the subagent_runs table exists (pure additive SQLite surface)."""
        if self._table_initialized:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subagent_runs (
                run_id TEXT PRIMARY KEY,
                child_session_key TEXT NOT NULL,
                parent_session_key TEXT NOT NULL,
                task TEXT NOT NULL,
                label TEXT,
                task_id TEXT,
                role TEXT NOT NULL,
                depth INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at REAL NOT NULL,
                ended_at REAL,
                result_text TEXT,
                error TEXT,
                tangible_artifacts TEXT,
                generation INTEGER NOT NULL,
                model TEXT,
                timeout_seconds REAL NOT NULL,
                context_mode TEXT NOT NULL,
                metadata TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subagent_parent ON subagent_runs(parent_session_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subagent_child ON subagent_runs(child_session_key)"
        )
        conn.commit()
        self._table_initialized = True

    def register_run(self, record: SubagentRunRecord) -> None:
        """Register a new subagent run in memory and persistent storage."""
        with self._lock:
            self._runs_by_id[record.run_id] = record
            self._runs_by_session_key[record.child_session_key] = record
            if record.parent_session_key not in self._runs_by_parent_key:
                self._runs_by_parent_key[record.parent_session_key] = []
            if record.run_id not in self._runs_by_parent_key[record.parent_session_key]:
                self._runs_by_parent_key[record.parent_session_key].append(record.run_id)

            try:
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                    self._ensure_table(conn)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO subagent_runs (
                            run_id, child_session_key, parent_session_key, task, label, task_id,
                            role, depth, status, started_at, ended_at, result_text, error,
                            tangible_artifacts, generation, model, timeout_seconds, context_mode, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.run_id,
                            record.child_session_key,
                            record.parent_session_key,
                            record.task,
                            record.label,
                            record.task_id,
                            record.role.value,
                            record.depth,
                            record.status.value,
                            record.started_at,
                            record.ended_at,
                            record.result_text,
                            record.error,
                            json.dumps(record.tangible_artifacts),
                            record.generation,
                            record.model,
                            record.timeout_seconds,
                            record.context_mode.value,
                            json.dumps(record.metadata),
                        ),
                    )
                    conn.commit()
            except Exception:
                # In-memory index remains authoritative if DB write fails
                pass

    def update_run_status(
        self,
        run_id_or_key: str,
        status: SubagentStatus,
        result_text: str | None = None,
        error: str | None = None,
        tangible_artifacts: list[str] | None = None,
    ) -> SubagentRunRecord | None:
        """Update terminal status, findings, and artifacts of a subagent run."""
        with self._lock:
            record = self.get_run(run_id_or_key)
            if not record:
                return None

            record.status = status
            if result_text is not None:
                record.result_text = result_text
            if error is not None:
                record.error = error
            if tangible_artifacts is not None:
                record.tangible_artifacts = list(tangible_artifacts)
            if status in (
                SubagentStatus.COMPLETED,
                SubagentStatus.FAILED,
                SubagentStatus.CANCELLED,
                SubagentStatus.TIMED_OUT,
            ):
                record.ended_at = time.time()

            try:
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                    self._ensure_table(conn)
                    conn.execute(
                        """
                        UPDATE subagent_runs
                        SET status = ?, ended_at = ?, result_text = ?, error = ?, tangible_artifacts = ?
                        WHERE run_id = ?
                        """,
                        (
                            record.status.value,
                            record.ended_at,
                            record.result_text,
                            record.error,
                            json.dumps(record.tangible_artifacts),
                            record.run_id,
                        ),
                    )
                    conn.commit()
            except Exception:
                pass

            return record

    def get_run(self, run_id_or_key: str) -> SubagentRunRecord | None:
        """Look up a subagent run by run_id or child_session_key."""
        with self._lock:
            if run_id_or_key in self._runs_by_id:
                return self._runs_by_id[run_id_or_key]
            if run_id_or_key in self._runs_by_session_key:
                return self._runs_by_session_key[run_id_or_key]

            # Try loading from database
            try:
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                    self._ensure_table(conn)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        "SELECT * FROM subagent_runs WHERE run_id = ? OR child_session_key = ?",
                        (run_id_or_key, run_id_or_key),
                    )
                    row = cursor.fetchone()
                    if row:
                        rec = self._row_to_record(row)
                        self._runs_by_id[rec.run_id] = rec
                        self._runs_by_session_key[rec.child_session_key] = rec
                        return rec
            except Exception:
                pass

            return None

    def list_runs(
        self,
        parent_session_key: str | None = None,
        status: SubagentStatus | None = None,
    ) -> list[SubagentRunRecord]:
        """List subagent runs, optionally filtered by parent session or status."""
        with self._lock:
            runs: list[SubagentRunRecord] = list(self._runs_by_id.values())
            if parent_session_key is not None:
                runs = [r for r in runs if r.parent_session_key == parent_session_key]
            if status is not None:
                runs = [r for r in runs if r.status == status]
            return runs

    def get_descendant_keys(self, root_session_key: str) -> set[str]:
        """Recursively collect all child and descendant session keys for a given session."""
        with self._lock:
            descendants: set[str] = set()
            queue = [root_session_key]
            visited = set()

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                # Direct children
                direct_child_ids = self._runs_by_parent_key.get(current, [])
                for rid in direct_child_ids:
                    rec = self._runs_by_id.get(rid)
                    if rec and rec.child_session_key not in descendants:
                        descendants.add(rec.child_session_key)
                        queue.append(rec.child_session_key)

            return descendants

    def list_controlled_runs(self, controller_session_key: str) -> list[SubagentRunRecord]:
        """List all runs controlled by controller_session_key (its direct or indirect descendants)."""
        with self._lock:
            descendant_keys = self.get_descendant_keys(controller_session_key)
            return [
                rec
                for rec in self._runs_by_id.values()
                if rec.child_session_key in descendant_keys
                or rec.parent_session_key == controller_session_key
            ]

    def clear(self) -> None:
        """Clear in-memory and database records (for test isolation)."""
        with self._lock:
            self._runs_by_id.clear()
            self._runs_by_session_key.clear()
            self._runs_by_parent_key.clear()
            try:
                with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
                    self._ensure_table(conn)
                    conn.execute("DELETE FROM subagent_runs")
                    conn.commit()
            except Exception:
                pass

    def _row_to_record(self, row: sqlite3.Row) -> SubagentRunRecord:
        """Convert a SQLite row into a SubagentRunRecord."""
        artifacts_raw = row["tangible_artifacts"]
        artifacts = json.loads(artifacts_raw) if artifacts_raw else []
        meta_raw = row["metadata"]
        meta = json.loads(meta_raw) if meta_raw else {}

        return SubagentRunRecord(
            run_id=row["run_id"],
            child_session_key=row["child_session_key"],
            parent_session_key=row["parent_session_key"],
            task=row["task"],
            label=row["label"] or "",
            task_id=row["task_id"] or "",
            role=SubagentRole(row["role"]),
            depth=int(row["depth"]),
            status=SubagentStatus(row["status"]),
            started_at=float(row["started_at"]),
            ended_at=float(row["ended_at"]) if row["ended_at"] is not None else None,
            result_text=row["result_text"],
            error=row["error"],
            tangible_artifacts=artifacts,
            generation=int(row["generation"]),
            model=row["model"],
            timeout_seconds=float(row["timeout_seconds"]),
            context_mode=SubagentSpawnContextMode(row["context_mode"]),
            metadata=meta,
        )
