"""Phase 5.14 — minimal sessions surface tests.

OpenClaw parity: ports focused subsets of
``src/sessions/session-id.test.ts`` +
``src/sessions/session-id-resolution.test.ts`` +
``src/sessions/classify-session-kind.ts`` (no dedicated
OpenClaw test file) + an in-memory ``SessionStore`` smoke
test.

The full OpenClaw session surface (38 files, 24K LOC) is
deferred to a follow-up phase. This slice lands the
minimum the ``agent_runtime`` + ``runner`` (Phase 5.15)
need: a UUID-shape helper, a kind classifier, and a
thread-safe in-memory store.

Python adaptations:
- ``expect(value).toBe(true|false)`` becomes a direct
  ``assert`` on the helper's boolean return.
- The OpenClaw session-store lives in
  ``src/sessions/`` alongside many other files; the Python
  port exposes a single ``InMemorySessionStore`` class
  with a focused protocol surface.
"""
from __future__ import annotations

import pytest

from src.sessions import (
    InMemorySessionStore,
    SessionRecord,
    classify_session_kind,
    get_default_session_store,
    is_valid_session_kind,
    looks_like_session_id,
    reset_default_session_store,
)


# ---------------------------------------------------------------------------
# looks_like_session_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("123e4567-e89b-12d3-a456-426614174000", True),
        ("00000000-0000-0000-0000-000000000000", True),
        ("ABCDEF12-3456-7890-ABCD-EF1234567890", True),
        ("", False),
        ("   ", False),
        ("not-a-uuid", False),
        ("123e4567e89b12d3a456426614174000", False),  # missing dashes
        ("123e4567-e89b-12d3-a456-42661417400", False),  # too short
        ("123e4567-e89b-12d3-a456-4266141740000", False),  # too long
    ],
)
def test_looks_like_session_id(value, expected):
    assert looks_like_session_id(value) is expected


def test_looks_like_session_id_rejects_non_string():
    assert looks_like_session_id(None) is False
    assert looks_like_session_id(123) is False
    assert looks_like_session_id({}) is False


# ---------------------------------------------------------------------------
# classify_session_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "unknown"),
        ("", "unknown"),
        ("unknown", "unknown"),
        ("UNKNOWN", "unknown"),
        # Direct sessions: "agent:<id>:direct:user" or "agent:<id>:dm:user".
        ("agent:main:direct:user-1", "direct"),
        ("agent:main:dm:user-1", "direct"),
        # Channel / group sessions: "agent:<id>:<channel>:<kind>:<id>".
        ("agent:main:telegram:group:g1", "channel"),
        ("agent:main:discord:channel:c1", "channel"),
        ("agent:main:matrix:room:r1", "channel"),
        # Thread sessions.
        ("agent:main:channel:c1:thread:t1", "thread"),
        # Cron sessions: marker is the :cron: token.
        ("agent:main:cron:job-1", "cron"),
        ("agent:main:cron:job-1:run:run-1", "cron"),
        # Bare / malformed inputs land in "unknown".
        ("agent:main", "unknown"),
        ("main", "unknown"),
    ],
)
def test_classify_session_kind(value, expected):
    assert classify_session_kind(value) == expected


def test_is_valid_session_kind():
    for kind in ("direct", "channel", "thread", "cron", "unknown"):
        assert is_valid_session_kind(kind) is True
    for kind in ("invalid", "", None, 42):
        assert is_valid_session_kind(kind) is False


# ---------------------------------------------------------------------------
# InMemorySessionStore
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    s = InMemorySessionStore()
    yield s
    s.reset()


def test_in_memory_store_get_or_create_returns_new_record(store):
    record = store.get_or_create(
        session_key="agent:main:main", agent_id="main", kind="direct"
    )
    assert isinstance(record, SessionRecord)
    assert record.session_key == "agent:main:main"
    assert record.agent_id == "main"
    assert record.kind == "direct"
    assert record.entries == ()
    assert record.created_at == record.updated_at


def test_in_memory_store_get_or_create_is_idempotent(store):
    record_a = store.get_or_create(
        session_key="agent:main:main", agent_id="main", kind="direct"
    )
    record_b = store.get_or_create(
        session_key="agent:main:main", agent_id="main", kind="channel"
    )
    # Same record returned; the second call does not overwrite
    # the kind.
    assert record_a is record_b
    assert record_b.kind == "direct"


def test_in_memory_store_append_entry_updates_record(store):
    record = store.get_or_create(
        session_key="agent:main:main", agent_id="main", kind="direct"
    )
    updated = store.append_entry(
        "agent:main:main", {"id": "msg-1", "kind": "user_message", "payload": {"text": "hi"}}
    )
    assert len(updated.entries) == 1
    assert updated.entries[0]["id"] == "msg-1"
    # Append again.
    again = store.append_entry(
        "agent:main:main", {"id": "msg-2", "kind": "assistant_message", "payload": {"text": "hello"}}
    )
    assert len(again.entries) == 2
    assert again.entries[1]["id"] == "msg-2"
    # Original record is unchanged (immutable update).
    assert len(record.entries) == 0


def test_in_memory_store_append_entry_raises_for_missing_session(store):
    with pytest.raises(KeyError):
        store.append_entry(
            "agent:main:does-not-exist", {"id": "x", "kind": "user_message", "payload": {}}
        )


def test_in_memory_store_list_sessions_filtered_by_agent(store):
    store.get_or_create(session_key="agent:main:main", agent_id="main", kind="direct")
    store.get_or_create(
        session_key="agent:ops:incident-1", agent_id="ops", kind="direct"
    )
    main_sessions = store.list_sessions(agent_id="main")
    assert len(main_sessions) == 1
    assert main_sessions[0].agent_id == "main"
    all_sessions = store.list_sessions()
    assert len(all_sessions) == 2


def test_in_memory_store_get_returns_none_for_missing(store):
    assert store.get("agent:main:missing") is None


def test_in_memory_store_get_returns_record_after_create(store):
    created = store.get_or_create(
        session_key="agent:main:main", agent_id="main", kind="direct"
    )
    fetched = store.get("agent:main:main")
    assert fetched is created


# ---------------------------------------------------------------------------
# default store singleton
# ---------------------------------------------------------------------------


def test_default_store_is_singleton():
    a = get_default_session_store()
    b = get_default_session_store()
    assert a is b
    # Reset clears state but keeps the same instance.
    reset_default_session_store()
    c = get_default_session_store()
    assert a is c
