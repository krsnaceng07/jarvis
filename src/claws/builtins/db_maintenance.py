"""Database Backup & Vacuum Autonomous Claw — JARVIS Autonomous Architecture (Task 2).

Periodically optimizes, vacuums, checkpoints, and backs up canonical SQLite state databases.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from ..base import Claw, ClawExecutionContext
from ..types import ClawPriority, ClawResult


class DatabaseMaintenanceClaw(Claw):
    """Autonomous Claw that performs SQLite WAL checkpoints, vacuuming, backups, and integrity checks."""

    def __init__(
        self,
        schedule: str = "0 */6 * * *",  # Every 6 hours
        priority: ClawPriority = ClawPriority.HIGH,
        backup_retention: int = 7,
    ) -> None:
        super().__init__(
            claw_id="claw:database_maintenance",
            name="Database Backup & Vacuum Claw",
            description="Performs SQLite WAL checkpoints, vacuuming, atomic backups, and integrity checks on state databases.",
            schedule=schedule,
            priority=priority,
            timeout_seconds=90.0,
        )
        self.backup_retention = backup_retention

    async def run(self, ctx: ClawExecutionContext) -> ClawResult:
        start_time = time.monotonic()
        state_dir = ctx.state_dir
        db_files = list(state_dir.glob("*.sqlite"))

        backup_dir = state_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        metrics: dict[str, Any] = {"dbs_checked": len(db_files), "results": {}}
        overall_ok = True
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        for db_file in db_files:
            db_name = db_file.name
            try:
                conn = sqlite3.connect(str(db_file), timeout=15.0)

                # 1. WAL Checkpoint (TRUNCATE) to commit WAL pages and reclaim disk space
                cur = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                cp_row = cur.fetchone()

                # 2. Integrity check
                cur = conn.execute("PRAGMA integrity_check;")
                check_res = cur.fetchone()[0]

                # 3. VACUUM to defragment and optimize tables
                conn.execute("VACUUM;")

                # 4. Atomic Online Backup via SQLite backup API
                backup_filename = f"{db_file.stem}_backup_{now_str}.sqlite"
                backup_filepath = backup_dir / backup_filename
                backup_conn = sqlite3.connect(str(backup_filepath))
                with backup_conn:
                    conn.backup(backup_conn, pages=100)
                backup_conn.close()
                conn.close()

                # Rotate old backups for this DB
                existing_backups = sorted(
                    backup_dir.glob(f"{db_file.stem}_backup_*.sqlite"),
                    key=os.path.getmtime,
                    reverse=True,
                )
                if len(existing_backups) > self.backup_retention:
                    for old_b in existing_backups[self.backup_retention :]:
                        try:
                            old_b.unlink()
                        except Exception:
                            pass

                size_bytes = os.path.getsize(db_file)
                is_ok = check_res == "ok"
                if not is_ok:
                    overall_ok = False

                metrics["results"][db_name] = {
                    "checkpoint": list(cp_row) if cp_row else None,
                    "integrity": check_res,
                    "size_bytes": size_bytes,
                    "backup_path": str(backup_filepath),
                    "status": "ok" if is_ok else "corrupted",
                }
            except Exception as e:
                overall_ok = False
                metrics["results"][db_name] = {"error": str(e), "status": "error"}

        duration_ms = (time.monotonic() - start_time) * 1000.0

        await ctx.checkpoint(
            {
                "timestamp": time.time(),
                "dbs_checked": len(db_files),
                "healthy": overall_ok,
                "backup_dir": str(backup_dir),
            }
        )

        if not overall_ok:
            await ctx.notify(
                "Database Integrity Alert",
                "One or more state databases encountered integrity issues during maintenance.",
                level="error",
            )

        return ClawResult(
            success=overall_ok,
            output=f"Processed {len(db_files)} state databases with WAL checkpoint, vacuum, and backup (healthy={overall_ok})",
            duration_ms=duration_ms,
            metrics=metrics,
        )


__all__ = ["DatabaseMaintenanceClaw"]
