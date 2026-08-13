"""Channel session store — SQLite persistence for channel sessions.

Mirrors OpenClaw's ``src/channels/session-store.ts``.

W2.3: replaces the in-memory ``BindingRegistry`` with a SQLite-backed
store that persists ``ChannelSession`` records in the shared state DB
(``~/.jarvis/state/jarvis.sqlite``).

Benefits over in-memory registry:
  - Sessions survive JARVIS restarts (Telegram bot remembers which
    chat it was paired with).
  - Multiple concurrent instances can read shared session state.
  - Audit trail for session lifecycle (created_at, last_message_at).

Schema is purely additive — the table does not exist in older builds,
so first use creates it lazily. No schema version bump needed (per
AGENTS.md additive SQLite rule).

Table: ``channel_sessions``
  - session_key (TEXT, PRIMARY KEY)   — derive_session_key(channel_id, conv_id)
  - channel_id  (TEXT NOT NULL)
  - conversation_id (TEXT NOT NULL)
  - agent_id    (TEXT NOT NULL DEFAULT 'default')
  - is_owner    (INTEGER NOT NULL DEFAULT 0)
  - created_at  (INTEGER NOT NULL)    — unix milliseconds
  - last_active (INTEGER NOT NULL)    — unix milliseconds

Architecture note: write transactions are synchronous commit sections
only. No await inside the transaction callback (per AGENTS.md).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from jarvis_channels import BindingRegistry, InboundMessage
from jarvis_channels.types import ChannelSession
from jarvis_channels import derive_session_key

_log = logging.getLogger("jarvis.channels.session_store")

# ── DDL ────────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS channel_sessions (
    session_key      TEXT PRIMARY KEY,
    channel_id       TEXT NOT NULL,
    conversation_id  TEXT NOT NULL,
    agent_id         TEXT NOT NULL DEFAULT 'default',
    is_owner         INTEGER NOT NULL DEFAULT 0,
    created_at       INTEGER NOT NULL,
    last_active      INTEGER NOT NULL
)
""".strip()

_UPSERT = """
INSERT INTO channel_sessions
    (session_key, channel_id, conversation_id, agent_id, is_owner, created_at, last_active)
VALUES
    (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(session_key) DO UPDATE SET
    last_active = excluded.last_active,
    is_owner    = excluded.is_owner
""".strip()

_SELECT_BY_KEY = """
SELECT session_key, channel_id, conversation_id, agent_id, is_owner, created_at, last_active
FROM channel_sessions WHERE session_key = ?
""".strip()

_SELECT_BY_CONV = """
SELECT session_key, channel_id, conversation_id, agent_id, is_owner, created_at, last_active
FROM channel_sessions WHERE channel_id = ? AND conversation_id = ?
""".strip()

_DELETE_BY_KEY = "DELETE FROM channel_sessions WHERE session_key = ?"

_SELECT_ALL = """
SELECT session_key, channel_id, conversation_id, agent_id, is_owner
FROM channel_sessions ORDER BY last_active DESC
""".strip()


# ── SQLite helpers ─────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _row_to_session(row: tuple) -> ChannelSession:
    session_key, channel_id, conversation_id, agent_id, is_owner, *_ = row
    return ChannelSession(
        session_key=session_key,
        channel_id=channel_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        is_owner=bool(is_owner),
    )


# ── Persisted registry ─────────────────────────────────────────────────


