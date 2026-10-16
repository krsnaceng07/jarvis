"""Logbook SQLite store: frames on disk, everything else in one plugin-owned DB.

Mirrors OpenClaw's ``extensions/logbook/src/store.ts``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Optional, Sequence

from .logbook_types import (
    LogbookBatch,
    LogbookBatchStatus,
    LogbookCard,
    LogbookCardDraft,
    LogbookDayStats,
    LogbookDistraction,
    LogbookFrame,
    LogbookObservation,
)

LOGBOOK_SCHEMA_VERSION = 1
LOGBOOK_SQLITE_BUSY_TIMEOUT_MS = 5000

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'error')),
  error TEXT,
  frame_count INTEGER NOT NULL DEFAULT 0,
  model TEXT,
  created_ms INTEGER NOT NULL,
  updated_ms INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_logbook_batches_day ON batches (day, start_ms);
CREATE TABLE IF NOT EXISTS frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  captured_at_ms INTEGER NOT NULL,
  day TEXT NOT NULL,
  path TEXT NOT NULL,
  screen_index INTEGER NOT NULL DEFAULT 0,
  width INTEGER,
  height INTEGER,
  byte_size INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL,
  idle INTEGER NOT NULL DEFAULT 0 CHECK (idle IN (0, 1)),
  batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_logbook_frames_day ON frames (day, captured_at_ms);
CREATE INDEX IF NOT EXISTS idx_logbook_frames_captured_at ON frames (captured_at_ms);
CREATE INDEX IF NOT EXISTS idx_logbook_frames_unbatched ON frames (batch_id) WHERE batch_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_logbook_frames_batch ON frames (batch_id, captured_at_ms) WHERE batch_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_logbook_observations_day ON observations (day, start_ms);
CREATE INDEX IF NOT EXISTS idx_logbook_observations_batch ON observations (batch_id);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'other',
  app_primary TEXT,
  app_secondary TEXT,
  distractions TEXT NOT NULL DEFAULT '[]',
  keyframe_id INTEGER REFERENCES frames(id) ON DELETE SET NULL,
  updated_ms INTEGER NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_logbook_cards_day ON cards (day, start_ms);
CREATE INDEX IF NOT EXISTS idx_logbook_cards_keyframe ON cards (keyframe_id) WHERE keyframe_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS standups (
  day TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  updated_ms INTEGER NOT NULL
) STRICT;
"""

EXPECTED_INDEXES = [
    ("idx_logbook_batches_day", "CREATE INDEX IF NOT EXISTS idx_logbook_batches_day ON batches (day, start_ms);"),
    ("idx_logbook_frames_day", "CREATE INDEX IF NOT EXISTS idx_logbook_frames_day ON frames (day, captured_at_ms);"),
    ("idx_logbook_frames_captured_at", "CREATE INDEX IF NOT EXISTS idx_logbook_frames_captured_at ON frames (captured_at_ms);"),
    ("idx_logbook_frames_unbatched", "CREATE INDEX IF NOT EXISTS idx_logbook_frames_unbatched ON frames (batch_id) WHERE batch_id IS NULL;"),
    ("idx_logbook_frames_batch", "CREATE INDEX IF NOT EXISTS idx_logbook_frames_batch ON frames (batch_id, captured_at_ms) WHERE batch_id IS NOT NULL;"),
    ("idx_logbook_observations_day", "CREATE INDEX IF NOT EXISTS idx_logbook_observations_day ON observations (day, start_ms);"),
    ("idx_logbook_observations_batch", "CREATE INDEX IF NOT EXISTS idx_logbook_observations_batch ON observations (batch_id);"),
    ("idx_logbook_cards_day", "CREATE INDEX IF NOT EXISTS idx_logbook_cards_day ON cards (day, start_ms);"),
    ("idx_logbook_cards_keyframe", "CREATE INDEX IF NOT EXISTS idx_logbook_cards_keyframe ON cards (keyframe_id) WHERE keyframe_id IS NOT NULL;"),
]


def day_key_for(ms: int) -> str:
    """Format an epoch-ms timestamp as a local-time YYYY-MM-DD day key."""
    import datetime

    dt = datetime.datetime.fromtimestamp(ms / 1000.0)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def _parse_distractions(raw: Any) -> list[LogbookDistraction]:
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        out: list[LogbookDistraction] = []
        for entry in parsed:
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("title"), str)
                and isinstance(entry.get("startMs"), (int, float))
                and isinstance(entry.get("endMs"), (int, float))
            ):
                out.append({
                    "title": entry["title"],
                    "startMs": int(entry["startMs"]),
                    "endMs": int(entry["endMs"]),
                })
        return out
    except Exception:
        return []


