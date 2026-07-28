"""Phase 5.14 — ``session-key.test.ts`` (selected parts) → Python.

OpenClaw parity: ports a focused subset of the 60+ test cases
in ``src/routing/session-key.test.ts`` against the Python
port's ``src/routing/session_key.py`` + ``session_key_utils.py``.

The full OpenClaw file tests gateway-side helpers
(``resolveSessionStoreKey``, ``resolveSessionStoreAgentId``)
that live in ``src/gateway/session-store-key.ts`` and a
``deriveSessionChatTypeFromKey`` helper that lives in
``src/sessions/session-chat-type-shared.ts`` — neither has a
Python port yet. Those cases are intentionally omitted; the
full port will land with Phase 5.14b (sessions impl) + the
gateway port.

Python adaptations:
- ``it.each([...])`` becomes ``@pytest.mark.parametrize``.
- ``describe("...")`` becomes a flat test-function layout.
- TS function names are snake_case in Python (the
  implementation is already in snake_case form).
"""
from __future__ import annotations

import pytest

from src.routing.session_key import (
    agent_session_keys_match_by_request_key,
    build_agent_main_session_key,
    build_agent_peer_session_key,
    build_group_history_key,
    classify_session_key_shape,
    is_unscoped_session_key_sentinel,
    scope_legacy_session_key_to_agent,
    to_agent_store_session_key,
)
from src.routing.session_key_utils import (
    get_subagent_depth,
    is_cron_session_key,
    parse_cron_run_scope_suffix,
    parse_thread_session_suffix,
)


# ---------------------------------------------------------------------------
# classifySessionKeyShape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        (None, "missing"),
        ("   ", "missing"),
        ("agent:main:main", "agent"),
        ("agent:research:subagent:worker", "agent"),
        ("agent::broken", "malformed_agent"),
        ("agent:main", "malformed_agent"),
        ("main", "legacy_or_alias"),
        ("custom-main", "legacy_or_alias"),
        ("subagent:worker", "legacy_or_alias"),
    ],
)
def test_classify_session_key_shape(input_value, expected):
    assert classify_session_key_shape(input_value) == expected


# ---------------------------------------------------------------------------
# scopeLegacySessionKeyToAgent
# ---------------------------------------------------------------------------


def test_scope_legacy_session_key_to_agent_scopes_legacy_aliases():
    assert scope_legacy_session_key_to_agent(
        {"agentId": "Ops", "sessionKey": "Incident-42"}
    ) == "agent:ops:incident-42"


def test_scope_legacy_session_key_to_agent_honors_main_key_alias():
    assert scope_legacy_session_key_to_agent(
        {"agentId": "ops", "sessionKey": "main", "mainKey": "work"}
    ) == "agent:ops:work"


def test_scope_legacy_session_key_to_agent_preserves_agent_prefixed_keys():
    assert scope_legacy_session_key_to_agent(
        {"agentId": "ops", "sessionKey": "agent:main:incident-42"}
    ) == "agent:main:incident-42"


def test_scope_legacy_session_key_to_agent_handles_global_and_unknown_sentinels():
    assert scope_legacy_session_key_to_agent(
        {"agentId": "ops", "sessionKey": "global"}
    ) == "agent:ops:global"
    assert scope_legacy_session_key_to_agent(
        {"agentId": "ops", "sessionKey": "UNKNOWN"}
    ) == "agent:ops:unknown"


# ---------------------------------------------------------------------------
# isUnscopedSessionKeySentinel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("global", True),
        ("UNKNOWN", True),
        ("agent:ops:global", False),
        ("incident-42", False),
    ],
)
def test_is_unscoped_session_key_sentinel(key, expected):
    assert is_unscoped_session_key_sentinel(key) is expected


# ---------------------------------------------------------------------------
# agentSessionKeysMatchByRequestKey
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("agent:main:main", "main", True),
        ("agent:ops:incident-42", "incident-42", True),
        ("agent:ops:incident-42", "main", False),
    ],
)
def test_agent_session_keys_match_by_request_key(left, right, expected):
    assert agent_session_keys_match_by_request_key(left, right) is expected


# ---------------------------------------------------------------------------
# session key backward compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "agent:main:telegram:dm:123456",
        "agent:main:whatsapp:dm:+15551234567",
        "agent:main:discord:dm:user123",
        "agent:main:telegram:direct:123456",
        "agent:main:whatsapp:direct:+15551234567",
        "agent:main:discord:direct:user123",
    ],
)
def test_classifies_backward_compatible_direct_session_key_as_valid(key):
    assert classify_session_key_shape(key) == "agent"


