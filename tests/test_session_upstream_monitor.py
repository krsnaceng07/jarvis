"""Tests for src/sessions/session_upstream_monitor.py.

Mirrors a focused subset of OpenClaw's
``src/sessions/session-upstream-monitor.test.ts`` — the parts
that exercise the monitor's own logic without depending on
the full session-state-events / session-accessor / transcript
plumbing. The DI option bag lets the test inject
``load_entry``, ``is_run_active``,
``load_own_recent_user_texts``, ``record_state_event``, and
``record_human_direct_message``; the test recorder tracks
``(state_event, human_direct_message)`` tuples for assertion.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

import pytest

from src.sessions.session_upstream_links import (
    SCHEMA_UPSTREAM_LINKS,
    SCHEMA_WATCH_CURSORS,
    SessionUpstreamLinkOptions,
    register_session_upstream_watch,
    upsert_session_upstream_link,
)
from src.sessions.session_upstream_monitor import (
    SessionUpstreamMonitorOptions,
    _upstream_source_key,
    run_session_upstream_monitor_tick,
)


# ── Test harness ───────────────────────────────────────────


class TestRecorder:
    """In-memory recorder that captures the two event kinds the monitor emits.

    Mirrors the shape of the OpenClaw session-state-events
    helpers (``recordStateEvent`` for ``upstream_missing``,
    ``recordHumanDirectMessage`` for ``human_direct_message``).
    Dedupe is keyed on ``dedupeKey`` so a repeated activity id
    from the same source on the next tick is collapsed — the
    real session-state-events helper persists this state in
    the canonical store.
    """

    def __init__(self) -> None:
        self.state_events: list[dict[str, Any]] = []
        self.human_direct: list[dict[str, Any]] = []
        self._seen_state: set[str] = set()
        self._seen_human: set[str] = set()

    def record_state_event(self, payload: dict[str, Any], _opts: dict[str, Any]) -> bool:
        key = payload.get("dedupeKey", "")
        if key in self._seen_state:
            return False
        self._seen_state.add(key)
        self.state_events.append(dict(payload))
        return True

    def record_human_direct_message(self, payload: dict[str, Any], _opts: dict[str, Any]) -> bool:
        key = payload.get("dedupeKey", "")
        if key in self._seen_human:
            return False
        self._seen_human.add(key)
        self.human_direct.append(dict(payload))
        return True


@pytest.fixture
def state_dir_db(tmp_path):
    """Per-test SQLite state DB with the two upstream-link tables.

    Mirrors the ``createDatabaseOptions`` helper in the TS test.
    """
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # Bootstrap schema.
    bootstrap = factory()
    try:
        bootstrap.executescript(
            f"{SCHEMA_UPSTREAM_LINKS};\n{SCHEMA_WATCH_CURSORS};"
        )
        bootstrap.commit()
    finally:
        bootstrap.close()

    return SessionUpstreamLinkOptions(connection_factory=factory)


def _create_link(
    session_key: str,
    catalog_id: str,
    state: SessionUpstreamLinkOptions,
    *,
    watched: bool = True,
    thread_id: Optional[str] = None,
    upstream_ref: Optional[dict[str, Any]] = None,
) -> None:
    upsert_session_upstream_link(
        {
            "sessionKey": session_key,
            "agentId": "main",
            "catalogId": catalog_id,
            "hostId": "gateway:local",
            "threadId": thread_id or f"thread-{catalog_id}",
            "upstreamKind": "claude-cli" if catalog_id == "claude" else "codex-app-server",
            "upstreamRef": upstream_ref or {"source": catalog_id},
            "marker": {"offset": 0},
        },
        state,
    )
    if watched:
        register_session_upstream_watch(
            watcher_session_key="agent:main:main",
            target_session_key=session_key,
            options=state,
        )


def _provider(
    provider_id: str,
    check_upstream_activity,
) -> dict[str, Any]:
    return {
        "id": provider_id,
        "label": provider_id,
        "list": None,
        "read": None,
        "checkUpstreamActivity": check_upstream_activity,
    }


def _make_options(
    state: SessionUpstreamLinkOptions,
    recorder: TestRecorder,
    providers: list[dict[str, Any]],
    *,
    now: Optional[int] = None,
    is_run_active=None,
    load_entry=None,
) -> SessionUpstreamMonitorOptions:
    def _now() -> int:
        return now if now is not None else 0

    if load_entry is None:
        def _load_entry(**kwargs):
            return {"sessionId": f"session-{kwargs['sessionKey']}"}

        load_entry = _load_entry

    async def _loader(_probe, _entry, _opts):
        return []

    return SessionUpstreamMonitorOptions(
        providers=providers,
        now=_now,
        load_entry=load_entry,
        is_run_active=is_run_active,
        load_own_recent_user_texts=_loader,
        record_state_event=recorder.record_state_event,
        record_human_direct_message=recorder.record_human_direct_message,
        connection_factory=state.connection_factory,
    )


# ── Tests ──────────────────────────────────────────────────


class TestSessionUpstreamMonitor:
    def test_records_watched_activity_once_and_advances_its_marker(
        self, state_dir_db: SessionUpstreamLinkOptions
    ) -> None:
        recorder = TestRecorder()
        watched = "agent:main:adopted:watched"
        unwatched = "agent:main:adopted:unwatched"
        _create_link(watched, "claude", state_dir_db)
        _create_link(unwatched, "claude", state_dir_db, watched=False)
        check_calls: list[list[dict[str, Any]]] = []
        scan_n = {"n": 0}

        async def check(probes):
            check_calls.append(list(probes))
            scan_n["n"] += 1
            return [
                {
                    "kind": "activity",
                    "sessionKey": p["sessionKey"],
                    "occurredAt": 2_000,
                    "humanTurns": 1,
                    "nextMarker": {"offset": 8},
                    "dedupeId": "8",
                }
                for p in probes
            ]

        provider = _provider("claude", check)
        options = _make_options(
            state_dir_db, recorder, [provider], now=3_000
        )
        missing_counts: dict = {}

        import asyncio

        asyncio.run(
            run_session_upstream_monitor_tick(options, missing_counts)
        )
        options2 = _make_options(
            state_dir_db, recorder, [provider], now=4_000
        )
        asyncio.run(
            run_session_upstream_monitor_tick(options2, missing_counts)
        )

        # check should be called twice (one per tick).
        assert len(check_calls) == 2
        # First call: only the watched link is probed.
        assert check_calls[0][0]["sessionKey"] == watched
        assert check_calls[0][0]["marker"] == {"offset": 0}
        # Second call: marker has advanced to {offset: 8}.
        assert check_calls[1][0]["sessionKey"] == watched
        assert check_calls[1][0]["marker"] == {"offset": 8}

        # One human_direct_message recorded.
        assert len(recorder.human_direct) == 1
        evt = recorder.human_direct[0]
        # The kind lives on the recorded state event, not on
        # the recorder payload (the human_direct_message
        # helper handles kind internally).
        assert "kind" not in evt
        assert evt["channel"] == "claude"
        assert evt["occurredAt"] == 2_000
        # Source identity is hashed into the dedupe key.
        source_key = _upstream_source_key(
            {"hostId": "gateway:local", "threadId": "thread-claude", "upstreamRef": {"source": "claude"}}
        )
        assert evt["dedupeKey"] == f"upstream:{watched}:{source_key}:8"

    def test_records_one_upstream_missing_event_after_three_misses_and_removes_link(
        self, state_dir_db: SessionUpstreamLinkOptions
    ) -> None:
        recorder = TestRecorder()
        session_key = "agent:main:adopted:missing"
        _create_link(session_key, "claude", state_dir_db)

        async def check(probes):
            return [
                {"kind": "missing", "sessionKey": p["sessionKey"]} for p in probes
            ]

        provider = _provider("claude", check)
        options = _make_options(
            state_dir_db, recorder, [provider], now=3_000
        )
        missing_counts: dict = {}

        import asyncio

        for _ in range(4):
            asyncio.run(
                run_session_upstream_monitor_tick(options, missing_counts)
            )

        # Provider should only be called 3 times (4th tick: link removed).
        from src.sessions.session_upstream_links import read_session_upstream_link

        assert read_session_upstream_link(session_key, "main", state_dir_db) is None
        assert len(missing_counts) == 0
        # One upstream_missing state event recorded.
        assert len(recorder.state_events) == 1
        evt = recorder.state_events[0]
        assert evt["kind"] == "upstream_missing"
        assert evt["actorType"] == "system"
        assert evt["summary"] == "upstream missing via claude"
        assert evt["payload"] == {"channel": "claude"}

    def test_prunes_missing_counters_when_link_leaves_watched_set(
        self, state_dir_db: SessionUpstreamLinkOptions
    ) -> None:
        recorder = TestRecorder()
        session_key = "agent:main:adopted:missing-pruned"
        _create_link(session_key, "claude", state_dir_db)

        check_calls: list[int] = []

        async def check(probes):
            check_calls.append(len(probes))
            return [{"kind": "missing", "sessionKey": p["sessionKey"]} for p in probes]

        provider = _provider("claude", check)
        options = _make_options(state_dir_db, recorder, [provider])
        missing_counts: dict = {}

        import asyncio

        asyncio.run(
            run_session_upstream_monitor_tick(options, missing_counts)
        )
        assert len(missing_counts) == 1

        from src.sessions.session_upstream_links import delete_session_upstream_link

        delete_session_upstream_link(session_key, "main", state_dir_db)
        asyncio.run(
            run_session_upstream_monitor_tick(options, missing_counts)
        )

        # Provider only called once (the un-watched link is filtered out).
        assert len(check_calls) == 1
        assert len(missing_counts) == 0

    def test_isolates_provider_failures(
        self, state_dir_db: SessionUpstreamLinkOptions
    ) -> None:
        recorder = TestRecorder()
        codex_session = "agent:main:adopted:codex"
        _create_link("agent:main:adopted:claude", "claude", state_dir_db)
        _create_link(codex_session, "codex", state_dir_db)

        async def claude_check(_probes):
            raise RuntimeError("broken")

        codex_calls: list[int] = []

        async def codex_check(probes):
            codex_calls.append(len(probes))
            return [
                {
                    "kind": "activity",
                    "sessionKey": codex_session,
                    "occurredAt": 5_000,
                    "humanTurns": 1,
                    "nextMarker": {"turnId": "turn-2"},
                    "dedupeId": "turn-2",
                }
            ]

        providers = [
            _provider("claude", claude_check),
            _provider("codex", codex_check),
        ]
        options = _make_options(state_dir_db, recorder, providers, now=3_000)

        import asyncio

        asyncio.run(run_session_upstream_monitor_tick(options))

        # codex still got called even though claude threw.
        assert len(codex_calls) == 1
        # codex session got a human_direct_message.
        assert len(recorder.human_direct) == 1
        assert recorder.human_direct[0]["channel"] == "codex"

    def test_defers_active_runs_without_advancing_marker(
        self, state_dir_db: SessionUpstreamLinkOptions
    ) -> None:
        recorder = TestRecorder()
        session_key = "agent:main:adopted:active"
        _create_link(session_key, "claude", state_dir_db)

        check_calls: list[int] = []

        async def check(probes):
            check_calls.append(len(probes))
            return []

        provider = _provider("claude", check)
        # When the run is active, the provider is not called.
        options_active = _make_options(
            state_dir_db,
            recorder,
            [provider],
            is_run_active=lambda _session_id: True,
        )
        import asyncio

        asyncio.run(run_session_upstream_monitor_tick(options_active))
        assert len(check_calls) == 0

        # When the run is no longer active, the provider IS called.
        options_idle = _make_options(
            state_dir_db,
            recorder,
            [provider],
            is_run_active=lambda _session_id: False,
        )
        asyncio.run(run_session_upstream_monitor_tick(options_idle))
        assert len(check_calls) == 1

    def test_preserves_coalesced_upstream_burst_count_in_event_payload(
        self, state_dir_db: SessionUpstreamLinkOptions
    ) -> None:
        recorder = TestRecorder()
        session_key = "agent:main:adopted:burst"
        _create_link(session_key, "codex", state_dir_db)

        async def check(probes):
            return [
                {
                    "kind": "activity",
                    "sessionKey": session_key,
                    "occurredAt": 2_000,
                    "humanTurns": 3,
                    "nextMarker": {"turnId": "turn-3", "userMessageCount": 1},
                    "dedupeId": "turn-3:1",
                }
            ]

        provider = _provider("codex", check)
        options = _make_options(state_dir_db, recorder, [provider], now=3_000)

        import asyncio

        asyncio.run(run_session_upstream_monitor_tick(options))

        assert len(recorder.human_direct) == 1
        assert recorder.human_direct[0]["payload"] == {"turns": 3}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
