"""jarvis_learning.storage.learning_db — dedicated learning SQLite database.

The learning database lives at ``~/.jarvis/learning/learning.sqlite``
and is completely separate from the shared JARVIS state DB.  This
avoids any schema version coordination issues.

Tables are created idempotently on first connection.  WAL mode is
enabled for concurrent reads during training data generation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..experience import Experience, Lesson
from ..feedback import Feedback
from ..knowledge import KnowledgeEntry
from ..procedures import Procedure
from ..strategies import FailurePattern, Strategy

logger = logging.getLogger(__name__)

# Default database path
_DEFAULT_DB_DIR = Path.home() / ".jarvis" / "learning"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "learning.sqlite"

# ── Schema DDL ────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS learning_experiences (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    user_input TEXT NOT NULL DEFAULT '',
    interpreted_intent TEXT NOT NULL DEFAULT '',
    context_summary TEXT NOT NULL DEFAULT '',
    plan TEXT NOT NULL DEFAULT '',
    reasoning_summary TEXT NOT NULL DEFAULT '',
    selected_tool TEXT NOT NULL DEFAULT '',
    tool_arguments TEXT NOT NULL DEFAULT '',
    tool_result TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    failure_type TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    user_feedback TEXT NOT NULL DEFAULT '',
    implicit_feedback TEXT NOT NULL DEFAULT '',
    reward_score REAL NOT NULL DEFAULT 0.0,
    reflection TEXT NOT NULL DEFAULT '',
    learned_lesson TEXT NOT NULL DEFAULT '',
    reusable_strategy TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    approved_for_training INTEGER NOT NULL DEFAULT 0,
    source_type TEXT NOT NULL DEFAULT 'llm_inferred',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    episode TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS learning_feedback (
    id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    feedback_type TEXT NOT NULL DEFAULT 'implicit',
    signal TEXT NOT NULL DEFAULT '',
    value TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS learning_strategies (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    intent TEXT NOT NULL DEFAULT '',
    context_conditions TEXT NOT NULL DEFAULT '{}',
    preferred_action TEXT NOT NULL DEFAULT '',
    tool TEXT NOT NULL DEFAULT '',
    argument_pattern TEXT NOT NULL DEFAULT '{}',
    verification TEXT NOT NULL DEFAULT '',
    fallback TEXT NOT NULL DEFAULT '',
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.5,
    last_used INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    origin TEXT NOT NULL DEFAULT 'reflection',
    source_experience_ids TEXT NOT NULL DEFAULT '[]',
    source_session_ids TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT 'learning_pipeline',
    manual_override INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 1,
    last_verified_success_ms INTEGER NOT NULL DEFAULT 0,
    last_verified_failure_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS learning_procedures (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    name TEXT NOT NULL UNIQUE,
    preconditions TEXT NOT NULL DEFAULT '{}',
    steps TEXT NOT NULL DEFAULT '[]',
    fallback TEXT NOT NULL DEFAULT '',
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS learning_failure_patterns (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    pattern_name TEXT NOT NULL,
    condition TEXT NOT NULL DEFAULT '{}',
    bad_action TEXT NOT NULL DEFAULT '',
    preferred_action TEXT NOT NULL DEFAULT '',
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.5,
    scope TEXT NOT NULL DEFAULT 'exact_arguments',
    recovery_strategy TEXT NOT NULL DEFAULT '',
    expiration_ms INTEGER NOT NULL DEFAULT 0,
    tool_name TEXT NOT NULL DEFAULT '',
    argument_signature TEXT NOT NULL DEFAULT '',
    environment_fingerprint TEXT NOT NULL DEFAULT '',
    intent_signature TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS learning_knowledge (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL NOT NULL DEFAULT 0.5,
    validation_state TEXT NOT NULL DEFAULT 'unvalidated',
    expires_at INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS learning_lessons (
    id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    summary TEXT NOT NULL,
    generalizable INTEGER NOT NULL DEFAULT 0,
    applicable_intents TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5
);

CREATE INDEX IF NOT EXISTS idx_exp_agent ON learning_experiences(agent_id);
CREATE INDEX IF NOT EXISTS idx_exp_session ON learning_experiences(session_id);
CREATE INDEX IF NOT EXISTS idx_exp_tool ON learning_experiences(selected_tool);
CREATE INDEX IF NOT EXISTS idx_exp_created ON learning_experiences(created_at);
CREATE INDEX IF NOT EXISTS idx_exp_approved ON learning_experiences(approved_for_training);
CREATE INDEX IF NOT EXISTS idx_fb_exp ON learning_feedback(experience_id);
CREATE INDEX IF NOT EXISTS idx_strat_intent ON learning_strategies(intent);
CREATE INDEX IF NOT EXISTS idx_know_validation ON learning_knowledge(validation_state);

CREATE TABLE IF NOT EXISTS learning_processed_events (
    agent_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL DEFAULT '',
    processed_at INTEGER NOT NULL,
    PRIMARY KEY (agent_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_proc_events_time ON learning_processed_events(processed_at);

CREATE TABLE IF NOT EXISTS learning_audit_log (
    entry_id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    model_id TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    strategy_id TEXT NOT NULL DEFAULT '',
    metrics TEXT NOT NULL DEFAULT '{}',
    operator_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON learning_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_model ON learning_audit_log(model_id);

CREATE TABLE IF NOT EXISTS learning_evidence (
    id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL DEFAULT '',
    trust_level TEXT NOT NULL DEFAULT 'TRUSTED',
    source_type TEXT NOT NULL DEFAULT 'execution_readback',
    source TEXT NOT NULL DEFAULT 'execution_readback',
    payload_digest TEXT NOT NULL DEFAULT '',
    raw_payload TEXT NOT NULL DEFAULT '{}',
    is_revoked INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_exp ON learning_evidence(experience_id);
CREATE INDEX IF NOT EXISTS idx_evidence_digest ON learning_evidence(payload_digest);
CREATE INDEX IF NOT EXISTS idx_evidence_trust ON learning_evidence(trust_level);

CREATE TABLE IF NOT EXISTS learning_causal_critiques (
    id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL,
    primary_failure_type TEXT NOT NULL,
    attribution_status TEXT NOT NULL,
    confidence REAL NOT NULL,
    hypotheses_json TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_causal_exp ON learning_causal_critiques(experience_id);

CREATE TABLE IF NOT EXISTS learning_reflection_jobs (
    id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refl_jobs_status ON learning_reflection_jobs(status);

CREATE TABLE IF NOT EXISTS learning_provenance_log (
    entry_id TEXT PRIMARY KEY,
    sequence_number INTEGER NOT NULL,
    timestamp_ns INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    sample_id TEXT NOT NULL,
    evidence_digest TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    canonical_entry_hash TEXT NOT NULL DEFAULT '',
    entry_hash TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prov_log_seq ON learning_provenance_log(sequence_number);
CREATE INDEX IF NOT EXISTS idx_prov_log_sample ON learning_provenance_log(sample_id);

CREATE TABLE IF NOT EXISTS learning_dataset_manifests (
    dataset_id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    merkle_root TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_dataset_revocations (
    dataset_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    revoked_by TEXT NOT NULL,
    timestamp REAL NOT NULL,
    revocation_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_generation INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    model_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp_monotonic REAL NOT NULL,
    timestamp_wallclock REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_evt_turn ON shadow_events(turn_id);
CREATE INDEX IF NOT EXISTS idx_shadow_evt_prio ON shadow_events(priority);
"""


