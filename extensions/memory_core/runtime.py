"""MemoryRuntime — sqlite-backed key/value store.

Phase 2 ships a simple SQLite-backed memory. Each row is
``(key TEXT PRIMARY KEY, value TEXT, category TEXT, updated_at TEXT)``.
Substring search is a SQL ``LIKE %q%``; semantic search via LanceDB
arrives in Phase 2.5.

Schema mirrors what OpenClaw's memory-core uses (sans the FTS5
index, which we'd add in Phase 2.5).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    updated_at TEXT NOT NULL,
    origin     TEXT NOT NULL DEFAULT 'untrusted',
    session_kind TEXT,
    observed_at TEXT,
    superseded_by TEXT,
    trigger_phrase TEXT,
    importance INTEGER,
    project    TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_category ON memory(category);
CREATE INDEX IF NOT EXISTS idx_memory_updated  ON memory(updated_at);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    key,
    value,
    category,
    content='memory'
);
CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
    INSERT INTO memory_fts(rowid, key, value, category) VALUES (new.rowid, new.key, new.value, new.category);
END;
CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, key, value, category) VALUES('delete', old.rowid, old.key, old.value, old.category);
END;
CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, key, value, category) VALUES('delete', old.rowid, old.key, old.value, old.category);
    INSERT INTO memory_fts(rowid, key, value, category) VALUES (new.rowid, new.key, new.value, new.category);
END;

CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    agent_id TEXT,
    description TEXT NOT NULL,
    trigger_keywords TEXT NOT NULL,
    channel_id TEXT,
    sender_id TEXT,
    expiry_days INTEGER NOT NULL DEFAULT 90,
    cooldown_hours INTEGER NOT NULL DEFAULT 24,
    max_fires INTEGER NOT NULL DEFAULT 3,
    fire_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_fired_at TEXT,
    state TEXT NOT NULL DEFAULT 'pending'
);
CREATE VIRTUAL TABLE IF NOT EXISTS intents_fts USING fts5(
    id,
    description,
    trigger_keywords,
    content='intents'
);
CREATE TRIGGER IF NOT EXISTS intents_ai AFTER INSERT ON intents BEGIN
    INSERT INTO intents_fts(rowid, id, description, trigger_keywords) VALUES (new.rowid, new.id, new.description, new.trigger_keywords);
END;
CREATE TRIGGER IF NOT EXISTS intents_ad AFTER DELETE ON intents BEGIN
    INSERT INTO intents_fts(intents_fts, rowid, id, description, trigger_keywords) VALUES('delete', old.rowid, old.id, old.description, old.trigger_keywords);
END;
CREATE TRIGGER IF NOT EXISTS intents_au AFTER UPDATE ON intents BEGIN
    INSERT INTO intents_fts(intents_fts, rowid, id, description, trigger_keywords) VALUES('delete', old.rowid, old.id, old.description, old.trigger_keywords);
    INSERT INTO intents_fts(rowid, id, description, trigger_keywords) VALUES (new.rowid, new.id, new.description, new.trigger_keywords);
END;
"""


def resolve_memory_db_path() -> Path:
    """Resolve the canonical SQLite database path for memory storage.

    Honors $JARVIS_DATA_DIR; defaults to ~/.jarvis/core/memory.sqlite.
    If the volume containing ~/.jarvis has inadequate disk space (< 50MB free,
    common on constrained Windows C: system drives), redirects to the workspace
    local data directory (e.g. E:/jarvis/.jarvis/core/memory.sqlite).
    If an existing database is present at ~/.jarvis and the redirected target does
    not yet exist, it is safely copied to preserve user memories.
    """
    import os
    import shutil

    env_dir = os.environ.get("JARVIS_DATA_DIR")
    if env_dir:
        return Path(env_dir) / "core" / "memory.sqlite"

    home_dir = Path.home() / ".jarvis"
    target_dir = home_dir

    def _is_space_safe(p: Path, min_bytes: int = 50 * 1024 * 1024) -> bool:
        try:
            curr = p
            while not curr.exists() and curr.parent != curr:
                curr = curr.parent
            return shutil.disk_usage(curr).free > min_bytes
        except Exception:
            return False

    if not _is_space_safe(home_dir):
        workspace_jarvis = Path(__file__).resolve().parents[2] / ".jarvis"
        if _is_space_safe(workspace_jarvis):
            target_dir = workspace_jarvis

    default_path = target_dir / "core" / "memory.sqlite"

    if target_dir != home_dir and not default_path.exists():
        home_db = home_dir / "core" / "memory.sqlite"
        if home_db.exists():
            try:
                default_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(home_db, default_path)
            except Exception:
                pass

    return default_path


