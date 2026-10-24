"""jarvis.storage.sqlite_broker — Canonical SQLite database bootstrap & broker.

OpenClaw parity:
- Ensures ~/.jarvis/core/memory.sqlite, ~/.jarvis/state/jarvis.sqlite, and ~/.jarvis/state/lance/
  are initialized before agent or gateway startup.
- Single synchronous commit section for database writes with WAL mode enabled.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger("jarvis.storage.sqlite_broker")


def _get_jarvis_data_dir() -> Path:
    env_dir = os.environ.get("JARVIS_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".jarvis"


def _init_memory_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT DEFAULT 'owner',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(category, key)
            );
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                category,
                key,
                value,
                content='facts',
                content_rowid='id'
            );
            """
        )
        conn.commit()


def _init_state_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_kv (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (namespace, key)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reflection_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL,
                task_goal TEXT NOT NULL,
                failed_action TEXT NOT NULL,
                error_message TEXT NOT NULL,
                root_cause TEXT NOT NULL,
                successful_workaround TEXT NOT NULL,
                lesson_learned TEXT NOT NULL,
                occurrence_count INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_reflection_fingerprint ON reflection_memories(fingerprint);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learned_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_pattern TEXT NOT NULL,
                optimal_tool TEXT NOT NULL,
                decomposed_steps_json TEXT NOT NULL,
                success_rate REAL DEFAULT 1.0,
                times_used INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.commit()


async def initialize_canonical_databases() -> None:
    """Initialize canonical memory and state SQLite databases with WAL mode."""
    data_dir = _get_jarvis_data_dir()
    core_dir = data_dir / "core"
    state_dir = data_dir / "state"
    lance_dir = state_dir / "lance"

    core_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    lance_dir.mkdir(parents=True, exist_ok=True)

    memory_db_path = core_dir / "memory.sqlite"
    state_db_path = state_dir / "jarvis.sqlite"

    await asyncio.to_thread(_init_memory_db, memory_db_path)
    await asyncio.to_thread(_init_state_db, state_db_path)

    logger.info("Canonical databases initialized: %s, %s", memory_db_path, state_db_path)


__all__ = [
    "initialize_canonical_databases",
]
