"""Tests for src/sessions/session_upstream_links.py.

Mirrors OpenClaw's ``src/sessions/session-upstream-links.test.ts``.

Tests use a temp-file SQLite DB so each ``connection_factory``
call opens a fresh connection against the same on-disk state
(mirroring the openclaw state DB's one-file-per-process model).
The watch-cursor table is seeded via the
``register_session_upstream_watch`` test-facade helper.
"""
from __future__ import annotations

import sqlite3

import pytest

from src.sessions.session_upstream_links import (
    SCHEMA_UPSTREAM_LINKS,
    SCHEMA_WATCH_CURSORS,
    SessionUpstreamLinkOptions,
    delete_session_upstream_link,
    list_watched_session_upstream_links,
    read_session_upstream_link,
    register_session_upstream_watch,
    update_session_upstream_link_marker,
    upsert_session_upstream_link,
)


@pytest.fixture
def options(tmp_path) -> SessionUpstreamLinkOptions:
    """Create a fresh file-backed SQLite DB per test."""
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # Bootstrap the schema once. The port's lazy ensure-schema
    # helper also creates these tables, but we do it eagerly here
    # to avoid the first-write race.
    bootstrap = factory()
    try:
        bootstrap.executescript(
            f"{SCHEMA_UPSTREAM_LINKS};\n{SCHEMA_WATCH_CURSORS};"
        )
        bootstrap.commit()
    finally:
        bootstrap.close()

    return SessionUpstreamLinkOptions(connection_factory=factory)


def _upsert_link(
    session_key: str,
    catalog_id: str,
    options: SessionUpstreamLinkOptions,
    *,
    now: int = 100,
) -> None:
    upsert_session_upstream_link(
        {
            "sessionKey": session_key,
            "agentId": "main",
            "catalogId": catalog_id,
            "hostId": "gateway:local",
            "threadId": f"thread-{session_key}",
            "upstreamKind": (
                "claude-cli" if catalog_id == "claude" else "codex-app-server"
            ),
            "upstreamRef": {"source": session_key},
            "marker": {"offset": 1},
        },
        SessionUpstreamLinkOptions(
            connection_factory=options.connection_factory, now=now
        ),
    )


class TestSessionUpstreamLinks:
    def test_stores_links_and_returns_only_watcher_joined_rows_grouped_by_catalog(
        self, options: SessionUpstreamLinkOptions
    ) -> None:
        watched = "agent:main:adopted:watched"
        unwatched = "agent:main:adopted:unwatched"
        _upsert_link(watched, "claude", options)
        _upsert_link(unwatched, "codex", options)
        assert (
            register_session_upstream_watch(
                watcher_session_key="agent:main:main",
                target_session_key=watched,
                options=options,
            )
            is True
        )

        result = list_watched_session_upstream_links(options)
        assert list(result.keys()) == ["claude"]
        assert result["claude"][0]["sessionKey"] == watched
        assert result["claude"][0]["marker"] == {"offset": 1}
        assert result["claude"][0]["upstreamRef"] == {"source": watched}

        update_session_upstream_link_marker(
            watched,
            "main",
            {"offset": 9},
            SessionUpstreamLinkOptions(
                connection_factory=options.connection_factory, now=200
            ),
        )
        link = list_watched_session_upstream_links(options)["claude"][0]
        assert link["marker"] == {"offset": 9}
        assert link["lastScannedAt"] == 200
        assert link["updatedAt"] == 200

        delete_session_upstream_link(watched, "main", options)
        assert list_watched_session_upstream_links(options) == {}

    def test_preserves_marker_on_same_source_refresh_and_rebases_on_source_change(
        self, options: SessionUpstreamLinkOptions
    ) -> None:
        session_key = "agent:main:adopted:refresh"
        _upsert_link(session_key, "claude", options)
        register_session_upstream_watch(
            watcher_session_key="agent:main:main",
            target_session_key=session_key,
            options=options,
        )
        update_session_upstream_link_marker(
            session_key, "main", {"offset": 4}, options
        )

        # Same source: scan progress must survive.
        upsert_session_upstream_link(
            {
                "sessionKey": session_key,
                "agentId": "main",
                "catalogId": "claude",
                "hostId": "gateway:local",
                "threadId": f"thread-{session_key}",
                "upstreamKind": "claude-cli",
                "upstreamRef": {"source": session_key},
                "marker": {"offset": 99},
            },
            options,
        )
        link = list_watched_session_upstream_links(options)["claude"][0]
        assert link["upstreamRef"] == {"source": session_key}
        assert link["marker"] == {"offset": 4}

        # Source change: the old cursor is meaningless for the new
        # thread; rebase.
        upsert_session_upstream_link(
            {
                "sessionKey": session_key,
                "agentId": "main",
                "catalogId": "claude",
                "hostId": "gateway:local",
                "threadId": "thread-refreshed",
                "upstreamKind": "claude-cli",
                "upstreamRef": {"source": "rebased"},
                "marker": {"offset": 99},
            },
            options,
        )
        link = list_watched_session_upstream_links(options)["claude"][0]
        assert link["threadId"] == "thread-refreshed"
        assert link["upstreamRef"] == {"source": "rebased"}
        assert link["marker"] == {"offset": 99}

    def test_read_session_upstream_link_returns_none_when_missing(
        self, options: SessionUpstreamLinkOptions
    ) -> None:
        assert read_session_upstream_link("missing", "main", options) is None

    def test_update_session_upstream_link_marker_returns_false_on_stale_cas(
        self, options: SessionUpstreamLinkOptions
    ) -> None:
        _upsert_link("agent:main:cas", "claude", options)
        result = update_session_upstream_link_marker(
            "agent:main:cas",
            "main",
            {"offset": 5},
            SessionUpstreamLinkOptions(
                connection_factory=options.connection_factory,
                now=300,
                expected_updated_at=999,
            ),
        )
        assert result is False
        link = read_session_upstream_link("agent:main:cas", "main", options)
        assert link is not None
        assert link["marker"] == {"offset": 1}
        assert link["updatedAt"] == 100

    def test_ambiguous_multi_agent_links_are_dropped(
        self, options: SessionUpstreamLinkOptions
    ) -> None:
        # Two different agents adopt the same session_key. The
        # key-only cursor join cannot disambiguate; the
        # fail-closed rule drops every link for the duplicated
        # key.
        upsert_session_upstream_link(
            {
                "sessionKey": "agent:main:adopted:dup",
                "agentId": "agent-1",
                "catalogId": "claude",
                "hostId": "gateway:local",
                "threadId": "thread-1",
                "upstreamKind": "claude-cli",
                "upstreamRef": {"source": "1"},
                "marker": {"offset": 1},
            },
            options,
        )
        upsert_session_upstream_link(
            {
                "sessionKey": "agent:main:adopted:dup",
                "agentId": "agent-2",
                "catalogId": "claude",
                "hostId": "gateway:local",
                "threadId": "thread-2",
                "upstreamKind": "claude-cli",
                "upstreamRef": {"source": "2"},
                "marker": {"offset": 2},
            },
            options,
        )
        register_session_upstream_watch(
            watcher_session_key="agent:main:main",
            target_session_key="agent:main:adopted:dup",
            options=options,
        )
        result = list_watched_session_upstream_links(options)
        # Fail-closed: drop ALL links for the duplicated key.
        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