class PersistedChannelRegistry:
    """SQLite-backed channel session registry.

    Drop-in replacement for ``BindingRegistry`` that persists sessions
    across restarts. Falls back to the in-memory registry on DB errors
    (open/schema failures) so the host never crashes due to DB issues.

    Parameters
    ----------
    db_path : Path
        Path to the shared state SQLite DB. Defaults to
        ``~/.jarvis/state/jarvis.sqlite``.
    fallback : BindingRegistry | None
        In-memory fallback. Created automatically if not supplied.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        fallback: BindingRegistry | None = None,
    ) -> None:
        self._db_path = db_path or _default_db_path()
        self._fallback = fallback or BindingRegistry()
        self._lock = threading.Lock()
        self._ready = False
        self._init_db()

    def _init_db(self) -> None:
        """Ensure the channel_sessions table exists. One-time call."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(_CREATE_TABLE)
                conn.commit()
            self._ready = True
            _log.info(
                "channel_session_store: persisted registry ready at %s",
                self._db_path,
            )
        except Exception as e:  # noqa: BLE001
            _log.warning(
                "channel_session_store: DB init failed (%s); using in-memory fallback",
                e,
            )
            self._ready = False

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

    def get_or_create(
        self,
        message: InboundMessage,
        *,
        agent_id: str | None = None,
    ) -> ChannelSession:
        """Return the existing session or create + persist a new one."""
        if not self._ready:
            return self._fallback.get_or_create(message, agent_id=agent_id)

        key = derive_session_key(message.channel_id, message.conversation_id)
        now = _now_ms()
        effective_agent_id = agent_id or "default"

        with self._lock:
            try:
                with self._conn() as conn:
                    # Check for existing row.
                    row = conn.execute(_SELECT_BY_KEY, (key,)).fetchone()
                    if row is not None:
                        # Update last_active + is_owner atomically.
                        conn.execute(
                            "UPDATE channel_sessions SET last_active=?, is_owner=? WHERE session_key=?",
                            (now, int(message.is_owner), key),
                        )
                        return _row_to_session(row)

                    # Insert new row.
                    conn.execute(
                        _UPSERT,
                        (
                            key,
                            message.channel_id,
                            message.conversation_id,
                            effective_agent_id,
                            int(message.is_owner),
                            now,
                            now,
                        ),
                    )
                    return ChannelSession(
                        session_key=key,
                        channel_id=message.channel_id,
                        conversation_id=message.conversation_id,
                        agent_id=effective_agent_id,
                        is_owner=message.is_owner,
                    )
            except Exception as e:  # noqa: BLE001
                _log.warning("channel_session_store: upsert failed (%s); using fallback", e)
                return self._fallback.get_or_create(message, agent_id=agent_id)

    def get(self, session_key: str) -> ChannelSession | None:
        """Return the session for ``session_key``, or None."""
        if not self._ready:
            return self._fallback.get(session_key)
        try:
            with self._conn() as conn:
                row = conn.execute(_SELECT_BY_KEY, (session_key,)).fetchone()
                return _row_to_session(row) if row else None
        except Exception as e:  # noqa: BLE001
            _log.warning("channel_session_store: get failed (%s)", e)
            return self._fallback.get(session_key)

    def get_by_conversation(
        self, channel_id: str, conversation_id: str
    ) -> ChannelSession | None:
        """Return the session for a channel + conversation id pair, or None."""
        if not self._ready:
            return self._fallback.get_by_conversation(channel_id, conversation_id)
        try:
            with self._conn() as conn:
                row = conn.execute(_SELECT_BY_CONV, (channel_id, conversation_id)).fetchone()
                return _row_to_session(row) if row else None
        except Exception as e:  # noqa: BLE001
            _log.warning("channel_session_store: get_by_conv failed (%s)", e)
            return self._fallback.get_by_conversation(channel_id, conversation_id)

    def remove(self, session_key: str) -> None:
        """Delete a session record."""
        if not self._ready:
            self._fallback.remove(session_key)
            return
        with self._lock:
            try:
                with self._conn() as conn:
                    conn.execute(_DELETE_BY_KEY, (session_key,))
            except Exception as e:  # noqa: BLE001
                _log.warning("channel_session_store: remove failed (%s)", e)
                self._fallback.remove(session_key)

    def all_sessions(self) -> list[ChannelSession]:
        """Return all persisted sessions."""
        if not self._ready:
            return self._fallback.all_sessions()
        try:
            with self._conn() as conn:
                rows = conn.execute(_SELECT_ALL).fetchall()
                return [_row_to_session(r) for r in rows]
        except Exception as e:  # noqa: BLE001
            _log.warning("channel_session_store: all_sessions failed (%s)", e)
            return self._fallback.all_sessions()

    def session_count(self) -> int:
        """Return the number of persisted sessions."""
        return len(self.all_sessions())

    def clear(self) -> None:
        """Delete all channel_sessions rows (tests / reset only)."""
        if not self._ready:
            self._fallback.clear()
            return
        with self._lock:
            try:
                with self._conn() as conn:
                    conn.execute("DELETE FROM channel_sessions")
            except Exception as e:  # noqa: BLE001
                _log.warning("channel_session_store: clear failed (%s)", e)
                self._fallback.clear()


def _default_db_path() -> Path:
    """Canonical path: ``~/.jarvis/state/jarvis.sqlite``."""
    return Path.home() / ".jarvis" / "state" / "jarvis.sqlite"


__all__ = ["PersistedChannelRegistry", "_default_db_path"]
