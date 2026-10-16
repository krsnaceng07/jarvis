"""Versioned, transactional SQLite migration engine for the scheduler projection.

Enforces schema evolution from v32 -> v33 with atomic transactions,
recovery audit tables, and crash safety.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

TARGET_SCHEMA_VERSION = 33

MIGRATION_V32_TO_V33_DDL = """
-- Schema metadata table
CREATE TABLE IF NOT EXISTS scheduler_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Materialized task projection
CREATE TABLE IF NOT EXISTS scheduler_tasks_projection (
    task_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    plan_id TEXT,
    plan_revision INTEGER DEFAULT 1,
    aggregate_state TEXT NOT NULL,
    channel TEXT NOT NULL,
    priority_ceiling INTEGER DEFAULT 3,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

-- Materialized node projection
CREATE TABLE IF NOT EXISTS scheduler_nodes_projection (
    node_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    plan_revision INTEGER NOT NULL,
    goal TEXT NOT NULL,
    capability_target TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    state TEXT NOT NULL,
    current_attempt INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    effective_deadline_utc TEXT,
    priority_level INTEGER DEFAULT 2,
    worker_id TEXT,
    lease_generation INTEGER DEFAULT 0,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES scheduler_tasks_projection(task_id)
);

CREATE INDEX IF NOT EXISTS idx_sched_nodes_task_state 
ON scheduler_nodes_projection(task_id, state);

CREATE INDEX IF NOT EXISTS idx_sched_nodes_state_deadline 
ON scheduler_nodes_projection(state, effective_deadline_utc);

-- Active resource leases with monotonic fencing tokens (compound primary key allows multiple SHARED leases)
CREATE TABLE IF NOT EXISTS resource_leases (
    resource_key TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    mode TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    acquired_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    PRIMARY KEY(resource_key, worker_id)
);

CREATE INDEX IF NOT EXISTS idx_leases_key_active
ON resource_leases(resource_key, is_active);

-- Worker registration and heartbeats
CREATE TABLE IF NOT EXISTS worker_registry (
    worker_id TEXT PRIMARY KEY,
    worker_epoch INTEGER NOT NULL,
    process_id INTEGER NOT NULL,
    host_identity TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    last_heartbeat_utc TEXT NOT NULL,
    status TEXT NOT NULL,
    heartbeat_timeout_seconds REAL DEFAULT 15.0
);

-- Reconciliation audit log for crash recovery
CREATE TABLE IF NOT EXISTS reconciliation_audit (
    audit_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    evidence_level INTEGER NOT NULL,
    reason TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL
);
"""


class MigrationEngine:
    """Manages transactional schema migrations for the scheduler database."""

    @staticmethod
    def get_current_version(conn: sqlite3.Connection) -> int:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='scheduler_meta';"
        )
        if not cursor.fetchone():
            return 32  # Pre-3.3 baseline schema version
        cursor.execute("SELECT value FROM scheduler_meta WHERE key='schema_version';")
        row = cursor.fetchone()
        return int(row[0]) if row else 32

    @staticmethod
    def apply_migrations(conn: sqlite3.Connection) -> int:
        current_version = MigrationEngine.get_current_version(conn)
        if current_version >= TARGET_SCHEMA_VERSION:
            return current_version

        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.executescript(MIGRATION_V32_TO_V33_DDL)
            cursor.execute(
                """
                INSERT INTO scheduler_meta (key, value) VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP;
                """,
                (str(TARGET_SCHEMA_VERSION),),
            )
            conn.commit()
            logger.info(
                "Migrated scheduler database from v%d to v%d",
                current_version,
                TARGET_SCHEMA_VERSION,
            )
            return TARGET_SCHEMA_VERSION
        except Exception as ex:
            conn.rollback()
            logger.error("Migration failed, rolled back: %s", ex)
            raise RuntimeError(f"Database migration failed: {ex}") from ex


__all__ = ["MigrationEngine", "TARGET_SCHEMA_VERSION"]
