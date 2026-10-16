"""Deep SQLite WAL journal and PRAGMA integrity auditing.

Validates PRAGMA integrity_check, quick_check, foreign_key_check, WAL checkpoints,
and database engine parameters, guaranteeing storage integrity.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class SQLiteAuditReport:
    """Comprehensive health and consistency audit for an individual SQLite database."""

    database_path: str
    integrity_check_passed: bool
    quick_check_passed: bool
    foreign_keys_passed: bool
    journal_mode: str
    synchronous_mode: int
    page_size: int
    schema_version: int
    user_version: int
    wal_file_present: bool
    wal_file_size_bytes: int
    checkpoint_status: str
    is_healthy: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class DatabaseIntegrityVerifier:
    """Audits SQLite databases across PRAGMAs, WAL state, and foreign key integrity."""

    @classmethod
    def audit_database(cls, db_path: Path) -> SQLiteAuditReport:
        """Run deep structural and consistency audit on target SQLite database."""
        if not db_path.exists():
            return SQLiteAuditReport(
                database_path=str(db_path),
                integrity_check_passed=False,
                quick_check_passed=False,
                foreign_keys_passed=False,
                journal_mode="UNKNOWN",
                synchronous_mode=-1,
                page_size=0,
                schema_version=0,
                user_version=0,
                wal_file_present=False,
                wal_file_size_bytes=0,
                checkpoint_status="FILE_NOT_FOUND",
                is_healthy=False,
            )

        wal_file = Path(f"{db_path}-wal")
        wal_present = wal_file.exists()
        wal_size = wal_file.stat().st_size if wal_present else 0

        integrity_ok = False
        quick_ok = False
        fk_ok = False
        j_mode = "UNKNOWN"
        sync_mode = -1
        page_size = 0
        schema_ver = 0
        user_ver = 0
        checkpoint_status = "NOT_EXECUTED"

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cur = conn.cursor()

            # 1. PRAGMA integrity_check
            cur.execute("PRAGMA integrity_check;")
            row = cur.fetchone()
            integrity_ok = bool(row and row[0].lower() == "ok")

            # 2. PRAGMA quick_check
            cur.execute("PRAGMA quick_check;")
            qrow = cur.fetchone()
            quick_ok = bool(qrow and qrow[0].lower() == "ok")

            # 3. PRAGMA foreign_key_check
            cur.execute("PRAGMA foreign_key_check;")
            fk_rows = cur.fetchall()
            fk_ok = len(fk_rows) == 0

            # 4. PRAGMA journal parameters
            cur.execute("PRAGMA journal_mode;")
            j_mode = str(cur.fetchone()[0]).lower()

            cur.execute("PRAGMA synchronous;")
            sync_mode = int(cur.fetchone()[0])

            cur.execute("PRAGMA page_size;")
            page_size = int(cur.fetchone()[0])

            cur.execute("PRAGMA schema_version;")
            schema_ver = int(cur.fetchone()[0])

            cur.execute("PRAGMA user_version;")
            user_ver = int(cur.fetchone()[0])

            # 5. Checkpoint execution
            if j_mode == "wal":
                try:
                    cur.execute("PRAGMA wal_checkpoint(PASSIVE);")
                    cp_row = cur.fetchone()
                    checkpoint_status = (
                        f"PASSIVE_OK (busy={cp_row[0]}, log={cp_row[1]}, ckpt={cp_row[2]})"
                    )
                except Exception as exc:
                    checkpoint_status = f"CHECKPOINT_ERROR: {exc}"
            else:
                checkpoint_status = "NON_WAL_JOURNAL"

            conn.close()

        except Exception as exc:
            logger.warning("Database audit error on %s: %s", db_path, exc)
            checkpoint_status = f"CONNECT_FAILED: {exc}"

        is_healthy = integrity_ok and quick_ok and fk_ok

        return SQLiteAuditReport(
            database_path=str(db_path),
            integrity_check_passed=integrity_ok,
            quick_check_passed=quick_ok,
            foreign_keys_passed=fk_ok,
            journal_mode=j_mode,
            synchronous_mode=sync_mode,
            page_size=page_size,
            schema_version=schema_ver,
            user_version=user_ver,
            wal_file_present=wal_present,
            wal_file_size_bytes=wal_size,
            checkpoint_status=checkpoint_status,
            is_healthy=is_healthy,
        )


__all__ = ["DatabaseIntegrityVerifier", "SQLiteAuditReport"]
