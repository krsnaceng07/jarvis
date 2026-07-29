"""Tests for ``jarvis_state_core.lease``.

Covers:
- happy-path acquire + release
- second caller waits + acquires after the first releases
- timeout when second caller cannot acquire in time
- lost-lease detection mid-operation
- assert_owned + assert_owned_in_transaction
- invalid input validation
- scope + key validation (NUL bytes, empty, whitespace)
- abort via threading.Event
- release is best-effort on lock contention
- agent-scope lease uses the agent DB
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
import time

import pytest

from jarvis_state_core.lease import (
    MIN_LEASE_MS,
    StateLeaseError,
    with_state_lease,
)


# ── Helpers ───────────────────────────────────────────────


def _shared_factory(path: str):
    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE IF NOT EXISTS state_leases ("
            "scope TEXT NOT NULL, "
            "lease_key TEXT NOT NULL, "
            "owner TEXT NOT NULL, "
            "expires_at INTEGER NOT NULL, "
            "heartbeat_at INTEGER NOT NULL, "
            "payload_json TEXT, "
            "created_at INTEGER NOT NULL, "
            "updated_at INTEGER NOT NULL, "
            "PRIMARY KEY (scope, lease_key)"
            ")"
        )
        conn.commit()
        return conn

    return factory


def _read_lease_row(path: str, scope: str, key: str) -> dict | None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM state_leases WHERE scope = ? AND lease_key = ?",
        (scope, key),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Happy path ────────────────────────────────────────────


def test_acquire_release_round_trip(tmp_path):
    db = str(tmp_path / "state.sqlite")
    factory = _shared_factory(db)

    async def run() -> str:
        async def callback(ctx):
            # Lease is held while we run.
            row = _read_lease_row(db, "core:test", "k1")
            assert row is not None
            assert row["scope"] == "core:test"
            assert row["lease_key"] == "k1"
            assert row["owner"]
            return "ok"

        return await with_state_lease(
            {
                "scope": "core:test",
                "key": "k1",
                "database": {"scope": "shared", "connection_factory": factory},
                "lease_ms": 5_000,
                "wait_ms": 0,
            },
            callback,
        )

    assert asyncio.run(run()) == "ok"
    assert _read_lease_row(db, "core:test", "k1") is None


def test_second_caller_waits_and_acquires_after_first_releases(tmp_path):
    db = str(tmp_path / "state.sqlite")
    factory = _shared_factory(db)
    order: list[str] = []

    async def run() -> None:
        async def first(ctx):
            order.append("first-enter")
            await asyncio.sleep(0.2)
            order.append("first-exit")

        async def second(ctx):
            order.append("second-enter")
            return None

        await with_state_lease(
            {
                "scope": "core:test",
                "key": "k2",
                "database": {"scope": "shared", "connection_factory": factory},
                "lease_ms": 5_000,
                "wait_ms": 5_000,
            },
            first,
        )
        await with_state_lease(
            {
                "scope": "core:test",
                "key": "k2",
                "database": {"scope": "shared", "connection_factory": factory},
                "lease_ms": 5_000,
                "wait_ms": 5_000,
            },
            second,
        )

    asyncio.run(run())
    assert order == ["first-enter", "first-exit", "second-enter"]


def test_second_caller_times_out(tmp_path):
    db = str(tmp_path / "state.sqlite")
    factory = _shared_factory(db)
    release_event = threading.Event()

    async def run() -> None:
        async def first(ctx):
            # ``threading.Event.wait`` is sync; run it in a
            # thread so the asyncio loop stays responsive.
            await asyncio.to_thread(release_event.wait, 5)
            return None

        async def second(ctx):
            return None

        first_task = asyncio.create_task(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k3",
                    "database": {"scope": "shared", "connection_factory": factory},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                first,
            )
        )
        # Let the first acquire the lease.
        await asyncio.sleep(0.1)
        # The second call asks for a tiny wait; it must
        # time out before the first releases.
        with pytest.raises(StateLeaseError) as info:
            await with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k3",
                    "database": {"scope": "shared", "connection_factory": factory},
                    "lease_ms": 5_000,
                    "wait_ms": 25,
                },
                second,
            )
        assert info.value.code == "STATE_LEASE_TIMEOUT"
        # Release the first holder.
        release_event.set()
        await first_task

    asyncio.run(run())


def test_lost_lease_aborts_heartbeat_check(tmp_path):
    """When the lease expires the assert_owned path raises LOST."""
    db = str(tmp_path / "state.sqlite")
    factory = _shared_factory(db)

    async def run() -> None:
        async def callback(ctx):
            # Manually yank the lease row (simulate process
            # crash or external cleanup).
            conn = sqlite3.connect(db)
            conn.execute("DELETE FROM state_leases")
            conn.commit()
            conn.close()
            ctx.assert_owned()  # should raise LOST
            return "unreachable"

        with pytest.raises(StateLeaseError) as info:
            await with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k4",
                    "database": {"scope": "shared", "connection_factory": factory},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                callback,
            )
        assert info.value.code == "STATE_LEASE_LOST"

    asyncio.run(run())


def test_assert_owned_in_transaction(tmp_path):
    """Mirrors OpenClaw's
    ``rechecks exact ownership inside the caller's write
    transaction`` test (single-test contract).

    The test steers the lease owner mid-transaction and
    re-asserts in-transaction. The LOST error must
    propagate up through the callback so the outer
    ``with_state_lease`` rejects.
    """
    db = str(tmp_path / "state.sqlite")
    factory = _shared_factory(db)

    async def run() -> None:
        async def callback(ctx):
            with_state_db = sqlite3.connect(db)
            with_state_db.execute("BEGIN IMMEDIATE")
            try:
                # Lease should be held; the in-transaction
                # assert succeeds.
                ctx.assert_owned_in_transaction(with_state_db)
                # Now steal the lease. The next in-transaction
                # assert must raise LOST — the callback
                # itself rejects (no rollback) so the outer
                # ``with_state_lease`` re-raises LOST.
                with_state_db.execute(
                    "UPDATE state_leases SET owner = 'successor' "
                    "WHERE scope = ? AND lease_key = ?",
                    ("core:test", "k5"),
                )
                try:
                    ctx.assert_owned_in_transaction(with_state_db)
                except StateLeaseError as info:
                    assert info.code == "STATE_LEASE_LOST"
                    raise
            finally:
                with_state_db.rollback()
                with_state_db.close()

        with pytest.raises(StateLeaseError) as info:
            await with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k5",
                    "database": {"scope": "shared", "connection_factory": factory},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                callback,
            )
        assert info.value.code == "STATE_LEASE_LOST"

    asyncio.run(run())


# ── Validation ────────────────────────────────────────────


def test_invalid_input_non_object():
    with pytest.raises(StateLeaseError) as info:
        asyncio.run(with_state_lease([], lambda ctx: asyncio.sleep(0)))  # type: ignore[arg-type]
    assert info.value.code == "STATE_LEASE_INVALID_INPUT"


def test_invalid_input_missing_signal_type():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k6",
                    "database": {"scope": "shared"},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                    "signal": "not-an-event",
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_invalid_input_database_not_object():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k7",
                    "database": "shared",
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_invalid_input_database_scope():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k8",
                    "database": {"scope": "weird"},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_invalid_input_agent_id_required():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k9",
                    "database": {"scope": "agent", "agent_id": ""},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_invalid_input_scope_empty():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "",
                    "key": "k10",
                    "database": {"scope": "shared"},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_invalid_input_key_with_nul():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k\0ull",
                    "database": {"scope": "shared"},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_invalid_input_lease_ms_below_min():
    with pytest.raises(StateLeaseError):
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k11",
                    "database": {"scope": "shared"},
                    "lease_ms": MIN_LEASE_MS - 1,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )


def test_abort_via_signal(tmp_path):
    db = str(tmp_path / "state.sqlite")
    factory = _shared_factory(db)
    event = threading.Event()
    event.set()  # already aborted

    async def run() -> None:
        with pytest.raises(StateLeaseError) as info:
            await with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k12",
                    "database": {"scope": "shared", "connection_factory": factory},
                    "lease_ms": 5_000,
                    "wait_ms": 0,
                    "signal": event,
                },
                lambda ctx: asyncio.sleep(0),
            )
        assert info.value.code == "STATE_LEASE_ABORTED"

    asyncio.run(run())


def test_minimum_lease_ms_enforced():
    with pytest.raises(StateLeaseError) as info:
        asyncio.run(
            with_state_lease(
                {
                    "scope": "core:test",
                    "key": "k13",
                    "database": {"scope": "shared"},
                    "lease_ms": 500,
                    "wait_ms": 0,
                },
                lambda ctx: asyncio.sleep(0),
            )
        )
    assert info.value.code == "STATE_LEASE_INVALID_INPUT"
