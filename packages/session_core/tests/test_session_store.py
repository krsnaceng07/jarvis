"""Tests for jarvis_session_core session store."""

from __future__ import annotations

from jarvis_session_core.session_store import (
    InMemorySessionStore,
    SessionRecord,
)


def test_in_memory_session_store() -> None:
    store = InMemorySessionStore()

    record = store.get_or_create(
        session_key="agent:main:direct:user1",
        agent_id="main",
        kind="direct",
    )
    assert isinstance(record, SessionRecord)
    assert record.session_key == "agent:main:direct:user1"
    assert record.agent_id == "main"
    assert record.kind == "direct"
    assert len(record.entries) == 0

    updated = store.append_entry(
        "agent:main:direct:user1",
        {"id": "1", "kind": "user_message", "payload": {"text": "hello"}},
    )
    assert len(updated.entries) == 1
    assert updated.entries[0]["payload"]["text"] == "hello"

    retrieved = store.get("agent:main:direct:user1")
    assert retrieved is not None
    assert len(retrieved.entries) == 1

    search_res = store.search_sessions("hello")
    assert len(search_res) == 1
    assert search_res[0]["session_key"] == "agent:main:direct:user1"

    store.set_route_pin("agent:main:direct:user1", model_ref="openai/gpt-4o")
    pinned = store.get("agent:main:direct:user1")
    assert pinned is not None
    assert pinned.model_ref == "openai/gpt-4o"

    store.rollover("agent:main:direct:user1")
    assert store.get("agent:main:direct:user1") is None
