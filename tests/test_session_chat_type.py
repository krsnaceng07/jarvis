"""Tests for src/sessions/session_chat_type.py + session_chat_type_shared.py.

Mirrors OpenClaw's ``extensions/sessions/session-chat-type-shared`` +
``session-chat-type`` test files.
"""
from __future__ import annotations

import pytest

from src.sessions.session_chat_type import (
    derive_session_chat_type,
    register_legacy_chat_type_deriver,
)
from src.sessions.session_chat_type_shared import (
    has_ambiguous_canonical_session_peer_shape,
    parse_canonical_session_peer_shape,
    derive_session_chat_type_from_key,
)


# ── parse_canonical_session_peer_shape ────────────────────────────


class TestParseCanonicalSessionPeerShape:
    def test_channel_shape(self) -> None:
        result = parse_canonical_session_peer_shape("discord:channel:abc")
        assert result is not None
        assert result.channel == "discord"
        assert result.chat_type == "channel"

    def test_group_shape(self) -> None:
        result = parse_canonical_session_peer_shape("telegram:group:g1")
        assert result is not None
        assert result.chat_type == "group"

    def test_direct_shape(self) -> None:
        result = parse_canonical_session_peer_shape("direct:user-1")
        assert result is not None
        assert result.chat_type == "direct"
        assert result.channel is None

    def test_dm_treated_as_direct(self) -> None:
        result = parse_canonical_session_peer_shape("dm:user-1")
        assert result is not None
        assert result.chat_type == "direct"

    def test_account_shape(self) -> None:
        result = parse_canonical_session_peer_shape("slack:acct-1:channel:c1")
        assert result is not None
        assert result.channel == "slack"
        assert result.chat_type == "channel"

    def test_agent_wrapper_returns_none(self) -> None:
        """An agent-wrapped key is opaque plugin identity, never a route."""
        assert parse_canonical_session_peer_shape("agent:1:discord:channel:abc") is None

    def test_ambiguous_returns_none(self) -> None:
        """Multiple matching shapes return ``None`` (caller should not trust)."""
        # "direct:abc:channel:def" — bare-direct (parts[0]=direct,
        # parts[1]=abc) AND account (parts[2]=channel canonical,
        # parts[3]=def) both match → ambiguous.
        assert parse_canonical_session_peer_shape("direct:abc:channel:def") is None

    def test_malformed_returns_none(self) -> None:
        assert parse_canonical_session_peer_shape("") is None
        assert parse_canonical_session_peer_shape("single") is None
        assert parse_canonical_session_peer_shape("discord") is None


class TestHasAmbiguousCanonicalSessionPeerShape:
    def test_clear_shape(self) -> None:
        assert has_ambiguous_canonical_session_peer_shape("discord:channel:abc") is False

    def test_ambiguous_shape(self) -> None:
        # Bare-direct + account shapes both match
        assert has_ambiguous_canonical_session_peer_shape("direct:abc:channel:def") is True

    def test_agent_wrapper_not_ambiguous(self) -> None:
        """Agent wrapper is opaque, never ambiguous."""
        assert has_ambiguous_canonical_session_peer_shape("agent:1:discord:channel:abc") is False


# ── derive_session_chat_type_from_key ────────────────────────────


class TestDeriveSessionChatTypeFromKey:
    def test_canonical(self) -> None:
        assert (
            derive_session_chat_type_from_key("agent:1:discord:channel:abc") == "channel"
        )
        assert (
            derive_session_chat_type_from_key("agent:1:telegram:group:g1") == "group"
        )
        assert derive_session_chat_type_from_key("direct:user-1") == "direct"

    def test_built_in_legacy_group(self) -> None:
        """``group:<id>`` is a built-in legacy shape."""
        assert derive_session_chat_type_from_key("group:abc123") == "group"

    def test_built_in_legacy_channel(self) -> None:
        """``channel:<id>`` is a built-in legacy shape."""
        assert derive_session_chat_type_from_key("channel:abc123") == "channel"

    def test_built_in_legacy_whatsapp(self) -> None:
        """Bare ``<id>@g.us`` JIDs map to ``group``."""
        assert derive_session_chat_type_from_key("123456@g.us") == "group"
        assert derive_session_chat_type_from_key("whatsapp:123456@g.us") == "group"

    def test_built_in_legacy_discord(self) -> None:
        """Discord ``guild-...:channel-...`` maps to ``channel``."""
        assert (
            derive_session_chat_type_from_key("discord:guild-123:channel-456") == "channel"
        )

    def test_empty_returns_unknown(self) -> None:
        assert derive_session_chat_type_from_key(None) == "unknown"
        assert derive_session_chat_type_from_key("") == "unknown"

    def test_uppercase_normalized(self) -> None:
        """Uppercase input is lowercased before derivation."""
        assert (
            derive_session_chat_type_from_key("AGENT:1:DISCORD:CHANNEL:abc") == "channel"
        )

    def test_unknown_for_garbage(self) -> None:
        assert derive_session_chat_type_from_key("some-garbage-key") == "unknown"


# ── derive_session_chat_type (top-level + legacy deriver) ────────


class TestDeriveSessionChatType:
    def setup_method(self) -> None:
        # Clean up any registered derivers from prior tests
        from src.sessions.session_chat_type import _LEGACY_CHAT_TYPE_DERIVERS
        _LEGACY_CHAT_TYPE_DERIVERS.clear()

    def test_built_in_derivation(self) -> None:
        assert derive_session_chat_type("agent:1:discord:channel:abc") == "channel"

    def test_falls_back_to_plugin_deriver(self) -> None:
        """A registered legacy deriver wins for unknown keys."""
        # Custom channel "mything" with no built-in support
        register_legacy_chat_type_deriver(
            "mything",
            lambda scoped: "channel" if scoped.startswith("mything:") else None,
        )
        assert derive_session_chat_type("mything:abc") == "channel"

    def test_no_fallback_returns_unknown(self) -> None:
        assert derive_session_chat_type("some-garbage-key") == "unknown"

    def test_empty_returns_unknown(self) -> None:
        assert derive_session_chat_type(None) == "unknown"
        assert derive_session_chat_type("") == "unknown"

    def test_deriver_error_swallowed(self) -> None:
        """A throwing deriver doesn't break the chain."""
        register_legacy_chat_type_deriver(
            "broken",
            lambda scoped: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # Falls through to unknown
        assert derive_session_chat_type("broken:abc") == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
