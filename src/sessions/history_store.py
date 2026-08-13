"""SQLite-persisted conversation history — W5.3.

Replaces the in-memory ``_ConversationHistory`` in
``ChannelSessionRunner`` with a per-session SQLite table so
conversation context survives JARVIS restarts.

Mirrors OpenClaw's:
  ``src/agents/sessions/session-history-store.ts``
  ``src/agents/sessions/conversation-history.ts``

Schema: ``channel_conversation_turns``
  - id          INTEGER PRIMARY KEY AUTOINCREMENT
  - session_key TEXT NOT NULL
  - role        TEXT NOT NULL  ('user'|'assistant'|'tool')
  - content     TEXT NOT NULL
  - tool_name   TEXT          (role='tool' only)
  - call_id     TEXT          (role='tool' only)
  - created_at  INTEGER NOT NULL  (unix milliseconds)

Rules (AGENTS.md):
  - Additive schema — no version bump (new table, older builds unaffected).
  - WAL mode + busy_timeout on every connection.
  - Write transactions are synchronous commit sections only.
  - No ``await`` inside SQLite transactions.
  - Falls back to in-memory history on DB errors.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger("jarvis.sessions.history_store")

# ── DDL ────────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS channel_conversation_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    tool_name   TEXT,
    call_id     TEXT,
    created_at  INTEGER NOT NULL
)
""".strip()

_CREATE_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_cct_session_key "
    "ON channel_conversation_turns (session_key, id)"
)

_INSERT = """
INSERT INTO channel_conversation_turns
    (session_key, role, content, tool_name, call_id, created_at)
VALUES (?, ?, ?, ?, ?, ?)
""".strip()

_SELECT_BY_SESSION = """
SELECT role, content, tool_name, call_id
FROM channel_conversation_turns
WHERE session_key = ?
ORDER BY id ASC
""".strip()

_COUNT_BY_SESSION = (
    "SELECT COUNT(*) FROM channel_conversation_turns WHERE session_key = ?"
)

_DELETE_BY_SESSION = (
    "DELETE FROM channel_conversation_turns WHERE session_key = ?"
)

_DELETE_ALL = "DELETE FROM channel_conversation_turns"

# ── Helpers ────────────────────────────────────────────────────────────


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_db_path() -> Path:
    return Path.home() / ".jarvis" / "state" / "jarvis.sqlite"


# ── Persisted history store ────────────────────────────────────────────