def _to_frame(row: sqlite3.Row) -> LogbookFrame:
    return {
        "id": row["id"],
        "capturedAtMs": row["captured_at_ms"],
        "day": row["day"],
        "path": row["path"],
        "screenIndex": row["screen_index"],
        "width": row["width"],
        "height": row["height"],
        "byteSize": row["byte_size"],
        "idle": bool(row["idle"]),
    }


def _to_batch(row: sqlite3.Row) -> LogbookBatch:
    return {
        "id": row["id"],
        "day": row["day"],
        "startMs": row["start_ms"],
        "endMs": row["end_ms"],
        "status": row["status"],
        "error": row["error"],
        "frameCount": row["frame_count"],
        "model": row["model"],
    }


def _to_card(row: sqlite3.Row) -> LogbookCard:
    return {
        "id": row["id"],
        "day": row["day"],
        "startMs": row["start_ms"],
        "endMs": row["end_ms"],
        "title": row["title"],
        "summary": row["summary"],
        "detail": row["detail"],
        "category": row["category"],
        "appPrimary": row["app_primary"],
        "appSecondary": row["app_secondary"],
        "distractions": _parse_distractions(row["distractions"]),
        "keyframeId": row["keyframe_id"],
    }


class LogbookStore:
    """SQLite-backed persistent store for Logbook frames, batches, observations, cards, and standups."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = str(Path(data_dir).resolve())
        os.makedirs(self.data_dir, exist_ok=True)
        try:
            os.chmod(self.data_dir, 0o700)
        except OSError:
            pass

        self.frames_dir = os.path.join(self.data_dir, "frames")
        os.makedirs(self.frames_dir, exist_ok=True)
        try:
            os.chmod(self.frames_dir, 0o700)
        except OSError:
            pass

        db_path = os.path.join(self.data_dir, "logbook.sqlite")
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        try:
            os.chmod(db_path, 0o600)
        except OSError:
            pass

        # Configure pragmas
        self.db.execute("PRAGMA foreign_keys = ON;")
        self.db.execute(f"PRAGMA busy_timeout = {LOGBOOK_SQLITE_BUSY_TIMEOUT_MS};")
        self.db.execute("PRAGMA journal_mode = WAL;")
        self.db.execute("PRAGMA synchronous = NORMAL;")

        # Check schema version
        cur = self.db.execute("PRAGMA user_version;")
        row = cur.fetchone()
        schema_version = int(row[0]) if row else 0

        if schema_version > LOGBOOK_SCHEMA_VERSION:
            self.db.close()
            raise ValueError(
                f"Logbook database uses newer schema version {schema_version}; this build supports {LOGBOOK_SCHEMA_VERSION}"
            )

        # Check if tables exist and whether any are not STRICT (legacy migration)
        self._ensure_schema(schema_version)

    @property
    def framesDir(self) -> str:
        return self.frames_dir

    def _ensure_schema(self, schema_version: int) -> None:
        cur = self.db.execute(
            "SELECT name, strict FROM pragma_table_list WHERE schema = 'main' AND type = 'table' AND name NOT LIKE 'sqlite_%';"
        )
        existing_tables = {r["name"]: r["strict"] for r in cur.fetchall()}

        non_strict_tables = [name for name, strict in existing_tables.items() if not strict]
        if non_strict_tables:
            # Need to migrate non-strict tables to strict
            self._migrate_to_strict(non_strict_tables)

        # Execute base schema and ensure indexes
        self.db.executescript(SCHEMA)

        # Ensure all expected indexes exist even on reopen
        for idx_name, idx_sql in EXPECTED_INDEXES:
            self.db.execute(idx_sql)

        if schema_version < LOGBOOK_SCHEMA_VERSION:
            self.db.execute(f"PRAGMA user_version = {LOGBOOK_SCHEMA_VERSION};")
            self.db.commit()

    def _migrate_to_strict(self, non_strict_tables: list[str]) -> None:
        """Migrate legacy tables to STRICT mode, rolling back if stored data violates strict types."""
        # We perform migration in a transaction
        table_ddl_map = {
            "batches": (
                "CREATE TABLE batches_strict ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  day TEXT NOT NULL,"
                "  start_ms INTEGER NOT NULL,"
                "  end_ms INTEGER NOT NULL,"
                "  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'error')),"
                "  error TEXT,"
                "  frame_count INTEGER NOT NULL DEFAULT 0,"
                "  model TEXT,"
                "  created_ms INTEGER NOT NULL,"
                "  updated_ms INTEGER NOT NULL"
                ") STRICT;",
                ["id", "day", "start_ms", "end_ms", "status", "error", "frame_count", "model", "created_ms", "updated_ms"],
            ),
            "frames": (
                "CREATE TABLE frames_strict ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  captured_at_ms INTEGER NOT NULL,"
                "  day TEXT NOT NULL,"
                "  path TEXT NOT NULL,"
                "  screen_index INTEGER NOT NULL DEFAULT 0,"
                "  width INTEGER,"
                "  height INTEGER,"
                "  byte_size INTEGER NOT NULL DEFAULT 0,"
                "  content_hash TEXT NOT NULL,"
                "  idle INTEGER NOT NULL DEFAULT 0 CHECK (idle IN (0, 1)),"
                "  batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL"
                ") STRICT;",
                ["id", "captured_at_ms", "day", "path", "screen_index", "width", "height", "byte_size", "content_hash", "idle", "batch_id"],
            ),
            "observations": (
                "CREATE TABLE observations_strict ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,"
                "  day TEXT NOT NULL,"
                "  start_ms INTEGER NOT NULL,"
                "  end_ms INTEGER NOT NULL,"
                "  text TEXT NOT NULL"
                ") STRICT;",
                ["id", "batch_id", "day", "start_ms", "end_ms", "text"],
            ),
            "cards": (
                "CREATE TABLE cards_strict ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  day TEXT NOT NULL,"
                "  start_ms INTEGER NOT NULL,"
                "  end_ms INTEGER NOT NULL,"
                "  title TEXT NOT NULL,"
                "  summary TEXT NOT NULL,"
                "  detail TEXT NOT NULL DEFAULT '',"
                "  category TEXT NOT NULL DEFAULT 'other',"
                "  app_primary TEXT,"
                "  app_secondary TEXT,"
                "  distractions TEXT NOT NULL DEFAULT '[]',"
                "  keyframe_id INTEGER REFERENCES frames(id) ON DELETE SET NULL,"
                "  updated_ms INTEGER NOT NULL"
                ") STRICT;",
                ["id", "day", "start_ms", "end_ms", "title", "summary", "detail", "category", "app_primary", "app_secondary", "distractions", "keyframe_id", "updated_ms"],
            ),
            "standups": (
                "CREATE TABLE standups_strict ("
                "  day TEXT PRIMARY KEY,"
                "  text TEXT NOT NULL,"
                "  updated_ms INTEGER NOT NULL"
                ") STRICT;",
                ["day", "text", "updated_ms"],
            ),
        }

        # Disable foreign keys during table recreation so ON DELETE SET NULL / CASCADE don't clear referenced rows
        self.db.execute("PRAGMA foreign_keys = OFF;")
        try:
            self.db.execute("BEGIN IMMEDIATE;")
            for table_name in non_strict_tables:
                if table_name not in table_ddl_map:
                    continue
                ddl, cols = table_ddl_map[table_name]
                strict_table = f"{table_name}_strict"
                self.db.execute(ddl)
                cols_str = ", ".join(cols)
                # Test whether copying data into strict table succeeds
                try:
                    self.db.execute(f"INSERT INTO {strict_table} ({cols_str}) SELECT {cols_str} FROM {table_name};")
                except Exception as exc:
                    self.db.execute("ROLLBACK;")
                    raise ValueError(f"Failed migrating SQLite table {table_name} to STRICT: {exc}") from exc
                self.db.execute(f"DROP TABLE {table_name};")
                self.db.execute(f"ALTER TABLE {strict_table} RENAME TO {table_name};")
            self.db.commit()
        except Exception:
            try:
                self.db.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            self.db.execute("PRAGMA foreign_keys = ON;")

    def close(self) -> None:
        """Close SQLite database connection."""
        try:
            self.db.close()
        except Exception:
            pass

    def frame_file_path(self, day: str, captured_at_ms: int) -> str:
        """Return target file path for a frame JPEG."""
        return os.path.join(self.frames_dir, day, f"{captured_at_ms}.jpg")

    frameFilePath = frame_file_path

    def insert_frame(self, params: dict[str, Any] | None = None, **kwargs: Any) -> int:
        """Insert a frame record and return its rowid.

        Mirrors OpenClaw's ``insertFrame``.
        """
        opts = {**(params or {}), **kwargs}
        captured_at_ms: int = opts.get("capturedAtMs") or opts.get("captured_at_ms") or 0
        day: str = opts.get("day") or ""
        path: str = opts.get("path") or ""
        screen_index: int = opts.get("screenIndex") if opts.get("screenIndex") is not None else opts.get("screen_index", 0)
        width: Optional[int] = opts.get("width")
        height: Optional[int] = opts.get("height")
        byte_size: int = opts.get("byteSize") if opts.get("byteSize") is not None else opts.get("byte_size", 0)
        content_hash: str = opts.get("contentHash") or opts.get("content_hash") or ""
        idle: int = 1 if opts.get("idle") else 0

        with self.db:
            cur = self.db.execute(
                """
                INSERT INTO frames (captured_at_ms, day, path, screen_index, width, height, byte_size, content_hash, idle, batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL);
                """,
                (captured_at_ms, day, path, screen_index, width, height, byte_size, content_hash, idle),
            )
            return int(cur.lastrowid)

    insertFrame = insert_frame

    def last_frame(self) -> Optional[dict[str, Any]]:
        """Return the most recently captured frame timestamp and hash."""
        cur = self.db.execute(
            "SELECT captured_at_ms, content_hash FROM frames ORDER BY captured_at_ms DESC, id DESC LIMIT 1;"
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"capturedAtMs": row["captured_at_ms"], "contentHash": row["content_hash"]}

    lastFrame = last_frame

    def unbatched_active_frames(self, limit: int) -> list[LogbookFrame]:
        """Return active unbatched frames up to limit ordered by capturedAtMs."""
        cur = self.db.execute(
            "SELECT id, captured_at_ms, day, path, screen_index, width, height, byte_size, idle FROM frames "
            "WHERE batch_id IS NULL AND idle = 0 ORDER BY captured_at_ms ASC, id ASC LIMIT ?;",
            (limit,),
        )
        return [_to_frame(r) for r in cur.fetchall()]

    unbatchedActiveFrames = unbatched_active_frames

    def count_unbatched_active_frames(self) -> int:
        """Count active unbatched frames."""
        cur = self.db.execute(
            "SELECT COUNT(*) AS count FROM frames WHERE batch_id IS NULL AND idle = 0;"
        )
        row = cur.fetchone()
        return int(row["count"]) if row else 0

    countUnbatchedActiveFrames = count_unbatched_active_frames

    def frame_by_id(self, frame_id: int) -> Optional[LogbookFrame]:
        """Return frame by id or None."""
        cur = self.db.execute(
            "SELECT id, captured_at_ms, day, path, screen_index, width, height, byte_size, idle FROM frames WHERE id = ?;",
            (frame_id,),
        )
        row = cur.fetchone()
        return _to_frame(row) if row else None

    frameById = frame_by_id

    def frames_in_range(self, start_ms: int, end_ms: int) -> list[LogbookFrame]:
        """Return frames in [start_ms, end_ms)."""
        cur = self.db.execute(
            "SELECT id, captured_at_ms, day, path, screen_index, width, height, byte_size, idle FROM frames "
            "WHERE captured_at_ms >= ? AND captured_at_ms < ? ORDER BY captured_at_ms ASC, id ASC;",
            (start_ms, end_ms),
        )
        return [_to_frame(r) for r in cur.fetchall()]

    framesInRange = frames_in_range

    def create_batch(self, params: dict[str, Any] | None = None, **kwargs: Any) -> int:
        """Create a new batch and assign frames atomically.

        Rolls back if any frame is missing or already batched.
        """
        opts = {**(params or {}), **kwargs}
        day: str = opts.get("day") or ""
        start_ms: int = opts.get("startMs") or opts.get("start_ms") or 0
        end_ms: int = opts.get("endMs") or opts.get("end_ms") or 0
        frame_ids: Sequence[int] = opts.get("frameIds") or opts.get("frame_ids") or []

        if not frame_ids:
            raise ValueError("Logbook batch requires at least one frame")

        now = int(time.time() * 1000)
        self.db.execute("BEGIN IMMEDIATE;")
        try:
            cur = self.db.execute(
                """
                INSERT INTO batches (day, start_ms, end_ms, status, error, frame_count, model, created_ms, updated_ms)
                VALUES (?, ?, ?, 'pending', NULL, ?, NULL, ?, ?);
                """,
                (day, start_ms, end_ms, len(frame_ids), now, now),
            )
            batch_id = int(cur.lastrowid)

            for frame_id in frame_ids:
                update_cur = self.db.execute(
                    "UPDATE frames SET batch_id = ? WHERE id = ? AND batch_id IS NULL;",
                    (batch_id, frame_id),
                )
                if update_cur.rowcount != 1:
                    raise ValueError(f"Logbook frame {frame_id} is missing or already batched")

            self.db.commit()
            return batch_id
        except Exception:
            self.db.execute("ROLLBACK;")
            raise

    createBatch = create_batch

    def set_batch_status(
        self,
        batch_id: int,
        status: LogbookBatchStatus,
        error: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Update batch status, error, and model."""
        now = int(time.time() * 1000)
        with self.db:
            self.db.execute(
                """
                UPDATE batches
                SET status = ?, error = ?, model = COALESCE(?, model), updated_ms = ?
                WHERE id = ?;
                """,
                (status, error, model, now, batch_id),
            )

    setBatchStatus = set_batch_status

    def latest_batch(self) -> Optional[LogbookBatch]:
        """Return the most recent batch or None."""
        cur = self.db.execute("SELECT * FROM batches ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        return _to_batch(row) if row else None

    latestBatch = latest_batch

    def reset_running_batches(self) -> None:
        """Requeue batches stuck in 'running' to 'pending' after restart."""
        now = int(time.time() * 1000)
        with self.db:
            self.db.execute(
                "UPDATE batches SET status = 'pending', updated_ms = ? WHERE status = 'running';",
                (now,),
            )

    resetRunningBatches = reset_running_batches

    def reset_error_batches(self) -> int:
        """Requeue failed batches for retry and return number of batches requeued."""
        now = int(time.time() * 1000)
        with self.db:
            cur = self.db.execute(
                "UPDATE batches SET status = 'pending', error = NULL, updated_ms = ? WHERE status = 'error';",
                (now,),
            )
            return int(cur.rowcount)

    resetErrorBatches = reset_error_batches

    def next_pending_batch(self) -> Optional[LogbookBatch]:
        """Return the next pending batch in chronological order."""
        cur = self.db.execute(
            "SELECT * FROM batches WHERE status = 'pending' ORDER BY start_ms ASC, id ASC LIMIT 1;"
        )
        row = cur.fetchone()
        return _to_batch(row) if row else None

    nextPendingBatch = next_pending_batch

    def batch_frames(self, batch_id: int) -> list[LogbookFrame]:
        """Return all frames assigned to a batch."""
        cur = self.db.execute(
            "SELECT id, captured_at_ms, day, path, screen_index, width, height, byte_size, idle "
            "FROM frames WHERE batch_id = ? ORDER BY captured_at_ms ASC, id ASC;",
            (batch_id,),
        )
        return [_to_frame(r) for r in cur.fetchall()]

    batchFrames = batch_frames

    def replace_observations(
        self,
        batch_id: int,
        day: str,
        segments: Sequence[dict[str, Any]],
    ) -> None:
        """Replace observations for a batch atomically."""
        self.db.execute("BEGIN IMMEDIATE;")
        try:
            # Check foreign key reference
            cur = self.db.execute("SELECT id FROM batches WHERE id = ?;", (batch_id,))
            if not cur.fetchone():
                raise ValueError(f"Batch {batch_id} does not exist")

            self.db.execute("DELETE FROM observations WHERE batch_id = ?;", (batch_id,))
            for segment in segments:
                start_ms = segment.get("startMs") or segment.get("start_ms") or 0
                end_ms = segment.get("endMs") or segment.get("end_ms") or 0
                text = segment.get("text") or ""
                self.db.execute(
                    "INSERT INTO observations (batch_id, day, start_ms, end_ms, text) VALUES (?, ?, ?, ?, ?);",
                    (batch_id, day, start_ms, end_ms, text),
                )
            self.db.commit()
        except Exception:
            self.db.execute("ROLLBACK;")
            raise

    replaceObservations = replace_observations

    def observations_in_range(
        self,
        day: str,
        start_ms: int,
        end_ms: int,
        tail_limit: Optional[int] = None,
    ) -> list[LogbookObservation]:
        """Query observations overlapping [start_ms, end_ms) for a day."""
        direction = "DESC" if tail_limit is not None else "ASC"
        query = (
            f"SELECT id, batch_id, day, start_ms, end_ms, text FROM observations "
            f"WHERE day = ? AND end_ms > ? AND start_ms < ? "
            f"ORDER BY start_ms {direction}, id {direction}"
        )
        params: list[Any] = [day, start_ms, end_ms]
        if tail_limit is not None:
            query += " LIMIT ?"
            params.append(tail_limit)

        cur = self.db.execute(query, tuple(params))
        rows = cur.fetchall()
        if tail_limit is not None:
            rows.reverse()

        return [
            {
                "id": r["id"],
                "batchId": r["batch_id"],
                "day": r["day"],
                "startMs": r["start_ms"],
                "endMs": r["end_ms"],
                "text": r["text"],
            }
            for r in rows
        ]

    observationsInRange = observations_in_range

    def cards_for_day(
        self,
        day: str,
        window: Optional[dict[str, int]] = None,
    ) -> list[LogbookCard]:
        """Return timeline cards for a day, optionally bounded by window."""
        query = (
            "SELECT id, day, start_ms, end_ms, title, summary, detail, category, "
            "app_primary, app_secondary, distractions, keyframe_id, updated_ms "
            "FROM cards WHERE day = ?"
        )
        params: list[Any] = [day]
        if window:
            start_ms = window.get("startMs") or window.get("start_ms") or 0
            end_ms = window.get("endMs") or window.get("end_ms") or 0
            query += " AND end_ms > ? AND start_ms < ?"
            params.extend([start_ms, end_ms])

        query += " ORDER BY start_ms ASC, id ASC;"
        cur = self.db.execute(query, tuple(params))
        return [_to_card(r) for r in cur.fetchall()]

    cardsForDay = cards_for_day

    def count_cards_for_day(self, day: str) -> int:
        """Return card count for a day."""
        cur = self.db.execute("SELECT COUNT(*) AS count FROM cards WHERE day = ?;", (day,))
        row = cur.fetchone()
        return int(row["count"]) if row else 0

    countCardsForDay = count_cards_for_day

    def replace_cards_in_window(
        self,
        day: str,
        start_ms: int,
        end_ms: int,
        drafts: Sequence[LogbookCardDraft],
    ) -> None:
        """Replace cards overlapping [start_ms, end_ms) for a day atomically."""
        now = int(time.time() * 1000)
        self.db.execute("BEGIN IMMEDIATE;")
        try:
            # Check keyframe references if any
            for draft in drafts:
                keyframe_id = draft.get("keyframeId") or draft.get("keyframe_id")
                if keyframe_id is not None:
                    kf_cur = self.db.execute("SELECT id FROM frames WHERE id = ?;", (keyframe_id,))
                    if not kf_cur.fetchone():
                        raise ValueError(f"Keyframe frame {keyframe_id} does not exist")

            self.db.execute(
                "DELETE FROM cards WHERE day = ? AND end_ms > ? AND start_ms < ?;",
                (day, start_ms, end_ms),
            )
            for draft in drafts:
                distractions_json = json.dumps(draft.get("distractions", []))
                self.db.execute(
                    """
                    INSERT INTO cards (day, start_ms, end_ms, title, summary, detail, category, app_primary, app_secondary, distractions, keyframe_id, updated_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        day,
                        draft.get("startMs") or draft.get("start_ms") or 0,
                        draft.get("endMs") or draft.get("end_ms") or 0,
                        draft.get("title", ""),
                        draft.get("summary", ""),
                        draft.get("detail", ""),
                        draft.get("category", "other"),
                        draft.get("appPrimary") or draft.get("app_primary"),
                        draft.get("appSecondary") or draft.get("app_secondary"),
                        distractions_json,
                        draft.get("keyframeId") or draft.get("keyframe_id"),
                        now,
                    ),
                )
            self.db.commit()
        except Exception:
            self.db.execute("ROLLBACK;")
            raise

    replaceCardsInWindow = replace_cards_in_window

    def list_days(self) -> list[dict[str, Any]]:
        """Return roll-up statistics of all days with cards."""
        cur = self.db.execute(
            """
            SELECT day, COUNT(*) AS cards, MIN(start_ms) AS first_ms, MAX(end_ms) AS last_ms
            FROM cards
            GROUP BY day
            ORDER BY day DESC;
            """
        )
        return [
            {
                "day": r["day"],
                "cards": r["cards"],
                "firstMs": r["first_ms"],
                "lastMs": r["last_ms"],
            }
            for r in cur.fetchall()
        ]

    listDays = list_days

    def timeline_for_day(self, day: str) -> dict[str, Any]:
        """Compute full timeline data and stats for a day."""
        cards = self.cards_for_day(day)
        categories: dict[str, int] = {}
        apps: dict[str, int] = {}
        tracked_ms = 0
        distraction_ms = 0

        for card in cards:
            duration = max(0, card["endMs"] - card["startMs"])
            tracked_ms += duration
            cat = card.get("category", "other")
            categories[cat] = categories.get(cat, 0) + duration

            app = card.get("appPrimary")
            if app:
                apps[app] = apps.get(app, 0) + duration

            for distraction in card.get("distractions", []):
                distraction_ms += max(0, distraction["endMs"] - distraction["startMs"])

        categories_list = [
            {"category": k, "ms": v}
            for k, v in sorted(categories.items(), key=lambda item: item[1], reverse=True)
        ]
        apps_list = [
            {"domain": k, "ms": v}
            for k, v in sorted(apps.items(), key=lambda item: item[1], reverse=True)
        ]

        stats: LogbookDayStats = {
            "trackedMs": tracked_ms,
            "distractionMs": distraction_ms,
            "categories": categories_list,
            "apps": apps_list,
        }

        return {
            "day": day,
            "cards": cards,
            "stats": stats,
        }

    timelineForDay = timeline_for_day

    def get_standup(self, day: str) -> Optional[dict[str, Any]]:
        """Get cached standup text for a day."""
        cur = self.db.execute("SELECT day, text, updated_ms FROM standups WHERE day = ?;", (day,))
        row = cur.fetchone()
        if not row:
            return None
        return {"day": row["day"], "text": row["text"], "updatedMs": row["updated_ms"]}

    getStandup = get_standup

    def save_standup(self, day: str, text: str) -> None:
        """Save or update standup summary for a day."""
        now = int(time.time() * 1000)
        with self.db:
            self.db.execute(
                """
                INSERT INTO standups (day, text, updated_ms) VALUES (?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET text = excluded.text, updated_ms = excluded.updated_ms;
                """,
                (day, text, now),
            )

    saveStandup = save_standup

    def prune_frames(self, older_than_ms: int) -> int:
        """Delete frames older than cutoff, removing image files before deleting rows."""
        cur = self.db.execute(
            "SELECT id, path, day FROM frames WHERE captured_at_ms < ?;",
            (older_than_ms,),
        )
        rows = cur.fetchall()
        if not rows:
            return 0

        days: set[str] = set()
        # Delete files from disk first. If file removal fails (e.g. dir locked), raise so DB metadata is kept!
        for row in rows:
            file_path = row["path"]
            if os.path.isdir(file_path):
                # Directory at file path is an error
                raise OSError(f"Path is a directory: {file_path}")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                raise
            days.add(row["day"])

        # Delete database rows in an immediate transaction
        self.db.execute("BEGIN IMMEDIATE;")
        deleted_count = 0
        try:
            for row in rows:
                frame_id = row["id"]
                current_cur = self.db.execute("SELECT path FROM frames WHERE id = ?;", (frame_id,))
                current = current_cur.fetchone()
                if not current:
                    continue
                if current["path"] != row["path"]:
                    raise ValueError(f"Logbook frame {frame_id} changed path while pruning")

                del_cur = self.db.execute("DELETE FROM frames WHERE id = ?;", (frame_id,))
                deleted_count += int(del_cur.rowcount)
            self.db.commit()
        except Exception:
            self.db.execute("ROLLBACK;")
            raise

        # Best effort cleanup of empty day directories
        for day in days:
            day_dir = os.path.join(self.frames_dir, day)
            try:
                os.rmdir(day_dir)
            except OSError:
                pass

        return deleted_count

    pruneFrames = prune_frames


__all__ = [
    "EXPECTED_INDEXES",
    "LOGBOOK_SCHEMA_VERSION",
    "LOGBOOK_SQLITE_BUSY_TIMEOUT_MS",
    "LogbookStore",
    "SCHEMA",
    "day_key_for",
]
