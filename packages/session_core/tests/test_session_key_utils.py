"""Tests for jarvis_session_core session key utils."""

from __future__ import annotations

from jarvis_session_core.classify_session_kind import (
    classify_session_kind,
    is_valid_session_kind,
)
from jarvis_session_core.session_key_utils import (
    get_subagent_depth,
    is_acp_session_key,
    is_cron_run_session_key,
    is_cron_session_key,
    is_subagent_session_key,
    normalize_session_key_preserving_opaque_peer_ids,
    normalize_session_peer_id,
    parse_agent_session_key,
    parse_cron_run_scope_suffix,
    parse_thread_session_suffix,
    to_agent_request_session_key,
)


def test_classify_session_kind() -> None:
    assert is_valid_session_kind("direct")
    assert is_valid_session_kind("channel")
    assert is_valid_session_kind("thread")
    assert not is_valid_session_kind("foo")

    assert classify_session_kind("agent:main:direct:user1") == "direct"
    assert classify_session_kind("agent:main:channel:general") == "channel"
    assert classify_session_kind("agent:main:channel:general:thread:123") == "thread"
    assert classify_session_kind("agent:main:cron:job1") == "cron"


def test_parse_agent_session_key() -> None:
    parsed = parse_agent_session_key("agent:main:direct:user1")
    assert parsed is not None
    assert parsed.agent_id == "main"
    assert parsed.rest == "direct:user1"
    # Test dict-like access compatibility
    assert parsed["agentId"] == "main"
    assert parsed["rest"] == "direct:user1"


def test_to_agent_request_session_key() -> None:
    assert to_agent_request_session_key("agent:main:direct:user1") == "direct:user1"
    assert to_agent_request_session_key("direct:user1") == "direct:user1"
    assert to_agent_request_session_key("") is None


def test_subagent_and_cron() -> None:
    assert is_cron_session_key("agent:main:cron:hourly")
    assert is_cron_run_session_key("agent:main:cron:hourly:run:run123")
    parsed_cron = parse_cron_run_scope_suffix("agent:main:cron:hourly:run:run123")
    assert parsed_cron.base_session_key == "agent:main:cron:hourly"
    assert parsed_cron.run_id == "run123"

    assert is_subagent_session_key("agent:main:subagent:task1")
    assert get_subagent_depth("agent:main:subagent:task1") == 1
    assert get_subagent_depth("agent:main:subagent:task1:subagent:task2") == 2

    assert is_acp_session_key("agent:main:acp:session1")

    thread_parsed = parse_thread_session_suffix("agent:main:channel:dev:thread:t99")
    assert thread_parsed.base_session_key == "agent:main:channel:dev"
    assert thread_parsed.thread_id == "t99"

    norm_peer = normalize_session_peer_id(
        {"channel": "discord", "peerKind": "direct", "peerId": " UserX "}
    )
    assert norm_peer == "userx"

    norm_key = normalize_session_key_preserving_opaque_peer_ids("AGENT:MAIN:DIRECT:USER1")
    assert norm_key == "agent:main:direct:user1"