class LearningDatabase:
    """Dedicated SQLite database for the learning system.

    Thread-safe via a write lock.  Reads are lock-free (WAL mode).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._write_lock = threading.Lock()
        self._ensure_dir()
        self._ensure_schema()

    @property
    def path(self) -> Path:
        return self._db_path

    def _ensure_dir(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        uri = self._db_path.as_uri()
        if readonly:
            uri += "?mode=ro"
        conn = sqlite3.connect(
            uri if readonly else str(self._db_path),
            uri=readonly,
            timeout=10.0,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._write_lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA_SQL)
                # Idempotent column additions for existing tables
                strat_cols = {
                    r["name"]
                    for r in conn.execute("PRAGMA table_info(learning_strategies)").fetchall()
                }
                new_strat_cols = [
                    ("status", "TEXT NOT NULL DEFAULT 'active'"),
                    ("origin", "TEXT NOT NULL DEFAULT 'reflection'"),
                    ("source_experience_ids", "TEXT NOT NULL DEFAULT '[]'"),
                    ("source_session_ids", "TEXT NOT NULL DEFAULT '[]'"),
                    ("created_by", "TEXT NOT NULL DEFAULT 'learning_pipeline'"),
                    ("manual_override", "INTEGER NOT NULL DEFAULT 0"),
                    ("verified", "INTEGER NOT NULL DEFAULT 1"),
                    ("last_verified_success_ms", "INTEGER NOT NULL DEFAULT 0"),
                    ("last_verified_failure_ms", "INTEGER NOT NULL DEFAULT 0"),
                    ("consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
                    ("risk_tier", "INTEGER NOT NULL DEFAULT 1"),
                    ("bayesian_state", "TEXT NOT NULL DEFAULT '{}'"),
                    ("precondition_contract", "TEXT NOT NULL DEFAULT '{}'"),
                ]
                for col_name, col_def in new_strat_cols:
                    if col_name not in strat_cols:
                        conn.execute(
                            f"ALTER TABLE learning_strategies ADD COLUMN {col_name} {col_def}"
                        )

                fp_cols = {
                    r["name"]
                    for r in conn.execute("PRAGMA table_info(learning_failure_patterns)").fetchall()
                }
                new_fp_cols = [
                    ("scope", "TEXT NOT NULL DEFAULT 'exact_arguments'"),
                    ("recovery_strategy", "TEXT NOT NULL DEFAULT ''"),
                    ("expiration_ms", "INTEGER NOT NULL DEFAULT 0"),
                    ("tool_name", "TEXT NOT NULL DEFAULT ''"),
                    ("argument_signature", "TEXT NOT NULL DEFAULT ''"),
                    ("environment_fingerprint", "TEXT NOT NULL DEFAULT ''"),
                    ("intent_signature", "TEXT NOT NULL DEFAULT ''"),
                ]
                for col_name, col_def in new_fp_cols:
                    if col_name not in fp_cols:
                        conn.execute(
                            f"ALTER TABLE learning_failure_patterns ADD COLUMN {col_name} {col_def}"
                        )

                conn.commit()
            finally:
                conn.close()

    # ── Experience CRUD ───────────────────────────────────────

    def store_experience(self, exp: Experience) -> None:
        """Insert or replace an experience."""
        data = exp.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = [int(v) if isinstance(v, bool) else v for v in data.values()]
        sql = f"INSERT OR REPLACE INTO learning_experiences ({col_names}) VALUES ({placeholders})"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()
        logger.debug("experience stored: id=%s", exp.id)

    def get_experience(self, exp_id: str) -> Experience | None:
        """Retrieve an experience by ID."""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT * FROM learning_experiences WHERE id = ?", (exp_id,)
            ).fetchone()
            if row is None:
                return None
            return Experience.from_dict(dict(row))
        finally:
            conn.close()

    def list_experiences(
        self,
        *,
        agent_id: str | None = None,
        limit: int = 100,
        approved_only: bool = False,
    ) -> list[Experience]:
        """List experiences with optional filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if approved_only:
            clauses.append("approved_for_training = 1")
        where = " AND ".join(clauses)
        sql = "SELECT * FROM learning_experiences"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(sql, params).fetchall()
            return [Experience.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_recent_experiences(self, limit: int = 100) -> list[Experience]:
        """Return the most recent experiences (convenience alias for list_experiences)."""
        return self.list_experiences(limit=limit)

    def count_experiences(self) -> int:
        conn = self._connect(readonly=True)
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM learning_experiences").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    # ── Feedback CRUD ─────────────────────────────────────────

    def store_feedback(self, fb: Feedback) -> None:
        data = fb.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = list(data.values())
        sql = f"INSERT OR REPLACE INTO learning_feedback ({col_names}) VALUES ({placeholders})"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def get_feedback_for(self, experience_id: str) -> list[Feedback]:
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(
                "SELECT * FROM learning_feedback WHERE experience_id = ? ORDER BY created_at",
                (experience_id,),
            ).fetchall()
            return [Feedback.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Strategy CRUD ─────────────────────────────────────────

    def store_strategy(self, strategy: Strategy) -> None:
        data = strategy.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = list(data.values())
        sql = f"INSERT OR REPLACE INTO learning_strategies ({col_names}) VALUES ({placeholders})"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def load_all_strategies(self) -> list[Strategy]:
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute("SELECT * FROM learning_strategies").fetchall()
            return [Strategy.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Failure patterns CRUD ─────────────────────────────────

    def store_failure_pattern(self, pattern: FailurePattern) -> None:
        data = pattern.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = list(data.values())
        sql = (
            f"INSERT OR REPLACE INTO learning_failure_patterns "
            f"({col_names}) VALUES ({placeholders})"
        )
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def load_all_failure_patterns(self) -> list[FailurePattern]:
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute("SELECT * FROM learning_failure_patterns").fetchall()
            return [FailurePattern.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Procedure CRUD ────────────────────────────────────────

    def store_procedure(self, proc: Procedure) -> None:
        data = proc.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = list(data.values())
        sql = f"INSERT OR REPLACE INTO learning_procedures ({col_names}) VALUES ({placeholders})"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def load_all_procedures(self) -> list[Procedure]:
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute("SELECT * FROM learning_procedures").fetchall()
            return [Procedure.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Knowledge CRUD ────────────────────────────────────────

    def store_knowledge(self, entry: KnowledgeEntry) -> None:
        data = entry.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = list(data.values())
        sql = f"INSERT OR REPLACE INTO learning_knowledge ({col_names}) VALUES ({placeholders})"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def load_all_knowledge(self) -> list[KnowledgeEntry]:
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute("SELECT * FROM learning_knowledge").fetchall()
            return [KnowledgeEntry.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Lesson CRUD ───────────────────────────────────────────

    def store_lesson(self, lesson: Lesson) -> None:
        data = lesson.to_dict()
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        values = [int(v) if isinstance(v, bool) else v for v in data.values()]
        sql = f"INSERT OR REPLACE INTO learning_lessons ({col_names}) VALUES ({placeholders})"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, values)
                conn.commit()
            finally:
                conn.close()

    def load_all_lessons(self) -> list[Lesson]:
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute("SELECT * FROM learning_lessons").fetchall()
            return [Lesson.from_dict(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Processed Events (Two-Tier Idempotency) ───────────────

    def record_processed_event(
        self,
        agent_id: str,
        event_id: str,
        event_type: str = "",
        processed_at: int | None = None,
    ) -> bool:
        """Record an event as processed in SQLite.

        Returns True if newly inserted, False if already exists (duplicate).
        """
        import time

        ts = processed_at if processed_at is not None else int(time.time() * 1000)
        sql = """
        INSERT INTO learning_processed_events (agent_id, event_id, event_type, processed_at)
        VALUES (?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, (agent_id, event_id, event_type, ts))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def has_processed_event(self, agent_id: str, event_id: str) -> bool:
        """Check if an event was already processed."""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT 1 FROM learning_processed_events WHERE agent_id = ? AND event_id = ?",
                (agent_id, event_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def clean_old_processed_events(self, older_than_ms: int) -> int:
        """Delete processed event markers older than the given timestamp."""
        with self._write_lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM learning_processed_events WHERE processed_at < ?",
                    (older_than_ms,),
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    # ── Audit Log (Append-Only Application Audit Trail) ───────

    def append_audit_log(
        self,
        entry_id: str,
        event_type: str,
        model_id: str = "",
        version: str = "",
        strategy_id: str = "",
        metrics: dict[str, Any] | None = None,
        operator_id: str = "",
        reason: str = "",
        timestamp: int | None = None,
    ) -> None:
        """Append an event to the append-only learning audit log."""
        import json
        import time

        ts = timestamp if timestamp is not None else int(time.time() * 1000)
        metrics_json = json.dumps(metrics or {})
        sql = """
        INSERT INTO learning_audit_log (
            entry_id, timestamp, event_type, model_id, version,
            strategy_id, metrics, operator_id, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    sql,
                    (
                        entry_id,
                        ts,
                        event_type,
                        model_id,
                        version,
                        strategy_id,
                        metrics_json,
                        operator_id,
                        reason,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve recent audit log entries."""
        import json

        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(
                "SELECT * FROM learning_audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if "metrics" in item and isinstance(item["metrics"], str):
                    try:
                        item["metrics"] = json.loads(item["metrics"])
                    except Exception:
                        pass
                results.append(item)
            return results
        finally:
            conn.close()

    # ── Audit Log ─────────────────────────────────────────────

    def record_audit_log(
        self,
        *,
        event_type: str,
        model_id: str = "",
        version: str = "",
        strategy_id: str = "",
        metrics: dict[str, Any] | None = None,
        operator_id: str = "",
        reason: str = "",
    ) -> str:
        """Insert a permanent audit log entry."""
        import time
        import uuid

        entry_id = f"audit_{uuid.uuid4().hex[:12]}"
        now = int(time.time() * 1000)
        metrics_json = json.dumps(metrics or {})
        sql = """
        INSERT INTO learning_audit_log
        (entry_id, timestamp, event_type, model_id, version, strategy_id, metrics, operator_id, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    sql,
                    (
                        entry_id,
                        now,
                        event_type,
                        model_id,
                        version,
                        strategy_id,
                        metrics_json,
                        operator_id,
                        reason,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return entry_id

    def list_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve recent audit logs."""
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(
                "SELECT * FROM learning_audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Evidence Storage ──────────────────────────────────────

    def store_evidence_record(
        self,
        digest_or_id: str,
        payload_or_exp_id: Any = "",
        trust_level: str = "TRUSTED",
        source: str = "execution_readback",
        payload_digest: str | None = None,
        created_at: int | None = None,
    ) -> None:
        """Store an authentic evidence record (supports both Phase 5 and Phase 6 signatures)."""
        ts = created_at if created_at is not None else int(time.time() * 1000)
        if isinstance(payload_or_exp_id, dict):
            # Signature: store_evidence_record(digest, payload, trust_level, source)
            digest = digest_or_id
            raw_payload_str = json.dumps(payload_or_exp_id, sort_keys=True)
            ev_id = digest_or_id
            exp_id = ""
            src_type = source
            src = source
        else:
            # Signature: store_evidence_record(evidence_id, experience_id, trust_level, source_type, payload_digest, created_at)
            ev_id = digest_or_id
            exp_id = str(payload_or_exp_id)
            src_type = source
            src = source
            digest = payload_digest or digest_or_id
            raw_payload_str = "{}"

        sql = """
        INSERT OR REPLACE INTO learning_evidence
        (id, experience_id, trust_level, source_type, source, payload_digest, raw_payload, is_revoked, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    sql,
                    (
                        ev_id,
                        exp_id,
                        str(trust_level).upper(),
                        src_type,
                        src,
                        digest,
                        raw_payload_str,
                        ts,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_evidence_for_experience(self, experience_id: str) -> list[dict[str, Any]]:
        """Get all evidence records associated with an experience."""
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(
                "SELECT * FROM learning_evidence WHERE experience_id = ? ORDER BY created_at ASC",
                (experience_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_evidence_record(self, evidence_digest: str) -> dict[str, Any] | None:
        """Get an evidence record by its SHA-256 payload_digest or id."""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT * FROM learning_evidence WHERE payload_digest = ? OR id = ? LIMIT 1",
                (evidence_digest, evidence_digest),
            ).fetchone()
            if not row:
                return None
            res = dict(row)
            if isinstance(res.get("raw_payload"), str):
                try:
                    res["raw_payload"] = json.loads(res["raw_payload"])
                except Exception:
                    pass
            return res
        finally:
            conn.close()

    store_evidence = store_evidence_record

    # ── Causal Critiques Storage ──────────────────────────────

    def store_causal_critique_record(
        self,
        critique_id: str,
        experience_id: str,
        primary_failure_type: str,
        attribution_status: str,
        confidence: float,
        hypotheses_json: str = "[]",
        created_at: int | None = None,
    ) -> None:
        """Insert a causal critique record."""
        import time

        ts = created_at if created_at is not None else int(time.time() * 1000)
        sql = """
        INSERT OR REPLACE INTO learning_causal_critiques
        (id, experience_id, primary_failure_type, attribution_status, confidence, hypotheses_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    sql,
                    (
                        critique_id,
                        experience_id,
                        primary_failure_type,
                        attribution_status,
                        confidence,
                        hypotheses_json,
                        ts,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_causal_critique_for_experience(self, experience_id: str) -> dict[str, Any] | None:
        """Get the causal critique for an experience."""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT * FROM learning_causal_critiques WHERE experience_id = ? ORDER BY created_at DESC LIMIT 1",
                (experience_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── Reflection Jobs Storage ───────────────────────────────

    def enqueue_reflection_job_record(
        self,
        job_id: str,
        priority: int,
        status: str,
        payload_json: str,
    ) -> None:
        """Insert or update a reflection job."""
        import time

        ts = int(time.time() * 1000)
        sql = """
        INSERT OR REPLACE INTO learning_reflection_jobs
        (id, priority, status, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, (job_id, priority, status, payload_json, ts, ts))
                conn.commit()
            finally:
                conn.close()

    def update_reflection_job_status(self, job_id: str, status: str) -> None:
        """Update job status and timestamp."""
        import time

        ts = int(time.time() * 1000)
        sql = "UPDATE learning_reflection_jobs SET status = ?, updated_at = ? WHERE id = ?"
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, (status, ts, job_id))
                conn.commit()
            finally:
                conn.close()

    def list_pending_reflection_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        """List queued/pending reflection jobs ordered by priority (ascending)."""
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(
                "SELECT * FROM learning_reflection_jobs WHERE status = 'queued' ORDER BY priority ASC, created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Provenance Log Storage ────────────────────────────────

    def store_provenance_log_entry(
        self,
        entry_id: str,
        sequence_number: int,
        timestamp_ns: int,
        event_type: str,
        sample_id: str,
        evidence_digest: str,
        previous_hash: str,
        entry_hash: str,
        details_json: str,
    ) -> None:
        """Insert a tamper-evident provenance log entry."""
        sql = """
        INSERT OR REPLACE INTO learning_provenance_log
        (entry_id, sequence_number, timestamp_ns, event_type, sample_id, evidence_digest, previous_hash, canonical_entry_hash, entry_hash, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    sql,
                    (
                        entry_id,
                        sequence_number,
                        timestamp_ns,
                        event_type,
                        sample_id,
                        evidence_digest,
                        previous_hash,
                        entry_hash,
                        entry_hash,
                        details_json,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_provenance_log_entries(self, limit: int = 1000) -> list[dict[str, Any]]:
        """List provenance log entries ordered by sequence_number."""
        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(
                "SELECT * FROM learning_provenance_log ORDER BY sequence_number ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    get_provenance_log_entries = list_provenance_log_entries

    # ── Dataset Manifests Storage ─────────────────────────────

    def store_dataset_manifest(
        self,
        dataset_id: str,
        target: str,
        manifest_json: str,
        merkle_root: str,
        created_at: float,
    ) -> None:
        """Insert or replace a dataset manifest record."""
        sql = """
        INSERT OR REPLACE INTO learning_dataset_manifests
        (dataset_id, target, manifest_json, merkle_root, created_at)
        VALUES (?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, (dataset_id, target, manifest_json, merkle_root, created_at))
                conn.commit()
            finally:
                conn.close()

    def get_dataset_manifest(self, dataset_id: str) -> dict[str, Any] | None:
        """Get a dataset manifest by dataset_id."""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT * FROM learning_dataset_manifests WHERE dataset_id = ? LIMIT 1",
                (dataset_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── Dataset Revocation Storage ────────────────────────────

    def store_dataset_revocation(self, revocation_dict: dict[str, Any]) -> None:
        """Store a dataset revocation record."""
        import json

        dataset_id = str(revocation_dict["dataset_id"])
        reason = str(revocation_dict["reason"])
        revoked_by = str(revocation_dict["revoked_by_operator_id"])
        ts = float(revocation_dict.get("timestamp", 0.0))
        rev_json = json.dumps(revocation_dict, sort_keys=True)

        sql = """
        INSERT OR REPLACE INTO learning_dataset_revocations
        (dataset_id, reason, revoked_by, timestamp, revocation_json)
        VALUES (?, ?, ?, ?, ?)
        """
        with self._write_lock:
            conn = self._connect()
            try:
                conn.execute(sql, (dataset_id, reason, revoked_by, ts, rev_json))
                conn.commit()
            finally:
                conn.close()

    def get_dataset_revocation(self, dataset_id: str) -> dict[str, Any] | None:
        """Get revocation record for a dataset."""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT * FROM learning_dataset_revocations WHERE dataset_id = ? LIMIT 1",
                (dataset_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def is_dataset_revoked(self, dataset_id: str) -> bool:
        """Check if a dataset has been revoked."""
        return self.get_dataset_revocation(dataset_id) is not None

    # ── Stats ─────────────────────────────────────────────────

    def get_stats(self) -> dict[str, int]:
        """Return row counts for all learning tables."""
        tables = [
            "learning_experiences",
            "learning_feedback",
            "learning_strategies",
            "learning_procedures",
            "learning_failure_patterns",
            "learning_knowledge",
            "learning_lessons",
            "learning_processed_events",
            "learning_audit_log",
            "learning_evidence",
            "learning_causal_critiques",
            "learning_reflection_jobs",
            "learning_provenance_log",
            "learning_dataset_manifests",
            "learning_dataset_revocations",
        ]
        stats: dict[str, int] = {}
        conn = self._connect(readonly=True)
        try:
            for table in tables:
                row = conn.execute(
                    f"SELECT COUNT(*) as cnt FROM {table}"  # noqa: S608
                ).fetchone()
                key = table.replace("learning_", "")
                stats[key] = row["cnt"] if row else 0
        finally:
            conn.close()
        return stats

    # ── Phase 9: Shadow Event Idempotent Storage ──────────────

    def save_shadow_event(self, envelope: Any) -> bool:
        """Save a canonical event envelope idempotently (INV-P9-PERSIST-001).

        Catches sqlite3.OperationalError (e.g. database locked/full) and degrades safely (INV-P9-PERSIST-002).
        """
        sql = """
        INSERT OR IGNORE INTO shadow_events (
            event_id, session_id, turn_id, task_id, task_generation,
            event_type, priority, model_id, tool_name, payload_digest,
            payload_json, timestamp_monotonic, timestamp_wallclock
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._write_lock:
                conn = self._connect()
                try:
                    conn.execute(
                        sql,
                        (
                            envelope.event_id,
                            envelope.session_id,
                            envelope.turn_id,
                            envelope.task_id,
                            envelope.task_generation,
                            envelope.event_type,
                            envelope.priority,
                            envelope.model_id,
                            envelope.tool_name,
                            envelope.compute_digest(),
                            envelope.to_json(),
                            envelope.timestamp_monotonic,
                            envelope.timestamp_wallclock,
                        ),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except sqlite3.OperationalError as op_err:
            logger.warning(
                "STORAGE_DEGRADED: Failed to save shadow event %s: %s",
                getattr(envelope, "event_id", "?"),
                op_err,
            )
            return False
        except Exception as ex:
            logger.error("Error saving shadow event: %s", ex)
            return False

    def get_shadow_event(self, event_id: str) -> dict[str, Any] | None:
        """Retrieve a shadow event by event_id."""
        sql = "SELECT * FROM shadow_events WHERE event_id = ?"
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(sql, (event_id,)).fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def list_shadow_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List recent shadow events, optionally filtered by event_type."""
        if event_type:
            sql = "SELECT * FROM shadow_events WHERE event_type = ? ORDER BY timestamp_monotonic DESC LIMIT ?"
            params = (event_type, limit)
        else:
            sql = "SELECT * FROM shadow_events ORDER BY timestamp_monotonic DESC LIMIT ?"
            params = (limit,)

        conn = self._connect(readonly=True)
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