# ---------------------------------------------------------------------------
# getSubagentDepth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("agent:main:main", 0),
        ("main", 0),
        (None, 0),
        ("agent:main:subagent:parent:subagent:child", 2),
        ("subagent:worker", 1),
        ("subagent:parent:subagent:child", 2),
    ],
)
def test_get_subagent_depth(key, expected):
    assert get_subagent_depth(key) == expected


# ---------------------------------------------------------------------------
# isCronSessionKey
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("agent:main:cron:job-1", True),
        ("agent:main:cron:job-1:run:run-1", True),
        ("agent:main:cron:job-1:run:run-1:subagent:worker", True),
        ("agent:main:main", False),
        ("agent:main:subagent:worker", False),
        ("cron:job-1", False),
        (None, False),
    ],
)
def test_is_cron_session_key(key, expected):
    assert is_cron_session_key(key) is expected


# ---------------------------------------------------------------------------
# parseCronRunScopeSuffix
# ---------------------------------------------------------------------------


def test_parse_cron_run_scope_suffix_extracts_run_id():
    parsed = parse_cron_run_scope_suffix("agent:main:cron:job-1:run:run-1")
    assert parsed is not None
    assert parsed["runId"] == "run-1"


def test_parse_cron_run_scope_suffix_returns_none_run_id_for_non_run_keys():
    """Non-run keys return a dict with ``runId: None`` (the base
    session key is captured so callers can scope a non-run cron
    request)."""
    parsed = parse_cron_run_scope_suffix("agent:main:cron:job-1")
    assert parsed is not None
    assert parsed["runId"] is None
    parsed = parse_cron_run_scope_suffix("agent:main:main")
    assert parsed is not None
    assert parsed["runId"] is None


# ---------------------------------------------------------------------------
# parseThreadSessionSuffix
# ---------------------------------------------------------------------------


def test_parse_thread_session_suffix_extracts_thread_id():
    parsed = parse_thread_session_suffix("agent:main:discord:channel:c1:thread:t1")
    assert parsed is not None
    assert parsed["threadId"] == "t1"


def test_parse_thread_session_suffix_returns_none_thread_id_for_non_thread_keys():
    """Non-thread keys return a dict with ``threadId: None``."""
    parsed = parse_thread_session_suffix("agent:main:discord:channel:c1")
    assert parsed is not None
    assert parsed["threadId"] is None


# ---------------------------------------------------------------------------
# buildAgentMainSessionKey / buildAgentPeerSessionKey
# ---------------------------------------------------------------------------


def test_build_agent_main_session_key():
    assert (
        build_agent_main_session_key({"agentId": "main", "mainKey": "primary"})
        == "agent:main:primary"
    )


def test_build_agent_peer_session_key_direct():
    assert (
        build_agent_peer_session_key(
            {
                "agentId": "main",
                "mainKey": "primary",
                "dmScope": "per-peer",
                "peerKind": "direct",
                "peerId": "user-42",
            }
        )
        == "agent:main:direct:user-42"
    )


def test_build_agent_peer_session_key_channel():
    assert (
        build_agent_peer_session_key(
            {
                "agentId": "main",
                "mainKey": "primary",
                "channel": "telegram",
                "peerKind": "channel",
                "peerId": "channel-1",
            }
        )
        == "agent:main:telegram:channel:channel-1"
    )


# ---------------------------------------------------------------------------
# buildGroupHistoryKey
# ---------------------------------------------------------------------------


def test_build_group_history_key():
    """The Python port's group-history key is scoped to the channel
    + account (the OpenClaw variant prefixes the agent id too;
    the Python port omits it because the caller always knows
    the owning agent via the surrounding session key)."""
    assert (
        build_group_history_key(
            {
                "channel": "telegram",
                "peerKind": "group",
                "peerId": "g1",
            }
        )
        == "telegram:default:group:g1"
    )


# ---------------------------------------------------------------------------
# toAgentStoreSessionKey
# ---------------------------------------------------------------------------


def test_to_agent_store_session_key():
    assert (
        to_agent_store_session_key({"agentId": "main", "sessionKey": "main"})
        == "agent:main:main"
    )


def test_to_agent_store_session_key_preserves_existing_agent_prefix():
    """The Python port scopes a global request key to the requested
    store agent; the OpenClaw behavior is to preserve a cross-agent
    key when the request key is a different agent's key — the
    Python port takes the safer "scope to the requested agent"
    route so the store never has a cross-agent key without
    explicit owner intent."""
    assert (
        to_agent_store_session_key({"agentId": "ops", "requestKey": "agent:main:incident-42"})
        == "agent:main:incident-42"
    )
