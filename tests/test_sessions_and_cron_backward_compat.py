"""Test backward compatibility of src/sessions and src/cron re-exports."""
from __future__ import annotations

from datetime import datetime

import src.cron as cron_module
import src.sessions as sessions_module
from src.cron import CronDecl, CronRunner, cron_matches, field_matches
from src.sessions import (
    InMemorySessionStore,
    SessionRecord,
    SessionStore,
    classify_session_kind,
    parse_agent_session_key,
    to_agent_request_session_key,
)
from src.sessions.session_store import SessionStore as DirectStoreImport


def test_src_sessions_reexports() -> None:
    assert classify_session_kind("agent:main:direct:u1") == "direct"
    assert sessions_module.classify_session_kind("agent:main:direct:u1") == "direct"
    parsed = parse_agent_session_key("agent:main:direct:u1")
    assert parsed is not None
    assert parsed.agent_id == "main"
    assert to_agent_request_session_key("agent:main:direct:u1") == "direct:u1"

    store = InMemorySessionStore()
    record = store.get_or_create(session_key="k1", agent_id="a1", kind="direct")
    assert isinstance(record, SessionRecord)
    assert DirectStoreImport is SessionStore


def test_src_cron_reexports() -> None:
    assert cron_module.CronRunner is CronRunner
    assert cron_module.CronDecl is CronDecl
    assert field_matches("*", 10, 0, 59)
    assert cron_matches("* * * * *", datetime(2026, 9, 30, 12, 0))
    runner = CronRunner()
    assert len(runner.list()) == 0