class ConversationHistoryStore:
    """SQLite-backed conversation turn store.

    Each session key maps to an ordered list of turns. Falls back to
    in-memory mode if the DB cannot be opened (same pattern as
    ``PersistedChannelRegistry``).

    Parameters
    ----------
    db_path : Path | None
        Defaults to ``~/.jarvis/state/jarvis.sqlite``.
    max_turns : int
        Maximum turns retained per session. When exceeded, the oldest
        turns are trimmed before the new turn is inserted.
        0 = unlimited.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        max_turns: int = 200,
    ) -> None:
        self._db_path = db_path or _default_db_path()
        self._max_turns = max_turns
        self._lock = threading.Lock()
        self._ready = False
        # In-memory fallback: dict[session_key, list[dict]]
        self._fallback: dict[str, list[dict[str, Any]]] = {}
        self._init_db()

    def _init_db(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(_CREATE_TABLE)
                conn.execute(_CREATE_IDX)
                conn.commit()
            self._ready = True
            _log.info("history_store: ready at %s", self._db_path)
        except Exception as e:  # noqa: BLE001
            _log.warning("history_store: init failed (%s); using in-memory fallback", e)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

    # ── Public API ──────────────────────────────────────────────────

    def append_user(self, session_key: str, text: str) -> None:
        """Append a user turn."""
        self._append(session_key, role="user", content=text)

    def append_assistant(self, session_key: str, text: str) -> None:
        """Append an assistant turn."""
        self._append(session_key, role="assistant", content=text)

    def append_tool_result(
        self,
        session_key: str,
        tool_name: str,
        call_id: str,
        content: str,
    ) -> None:
        """Append a tool result turn."""
        self._append(
            session_key,
            role="tool",
            content=content,
            tool_name=tool_name,
            call_id=call_id,
        )

    def get_turns(self, session_key: str) -> list[dict[str, Any]]:
        """Return all turns for ``session_key`` in chronological order."""
        if not self._ready:
            return list(self._fallback.get(session_key, []))
        try:
            with self._conn() as conn:
                rows = conn.execute(_SELECT_BY_SESSION, (session_key,)).fetchall()
            result = []
            for role, content, tool_name, call_id in rows:
                turn: dict[str, Any] = {"role": role, "content": content}
                if role == "tool":
                    if tool_name:
                        turn["tool_name"] = tool_name
                    if call_id:
                        turn["call_id"] = call_id
                result.append(turn)
            return result
        except Exception as e:  # noqa: BLE001
            _log.warning("history_store: get_turns failed (%s)", e)
            return list(self._fallback.get(session_key, []))

    def turn_count(self, session_key: str) -> int:
        """Return the number of turns for ``session_key``."""
        if not self._ready:
            return len(self._fallback.get(session_key, []))
        try:
            with self._conn() as conn:
                row = conn.execute(_COUNT_BY_SESSION, (session_key,)).fetchone()
            return row[0] if row else 0
        except Exception as e:  # noqa: BLE001
            _log.warning("history_store: turn_count failed (%s)", e)
            return len(self._fallback.get(session_key, []))

    def clear_session(self, session_key: str) -> None:
        """Delete all turns for one session."""
        if not self._ready:
            self._fallback.pop(session_key, None)
            return
        with self._lock:
            try:
                with self._conn() as conn:
                    conn.execute(_DELETE_BY_SESSION, (session_key,))
            except Exception as e:  # noqa: BLE001
                _log.warning("history_store: clear_session failed (%s)", e)
                self._fallback.pop(session_key, None)

    def clear_all(self) -> None:
        """Delete all turns (tests / reset)."""
        if not self._ready:
            self._fallback.clear()
            return
        with self._lock:
            try:
                with self._conn() as conn:
                    conn.execute(_DELETE_ALL)
            except Exception as e:  # noqa: BLE001
                _log.warning("history_store: clear_all failed (%s)", e)
                self._fallback.clear()

    # ── Internal ────────────────────────────────────────────────────

    def _append(
        self,
        session_key: str,
        *,
        role: str,
        content: str,
        tool_name: str | None = None,
        call_id: str | None = None,
    ) -> None:
        if not self._ready:
            turns = self._fallback.setdefault(session_key, [])
            turn: dict[str, Any] = {"role": role, "content": content}
            if role == "tool":
                if tool_name:
                    turn["tool_name"] = tool_name
                if call_id:
                    turn["call_id"] = call_id
            turns.append(turn)
            if self._max_turns and len(turns) > self._max_turns:
                del turns[: len(turns) - self._max_turns]
            return

        with self._lock:
            try:
                with self._conn() as conn:
                    conn.execute(
                        _INSERT,
                        (session_key, role, content, tool_name, call_id, _now_ms()),
                    )
                    if self._max_turns:
                        self._trim(conn, session_key)
            except Exception as e:  # noqa: BLE001
                _log.warning("history_store: append failed (%s)", e)
                # Fallback: keep in memory so the turn isn't lost.
                turns = self._fallback.setdefault(session_key, [])
                turns.append({"role": role, "content": content})

    def _trim(self, conn: sqlite3.Connection, session_key: str) -> None:
        """Delete oldest rows when max_turns is exceeded (within same conn)."""
        count = conn.execute(_COUNT_BY_SESSION, (session_key,)).fetchone()[0]
        excess = count - self._max_turns
        if excess <= 0:
            return
        conn.execute(
            """DELETE FROM channel_conversation_turns
               WHERE id IN (
                   SELECT id FROM channel_conversation_turns
                   WHERE session_key = ?
                   ORDER BY id ASC
                   LIMIT ?
               )""",
            (session_key, excess),
        )


__all__ = ["ConversationHistoryStore"]
