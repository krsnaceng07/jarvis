"""Tests for src/sessions/agent_harness_session_key.py.

Mirrors OpenClaw's ``src/sessions/agent-harness-session-key.test.ts``.
"""
from __future__ import annotations

import pytest

from src.sessions.agent_harness_session_key import (
    AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE,
    AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE,
    is_agent_harness_session_key,
    is_agent_harness_session_key_owned_by,
    is_valid_agent_harness_session_store_entry,
    resolve_agent_harness_session_context_error,
    resolve_agent_harness_session_id_mismatch_error,
    resolve_agent_harness_session_store_entry_error,
    resolve_missing_agent_harness_session_error,
)


@pytest.mark.parametrize(
    "session_key",
    [
        "harness:codex:supervision:native-thread",
        "agent:main:harness:codex:supervision:native-thread",
    ],
)
def test_recognizes_reserved_namespace(session_key: str) -> None:
    assert is_agent_harness_session_key(session_key) is True
    err = resolve_missing_agent_harness_session_error(session_key, None)
    assert err is not None
    assert "reserved" in err.lower()
    assert resolve_missing_agent_harness_session_error(session_key, {"sessionId": "existing"}) is None


def test_ties_trusted_creation_to_matching_persisted_harness_owner() -> None:
    key = "agent:main:harness:codex:supervision:native-thread"
    assert is_agent_harness_session_key_owned_by(key, "codex") is True
    assert is_agent_harness_session_key_owned_by(key, "CODEX-APP-SERVER") is True
    assert is_agent_harness_session_key_owned_by(key, "other") is False
    assert is_agent_harness_session_key_owned_by("agent:main:ordinary", "codex") is False


def test_compares_exact_owner_segment_instead_of_owner_id_prefix() -> None:
    key = "agent:main:harness:foo:bar:native-thread"
    assert is_agent_harness_session_key_owned_by(key, "foo") is True
    assert is_agent_harness_session_key_owned_by(key, "foo:bar") is False
    assert (
        resolve_agent_harness_session_store_entry_error(
            key,
            {
                "agentHarnessId": "foo:bar",
                "modelSelectionLocked": True,
                "sessionId": "native-session",
            },
        )
        == AGENT_HARNESS_SESSION_KEY_RESERVED_MESSAGE
    )
    assert (
        resolve_agent_harness_session_store_entry_error(
            key,
            {
                "agentHarnessId": "foo",
                "modelSelectionLocked": True,
                "sessionId": "native-session",
            },
        )
        is None
    )


def test_validates_durable_lock_metadata_for_reserved_and_ordinary_rows() -> None:
    key = "agent:main:harness:codex:supervision:native-thread"
    assert (
        resolve_agent_harness_session_store_entry_error(
            key,
            {
                "agentHarnessId": "codex",
                "modelSelectionLocked": True,
                "sessionId": "native-session",
            },
        )
        is None
    )
    assert (
        resolve_agent_harness_session_store_entry_error(
            key,
            {
                "agentHarnessId": "codex",
                "modelSelectionLocked": False,
                "sessionId": "native-session",
            },
        )
        is None
    )
    assert (
        resolve_agent_harness_session_store_entry_error(
            "agent:main:ordinary", {"modelSelectionLocked": False}
        )
        is None
    )
    assert (
        is_valid_agent_harness_session_store_entry(
            "agent:main:ordinary",
            {
                "agentHarnessId": "codex",
                "modelSelectionLocked": True,
                "sessionId": "native-session",
            },
        )
        is True
    )
    assert (
        resolve_agent_harness_session_store_entry_error(
            "agent:main:ordinary",
            {"modelSelectionLocked": True, "sessionId": "native-session"},
        )
        is None
    )
    assert (
        is_valid_agent_harness_session_store_entry(
            "agent:main:ordinary",
            {"modelSelectionLocked": True, "sessionId": "native-session"},
        )
        is False
    )


def test_requires_valid_durable_row_for_protected_reserved_runtime_contexts() -> None:
    key = "agent:main:harness:codex:supervision:native-thread"
    err = resolve_agent_harness_session_context_error(key, None)
    assert err is not None
    assert "reserved" in err.lower()
    assert (
        resolve_agent_harness_session_context_error(
            key,
            {
                "agentHarnessId": "codex",
                "modelSelectionLocked": False,
                "sessionId": "native-session",
            },
        )
        is None
    )
    assert (
        resolve_agent_harness_session_context_error(
            key,
            {"agentHarnessId": "codex", "modelSelectionLocked": True},
        )
        == AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    )
    assert (
        resolve_agent_harness_session_context_error(
            key,
            {
                "agentHarnessId": "codex",
                "modelSelectionLocked": True,
                "sessionId": "native-session",
            },
        )
        is None
    )
    assert resolve_agent_harness_session_context_error("agent:main:ordinary", None) is None


def test_keeps_pre_existing_unlocked_harness_prefixed_sessions_ordinary() -> None:
    key = "agent:main:harness:notes"
    entry = {"agentHarnessId": "openclaw", "sessionId": "legacy-session"}

    assert resolve_agent_harness_session_context_error(key, entry) is None
    assert resolve_agent_harness_session_store_entry_error(key, entry) is None
    assert (
        resolve_agent_harness_session_id_mismatch_error(entry, "replacement-session")
        is None
    )
    assert is_valid_agent_harness_session_store_entry(key, entry) is False


def test_rejects_caller_selected_session_id_that_would_rotate_a_durable_lock() -> None:
    entry = {
        "agentHarnessId": "codex",
        "modelSelectionLocked": True,
        "sessionId": "native-session",
    }
    assert resolve_agent_harness_session_id_mismatch_error(entry, "native-session") is None
    assert (
        resolve_agent_harness_session_id_mismatch_error(entry, "replacement-session")
        == AGENT_HARNESS_SESSION_ID_LOCKED_MESSAGE
    )


def test_does_not_turn_a_legacy_model_selection_lock_into_harness_ownership() -> None:
    entry = {"modelSelectionLocked": True, "sessionId": "ordinary-session"}
    assert (
        resolve_agent_harness_session_id_mismatch_error(entry, "replacement-session")
        is None
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
