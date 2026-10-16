"""Gateway runtime process singleton protection for Track 3.4."""

from __future__ import annotations

import datetime
from pathlib import Path
import sqlite3

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException


class GatewaySingletonLock:
    """Exclusive SQLite lock ensuring only one Gateway runtime process is active per state dir."""

    def __init__(self, db_path: str | Path | None = None, lease_ttl_seconds: float = 30.0) -> None:
        self.db_path = str(db_path or ":memory:")
        self.lease_ttl_seconds = lease_ttl_seconds
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_singleton_lease (
                    lock_name TEXT PRIMARY KEY,
                    process_id TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL
                );
                """
            )

    def acquire_lease(self, process_id: str) -> bool:
        """Attempt to acquire or refresh exclusive gateway lease."""
        now = datetime.datetime.now(datetime.timezone.utc)
        exp_str = (now + datetime.timedelta(seconds=self.lease_ttl_seconds)).isoformat()

        with self._conn:
            cur = self._conn.execute(
                "SELECT * FROM gateway_singleton_lease WHERE lock_name = 'gateway_primary';"
            )
            row = cur.fetchone()
            if row:
                stored_pid = row["process_id"]
                stored_exp = datetime.datetime.fromisoformat(row["expires_at_utc"])
                if stored_pid != process_id and now < stored_exp:
                    raise GatewayException(
                        code=GatewayErrorCode.SESSION_FORBIDDEN,
                        message=f"Gateway lease currently held by active process '{stored_pid}'.",
                    )

            self._conn.execute(
                """
                INSERT INTO gateway_singleton_lease (lock_name, process_id, expires_at_utc)
                VALUES ('gateway_primary', ?, ?)
                ON CONFLICT(lock_name) DO UPDATE SET
                    process_id = excluded.process_id,
                    expires_at_utc = excluded.expires_at_utc;
                """,
                (process_id, exp_str),
            )
            return True

    def release_lease(self, process_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM gateway_singleton_lease WHERE lock_name = 'gateway_primary' AND process_id = ?;",
                (process_id,),
            )

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


__all__ = ["GatewaySingletonLock"]
