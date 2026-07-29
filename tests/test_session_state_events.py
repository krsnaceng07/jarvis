"""Tests for src/sessions/session_state_events.py.

Mirrors a focused subset of OpenClaw's
``src/sessions/session-state-events.test.ts`` — the parts
that exercise the public surface (record / read / list /
acknowledge / register watch / sweep). Tests use a
temp-file SQLite DB so the canonical state-event schema
is created lazily and isolated per test.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

import pytest

from src.sessions.session_state_events import (
    SCHEMA_STATE_EVENTS,
    SCHEMA_STATE_EVENTS_INDEX,
    SCHEMA_STATE_HEADS,
    SCHEMA_WATCH_CURSORS,
    SessionStateDatabaseOptions,
    acknowledge_session_state_notices,
    classify_session_state_actor,
    ensure_schema,
    get_session_state_version,
    get_session_state_versions,
    handle_session_state_session_reset,
    list_ambient_group_watch_targets,
    list_session_state_events_since,
    record_session_compacted,
    record_session_goal_changed,
    record_session_human_direct_message,
    record_session_state_event,
    record_subagent_spawned,
    record_subagent_terminal_state,
    register_main_session_group_watch,
    register_session_state_watch,
    sweep_session_state_watch_notices,
)


@pytest.fixture
def options(tmp_path) -> SessionStateDatabaseOptions:
    """Per-test SQLite state DB with the state-event tables."""
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    bootstrap = factory()
    try:
        bootstrap.executescript(
            f"{SCHEMA_STATE_EVENTS};\n"
            f"{SCHEMA_STATE_HEADS};\n"
            f"{SCHEMA_WATCH_CURSORS};\n"
            f"{SCHEMA_STATE_EVENTS_INDEX};"
        )
        bootstrap.commit()
    finally:
        bootstrap.close()

    return SessionStateDatabaseOptions(connection_factory=factory)


# ── Helpers ────────────────────────────────────────────────


def _record(
    options: SessionStateDatabaseOptions,
    *,
    session_key: str = "agent:main:watched",
    agent_id: str = "main",
    kind: str = "human_direct_message",
    actor_type: str = "human",
    dedupe_key: Optional[str] = None,
    summary: str = "human message via slack",
    payload: Optional[dict[str, Any]] = None,
    now: int = 1_000,
) -> bool:
    return record_session_state_event(
        {
            "sessionKey": session_key,
            "agentId": agent_id,
            "kind": kind,
            "actorType": actor_type,
            **({"dedupeKey": dedupe_key} if dedupe_key else {}),
            "summary": summary,
            **({"payload": payload} if payload else {}),
        },
        SessionStateDatabaseOptions(
            connection_factory=options.connection_factory, now=now
        ),
    )


class TestClassifySessionStateActor:
    def test_recognizes_known_actor_types(self) -> None:
        for known in ("user", "operator", "human", "system"):
            assert classify_session_state_actor(actor_type=known) == known

    def test_lowercases_unknown_actor_type(self) -> None:
        assert classify_session_state_actor(actor_type="User") == "user"

    def test_unknown_actor_type_falls_back_to_system(self) -> None:
        assert classify_session_state_actor(actor_type="robot") == "system"

    def test_accepts_actor_dict_shape(self) -> None:
        assert (
            classify_session_state_actor(actor={"actorType": "operator"})
            == "operator"
        )


class TestRecordSessionStateEvent:
    def test_records_event_and_updates_head(self, options: SessionStateDatabaseOptions) -> None:
        assert (
            _record(
                options,
                dedupe_key="event-1",
                now=1_000,
            )
            is True
        )
        assert get_session_state_version("agent:main:watched", "main", options) >= 1

    def test_dedupe_rejects_duplicate(self, options: SessionStateDatabaseOptions) -> None:
        assert _record(options, dedupe_key="dup", now=1_000) is True
        # Same dedupe key → drop.
        assert _record(options, dedupe_key="dup", now=2_000) is False
        events = list_session_state_events_since(
            "agent:main:watched", "main", 0, 10, options
        )["events"]
        assert len(events) == 1

    def test_version_reflects_latest_sequence(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        _record(options, dedupe_key="a", now=1_000)
        _record(options, dedupe_key="b", now=2_000)
        _record(options, dedupe_key="c", now=3_000)
        version = get_session_state_version("agent:main:watched", "main", options)
        assert version == 3

    def test_get_session_state_versions_returns_all(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        _record(
            options,
            session_key="agent:main:one",
            dedupe_key="a",
            now=1_000,
        )
        _record(
            options,
            session_key="agent:main:two",
            dedupe_key="b",
            now=2_000,
        )
        versions = get_session_state_versions(options)
        assert "agent:main:one" in versions
        assert "agent:main:two" in versions


class TestListSessionStateEventsSince:
    def test_returns_empty_when_at_head(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        _record(options, dedupe_key="a", now=1_000)
        result = list_session_state_events_since(
            "agent:main:watched", "main", 999, 10, options
        )
        assert result["events"] == []
        assert result["version"] >= 1

    def test_returns_events_in_sequence_order(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        _record(options, dedupe_key="a", now=1_000)
        _record(options, dedupe_key="b", now=2_000)
        _record(options, dedupe_key="c", now=3_000)
        result = list_session_state_events_since(
            "agent:main:watched", "main", 0, 10, options
        )
        events = result["events"]
        assert len(events) == 3
        # The summaries are recorded in order.
        assert [e["kind"] for e in events] == [
            "human_direct_message",
            "human_direct_message",
            "human_direct_message",
        ]

    def test_respects_limit(self, options: SessionStateDatabaseOptions) -> None:
        for i in range(5):
            _record(
                options,
                dedupe_key=f"k{i}",
                now=1_000 + i,
            )
        result = list_session_state_events_since(
            "agent:main:watched", "main", 0, 2, options
        )
        assert len(result["events"]) == 2


class TestAcknowledgeSessionStateNotices:
    def test_returns_true_for_existing_cursor(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        register_session_state_watch(
            watcher_session_key="agent:main:watcher",
            target_session_key="agent:main:watched",
            options=options,
        )
        assert (
            acknowledge_session_state_notices(
                "agent:main:watched",
                "main",
                "agent:main:watcher",
                100,
                options,
            )
            is True
        )

    def test_returns_false_for_missing_cursor(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            acknowledge_session_state_notices(
                "agent:main:watched",
                "main",
                "agent:main:watcher",
                100,
                options,
            )
            is False
        )


class TestHandleSessionStateSessionReset:
    def test_clears_events_head_and_watchers(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        _record(options, dedupe_key="a", now=1_000)
        register_session_state_watch(
            watcher_session_key="agent:main:watcher",
            target_session_key="agent:main:watched",
            options=options,
        )
        handle_session_state_session_reset(
            "agent:main:watched", "main", options
        )
        assert (
            get_session_state_version("agent:main:watched", "main", options)
            == 0
        )
        assert (
            list_session_state_events_since(
                "agent:main:watched", "main", 0, 10, options
            )["events"]
            == []
        )


class TestRegisterSessionStateWatch:
    def test_registers_explicit_cursor(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            register_session_state_watch(
                watcher_session_key="agent:main:watcher",
                target_session_key="agent:main:watched",
                options=options,
            )
            is True
        )

    def test_rejects_same_watcher_and_target(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            register_session_state_watch(
                watcher_session_key="agent:main:watched",
                target_session_key="agent:main:watched",
                options=options,
            )
            is False
        )

    def test_rejects_invalid_provenance(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            register_session_state_watch(
                watcher_session_key="agent:main:watcher",
                target_session_key="agent:main:watched",
                provenance="bogus",  # type: ignore[arg-type]
                options=options,
            )
            is False
        )


class TestRegisterMainSessionGroupWatch:
    def test_registers_ambient_group_watches(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        accepted = register_main_session_group_watch(
            agent_id="main",
            targets=["agent:main:one", "agent:main:two"],
            options=options,
        )
        assert accepted == 2
        targets = list_ambient_group_watch_targets(options)
        assert set(targets) == {"agent:main:one", "agent:main:two"}


class TestRecordConvenienceHelpers:
    def test_record_session_compacted(self, options: SessionStateDatabaseOptions) -> None:
        assert (
            record_session_compacted(
                session_key="agent:main:watched",
                agent_id="main",
                options=options,
            )
            is True
        )

    def test_record_session_goal_changed(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            record_session_goal_changed(
                session_key="agent:main:watched",
                agent_id="main",
                options=options,
            )
            is True
        )

    def test_record_subagent_spawned(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            record_subagent_spawned(
                session_key="agent:main:watched",
                agent_id="main",
                subagent_id="sub-1",
                options=options,
            )
            is True
        )

    def test_record_subagent_terminal_state(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        assert (
            record_subagent_terminal_state(
                session_key="agent:main:watched",
                agent_id="main",
                subagent_id="sub-1",
                terminal="completed",
                options=options,
            )
            is True
        )

    def test_record_session_human_direct_message_clamps_occurred_at(
        self, options: SessionStateDatabaseOptions
    ) -> None:
        now = 100 * 24 * 60 * 60_000
        ancient = 1_000  # far beyond the 24h clamp window
        assert (
            record_session_human_direct_message(
                {
                    "sessionKey": "agent:main:watched",
                    "agentId": "main",
                    "actor": {"actorType": "human"},
                    "channel": "discord",
                    "dedupeKey": "clamp-1",
                    "occurredAt": ancient,
                },
                SessionStateDatabaseOptions(
                    connection_factory=options.connection_factory, now=now
                ),
            )
            is True
        )
        result = list_session_state_events_since(
            "agent:main:watched", "main", 0, 10, options
        )
        # occurredAt is clamped into [now - 24h, now].
        assert result["events"][0]["occurredAt"] == now - 24 * 60 * 60_000


class TestSweepSessionStateWatchNotices:
    def test_sweep_returns_count(self, options: SessionStateDatabaseOptions) -> None:
        # Recent event: not pruned.
        _record(options, dedupe_key="recent", now=2_000)
        # Old event: 40 days ago, beyond the 30-day window.
        ancient = 2_000 - 40 * 24 * 60 * 60_000
        _record(
            options,
            dedupe_key="ancient",
            now=ancient,
        )
        pruned = sweep_session_state_watch_notices(
            SessionStateDatabaseOptions(
                connection_factory=options.connection_factory, now=2_000
            )
        )
        assert pruned >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
