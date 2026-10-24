"""Persistent SQLite Task Queue for Autonomous Claws — JARVIS Autonomous Architecture.

Provides database-first ACID queueing, priority scheduling, audit logging,
and execution checkpointing for background worker agents.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import ClawJob, ClawJobStatus, ClawPriority, ClawResult

logger = logging.getLogger("jarvis.claws.task_queue")


class ClawTaskQueue:
    """Persistent SQLite task queue for Claw worker jobs."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            state_dir = Path.home() / ".jarvis" / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = state_dir / "claws.sqlite"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Create tables and indexes idempotently."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS claw_jobs (
                    job_id TEXT PRIMARY KEY,
                    claw_id TEXT NOT NULL,
                    schedule TEXT,
                    priority INTEGER NOT NULL DEFAULT 5,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    payload TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    last_error TEXT,
                    result TEXT,
                    created_at TEXT NOT NULL,
                    scheduled_at TEXT,
                    started_at TEXT,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_claw_jobs_status_prio
                ON claw_jobs(status, priority DESC, created_at ASC);

                CREATE TABLE IF NOT EXISTS claw_audit_ledger (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    claw_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_claw_audit_claw
                ON claw_audit_ledger(claw_id, timestamp DESC);

                CREATE TABLE IF NOT EXISTS claw_checkpoints (
                    claw_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def enqueue(
        self,
        claw_id: str,
        schedule: str | None = None,
        priority: ClawPriority = ClawPriority.NORMAL,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> ClawJob:
        """Enqueue a new autonomous job into the persistent SQLite queue."""
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_dict = payload or {}
        payload_str = json.dumps(payload_dict)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO claw_jobs (
                    job_id, claw_id, schedule, priority, status,
                    payload, attempts, max_attempts, created_at
                ) VALUES (?, ?, ?, ?, 'PENDING', ?, 0, ?, ?);
                """,
                (
                    job_id,
                    claw_id,
                    schedule,
                    priority.value,
                    payload_str,
                    max_attempts,
                    now_iso,
                ),
            )
            self._record_audit_raw(conn, job_id, claw_id, "ENQUEUED", {"priority": priority.value})
            conn.commit()

        return ClawJob(
            job_id=job_id,
            claw_id=claw_id,
            schedule=schedule,
            priority=priority,
            status=ClawJobStatus.PENDING,
            payload=payload_dict,
            attempts=0,
            max_attempts=max_attempts,
            created_at=now_iso,
        )

    def dequeue_next(self) -> ClawJob | None:
        """Atomically fetch and mark the highest priority pending job as RUNNING."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM claw_jobs
                WHERE status = 'PENDING'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1;
                """
            )
            row = cursor.fetchone()
            if not row:
                return None

            job = ClawJob.from_row(dict(row))
            new_attempts = job.attempts + 1

            conn.execute(
                """
                UPDATE claw_jobs
                SET status = 'RUNNING', started_at = ?, attempts = ?
                WHERE job_id = ? AND status = 'PENDING';
                """,
                (now_iso, new_attempts, job.job_id),
            )
            self._record_audit_raw(
                conn, job.job_id, job.claw_id, "STARTED", {"attempt": new_attempts}
            )
            conn.commit()

            job.status = ClawJobStatus.RUNNING
            job.started_at = now_iso
            job.attempts = new_attempts
            return job

    def mark_completed(self, job_id: str, result: ClawResult) -> None:
        """Mark a job as COMPLETED and store execution result."""
        now_iso = datetime.now(timezone.utc).isoformat()
        res_dict = result.to_dict()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE claw_jobs
                SET status = 'COMPLETED', completed_at = ?, result = ?
                WHERE job_id = ?;
                """,
                (now_iso, json.dumps(res_dict), job_id),
            )
            cursor = conn.execute("SELECT claw_id FROM claw_jobs WHERE job_id = ?;", (job_id,))
            row = cursor.fetchone()
            claw_id = row["claw_id"] if row else "unknown"
            self._record_audit_raw(conn, job_id, claw_id, "COMPLETED", res_dict)
            conn.commit()

    def mark_failed(self, job_id: str, error: str, retryable: bool = True) -> bool:
        """Mark a job as FAILED or RETRYING if within max_attempts.

        Returns True if the job is scheduled for RETRYING, False if terminal failure.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT claw_id, attempts, max_attempts FROM claw_jobs WHERE job_id = ?;",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False

            claw_id = row["claw_id"]
            attempts = int(row["attempts"])
            max_attempts = int(row["max_attempts"])

            will_retry = retryable and (attempts < max_attempts)
            next_status = ClawJobStatus.PENDING if will_retry else ClawJobStatus.FAILED

            conn.execute(
                """
                UPDATE claw_jobs
                SET status = ?, last_error = ?, completed_at = CASE WHEN ? = 'FAILED' THEN ? ELSE NULL END
                WHERE job_id = ?;
                """,
                (next_status.value, error, next_status.value, now_iso, job_id),
            )
            event_type = "RETRY_SCHEDULED" if will_retry else "FAILED"
            self._record_audit_raw(
                conn,
                job_id,
                claw_id,
                event_type,
                {"error": error, "attempts": attempts, "max_attempts": max_attempts},
            )
            conn.commit()
            return will_retry

    def cancel_job(self, job_id: str, reason: str = "User cancelled") -> bool:
        """Cancel a pending or running job."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE claw_jobs
                SET status = 'CANCELLED', completed_at = ?, last_error = ?
                WHERE job_id = ? AND status IN ('PENDING', 'RUNNING');
                """,
                (now_iso, reason, job_id),
            )
            updated = cursor.rowcount > 0
            if updated:
                self._record_audit_raw(conn, job_id, "unknown", "CANCELLED", {"reason": reason})
            conn.commit()
            return updated

    def get_job(self, job_id: str) -> ClawJob | None:
        """Fetch a specific job by job_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM claw_jobs WHERE job_id = ?;", (job_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ClawJob.from_row(dict(row))

    def purge_completed_jobs(self, older_than_days: int = 7) -> int:
        """Delete old completed or cancelled jobs to maintain SQLite queue hygiene."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM claw_jobs
                WHERE status IN ('COMPLETED', 'CANCELLED')
                  AND completed_at < ?;
                """,
                (cutoff,),
            )
            count = cursor.rowcount
            conn.commit()
            return count

    def list_jobs(
        self,
        claw_id: str | None = None,
        status: ClawJobStatus | None = None,
        limit: int = 50,
    ) -> list[ClawJob]:
        """Query jobs by claw_id and/or status."""
        query = "SELECT * FROM claw_jobs WHERE 1=1"
        params: list[Any] = []
        if claw_id:
            query += " AND claw_id = ?"
            params.append(claw_id)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [ClawJob.from_row(dict(r)) for r in cursor.fetchall()]

    def save_checkpoint(self, claw_id: str, data: dict[str, Any]) -> None:
        """Save a state checkpoint for a Claw."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO claw_checkpoints (claw_id, data, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(claw_id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at;
                """,
                (claw_id, json.dumps(data), now_iso),
            )
            conn.commit()

    def get_checkpoint(self, claw_id: str) -> dict[str, Any] | None:
        """Retrieve the latest checkpoint for a Claw."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM claw_checkpoints WHERE claw_id = ?;", (claw_id,)
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["data"])
                except Exception:
                    return None
            return None

    def get_audit_log(self, claw_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve audit log entries."""
        query = "SELECT * FROM claw_audit_ledger"
        params: list[Any] = []
        if claw_id:
            query += " WHERE claw_id = ?"
            params.append(claw_id)
        query += " ORDER BY timestamp DESC LIMIT ?;"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                if d.get("details"):
                    try:
                        d["details"] = json.loads(d["details"])
                    except Exception:
                        pass
                results.append(d)
            return results

    def get_stats(self) -> dict[str, Any]:
        """Summary metrics across all queued, running, completed, and failed jobs."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT status, count(*) as count
                FROM claw_jobs
                GROUP BY status;
                """
            )
            counts = {row["status"]: row["count"] for row in cursor.fetchall()}
            cursor2 = conn.execute("SELECT count(DISTINCT claw_id) as active_claws FROM claw_jobs;")
            claws_count = cursor2.fetchone()["active_claws"]
            return {
                "active_claws": claws_count,
                "pending": counts.get("PENDING", 0),
                "running": counts.get("RUNNING", 0),
                "completed": counts.get("COMPLETED", 0),
                "failed": counts.get("FAILED", 0),
                "cancelled": counts.get("CANCELLED", 0),
                "total_jobs": sum(counts.values()),
            }

    def _record_audit_raw(
        self,
        conn: sqlite3.Connection,
        job_id: str,
        claw_id: str,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO claw_audit_ledger (job_id, claw_id, event_type, details, timestamp)
            VALUES (?, ?, ?, ?, ?);
            """,
            (job_id, claw_id, event_type, json.dumps(details), now_iso),
        )


__all__ = ["ClawTaskQueue"]
