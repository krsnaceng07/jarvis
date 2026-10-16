"""Tests for session_state_notices + transcript_events ports.

Mirrors the OpenClaw test cases for both modules.
"""
from __future__ import annotations

import pytest

from src.sessions.session_state_notices import (
    SESSION_STATE_CONTEXT_PREFIX,
    decode_session_state_notice_context_key,
    encode_notice_target,
    enqueue_session_state_notice,
    is_notifiable_watcher_key,
    reset_session_state_notice_hooks_for_tests,
    session_state_notice_text,
    set_enqueue_system_event,
    set_request_heartbeat,
    should_wake_watcher,
)
from src.sessions.transcript_events import (
    emit_session_transcript_update,
    normalize_session_transcript_update,
    on_internal_session_transcript_update,
    on_session_transcript_update,
    _reset_transcript_event_listeners_for_tests,
)


# ── session_state_notices ────────────────────────────────────────


class TestSessionStateNoticesEncoding:
    def test_encode_decode_round_trip(self) -> None:
        sk = "agent:1:discord:channel:abc"
        encoded = encode_notice_target(sk)
        decoded = decode_session_state_notice_context_key(
            SESSION_STATE_CONTEXT_PREFIX + encoded
        )
        assert decoded == sk

    def test_decode_missing_prefix(self) -> None:
        assert decode_session_state_notice_context_key("other:abc") is None

    def test_decode_empty_encoded(self) -> None:
        assert (
            decode_session_state_notice_context_key(SESSION_STATE_CONTEXT_PREFIX) is None
        )

    def test_decode_odd_length(self) -> None:
        assert (
            decode_session_state_notice_context_key(
                SESSION_STATE_CONTEXT_PREFIX + "abc"
            )
            is None
        )

    def test_decode_non_hex(self) -> None:
        assert (
            decode_session_state_notice_context_key(
                SESSION_STATE_CONTEXT_PREFIX + "zz"
            )
            is None
        )

    def test_decode_invalid_utf8(self) -> None:
        # 0xff is not valid UTF-8 start byte
        assert (
            decode_session_state_notice_context_key(
                SESSION_STATE_CONTEXT_PREFIX + "ff"
            )
            is None
        )


class TestSessionStateNoticeText:
    def test_text_is_byte_stable(self) -> None:
        text1 = session_state_notice_text("agent:1:discord:channel:abc", 42)
        text2 = session_state_notice_text("agent:1:discord:channel:abc", 42)
        assert text1 == text2

    def test_text_contains_target_and_seq(self) -> None:
        text = session_state_notice_text("agent:1:discord:channel:abc", 42)
        assert "agent:1:discord:channel:abc" in text
        assert "42" in text

    def test_text_differs_by_seq(self) -> None:
        text1 = session_state_notice_text("agent:1:abc", 42)
        text2 = session_state_notice_text("agent:1:abc", 43)
        assert text1 != text2


class TestWatcherEligibility:
    def test_should_wake_non_subagent(self) -> None:
        assert should_wake_watcher("agent:1:discord:channel:abc") is True

    def test_should_not_wake_subagent(self) -> None:
        assert should_wake_watcher("agent:1:subagent:abc") is False

    def test_is_notifiable_agent_key(self) -> None:
        assert is_notifiable_watcher_key("agent:1:discord:channel:abc") is True

    def test_is_not_notifiable_bare_key(self) -> None:
        """Bare keys (no agent wrapper) are not notifiable."""
        assert is_notifiable_watcher_key("discord:channel:abc") is False


class TestEnqueueSessionStateNotice:
    def setup_method(self) -> None:
        reset_session_state_notice_hooks_for_tests()
        self.enqueue_calls: list = []
        self.heartbeat_calls: list = []

        def fake_enqueue(message: str, options: dict) -> None:
            self.enqueue_calls.append({"message": message, "options": dict(options)})

        def fake_heartbeat(options: dict) -> None:
            self.heartbeat_calls.append(dict(options))

        set_enqueue_system_event(fake_enqueue)
        set_request_heartbeat(fake_heartbeat)

    def teardown_method(self) -> None:
        reset_session_state_notice_hooks_for_tests()

    def test_enqueues_with_encoded_context(self) -> None:
        enqueue_session_state_notice(
            {
                "watcherSessionKey": "agent:1:discord:channel:w",
                "targetSessionKey": "agent:1:discord:channel:t",
                "lastSeenSequence": 42,
            }
        )
        assert len(self.enqueue_calls) == 1
        call = self.enqueue_calls[0]
        assert "agent:1:discord:channel:t" in call["message"]
        assert "42" in call["message"]
        assert call["options"]["sessionKey"] == "agent:1:discord:channel:w"
        assert call["options"]["contextKey"].startswith(SESSION_STATE_CONTEXT_PREFIX)
        # Context encodes the target key
        encoded = call["options"]["contextKey"][len(SESSION_STATE_CONTEXT_PREFIX):]
        assert decode_session_state_notice_context_key(
            call["options"]["contextKey"]
        ) == "agent:1:discord:channel:t"

    def test_wakes_heartbeat_by_default(self) -> None:
        enqueue_session_state_notice(
            {
                "watcherSessionKey": "agent:1:discord:channel:w",
                "targetSessionKey": "agent:1:discord:channel:t",
                "lastSeenSequence": 42,
            }
        )
        assert len(self.heartbeat_calls) == 1
        assert self.heartbeat_calls[0]["intent"] == "immediate"
        assert self.heartbeat_calls[0]["source"] == "session-state"
        assert self.heartbeat_calls[0]["sessionKey"] == "agent:1:discord:channel:w"

    def test_queue_only_skips_heartbeat(self) -> None:
        """``queueOnly=True`` coalesces — no heartbeat wake."""
        enqueue_session_state_notice(
            {
                "watcherSessionKey": "agent:1:discord:channel:w",
                "targetSessionKey": "agent:1:discord:channel:t",
                "lastSeenSequence": 42,
                "queueOnly": True,
            }
        )
        assert len(self.heartbeat_calls) == 0
        # Enqueue still happens (with replace=True for coalesce)
        assert len(self.enqueue_calls) == 1
        assert self.enqueue_calls[0]["options"].get("replace") is True

    def test_subagent_watcher_skips_heartbeat(self) -> None:
        enqueue_session_state_notice(
            {
                "watcherSessionKey": "agent:1:subagent:w",
                "targetSessionKey": "agent:1:discord:channel:t",
                "lastSeenSequence": 42,
            }
        )
        assert len(self.heartbeat_calls) == 0
        # Enqueue still happens (durable event for subagent)
        assert len(self.enqueue_calls) == 1


