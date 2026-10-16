"""SQLite recovery engine with committed vs uncommitted WAL transaction validation.

Ensures that committed transactions survive reboot intact while uncommitted transactions
in the WAL journal are cleanly discarded without partial promotion or schema corruption.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


class SQLiteRecoveryEngine:
    """Manages transactional durability stress testing and recovery validation."""

    TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS journal_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT NOT NULL,
        generation INTEGER NOT NULL,
        committed_at_utc TEXT NOT NULL
    );
    """

    @classmethod
    def seed_test_database(
        cls,
        db_path: Path,
        committed_count: int = 50,
        uncommitted_count: int = 10,
    ) -> dict[str, Any]:
        """Seed a database with committed records and leave uncommitted WAL transactions."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=FULL;")
        conn.execute(cls.TABLE_SCHEMA)

        # 1. Insert and commit verified records
        for i in range(committed_count):
            conn.execute(
                "INSERT OR REPLACE INTO journal_records (key, value, generation, committed_at_utc) "
                "VALUES (?, ?, ?, datetime('now'));",
                (f"committed_key_{i}", f"committed_val_{i}", 1),
            )
        conn.commit()

        # 2. Begin transaction and write uncommitted records without committing
        if uncommitted_count > 0:
            conn.execute("BEGIN TRANSACTION;")
            for j in range(uncommitted_count):
                conn.execute(
                    "INSERT INTO journal_records (key, value, generation, committed_at_utc) "
                    "VALUES (?, ?, ?, datetime('now'));",
                    (f"uncommitted_key_{j}", f"uncommitted_val_{j}", 2),
                )
            # DO NOT COMMIT - close immediately to simulate process crash
            conn.close()
        else:
            conn.close()

        return {
            "committed_expected": committed_count,
            "uncommitted_expected": uncommitted_count,
        }

    @classmethod
    def verify_recovery(cls, db_path: Path, expected_committed: int) -> dict[str, Any]:
        """Verify that committed records survived and uncommitted transactions were rolled back."""
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        cur = conn.cursor()

        # Count total rows
        cur.execute("SELECT COUNT(*) FROM journal_records;")
        total_rows = int(cur.fetchone()[0])

        # Check for presence of uncommitted keys (should be ZERO)
        cur.execute("SELECT COUNT(*) FROM journal_records WHERE key LIKE 'uncommitted_%';")
        uncommitted_present = int(cur.fetchone()[0])

        conn.close()

        clean_rollback = uncommitted_present == 0
        committed_intact = total_rows == expected_committed

        return {
            "total_rows": total_rows,
            "expected_committed": expected_committed,
            "committed_intact": committed_intact,
            "uncommitted_present": uncommitted_present,
            "clean_rollback": clean_rollback,
            "is_consistent": committed_intact and clean_rollback,
        }


__all__ = ["SQLiteRecoveryEngine"]
