"""SQLite state storage for 1Password plugin: audit logs, standing grants, and authorization nonces.

OpenClaw parity: mirrors OpenClaw's shared SQLite tables:
- `onepassword_audit_log`: durable history of all access attempts (never stores secrets or tokens).
- `onepassword_grants`: durable standing grants per (agent_id, slug) bounded to max 1,024 LRU entries.
- `onepassword_nonces`: single-use authorization nonces with 600s TTL.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path

from .config import MAX_STANDING_GRANTS
from .token import get_state_dir
from .types import AuditOutcome, AuditRow, StandingGrant

logger = logging.getLogger("jarvis.onepassword.storage")


def get_default_db_path(state_dir: Path | None = None) -> Path:
    """Return default SQLite database path."""
    root = state_dir or get_state_dir()
    state_folder = root / "state"
    state_folder.mkdir(parents=True, exist_ok=True)
    return state_folder / "jarvis.sqlite"


class OnepasswordStorage:
    """Synchronous SQLite storage manager for 1Password state."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            self.db_path = get_default_db_path()
        elif isinstance(db_path, str):
            self.db_path = Path(db_path)
        else:
            self.db_path = db_path

        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with foreign keys and WAL mode."""
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _ensure_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            # Table 1: Audit Log
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS onepassword_audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    agent_id TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    error_code TEXT,
                    reason TEXT,
                    cached INTEGER NOT NULL DEFAULT 0,
                    duration_ms REAL NOT NULL DEFAULT 0.0
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_onepassword_audit_timestamp
                ON onepassword_audit_log(timestamp DESC);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_onepassword_audit_slug
                ON onepassword_audit_log(slug);
                """
            )

            # Table 2: Standing Grants (LRU bounded)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS onepassword_grants (
                    agent_id TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    granted_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_used_at REAL NOT NULL,
                    PRIMARY KEY (agent_id, slug)
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_onepassword_grants_lru
                ON onepassword_grants(last_used_at ASC);
                """
            )

            # Table 3: Single-Use Authorization Nonces
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS onepassword_nonces (
                    nonce TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_onepassword_nonces_expires
                ON onepassword_nonces(expires_at ASC);
                """
            )

    # ── Audit Log Methods ─────────────────────────────────────────────────────

    def record_audit(
        self,
        slug: str,
        action: str,
        outcome: AuditOutcome,
        agent_id: str = "",
        error_code: str | None = None,
        reason: str = "",
        cached: bool = False,
        duration_ms: float = 0.0,
        row_id: str | None = None,
        now: float | None = None,
    ) -> AuditRow:
        """Record an access attempt in SQLite onepassword_audit_log."""
        record_id = row_id or str(uuid.uuid4())
        ts = time.time() if now is None else now
        truncated_reason = reason[:300] if reason else ""

        row = AuditRow(
            id=record_id,
            timestamp=ts,
            agent_id=agent_id,
            slug=slug,
            action=action,
            outcome=outcome,
            error_code=error_code,
            reason=truncated_reason,
            cached=cached,
            duration_ms=duration_ms,
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO onepassword_audit_log (
                    id, timestamp, agent_id, slug, action, outcome,
                    error_code, reason, cached, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    row.id,
                    row.timestamp,
                    row.agent_id,
                    row.slug,
                    row.action,
                    row.outcome,
                    row.error_code,
                    row.reason,
                    1 if row.cached else 0,
                    row.duration_ms,
                ),
            )

        return row

    def get_audit_log(self, limit: int = 50, slug: str | None = None) -> list[AuditRow]:
        """Fetch newest-first audit rows up to limit."""
        with self._get_connection() as conn:
            if slug:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, agent_id, slug, action, outcome,
                           error_code, reason, cached, duration_ms
                    FROM onepassword_audit_log
                    WHERE slug = ?
                    ORDER BY timestamp DESC
                    LIMIT ?;
                    """,
                    (slug, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, agent_id, slug, action, outcome,
                           error_code, reason, cached, duration_ms
                    FROM onepassword_audit_log
                    ORDER BY timestamp DESC
                    LIMIT ?;
                    """,
                    (limit,),
                )

            rows: list[AuditRow] = []
            for r in cursor.fetchall():
                rows.append(
                    AuditRow(
                        id=r["id"],
                        timestamp=r["timestamp"],
                        agent_id=r["agent_id"],
                        slug=r["slug"],
                        action=r["action"],
                        outcome=r["outcome"],
                        error_code=r["error_code"],
                        reason=r["reason"] or "",
                        cached=bool(r["cached"]),
                        duration_ms=float(r["duration_ms"]),
                    )
                )
            return rows

    # ── Standing Grants Methods ───────────────────────────────────────────────

    def has_standing_grant(self, agent_id: str, slug: str, now: float | None = None) -> bool:
        """Check if an unexpired standing grant exists for the agent and slug."""
        if not agent_id:
            return False
        current_time = time.time() if now is None else now
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT expires_at FROM onepassword_grants
                WHERE agent_id = ? AND slug = ?;
                """,
                (agent_id, slug),
            )
            row = cursor.fetchone()
            if not row:
                return False
            expires_at = float(row["expires_at"])
            if current_time > expires_at:
                # Expired grant
                conn.execute(
                    "DELETE FROM onepassword_grants WHERE agent_id = ? AND slug = ?;",
                    (agent_id, slug),
                )
                return False

            # Update last_used_at
            conn.execute(
                "UPDATE onepassword_grants SET last_used_at = ? WHERE agent_id = ? AND slug = ?;",
                (current_time, agent_id, slug),
            )
            return True

    def save_standing_grant(
        self,
        agent_id: str,
        slug: str,
        grant_ttl_hours: int = 720,
        now: float | None = None,
    ) -> StandingGrant:
        """Save or refresh a standing grant with LRU eviction at capacity."""
        if not agent_id:
            raise ValueError("Standing grants require a non-empty agent identity")

        current_time = time.time() if now is None else now
        expires_at = current_time + (grant_ttl_hours * 3600.0)

        with self._get_connection() as conn:
            # Check capacity
            count_cursor = conn.execute("SELECT COUNT(*) as cnt FROM onepassword_grants;")
            count = count_cursor.fetchone()["cnt"]

            if count >= MAX_STANDING_GRANTS:
                # Evict oldest entry by last_used_at
                conn.execute(
                    """
                    DELETE FROM onepassword_grants
                    WHERE (agent_id, slug) IN (
                        SELECT agent_id, slug FROM onepassword_grants
                        ORDER BY last_used_at ASC
                        LIMIT 1
                    );
                    """
                )

            conn.execute(
                """
                INSERT OR REPLACE INTO onepassword_grants (
                    agent_id, slug, granted_at, expires_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (agent_id, slug, current_time, expires_at, current_time),
            )

        return StandingGrant(
            agent_id=agent_id,
            slug=slug,
            granted_at=current_time,
            expires_at=expires_at,
            last_used_at=current_time,
        )

    def revoke_standing_grant(self, agent_id: str, slug: str) -> bool:
        """Revoke a standing grant."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM onepassword_grants WHERE agent_id = ? AND slug = ?;",
                (agent_id, slug),
            )
            return cursor.rowcount > 0

    def list_standing_grants(
        self,
        agent_id: str | None = None,
        now: float | None = None,
    ) -> list[StandingGrant]:
        """List active standing grants."""
        current_time = time.time() if now is None else now
        with self._get_connection() as conn:
            if agent_id:
                cursor = conn.execute(
                    """
                    SELECT agent_id, slug, granted_at, expires_at, last_used_at
                    FROM onepassword_grants
                    WHERE agent_id = ? AND expires_at >= ?
                    ORDER BY granted_at DESC;
                    """,
                    (agent_id, current_time),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT agent_id, slug, granted_at, expires_at, last_used_at
                    FROM onepassword_grants
                    WHERE expires_at >= ?
                    ORDER BY granted_at DESC;
                    """,
                    (current_time,),
                )

            grants: list[StandingGrant] = []
            for r in cursor.fetchall():
                grants.append(
                    StandingGrant(
                        agent_id=r["agent_id"],
                        slug=r["slug"],
                        granted_at=float(r["granted_at"]),
                        expires_at=float(r["expires_at"]),
                        last_used_at=float(r["last_used_at"]),
                    )
                )
            return grants

    # ── Authorization Nonce Methods ───────────────────────────────────────────

    def create_authorization_nonce(
        self,
        agent_id: str,
        slug: str,
        ttl_seconds: int = 600,
        now: float | None = None,
    ) -> str:
        """Generate and store a single-use authorization nonce."""
        nonce = f"auth-{uuid.uuid4().hex}"
        current_time = time.time() if now is None else now
        expires_at = current_time + float(ttl_seconds)

        with self._get_connection() as conn:
            # Purge expired nonces
            conn.execute("DELETE FROM onepassword_nonces WHERE expires_at < ?;", (current_time,))
            conn.execute(
                """
                INSERT INTO onepassword_nonces (nonce, agent_id, slug, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (nonce, agent_id, slug, current_time, expires_at),
            )

        return nonce

    def consume_authorization_nonce(
        self,
        nonce: str,
        agent_id: str,
        slug: str,
        now: float | None = None,
    ) -> tuple[bool, str | None]:
        """Consume a single-use authorization nonce.

        Returns (valid, failure_code).
        """
        if not nonce:
            return False, "POLICY_NOT_EVALUATED"

        current_time = time.time() if now is None else now
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT agent_id, slug, expires_at FROM onepassword_nonces
                WHERE nonce = ?;
                """,
                (nonce,),
            )
            row = cursor.fetchone()
            if not row:
                return False, "POLICY_NOT_EVALUATED"

            # Delete the nonce immediately so it is single-use
            conn.execute("DELETE FROM onepassword_nonces WHERE nonce = ?;", (nonce,))

            if current_time > float(row["expires_at"]):
                return False, "GRANT_EXPIRED"

            if row["slug"] != slug:
                return False, "POLICY_CHANGED"

            # If agent_id is provided, verify it matches
            if agent_id and row["agent_id"] and row["agent_id"] != agent_id:
                return False, "POLICY_NOT_EVALUATED"

            return True, None