# Common conversational stop words (OpenClaw query-expansion parity)
STOP_WORDS = {
    "a", "an", "the", "this", "that", "these", "those",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it", "they", "them",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "can", "may", "might",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into",
    "through", "during", "before", "after", "above", "below", "between", "under", "over",
    "and", "or", "but", "if", "then", "because", "as", "while", "when", "where",
    "what", "which", "who", "how", "why",
    "yesterday", "today", "tomorrow", "earlier", "later", "now", "recently",
    "tell", "give", "show", "find", "search", "get", "lookup", "please", "help",
    "thing", "something", "anything", "everything",
}


def extract_query_keywords(query: str) -> list[str]:
    """Extract high-signal keywords by filtering conversational stop words."""
    if not query:
        return []
    raw_tokens = [t.lower() for t in re.split(r"\W+", query.strip()) if t]
    filtered = [
        t for t in raw_tokens
        if len(t) >= 2 and t not in STOP_WORDS and not t.isdigit()
    ]
    return filtered if filtered else [t for t in raw_tokens if t]


def strip_memory_annotations(text: str) -> str:
    """Strip metadata comment tags from memory snippets before presentation."""
    if not text:
        return ""
    cleaned = re.sub(
        r"<!--\s*(?:trigger|importance|project|observed)\s*:[^>]*-->",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<!--\s*status\s*:[^>]*-->", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


class MemoryRuntime:
    """SQLite-backed key/value memory store.

    The runtime is a singleton per process (one SQLite file, one
    connection pool). Use ``MemoryRuntime.default()`` to get the
    process-wide instance; the data dir comes from
    ``$JARVIS_DATA_DIR`` or ``~/.jarvis``.
    """

    _default: MemoryRuntime | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = resolve_memory_db_path()
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # ``check_same_thread=False`` because plugins call us from
        # the async event loop. We serialize access via a lock.
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn_lock = threading.Lock()

        # Run schema migrations
        with self._conn_lock:
            cur = self._conn.execute("PRAGMA table_info(memory)")
            columns = {row["name"] for row in cur.fetchall()}
            if "origin" not in columns:
                self._conn.execute(
                    "ALTER TABLE memory ADD COLUMN origin TEXT NOT NULL DEFAULT 'untrusted'"
                )
            if "session_kind" not in columns:
                self._conn.execute("ALTER TABLE memory ADD COLUMN session_kind TEXT")
            if "observed_at" not in columns:
                self._conn.execute("ALTER TABLE memory ADD COLUMN observed_at TEXT")
            if "superseded_by" not in columns:
                self._conn.execute("ALTER TABLE memory ADD COLUMN superseded_by TEXT")
            if "trigger_phrase" not in columns:
                self._conn.execute("ALTER TABLE memory ADD COLUMN trigger_phrase TEXT")
            if "importance" not in columns:
                self._conn.execute("ALTER TABLE memory ADD COLUMN importance INTEGER")
            if "project" not in columns:
                self._conn.execute("ALTER TABLE memory ADD COLUMN project TEXT")

        # Rebuild index only if FTS table is empty while memory has entries
        try:
            with self._conn_lock:
                cur = self._conn.execute("SELECT count(*) as c FROM memory_fts")
                row = cur.fetchone()
                fts_count = row["c"] if row else 0
                if fts_count == 0:
                    cur = self._conn.execute("SELECT count(*) as c FROM memory")
                    mem_row = cur.fetchone()
                    if mem_row and mem_row["c"] > 0:
                        self._rebuild_index_locked()
        except sqlite3.OperationalError:
            pass

    @classmethod
    def default(cls) -> MemoryRuntime:
        with cls._lock:
            if cls._default is None:
                cls._default = cls(resolve_memory_db_path())
            return cls._default

    # ── CRUD ───────────────────────────────────────────────────────

    def set(
        self,
        key: str,
        value: str,
        category: str = "general",
        origin: str = "owner",
        session_kind: str | None = None,
        observed_at: str | None = None,
        superseded_by: str | None = None,
        project: str | None = None,
        trigger_phrase: str | None = None,
        importance: int | None = None,
    ) -> None:
        import datetime
        import re

        # Extract trigger_phrase, importance, and project from value if not explicitly passed
        if not trigger_phrase:
            trigger_match = re.search(r"<!--\s*trigger:\s*(.*?)\s*-->", value, re.IGNORECASE)
            if trigger_match:
                trigger_phrase = trigger_match.group(1).strip()

        if importance is None:
            importance_match = re.search(r"<!--\s*importance:\s*(\d+)\s*-->", value, re.IGNORECASE)
            if importance_match:
                try:
                    importance = int(importance_match.group(1).strip())
                except ValueError:
                    pass

        if not project:
            project_match = re.search(r"<!--\s*project:\s*(.*?)\s*-->", value, re.IGNORECASE)
            if project_match:
                project = project_match.group(1).strip()

        if not observed_at:
            obs_match = re.search(r"<!--\s*observed:\s*([0-9T: -]+)", value, re.IGNORECASE)
            if obs_match:
                observed_at = obs_match.group(1).strip()
            else:
                observed_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")

        status_match = re.search(r"status:\s*(active|superseded)", value, re.IGNORECASE)
        if status_match and status_match.group(1).lower() == "superseded" and not superseded_by:
            superseded_by = "superseded"

        with self._conn_lock:
            self._conn.execute(
                """
                INSERT INTO memory (
                    key, value, category, updated_at, origin, session_kind,
                    observed_at, superseded_by, trigger_phrase, importance, project
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    category=excluded.category,
                    updated_at=excluded.updated_at,
                    origin=excluded.origin,
                    session_kind=excluded.session_kind,
                    observed_at=excluded.observed_at,
                    superseded_by=excluded.superseded_by,
                    trigger_phrase=excluded.trigger_phrase,
                    importance=excluded.importance,
                    project=excluded.project
                """,
                (
                    key,
                    value,
                    category,
                    datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                    origin,
                    session_kind,
                    observed_at,
                    superseded_by,
                    trigger_phrase,
                    importance,
                    project,
                ),
            )
            self._rebuild_index_locked()

    def get(self, key: str) -> str | None:
        with self._conn_lock:
            row = self._conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def delete(self, key: str) -> bool:
        with self._conn_lock:
            cursor = self._conn.execute("DELETE FROM memory WHERE key = ?", (key,))
            self._rebuild_index_locked()
        return cursor.rowcount > 0

    def delete_file_chunks(self, filename: str) -> None:
        """Clear all chunks belonging to the given file (e.g. 'MEMORY.md')."""
        with self._conn_lock:
            # Delete keys like 'MEMORY.md:0', 'MEMORY.md:1', etc.
            self._conn.execute("DELETE FROM memory WHERE key LIKE ?", (f"{filename}:%",))
            self._rebuild_index_locked()

    # ── Intents ────────────────────────────────────────────────────

    def create_intent(
        self,
        description: str,
        trigger_keywords: str,
        agent_id: str | None = None,
        channel_id: str | None = None,
        sender_id: str | None = None,
        expiry_days: int = 90,
        cooldown_hours: int = 24,
        max_fires: int = 3,
    ) -> str:
        import datetime
        import uuid

        intent_id = str(uuid.uuid4())
        created_at = datetime.datetime.now(datetime.UTC).isoformat()

        with self._conn_lock:
            self._conn.execute(
                """
                INSERT INTO intents (
                    id, agent_id, description, trigger_keywords, channel_id, sender_id,
                    expiry_days, cooldown_hours, max_fires, fire_count, created_at, state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'armed')
                """,
                (
                    intent_id,
                    agent_id,
                    description,
                    trigger_keywords,
                    channel_id,
                    sender_id,
                    expiry_days,
                    cooldown_hours,
                    max_fires,
                    created_at,
                ),
            )

        return f"Created standing intent '{intent_id}' for condition: {description}"

    def list_intents(self, include_cancelled: bool = False) -> str:
        with self._conn_lock:
            if include_cancelled:
                cur = self._conn.execute(
                    "SELECT id, description, trigger_keywords, state, fire_count, max_fires, created_at "
                    "FROM intents ORDER BY created_at DESC"
                )
            else:
                cur = self._conn.execute(
                    "SELECT id, description, trigger_keywords, state, fire_count, max_fires, created_at "
                    "FROM intents WHERE state != 'cancelled' ORDER BY created_at DESC"
                )
            rows = cur.fetchall()

        if not rows:
            return "No standing intents found."

        lines = ["Standing intents:"]
        for r in rows:
            lines.append(
                f"  - [{r['id']}] ({r['state']}, {r['fire_count']}/{r['max_fires']} fires) {r['description']} (Triggers: {r['trigger_keywords']})"
            )
        return "\n".join(lines)

    def cancel_intent(self, intent_id: str) -> str:
        with self._conn_lock:
            cur = self._conn.execute("SELECT id FROM intents WHERE id = ?", (intent_id,))
            if not cur.fetchone():
                return f"Intent '{intent_id}' not found."
            self._conn.execute("UPDATE intents SET state = 'cancelled' WHERE id = ?", (intent_id,))
        return f"Cancelled intent '{intent_id}'"

    def sweep_intents(self, agent_id: str | None = None) -> None:
        """Maintain standing intent lifecycle (expiry and re-arming). Mirrors OpenClaw's maintainStandingIntentLifecycle."""
        import datetime

        now = datetime.datetime.now(datetime.UTC)
        with self._conn_lock:
            agent_filter = "AND agent_id = ?" if agent_id else ""
            params: list[Any] = [now.isoformat()]
            if agent_id:
                params.append(agent_id)

            self._conn.execute(
                f"""
                UPDATE intents
                SET state = 'expired'
                WHERE state IN ('armed', 'fired', 'pending')
                AND datetime(created_at, '+' || expiry_days || ' days') < ?
                {agent_filter}
                """,
                tuple(params),
            )

            self._conn.execute(
                f"""
                UPDATE intents
                SET state = 'armed'
                WHERE state = 'fired'
                AND fire_count < max_fires
                AND last_fired_at IS NOT NULL
                AND datetime(last_fired_at, '+' || cooldown_hours || ' hours') < ?
                {agent_filter}
                """,
                tuple(params),
            )


    def get_triggered_intents(
        self,
        inbound_message: str,
        agent_id: str | None = None,
        channel_id: str | None = None,
        sender_id: str | None = None,
    ) -> list[dict[str, Any]]:
        import datetime

        now = datetime.datetime.now(datetime.UTC)
        triggered = []

        with self._conn_lock:
            # First, check expiries for armed and fired intents
            self._conn.execute(
                """
                UPDATE intents
                SET state = 'expired'
                WHERE state IN ('armed', 'fired', 'pending')
                AND datetime(created_at, '+' || expiry_days || ' days') < ?
                """,
                (now.isoformat(),),
            )

            # Check cooldowns to rearm fired intents
            self._conn.execute(
                """
                UPDATE intents
                SET state = 'armed'
                WHERE state = 'fired'
                AND last_fired_at IS NOT NULL
                AND datetime(last_fired_at, '+' || cooldown_hours || ' hours') < ?
                """,
                (now.isoformat(),),
            )

            # Use FTS to find candidate armed intents matching inbound_message
            cur = self._conn.execute(
                """
                SELECT rowid, id, description, trigger_keywords, channel_id, sender_id, agent_id, fire_count, max_fires, created_at
                FROM intents
                WHERE state = 'armed'
                """
            )
            candidates = cur.fetchall()

            to_fire = []
            for row in candidates:
                keywords = [k.strip().lower() for k in row["trigger_keywords"].split(",") if k.strip()]
                msg_lower = inbound_message.lower()

                matches = any(re.search(r"\b" + re.escape(k) + r"\b", msg_lower) for k in keywords)
                if not matches:
                    continue

                # Verify scoping
                if row["agent_id"] and agent_id and row["agent_id"] != agent_id:
                    continue
                if row["channel_id"] and channel_id and row["channel_id"] != channel_id:
                    continue
                if row["sender_id"] and sender_id and row["sender_id"] != sender_id:
                    continue

                to_fire.append(row)
                triggered.append(dict(row))

                if len(to_fire) >= 256:
                    break

            # State transitions for fired intents in one transaction
            for row in to_fire:
                new_fire_count = row["fire_count"] + 1
                new_state = "done" if new_fire_count >= row["max_fires"] else "fired"
                self._conn.execute(
                    """
                    UPDATE intents
                    SET fire_count = ?, last_fired_at = ?, state = ?
                    WHERE id = ?
                    """,
                    (new_fire_count, now.isoformat(), new_state, row["id"]),
                )

        return triggered

    # ── Read / Search ──────────────────────────────────────────────

    def count(self) -> int:
        with self._conn_lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM memory").fetchone()
        return int(row["n"])

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn_lock:
            rows = self._conn.execute(
                "SELECT key, value, category, project FROM memory ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_substring(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """SQL ``LIKE %q%`` search across both key and value columns."""
        like = f"%{query}%"
        with self._conn_lock:
            rows = self._conn.execute(
                """
                SELECT key, value, category, project FROM memory
                WHERE key LIKE ? OR value LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_text(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search the FTS index using a phrase-oriented query."""
        if not query.strip():
            return []

        quoted = f'"{query.replace(chr(34), chr(34) * 2).strip()}"'
        with self._conn_lock:
            rows = self._conn.execute(
                """
                SELECT m.key, m.value, m.category, m.project
                FROM memory_fts f
                JOIN memory m ON f.rowid = m.rowid
                WHERE memory_fts MATCH ?
                ORDER BY bm25(memory_fts)
                LIMIT ?
                """,
                (quoted, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_ranked(
        self,
        query: str,
        limit: int = 20,
        min_score: float = 0.0,
        active_projects: list[str] | None = None,
        corpus: str = "memory",
        citations: bool = False,
    ) -> list[dict[str, Any]]:
        """Search memory with OpenClaw hybrid scoring: relevance x recency decay x importance x project.

        - Recency decay: 30-day half-life on dated notes (e.g. YYYY-MM-DD.md). Evergreen for MEMORY.md/USER.md.
        - Importance multiplier: 1-10 scale (1.0 + (importance - 5) * 0.1). Neutral if unset.
        - Project scoping: 1.25x boost for active repo keys, 0.8x demotion for other repos, neutral if untagged.
        """
        import datetime
        import math

        if not query.strip():
            return []

        candidates: dict[str, dict[str, Any]] = {}

        # 1. Candidate retrieval via FTS5 with query expansion
        try:
            tokens = extract_query_keywords(query)
            fts_query = " OR ".join(f'"{t}"' for t in tokens) if tokens else f'"{query.strip()}"'
            with self._conn_lock:
                rows = self._conn.execute(
                    """
                    SELECT m.key, m.value, m.category, m.updated_at, m.origin,
                           m.session_kind, m.observed_at, m.superseded_by,
                           m.trigger_phrase, m.importance, m.project,
                           bm25(memory_fts) as rank
                    FROM memory_fts f
                    JOIN memory m ON f.rowid = m.rowid
                    WHERE memory_fts MATCH ?
                    LIMIT ?
                    """,
                    (fts_query, max(limit * 4, 100)),
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    bm25_val = float(d.get("rank", 0.0))
                    # bm25 is negative in sqlite (more negative = better match)
                    base_score = 1.0 / (1.0 + max(0.0, abs(bm25_val)))
                    d["base_score"] = base_score
                    candidates[d["key"]] = d
        except sqlite3.OperationalError:
            pass

        # 2. Substring recall fallback via LIKE
        like = f"%{query.strip()}%"
        with self._conn_lock:
            rows = self._conn.execute(
                """
                SELECT key, value, category, updated_at, origin,
                       session_kind, observed_at, superseded_by,
                       trigger_phrase, importance, project
                FROM memory
                WHERE key LIKE ? OR value LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like, like, max(limit * 2, 50)),
            ).fetchall()
            for r in rows:
                d = dict(r)
                k = d["key"]
                if k not in candidates:
                    d["base_score"] = 0.5
                    candidates[k] = d
                else:
                    candidates[k]["base_score"] = max(candidates[k].get("base_score", 0.5), 0.7)

        # 3. Score candidates with recency, importance, project signals
        now = datetime.datetime.now(datetime.UTC)
        results: list[dict[str, Any]] = []

        for item in candidates.values():
            key = item["key"]
            val = item["value"]

            # Corpus filter: if corpus == "memory", exclude session transcripts
            if corpus == "memory" and key.startswith("sessions/"):
                continue
            elif corpus == "sessions" and not key.startswith("sessions/"):
                continue

            base_score = float(item.get("base_score", 0.5))

            # Recency decay calculation: 30-day half-life for dated notes
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", key) or re.search(
                r"(\d{4}-\d{2}-\d{2})", val[:100]
            )
            recency_decay = 1.0
            if date_match and not key.startswith("MEMORY.md") and not key.startswith("USER.md"):
                try:
                    note_date = datetime.datetime.strptime(
                        date_match.group(1), "%Y-%m-%d"
                    ).replace(tzinfo=datetime.UTC)
                    delta_days = (now - note_date).total_seconds() / 86400.0
                    if delta_days > 0:
                        recency_decay = math.pow(2.0, -(delta_days / 30.0))
                except Exception:
                    recency_decay = 1.0

            # Importance multiplier: 1 to 10 scale
            importance = item.get("importance")
            if importance is not None:
                importance_mult = max(0.2, 1.0 + (int(importance) - 5) * 0.1)
            else:
                importance_mult = 1.0

            # Project scoping
            project = item.get("project")
            project_factor = 1.0
            if active_projects is not None:
                if project:
                    if project in active_projects:
                        project_factor = 1.25
                    else:
                        project_factor = 0.8
                else:
                    project_factor = 1.0

            final_score = base_score * recency_decay * importance_mult * project_factor
            if final_score < min_score:
                continue

            cleaned_val = strip_memory_annotations(val)
            if citations:
                if ":" in key and any(ch.isdigit() for ch in key.split(":")[-1]):
                    parts = key.rsplit(":", 1)
                    citation = f"{parts[0]}#L{parts[1]}"
                else:
                    citation = key
                item["citation"] = citation
                item["value"] = f"{cleaned_val}\n\nSource: {citation}"
            else:
                item["value"] = cleaned_val

            item["score"] = round(final_score, 4)
            item["recency_decay"] = round(recency_decay, 4)
            item["importance_mult"] = round(importance_mult, 4)
            item["project_factor"] = round(project_factor, 4)
            results.append(item)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_triggered_memory(
        self, message: str, active_projects: list[str] | None = None, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Find memory entries with a trigger_phrase that matches the message.
        Excludes 'untrusted' and 'system' origins.
        """
        message_lower = message.lower()
        with self._conn_lock:
            # Fetch all curated triggers
            rows = self._conn.execute(
                """
                SELECT key, value, category, trigger_phrase, project
                FROM memory
                WHERE trigger_phrase IS NOT NULL
                AND origin NOT IN ('untrusted', 'system')
                AND key NOT LIKE 'memory/%'
                ORDER BY updated_at DESC
                """
            ).fetchall()

        hits = []
        for r in rows:
            trigger = r["trigger_phrase"]
            project = r["project"]

            # Check project scope if specified
            if project and active_projects is not None:
                if project not in active_projects:
                    continue

            if trigger:
                keywords = [k.strip() for k in trigger.split(",") if k.strip()]
                if any(k.lower() in message_lower for k in keywords):
                    hits.append(dict(r))
                    if len(hits) >= limit:
                        break
        return hits

    def _rebuild_index_locked(self) -> None:
        try:
            self._conn.execute("DELETE FROM memory_fts")
            self._conn.execute(
                """
                INSERT INTO memory_fts(rowid, key, value, category)
                SELECT rowid, key, value, category FROM memory
                """
            )
        except sqlite3.OperationalError as e:
            import logging

            logging.getLogger("jarvis.memory_core").warning(
                "Failed to rebuild FTS index (possibly low disk space): %s", e
            )

    def rebuild_index(self) -> None:
        """Rebuild the FTS index from the canonical memory table."""
        with self._conn_lock:
            self._rebuild_index_locked()

    # ── Bulk import (used by the doctor apply path) ────────────────

    def bulk_set(self, entries: list[dict[str, str]]) -> int:
        """Insert many rows in one transaction. Returns rows inserted."""
        n = 0
        with self._conn_lock:
            for e in entries:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO memory (key, value, category, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        e["key"],
                        e["value"],
                        e.get("category", "general"),
                        e.get("updated_at", ""),
                    ),
                )
                n += 1
            self._rebuild_index_locked()
        return n

    def reset_index(self) -> int:
        """Clear the derived SQLite memory and FTS tables without touching raw markdown files."""
        with self._conn_lock:
            cur = self._conn.execute("SELECT count(*) as c FROM memory")
            count = int(cur.fetchone()["c"])
            self._conn.execute("DELETE FROM memory")
            self._conn.execute("DELETE FROM memory_fts")
            return count

    def forget(
        self,
        key: str | None = None,
        query: str | None = None,
        workspace_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Forget memory entries by key or query.

        Synchronously deletes from SQLite (memory + memory_fts) and
        rewrites MEMORY.md and USER.md on disk in lockstep.
        """
        deleted_keys: list[str] = []
        with self._conn_lock:
            if key:
                cur = self._conn.execute(
                    "SELECT key FROM memory WHERE key = ? OR key LIKE ?",
                    (key, f"{key}:%"),
                )
                rows = cur.fetchall()
                for r in rows:
                    deleted_keys.append(str(r["key"]))
                if not deleted_keys:
                    deleted_keys.append(key)
            elif query:
                like_q = f"%{query.strip()}%"
                cur = self._conn.execute(
                    "SELECT key FROM memory WHERE key LIKE ? OR value LIKE ?",
                    (like_q, like_q),
                )
                rows = cur.fetchall()
                for r in rows:
                    deleted_keys.append(str(r["key"]))

            for k in deleted_keys:
                self._conn.execute("DELETE FROM memory WHERE key = ?", (k,))
            if deleted_keys:
                self._rebuild_index_locked()

        # Synchronously rewrite workspace markdown files
        removed_md_lines = 0
        if workspace_dir:
            ws = Path(workspace_dir)
            # 1. MEMORY.md
            mem_file = ws / "MEMORY.md"
            if mem_file.is_file():
                try:
                    lines = mem_file.read_text(encoding="utf-8").splitlines()
                    new_lines: list[str] = []
                    for line in lines:
                        match = False
                        for k in deleted_keys:
                            if k.lower() in line.lower():
                                match = True
                                break
                        if query and query.lower() in line.lower():
                            match = True
                        if match:
                            removed_md_lines += 1
                        else:
                            new_lines.append(line)
                    mem_file.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
                except Exception:
                    pass

            # 2. USER.md
            user_file = ws / "USER.md"
            if user_file.is_file():
                try:
                    lines = user_file.read_text(encoding="utf-8").splitlines()
                    new_lines = []
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        match = False
                        for k in deleted_keys:
                            clean_k = k.split(":")[-1].lower()
                            if f"- {clean_k}:" in line.lower() or f"- {k.lower()}:" in line.lower():
                                match = True
                                break
                        if query and query.lower() in line.lower() and line.strip().startswith("- "):
                            match = True
                        if match:
                            removed_md_lines += 1
                            # Also remove preceding observation comment if present
                            if new_lines and "<!-- observed:" in new_lines[-1]:
                                new_lines.pop()
                                if new_lines and not new_lines[-1].strip():
                                    new_lines.pop()
                        else:
                            new_lines.append(line)
                        i += 1
                    user_file.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
                except Exception:
                    pass

        return {
            "status": "ok",
            "forgotten_count": len(deleted_keys),
            "keys": deleted_keys,
            "removed_markdown_lines": removed_md_lines,
        }

    def close(self) -> None:
        with self._conn_lock:
            self._conn.close()


__all__ = [
    "MemoryRuntime",
    "extract_query_keywords",
    "strip_memory_annotations",
    "resolve_memory_db_path",
]


# Sentinel: touch the imported name so ruff doesn't flag unused-import.
_ = json