# ── transcript_events ────────────────────────────────────────────


class TestTranscriptEventsListener:
    def setup_method(self) -> None:
        _reset_transcript_event_listeners_for_tests()
        self.public_calls: list = []
        self.internal_calls: list = []

    def test_register_and_emit_public(self) -> None:
        on_session_transcript_update(lambda u: self.public_calls.append(dict(u)))
        emit_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:discord:channel:abc",
                },
            }
        )
        assert len(self.public_calls) == 1
        assert self.public_calls[0]["target"].session_key == "agent:1:discord:channel:abc"

    def test_register_and_emit_internal(self) -> None:
        on_internal_session_transcript_update(
            lambda u: self.internal_calls.append(dict(u))
        )
        emit_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:discord:channel:abc",
                },
            }
        )
        assert len(self.internal_calls) == 1

    def test_unregister(self) -> None:
        unregister = on_session_transcript_update(
            lambda u: self.public_calls.append(dict(u))
        )
        unregister()
        emit_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:discord:channel:abc",
                },
            }
        )
        assert self.public_calls == []

    def test_multiple_listeners_called_in_order(self) -> None:
        order: list[str] = []
        on_session_transcript_update(lambda _u: order.append("a"))
        on_session_transcript_update(lambda _u: order.append("b"))
        emit_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:discord:channel:abc",
                },
            }
        )
        assert order == ["a", "b"]

    def test_listener_exception_swallowed(self) -> None:
        order: list[str] = []
        on_session_transcript_update(
            lambda _u: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        on_session_transcript_update(lambda _u: order.append("ok"))
        emit_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:discord:channel:abc",
                },
            }
        )
        assert order == ["ok"]


class TestNormalizeSessionTranscriptUpdate:
    def test_normalize_with_file(self) -> None:
        result = normalize_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:discord:channel:abc",
                },
            },
            {"allowIdentityOnly": False},
        )
        assert result is not None
        assert result["sessionFile"] == "/tmp/x"
        assert result["target"].session_key == "agent:1:discord:channel:abc"

    def test_normalize_with_file_and_seq(self) -> None:
        result = normalize_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "messageSeq": 42,
            },
            {"allowIdentityOnly": False},
        )
        assert result is not None
        assert result["messageSeq"] == 42

    def test_normalize_without_file_returns_none(self) -> None:
        """Missing ``sessionFile`` + ``allowIdentityOnly=False`` → None."""
        result = normalize_session_transcript_update(
            {
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:abc",
                },
            },
            {"allowIdentityOnly": False},
        )
        assert result is None

    def test_normalize_allow_identity_only(self) -> None:
        """``allowIdentityOnly=True`` accepts file-less updates."""
        result = normalize_session_transcript_update(
            {
                "target": {
                    "agentId": "1",
                    "sessionId": "s1",
                    "sessionKey": "agent:1:abc",
                },
            },
            {"allowIdentityOnly": True},
        )
        assert result is not None

    def test_normalize_invalid_message_seq(self) -> None:
        """Non-positive messageSeq is dropped."""
        result = normalize_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "messageSeq": 0,
            },
            {"allowIdentityOnly": False},
        )
        assert result is not None
        assert "messageSeq" not in result

    def test_normalize_derives_agent_from_session_key(self) -> None:
        """When ``agentId`` is missing but ``sessionKey`` is set,
        the agent id is parsed from the session key."""
        result = normalize_session_transcript_update(
            {
                "sessionFile": "/tmp/x",
                "target": {
                    "sessionId": "s1",
                    "sessionKey": "agent:42:discord:channel:abc",
                },
            },
            {"allowIdentityOnly": False},
        )
        assert result is not None
        assert result["agentId"] == "42"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
