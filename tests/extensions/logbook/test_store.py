"""Unit tests for LogbookStore.

Mirrors OpenClaw's ``extensions/logbook/src/store.test.ts`` 1:1.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile
import pytest

from extensions.logbook.src.logbook_types import LogbookCardDraft
from extensions.logbook.src.store import LogbookStore, day_key_for

DAY = "2026-07-03"


def draft(overrides: dict | None = None) -> LogbookCardDraft:
    import datetime

    dt = datetime.datetime.fromisoformat(f"{DAY}T10:00:00")
    base = int(dt.timestamp() * 1000)
    d: LogbookCardDraft = {
        "day": DAY,
        "startMs": base,
        "endMs": base + 30 * 60000,
        "title": "Card",
        "summary": "Summary",
        "detail": "",
        "category": "coding",
        "appPrimary": "github.com",
        "appSecondary": None,
        "distractions": [],
        "keyframeId": None,
    }
    if overrides:
        d.update(overrides)  # type: ignore[arg-type]
    return d


def query_plan_details(db: sqlite3.Connection, sql: str) -> list[str]:
    cur = db.execute(f"EXPLAIN QUERY PLAN {sql};")
    return [r[3] for r in cur.fetchall()]


class TestLogbookStore:
    @pytest.fixture(autouse=True)
    def setup_store(self, tmp_path: Path):
        self.dir = str(tmp_path)
        self.store = LogbookStore(self.dir)
        yield
        self.store.close()

    def insert_frame(self, captured_at_ms: int, idle: bool = False, hash_val: str | None = None) -> int:
        day = day_key_for(captured_at_ms)
        file_path = self.store.frame_file_path(day, captured_at_ms)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("jpeg-bytes")
        return self.store.insert_frame({
            "capturedAtMs": captured_at_ms,
            "day": day,
            "path": file_path,
            "screenIndex": 0,
            "byteSize": 9,
            "contentHash": hash_val or f"hash-{captured_at_ms}",
            "idle": idle,
        })

    def test_tracks_unbatched_active_frames_and_excludes_idle_ones(self) -> None:
        t0 = 1700000000000
        self.insert_frame(t0)
        self.insert_frame(t0 + 1000, idle=True)
        self.insert_frame(t0 + 2000)

        assert self.store.count_unbatched_active_frames() == 2
        batch_id = self.store.create_batch({
            "day": day_key_for(t0),
            "startMs": t0,
            "endMs": t0 + 3000,
            "frameIds": [f["id"] for f in self.store.unbatched_active_frames(10)],
        })
        assert self.store.count_unbatched_active_frames() == 0
        assert len(self.store.batch_frames(batch_id)) == 2

    def test_creates_every_owned_table_as_strict_with_foreign_keys_enabled(self) -> None:
        db_path = os.path.join(self.dir, "logbook.sqlite")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT name, strict FROM pragma_table_list WHERE schema = 'main' AND type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            tables = [{"name": r["name"], "strict": r["strict"]} for r in cur.fetchall()]
            assert tables == [
                {"name": "batches", "strict": 1},
                {"name": "cards", "strict": 1},
                {"name": "frames", "strict": 1},
                {"name": "observations", "strict": 1},
                {"name": "standups", "strict": 1},
            ]
            cur = conn.execute("PRAGMA user_version;")
            assert cur.fetchone()[0] == 1

            cur = conn.execute("PRAGMA foreign_key_list(observations);")
            obs_fks = [dict(r) for r in cur.fetchall()]
            assert any(fk["table"] == "batches" and fk["on_delete"].upper() == "CASCADE" for fk in obs_fks)

            cur = conn.execute("PRAGMA foreign_key_list(cards);")
            card_fks = [dict(r) for r in cur.fetchall()]
            assert any(fk["table"] == "frames" and fk["on_delete"].upper() == "SET NULL" for fk in card_fks)
        finally:
            conn.close()

    @pytest.mark.parametrize(
        "sql,expected_index,scanned_table,ordered",
        [
            (
                "SELECT id FROM frames WHERE batch_id = 1 ORDER BY captured_at_ms ASC",
                "idx_logbook_frames_batch",
                "frames",
                True,
            ),
            (
                "DELETE FROM observations WHERE batch_id = 1",
                "idx_logbook_observations_batch",
                "observations",
                False,
            ),
            (
                "DELETE FROM frames WHERE id = 1",
                "idx_logbook_cards_keyframe",
                "cards",
                False,
            ),
            (
                "SELECT id FROM frames ORDER BY captured_at_ms DESC LIMIT 1",
                "idx_logbook_frames_captured_at",
                "frames",
                True,
            ),
            (
                "SELECT id FROM frames WHERE captured_at_ms >= 1 AND captured_at_ms < 2 ORDER BY captured_at_ms ASC",
                "idx_logbook_frames_captured_at",
                "frames",
                True,
            ),
        ],
    )
    def test_uses_supporting_index(self, sql: str, expected_index: str, scanned_table: str, ordered: bool) -> None:
        db_path = os.path.join(self.dir, "logbook.sqlite")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            plan = query_plan_details(conn, sql)
            assert any(expected_index in detail for detail in plan)
            assert not any(detail.startswith(f"SCAN {scanned_table}") and " USING " not in detail for detail in plan)
            if ordered:
                assert not any("USE TEMP B-TREE FOR ORDER BY" in detail for detail in plan)
        finally:
            conn.close()

    def test_restores_missing_schema_1_indexes_on_reopen(self) -> None:
        self.store.close()
        db_path = os.path.join(self.dir, "logbook.sqlite")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            DROP INDEX IF EXISTS idx_logbook_frames_captured_at;
            DROP INDEX IF EXISTS idx_logbook_frames_batch;
            DROP INDEX IF EXISTS idx_logbook_observations_batch;
            DROP INDEX IF EXISTS idx_logbook_cards_keyframe;
        """)
        conn.close()

        # Reopen store
        self.store = LogbookStore(self.dir)

        reopened = sqlite3.connect(db_path)
        try:
            cur = reopened.execute(
                """
                SELECT name FROM sqlite_schema
                WHERE type = 'index'
                  AND name IN (
                    'idx_logbook_cards_keyframe',
                    'idx_logbook_frames_batch',
                    'idx_logbook_frames_captured_at',
                    'idx_logbook_observations_batch'
                  )
                ORDER BY name;
                """
            )
            indexes = [r[0] for r in cur.fetchall()]
            assert indexes == [
                "idx_logbook_cards_keyframe",
                "idx_logbook_frames_batch",
                "idx_logbook_frames_captured_at",
                "idx_logbook_observations_batch",
            ]
        finally:
            reopened.close()

    def test_rejects_values_that_violate_strict_column_types(self) -> None:
        db_path = os.path.join(self.dir, "logbook.sqlite")
        conn = sqlite3.connect(db_path)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO standups (day, text, updated_ms) VALUES (?, ?, ?);",
                    (DAY, "bad timestamp", "not-an-integer"),
                )
            cur = conn.execute("SELECT COUNT(*) FROM standups;")
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()

    def test_rolls_back_whole_batch_when_any_frame_missing(self) -> None:
        t0 = 1700000000000
        frame_id = self.insert_frame(t0)

        with pytest.raises(ValueError, match="Logbook frame 999999 is missing or already batched"):
            self.store.create_batch({
                "day": day_key_for(t0),
                "startMs": t0,
                "endMs": t0 + 1000,
                "frameIds": [frame_id, 999999],
            })

        assert self.store.latest_batch() is None
        assert [f["id"] for f in self.store.unbatched_active_frames(10)] == [frame_id]

    def test_does_not_steal_frame_from_existing_batch(self) -> None:
        t0 = 1700000000000
        first_frame = self.insert_frame(t0)
        second_frame = self.insert_frame(t0 + 1000)

        first_batch = self.store.create_batch({
            "day": day_key_for(t0),
            "startMs": t0,
            "endMs": t0 + 1000,
            "frameIds": [first_frame],
        })

        with pytest.raises(ValueError, match=f"Logbook frame {first_frame} is missing or already batched"):
            self.store.create_batch({
                "day": day_key_for(t0),
                "startMs": t0,
                "endMs": t0 + 2000,
                "frameIds": [first_frame, second_frame],
            })

        latest = self.store.latest_batch()
        assert latest is not None and latest["id"] == first_batch
        assert [f["id"] for f in self.store.batch_frames(first_batch)] == [first_frame]
        assert [f["id"] for f in self.store.unbatched_active_frames(10)] == [second_frame]

    def test_rejects_empty_and_duplicate_frame_claims(self) -> None:
        t0 = 1700000000000
        with pytest.raises(ValueError, match="Logbook batch requires at least one frame"):
            self.store.create_batch({"day": DAY, "startMs": t0, "endMs": t0 + 1000, "frameIds": []})

        frame_id = self.insert_frame(t0)
        with pytest.raises(ValueError, match=f"Logbook frame {frame_id} is missing or already batched"):
            self.store.create_batch({
                "day": DAY,
                "startMs": t0,
                "endMs": t0 + 1000,
                "frameIds": [frame_id, frame_id],
            })
        assert self.store.latest_batch() is None
        assert self.store.count_unbatched_active_frames() == 1

    def test_resets_running_batches_to_pending(self) -> None:
        t0 = 1700000000000
        frame_id = self.insert_frame(t0)
        batch_id = self.store.create_batch({
            "day": day_key_for(t0),
            "startMs": t0,
            "endMs": t0 + 1000,
            "frameIds": [frame_id],
        })
        self.store.set_batch_status(batch_id, "running")
        self.store.reset_running_batches()
        next_b = self.store.next_pending_batch()
        assert next_b is not None and next_b["id"] == batch_id

    def test_replaces_only_cards_overlapping_revision_window(self) -> None:
        import datetime

        base = int(datetime.datetime.fromisoformat(f"{DAY}T09:00:00").timestamp() * 1000)
        self.store.replace_cards_in_window(
            DAY,
            base,
            base + 4 * 3600 * 1000,
            [
                draft({"startMs": base, "endMs": base + 30 * 60000, "title": "Early"}),
                draft({"startMs": base + 60 * 60000, "endMs": base + 90 * 60000, "title": "Mid"}),
            ],
        )

        assert self.store.cards_for_day(DAY, {"startMs": base + 30 * 60000, "endMs": base + 60 * 60000}) == []
        mid_cards = self.store.cards_for_day(DAY, {"startMs": base + 50 * 60000, "endMs": base + 120 * 60000})
        assert [c["title"] for c in mid_cards] == ["Mid"]

        # Revise only window covering Mid
        self.store.replace_cards_in_window(
            DAY,
            base + 50 * 60000,
            base + 120 * 60000,
            [draft({"startMs": base + 55 * 60000, "endMs": base + 95 * 60000, "title": "Mid revised"})],
        )
        titles = [c["title"] for c in self.store.cards_for_day(DAY)]
        assert titles == ["Early", "Mid revised"]

    def test_round_trips_distractions_and_computes_day_stats(self) -> None:
        import datetime

        base = int(datetime.datetime.fromisoformat(f"{DAY}T10:00:00").timestamp() * 1000)
        self.store.replace_cards_in_window(
            DAY,
            base,
            base + 60 * 60000,
            [
                draft({
                    "startMs": base,
                    "endMs": base + 30 * 60000,
                    "distractions": [{"startMs": base + 5 * 60000, "endMs": base + 10 * 60000, "title": "Twitter"}],
                }),
                draft({
                    "startMs": base + 30 * 60000,
                    "endMs": base + 60 * 60000,
                    "title": "Review",
                    "category": "review",
                    "appPrimary": None,
                    "appSecondary": "",
                }),
            ],
        )

        cards = self.store.cards_for_day(DAY)
        assert [c["title"] for c in cards] == ["Card", "Review"]
        assert cards[0]["distractions"] == [
            {"startMs": base + 5 * 60000, "endMs": base + 10 * 60000, "title": "Twitter"}
        ]

        stats = self.store.timeline_for_day(DAY)["stats"]
        assert stats["trackedMs"] == 60 * 60000
        assert stats["distractionMs"] == 5 * 60000
        assert stats["categories"] == [
            {"category": "coding", "ms": 30 * 60000},
            {"category": "review", "ms": 30 * 60000},
        ]
        assert stats["apps"][0]["domain"] == "github.com"
        assert self.store.count_cards_for_day(DAY) == len(cards)
        assert self.store.count_cards_for_day("2026-07-04") == 0

    def test_prunes_old_frames_and_files(self) -> None:
        now = 1700000000000
        old_id = self.insert_frame(now - 20 * 24 * 3600 * 1000)
        new_id = self.insert_frame(now)

        old_frame = self.store.frame_by_id(old_id)
        assert old_frame is not None
        old_path = old_frame["path"]

        assert self.store.prune_frames(now - 14 * 24 * 3600 * 1000) == 1
        assert self.store.frame_by_id(old_id) is None
        assert not os.path.exists(old_path)
        assert self.store.frame_by_id(new_id) is not None

    def test_keeps_frame_metadata_when_file_cannot_be_removed(self) -> None:
        now = 1700000000000
        first_id = self.insert_frame(now - 21 * 24 * 3600 * 1000)
        blocked_id = self.insert_frame(now - 20 * 24 * 3600 * 1000)

        blocked_frame = self.store.frame_by_id(blocked_id)
        assert blocked_frame is not None
        blocked_path = blocked_frame["path"]
        os.remove(blocked_path)
        os.makedirs(blocked_path, exist_ok=True)  # turning file into dir causes OSError on removal

        with pytest.raises(OSError):
            self.store.prune_frames(now - 14 * 24 * 3600 * 1000)

        assert self.store.frame_by_id(first_id) is not None
        assert self.store.frame_by_id(blocked_id) is not None

        os.rmdir(blocked_path)
        assert self.store.prune_frames(now - 14 * 24 * 3600 * 1000) == 2
        assert self.store.frame_by_id(first_id) is None
        assert self.store.frame_by_id(blocked_id) is None

    def test_detaches_pruned_keyframes_from_surviving_cards(self) -> None:
        now = 1700000000000
        old_id = self.insert_frame(now - 20 * 24 * 3600 * 1000)
        self.store.replace_cards_in_window(DAY, 0, 9223372036854775807, [draft({"keyframeId": old_id})])
        self.store.prune_frames(now - 14 * 24 * 3600 * 1000)
        card = self.store.cards_for_day(DAY)[0]
        assert card["keyframeId"] is None

    def test_replaces_observations_on_batch_retry(self) -> None:
        t0 = 1700000000000
        frame_id = self.insert_frame(t0)
        batch_id = self.store.create_batch({
            "day": DAY,
            "startMs": t0,
            "endMs": t0 + 1000,
            "frameIds": [frame_id],
        })

        self.store.replace_observations(batch_id, DAY, [{"startMs": t0, "endMs": t0 + 500, "text": "first run"}])
        self.store.replace_observations(batch_id, DAY, [{"startMs": t0, "endMs": t0 + 500, "text": "retry run"}])

        obs = self.store.observations_in_range(DAY, 0, 9223372036854775807)
        assert len(obs) == 1
        assert obs[0]["text"] == "retry run"

    def test_rejects_observations_for_missing_batch(self) -> None:
        with pytest.raises(ValueError):
            self.store.replace_observations(999999, DAY, [{"startMs": 1, "endMs": 2, "text": "orphan"}])
        assert self.store.observations_in_range(DAY, 0, 9223372036854775807) == []

    def test_requeues_errored_batches(self) -> None:
        t0 = 1700000000000
        frame_id = self.insert_frame(t0)
        batch_id = self.store.create_batch({
            "day": day_key_for(t0),
            "startMs": t0,
            "endMs": t0 + 1000,
            "frameIds": [frame_id],
        })
        self.store.set_batch_status(batch_id, "error", "failed")
        assert self.store.next_pending_batch() is None
        assert self.store.reset_error_batches() == 1
        requeued = self.store.next_pending_batch()
        assert requeued is not None and requeued["id"] == batch_id
        assert requeued["error"] is None

    def test_stores_and_updates_standups(self) -> None:
        self.store.save_standup(DAY, "## Done\n- shipped")
        self.store.save_standup(DAY, "## Done\n- shipped more")
        standup = self.store.get_standup(DAY)
        assert standup is not None
        assert "shipped more" in standup["text"]

    def test_migrates_legacy_tables_to_strict(self) -> None:
        self.store.close()
        db_path = os.path.join(self.dir, "logbook.sqlite")
        os.remove(db_path)
        legacy = sqlite3.connect(db_path)
        legacy.executescript(f"""
            CREATE TABLE batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                frame_count INTEGER NOT NULL DEFAULT 0,
                model TEXT,
                created_ms INTEGER NOT NULL,
                updated_ms INTEGER NOT NULL
            );
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at_ms INTEGER NOT NULL,
                day TEXT NOT NULL,
                path TEXT NOT NULL,
                screen_index INTEGER NOT NULL DEFAULT 0,
                width INTEGER,
                height INTEGER,
                byte_size INTEGER NOT NULL DEFAULT 0,
                content_hash TEXT NOT NULL,
                idle INTEGER NOT NULL DEFAULT 0,
                batch_id INTEGER
            );
            INSERT INTO batches VALUES (7, '{DAY}', 10, 20, 'pending', NULL, 1, NULL, 10, 10);
            INSERT INTO frames VALUES (11, 10, '{DAY}', '/tmp/frame.jpg', 0, NULL, NULL, 1, 'hash', 0, 7);
        """)
        legacy.close()

        self.store = LogbookStore(self.dir)
        frames = self.store.batch_frames(7)
        assert [f["id"] for f in frames] == [11]

        migrated = sqlite3.connect(db_path)
        migrated.row_factory = sqlite3.Row
        try:
            cur = migrated.execute(
                "SELECT name, strict FROM pragma_table_list WHERE schema = 'main' AND type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            tables = [{"name": r["name"], "strict": r["strict"]} for r in cur.fetchall()]
            assert tables == [
                {"name": "batches", "strict": 1},
                {"name": "cards", "strict": 1},
                {"name": "frames", "strict": 1},
                {"name": "observations", "strict": 1},
                {"name": "standups", "strict": 1},
            ]
        finally:
            migrated.close()

    def test_rolls_back_legacy_strict_migration_on_type_violation(self) -> None:
        legacy_dir = os.path.join(self.dir, "invalid-legacy")
        os.makedirs(legacy_dir, exist_ok=True)
        db_path = os.path.join(legacy_dir, "logbook.sqlite")
        legacy = sqlite3.connect(db_path)
        legacy.executescript(f"""
            CREATE TABLE standups (day TEXT PRIMARY KEY, text TEXT NOT NULL, updated_ms TEXT NOT NULL);
            INSERT INTO standups VALUES ('{DAY}', 'legacy', 'not-an-integer');
        """)
        legacy.close()

        with pytest.raises(ValueError, match="Failed migrating SQLite table standups to STRICT"):
            LogbookStore(legacy_dir)
