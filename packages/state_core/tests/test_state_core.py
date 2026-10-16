"""Tests for jarvis_state_core — canonical state database.

Covers:
- StateDatabase connection management (pragmas, path
  resolution)
- run_queued_store_write + run_write_transaction (per-key
  FIFO + per-store-path serialization)
- Query helper (SELECT / INSERT / UPDATE / DELETE with
  where / order by / limit)
- ensure_schema baseline tables

Mirrors a focused subset of OpenClaw's
``src/state/openclaw-state-db.test.ts``.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading

import pytest

from jarvis_state_core import (
    Query,
    StateDatabase,
    StateDatabaseOptions,
    ensure_schema,
    reset_state_for_tests,
    run_queued_store_write,
    run_write_transaction,
)


@pytest.fixture(autouse=True)
def _reset_state():
    reset_state_for_tests()
    yield
    reset_state_for_tests()


@pytest.fixture
def tmp_db(tmp_path):
    """Create a fresh temp-file SQLite DB with the canonical schema."""
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    bootstrap = factory()
    try:
        ensure_schema(bootstrap)
    finally:
        bootstrap.close()

    return StateDatabase(StateDatabaseOptions(connection_factory=factory, path=str(db_path)))


# ── StateDatabase connection management ───────────────────


class TestStateDatabaseOpen:
    def test_open_returns_connection_with_row_factory(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_open_applies_busy_timeout_pragma(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            row = conn.execute("PRAGMA busy_timeout").fetchone()
            assert row is not None
            assert int(row[0]) == 5_000
        finally:
            conn.close()

    def test_open_applies_custom_busy_timeout(self, tmp_path) -> None:
        db_path = tmp_path / "state.sqlite"
        db_path.touch()

        def factory() -> sqlite3.Connection:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn

        bootstrap = factory()
        try:
            ensure_schema(bootstrap)
        finally:
            bootstrap.close()

        db = StateDatabase(
            StateDatabaseOptions(
                connection_factory=factory,
                path=str(db_path),
                busy_timeout_ms=10_000,
            )
        )
        conn = db.open()
        try:
            row = conn.execute("PRAGMA busy_timeout").fetchone()
            assert int(row[0]) == 10_000
        finally:
            conn.close()

    def test_open_raises_without_connection_factory(self) -> None:
        db = StateDatabase()
        with pytest.raises(ValueError, match="connection_factory"):
            db.open()

    def test_path_returns_canonical_db_path(self, tmp_path) -> None:
        db_path = tmp_path / "state.sqlite"
        db = StateDatabase(StateDatabaseOptions(path=str(db_path)))
        assert db.path() == str(db_path)

    def test_path_falls_back_to_env(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
        db = StateDatabase(
            StateDatabaseOptions(
                env={k: v for k, v in os.environ.items() if k == "JARVIS_STATE_DIR"}
            )
        )
        assert db.path() == str(tmp_path / "jarvis.sqlite")


# ── ensure_schema ────────────────────────────────────────


class TestEnsureSchema:
    def test_creates_baseline_tables(self, tmp_path) -> None:
        db_path = tmp_path / "fresh.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            ensure_schema(conn)
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "session_state_events" in tables
            assert "session_state_heads" in tables
            assert "session_watch_cursors" in tables
            assert "session_upstream_links" in tables
            assert "state_lease_owners" in tables
        finally:
            conn.close()

    def test_idempotent(self, tmp_path) -> None:
        db_path = tmp_path / "fresh.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            ensure_schema(conn)
            # Second call should be a no-op.
            ensure_schema(conn)
        finally:
            conn.close()


# ── Query helper ──────────────────────────────────────────


class TestQuerySelect:
    def test_select_star(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            conn.execute(
                "INSERT INTO session_state_heads (session_key, version, updated_at) "
                "VALUES (?, ?, ?)",
                ("s1", 1, 1_000),
            )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            q = Query(conn).select("*").from_table("session_state_heads")
            rows = q.execute()
            assert len(rows) == 1
            assert rows[0]["session_key"] == "s1"
            assert rows[0]["version"] == 1
        finally:
            conn.close()

    def test_select_with_where(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            for key, version in [("s1", 1), ("s2", 2), ("s3", 3)]:
                conn.execute(
                    "INSERT INTO session_state_heads (session_key, version, updated_at) "
                    "VALUES (?, ?, ?)",
                    (key, version, 1_000),
                )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            rows = (
                Query(conn)
                .select("session_key", "version")
                .from_table("session_state_heads")
                .where("version", 2)
                .execute()
            )
            assert len(rows) == 1
            assert rows[0]["session_key"] == "s2"
        finally:
            conn.close()

    def test_select_with_order_by_and_limit(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            for key, version in [("s1", 3), ("s2", 1), ("s3", 2)]:
                conn.execute(
                    "INSERT INTO session_state_heads (session_key, version, updated_at) "
                    "VALUES (?, ?, ?)",
                    (key, version, 1_000),
                )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            rows = (
                Query(conn)
                .select("session_key")
                .from_table("session_state_heads")
                .order_by("version")
                .limit(2)
                .execute()
            )
            assert [r["session_key"] for r in rows] == ["s2", "s3"]
        finally:
            conn.close()

    def test_select_distinct(self, tmp_db) -> None:
        # Use session_state_events (no unique constraint on
        # session_key) so we can insert duplicate keys.
        conn = tmp_db.open()
        try:
            for key in ["s1", "s1", "s2"]:
                conn.execute(
                    "INSERT INTO session_state_events ("
                    "session_key, agent_id, kind, actor_type, "
                    "occurred_at, recorded_at, summary"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (key, "main", "kind1", "human", 1_000, 1_000, "s"),
                )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            rows = (
                Query(conn)
                .select("session_key")
                .distinct()
                .from_table("session_state_events")
                .execute()
            )
            assert {r["session_key"] for r in rows} == {"s1", "s2"}
        finally:
            conn.close()

    def test_select_take_first(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            conn.execute(
                "INSERT INTO session_state_heads (session_key, version, updated_at) "
                "VALUES (?, ?, ?)",
                ("s1", 1, 1_000),
            )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            row = (
                Query(conn)
                .select("*")
                .from_table("session_state_heads")
                .where("session_key", "s1")
                .execute_take_first()
            )
            assert row is not None
            assert row["version"] == 1
        finally:
            conn.close()

    def test_select_take_first_returns_none_when_empty(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            row = Query(conn).select("*").from_table("session_state_heads").execute_take_first()
            assert row is None
        finally:
            conn.close()


class TestQueryInsert:
    def test_insert_basic(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            builder = (
                Query(conn)
                .insert_into("session_state_heads")
                .values(
                    session_key="s1",
                    version=1,
                    updated_at=1_000,
                )
            )
            cursor = builder.execute()
            conn.commit()
            assert cursor.lastrowid == 1
        finally:
            conn.close()
        # Verify the row is there.
        conn = tmp_db.open()
        try:
            row = conn.execute(
                "SELECT session_key, version FROM session_state_heads WHERE session_key = ?",
                ("s1",),
            ).fetchone()
            assert row["session_key"] == "s1"
            assert row["version"] == 1
        finally:
            conn.close()

    def test_insert_raises_when_values_empty(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            with pytest.raises(ValueError, match="values are required"):
                Query(conn).insert_into("session_state_heads").execute()
        finally:
            conn.close()

    def test_insert_on_conflict_do_nothing(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            for _ in range(2):
                (
                    Query(conn)
                    .insert_into("session_state_heads")
                    .values(session_key="s1", version=1, updated_at=1_000)
                    .on_conflict("do_nothing")
                    .execute()
                )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM session_state_heads").fetchone()["n"]
            assert count == 1
        finally:
            conn.close()


class TestQueryUpdate:
    def test_update_with_where(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            conn.execute(
                "INSERT INTO session_state_heads (session_key, version, updated_at) "
                "VALUES (?, ?, ?)",
                ("s1", 1, 1_000),
            )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            cursor = (
                Query(conn)
                .update_table("session_state_heads")
                .set("version", 5)
                .where("session_key", "s1")
                .execute()
            )
            conn.commit()
            assert cursor.rowcount == 1
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            row = conn.execute(
                "SELECT version FROM session_state_heads WHERE session_key = ?",
                ("s1",),
            ).fetchone()
            assert row["version"] == 5
        finally:
            conn.close()

    def test_update_raises_when_set_empty(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            with pytest.raises(ValueError, match="set is required"):
                Query(conn).update_table("session_state_heads").execute()
        finally:
            conn.close()


class TestQueryDelete:
    def test_delete_with_where(self, tmp_db) -> None:
        conn = tmp_db.open()
        try:
            for key in ["s1", "s2"]:
                conn.execute(
                    "INSERT INTO session_state_heads (session_key, version, updated_at) "
                    "VALUES (?, ?, ?)",
                    (key, 1, 1_000),
                )
            conn.commit()
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            cursor = (
                Query(conn).delete_from("session_state_heads").where("session_key", "s1").execute()
            )
            conn.commit()
            assert cursor.rowcount == 1
        finally:
            conn.close()
        conn = tmp_db.open()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM session_state_heads").fetchone()["n"]
            assert count == 1
        finally:
            conn.close()


# ── run_queued_store_write ─────────────────────────────────


class TestRunQueuedStoreWrite:
    def test_executes_callback(self) -> None:
        async def body() -> str:
            return "ok"

        result = asyncio.run(run_queued_store_write(queues={}, key="k1", label="test", fn=body))
        assert result == "ok"

    def test_serializes_per_key(self) -> None:
        execution_order: list[str] = []
        barrier = threading.Event()

        async def task(name: str) -> str:
            execution_order.append(f"{name}-start")
            # Block until the second task is enqueued.
            if name == "first":
                barrier.wait(timeout=2.0)
            else:
                # The second task must wait for the first
                # to finish (per-key FIFO).
                await asyncio.sleep(0.05)
            execution_order.append(f"{name}-end")
            return name

        async def first() -> str:
            return await task("first")

        async def second() -> str:
            return await task("second")

        async def body() -> None:
            queues: dict = {}
            # Enqueue the first task.
            t1 = asyncio.create_task(
                run_queued_store_write(queues=queues, key="k1", label="test", fn=first)
            )
            await asyncio.sleep(0.01)
            # Enqueue the second task; it must wait for
            # the first to finish.
            t2 = asyncio.create_task(
                run_queued_store_write(queues=queues, key="k1", label="test", fn=second)
            )
            # Set the barrier so the first task can finish.
            await asyncio.sleep(0.01)
            barrier.set()
            await t1
            await t2

        asyncio.run(body())
        # The first task started, then the second task started
        # AFTER the first finished (per-key FIFO).
        assert execution_order == [
            "first-start",
            "first-end",
            "second-start",
            "second-end",
        ]


# ── run_write_transaction ─────────────────────────────────


class TestRunWriteTransaction:
    def test_commits_on_success(self, tmp_db) -> None:
        async def body(conn) -> None:
            Query(conn).insert_into("session_state_heads").values(
                session_key="s1", version=1, updated_at=1_000
            ).execute()

        asyncio.run(run_write_transaction(tmp_db, fn=body))
        # Verify the row is committed.
        conn = tmp_db.open()
        try:
            row = conn.execute(
                "SELECT version FROM session_state_heads WHERE session_key = ?",
                ("s1",),
            ).fetchone()
            assert row["version"] == 1
        finally:
            conn.close()

    def test_rolls_back_on_exception(self, tmp_db) -> None:
        async def body(conn) -> None:
            Query(conn).insert_into("session_state_heads").values(
                session_key="s1", version=1, updated_at=1_000
            ).execute()
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(run_write_transaction(tmp_db, fn=body))
        # Verify the row was rolled back.
        conn = tmp_db.open()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM session_state_heads").fetchone()["n"]
            assert count == 0
        finally:
            conn.close()

    def test_returns_value_from_callback(self, tmp_db) -> None:
        async def body(conn) -> int:
            Query(conn).insert_into("session_state_heads").values(
                session_key="s1", version=1, updated_at=1_000
            ).execute()
            return 42

        result = asyncio.run(run_write_transaction(tmp_db, fn=body))
        assert result == 42

    def test_serializes_per_store_path(self, tmp_db) -> None:
        # Different store_paths are independent queues, but
        # SQLite itself serializes the actual writes via
        # the write lock. The test verifies that two writes
        # on different store_paths BOTH complete (the
        # busy_timeout pragma lets the second one wait for
        # the first).
        completed: list[str] = []

        async def body(name: str) -> None:
            async def _inner(conn) -> None:
                Query(conn).insert_into("session_state_heads").values(
                    session_key=name, version=1, updated_at=1_000
                ).execute()
                completed.append(name)

            await run_write_transaction(tmp_db, store_path=name, fn=_inner)

        async def run_both() -> None:
            await asyncio.gather(body("a"), body("b"))

        asyncio.run(run_both())
        assert set(completed) == {"a", "b"}
        # Verify both rows landed.
        conn = tmp_db.open()
        try:
            count = conn.execute("SELECT COUNT(*) AS n FROM session_state_heads").fetchone()["n"]
            assert count == 2
        finally:
            conn.close()

    def test_same_store_path_serializes(self, tmp_db) -> None:
        execution_order: list[str] = []

        async def body(name: str) -> None:
            async def _inner(conn) -> None:
                execution_order.append(f"{name}-start")
                Query(conn).insert_into("session_state_heads").values(
                    session_key=name, version=1, updated_at=1_000
                ).execute()
                await asyncio.sleep(0.02)
                execution_order.append(f"{name}-end")

            await run_write_transaction(tmp_db, store_path="shared", fn=_inner)

        async def run_both() -> None:
            await asyncio.gather(body("a"), body("b"))

        asyncio.run(run_both())
        # Same store_path must serialize. One of
        # (a-start, a-end) must come before the other.
        if execution_order[0] == "a-start":
            assert execution_order == [
                "a-start",
                "a-end",
                "b-start",
                "b-end",
            ]
        else:
            assert execution_order == [
                "b-start",
                "b-end",
                "a-start",
                "a-end",
            ]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
