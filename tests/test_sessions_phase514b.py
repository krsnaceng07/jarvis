"""Tests for the Phase 5.14b session ports.

Mirrors the test cases from OpenClaw's
``extensions/sessions/user-turn-media``,
``session-state-event-kinds``,
``session-label``, and
``session-lifecycle-identity`` test files.
"""
from __future__ import annotations

import pytest

from src.sessions import (
    MEDIA_ONLY_USER_TEXT,
    NOTIFY_BY_SESSION_STATE_EVENT_KIND,
    ParsedSessionLabel,
    SESSION_LABEL_MAX_LENGTH,
    SessionStateEventKind,
    decode_session_identity,
    normalize_session_identities,
    parse_session_label,
)


class TestUserTurnMedia:
    def test_marker_constant(self) -> None:
        """The marker is the exact OpenClaw constant value."""
        assert MEDIA_ONLY_USER_TEXT == "[User sent media without caption]"


class TestSessionStateEventKinds:
    def test_notify_table_keys(self) -> None:
        """The notify table covers every event kind."""
        for kind in [
            "human_direct_message",
            "adopted",
            "run_completed",
            "run_failed",
            "child_spawned",
            "goal_changed",
            "upstream_missing",
            "compacted",
        ]:
            assert kind in NOTIFY_BY_SESSION_STATE_EVENT_KIND

    def test_notify_table_values(self) -> None:
        """The notify policy matches OpenClaw's values."""
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["human_direct_message"] is True
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["upstream_missing"] is True
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["goal_changed"] is True
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["adopted"] is False
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["run_completed"] is False
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["run_failed"] is False
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["child_spawned"] is False
        assert NOTIFY_BY_SESSION_STATE_EVENT_KIND["compacted"] is False


class TestParseSessionLabel:
    def test_valid_label(self) -> None:
        result = parse_session_label("  My Session  ")
        assert result == ParsedSessionLabel(ok=True, label="My Session")

    def test_empty_string_rejected(self) -> None:
        result = parse_session_label("")
        assert result.ok is False
        assert "empty" in (result.error or "")

    def test_whitespace_only_rejected(self) -> None:
        result = parse_session_label("   ")
        assert result.ok is False
        assert "empty" in (result.error or "")

    def test_non_string_rejected(self) -> None:
        for bad in [123, None, [], {}]:
            result = parse_session_label(bad)
            assert result.ok is False
            assert "string" in (result.error or "")

    def test_too_long_rejected(self) -> None:
        result = parse_session_label("a" * (SESSION_LABEL_MAX_LENGTH + 1))
        assert result.ok is False
        assert "too long" in (result.error or "")

    def test_max_length_accepted(self) -> None:
        result = parse_session_label("a" * SESSION_LABEL_MAX_LENGTH)
        assert result.ok is True
        assert result.label == "a" * SESSION_LABEL_MAX_LENGTH


class TestNormalizeSessionIdentities:
    def test_basic(self) -> None:
        result = normalize_session_identities("hook", ["alpha", "beta"])
        assert result == ['["hook","alpha"]', '["hook","beta"]']

    def test_strips_whitespace(self) -> None:
        result = normalize_session_identities("hook", ["  alpha  ", "  beta"])
        assert result == ['["hook","alpha"]', '["hook","beta"]']

    def test_drops_empty(self) -> None:
        result = normalize_session_identities("hook", ["alpha", "", None, "beta"])
        assert result == ['["hook","alpha"]', '["hook","beta"]']

    def test_dedupes(self) -> None:
        result = normalize_session_identities("hook", ["alpha", "alpha", "beta"])
        assert result == ['["hook","alpha"]', '["hook","beta"]']

    def test_sorts(self) -> None:
        result = normalize_session_identities("hook", ["zebra", "alpha", "mike"])
        assert result == ['["hook","alpha"]', '["hook","mike"]', '["hook","zebra"]']

    def test_empty_scope_raises(self) -> None:
        with pytest.raises(ValueError, match="scope is required"):
            normalize_session_identities("   ", ["alpha"])

    def test_round_trip_with_decode(self) -> None:
        normalized = normalize_session_identities("hook", ["alpha", "beta"])
        for item in normalized:
            decoded = decode_session_identity(item)
            assert decoded is not None
            assert decoded["scope"] == "hook"
            assert decoded["identity"] in {"alpha", "beta"}


class TestDecodeSessionIdentity:
    def test_valid(self) -> None:
        assert decode_session_identity('["hook","alpha"]') == {
            "scope": "hook",
            "identity": "alpha",
        }

    def test_non_string(self) -> None:
        assert decode_session_identity(123) is None
        assert decode_session_identity(None) is None
        assert decode_session_identity([]) is None

    def test_invalid_json(self) -> None:
        assert decode_session_identity("not json") is None

    def test_wrong_shape(self) -> None:
        # Not a 2-element array
        assert decode_session_identity("[1, 2, 3]") is None
        # Non-string elements
        assert decode_session_identity("[1, 2]") is None
        assert decode_session_identity('["scope", null]') is None
        # Object instead of array
        assert decode_session_identity('{"scope": "x"}') is None

    def test_round_trip(self) -> None:
        original = ["session:start", "agent-1"]
        import json

        encoded = json.dumps(original, separators=(",", ":"))
        decoded = decode_session_identity(encoded)
        assert decoded == {"scope": "session:start", "identity": "agent-1"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
