"""Tests for src/sessions/session_key_utils.py.

Mirrors OpenClaw's ``extensions/sessions/session-key-case-preservation.test.ts``
+ ``session-key-utils`` (internal) tests.
"""
from __future__ import annotations

import pytest

from src.sessions.session_key_utils import (
    ParsedAgentSessionKey,
    ParsedCronRunScopeSuffix,
    ParsedSessionDeliveryRoute,
    ParsedThreadSessionSuffix,
    RawSessionConversationRef,
    _reset_session_key_cache_for_tests,
    get_subagent_depth,
    is_acp_session_key,
    is_case_preserving_peer,
    is_cron_run_session_key,
    is_cron_session_key,
    is_subagent_session_key,
    normalize_session_key_preserving_opaque_peer_ids,
    normalize_session_peer_id,
    parse_agent_session_key,
    parse_cron_run_scope_suffix,
    parse_raw_session_conversation_ref,
    parse_session_delivery_route,
    parse_thread_session_suffix,
    requires_folded_session_key_alias_proof,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    _reset_session_key_cache_for_tests()
    yield
    _reset_session_key_cache_for_tests()


# ── normalize_session_key_preserving_opaque_peer_ids ──────────────


class TestNormalizeSessionKeyPreservingOpaquePeerIds:
    def test_lowercases_structural_prefix(self) -> None:
        assert normalize_session_key_preserving_opaque_peer_ids("AGENT:1:DISCORD:channel:abc") == \
            "agent:1:discord:channel:abc"

    def test_empty_returns_empty(self) -> None:
        assert normalize_session_key_preserving_opaque_peer_ids(None) == ""
        assert normalize_session_key_preserving_opaque_peer_ids("") == ""

    def test_signal_group_segment_preserved(self) -> None:
        """Signal group peer-id segment stays case-preserved."""
        assert (
            normalize_session_key_preserving_opaque_peer_ids(
                "agent:1:signal:group:ABCdef"
            )
            == "agent:1:signal:group:ABCdef"
        )

    def test_matrix_channel_tail_preserved(self) -> None:
        """Matrix room id (opaque tail) stays case-preserved."""
        assert (
            normalize_session_key_preserving_opaque_peer_ids(
                "agent:1:matrix:channel:!Abc:Matrix.Org"
            )
            == "agent:1:matrix:channel:!Abc:Matrix.Org"
        )

    def test_canonicalizes_around_preserved_tail(self) -> None:
        """Structural segments are lowercased, Matrix tail is preserved."""
        normalized = normalize_session_key_preserving_opaque_peer_ids(
            "AGENT:1:MATRIX:CHANNEL:!Abc:Matrix.Org"
        )
        assert normalized.startswith("agent:1:matrix:channel:")
        assert "!Abc:Matrix.Org" in normalized

    def test_cache_hit(self) -> None:
        """The result is cached (same input → same output, no recomputation)."""
        a = normalize_session_key_preserving_opaque_peer_ids("agent:1:discord:channel:abc")
        b = normalize_session_key_preserving_opaque_peer_ids("agent:1:discord:channel:abc")
        assert a == b

    def test_too_long_skips_cache(self) -> None:
        """Keys longer than 4096 chars skip the cache."""
        long_key = "a" * 5000
        result = normalize_session_key_preserving_opaque_peer_ids(long_key)
        assert result == long_key.lower()


# ── normalize_session_peer_id ────────────────────────────────────


class TestNormalizeSessionPeerId:
    def test_lowercases_by_default(self) -> None:
        assert normalize_session_peer_id(
            {"channel": "discord", "peer_kind": "channel", "peer_id": "ABC"}
        ) == "abc"

    def test_signal_group_preserves_case(self) -> None:
        assert normalize_session_peer_id(
            {"channel": "signal", "peer_kind": "group", "peer_id": "ABCdef"}
        ) == "ABCdef"

    def test_matrix_channel_preserves_case(self) -> None:
        assert normalize_session_peer_id(
            {"channel": "matrix", "peer_kind": "channel", "peer_id": "!Abc:Org"}
        ) == "!Abc:Org"

    def test_empty_peer_id(self) -> None:
        assert normalize_session_peer_id(
            {"channel": "discord", "peer_kind": "channel", "peer_id": ""}
        ) == ""
        assert normalize_session_peer_id(
            {"channel": "discord", "peer_kind": "channel", "peer_id": "  "}
        ) == ""

    def test_missing_peer_id(self) -> None:
        assert normalize_session_peer_id(
            {"channel": "discord", "peer_kind": "channel"}
        ) == ""


# ── is_case_preserving_peer ──────────────────────────────────────


class TestIsCasePreservingPeer:
    def test_signal_group(self) -> None:
        assert is_case_preserving_peer("signal", "group") is True

    def test_matrix_channel(self) -> None:
        assert is_case_preserving_peer("matrix", "channel") is True

    def test_matrix_group(self) -> None:
        assert is_case_preserving_peer("matrix", "group") is True

    def test_discord_channel_lowercases(self) -> None:
        assert is_case_preserving_peer("discord", "channel") is False

    def test_unknown_channel(self) -> None:
        assert is_case_preserving_peer("unknown", "group") is False


# ── parse_agent_session_key ──────────────────────────────────────


class TestParseAgentSessionKey:
    def test_basic(self) -> None:
        result = parse_agent_session_key("agent:1:discord:channel:abc")
        assert result == ParsedAgentSessionKey(
            agent_id="1", rest="discord:channel:abc"
        )

    def test_no_agent_prefix(self) -> None:
        assert parse_agent_session_key("discord:channel:abc") is None

    def test_too_short(self) -> None:
        assert parse_agent_session_key("agent:1") is None

    def test_empty(self) -> None:
        assert parse_agent_session_key(None) is None
        assert parse_agent_session_key("") is None

    def test_uppercase_normalized(self) -> None:
        """Uppercase structural prefix is lowercased before parsing."""
        result = parse_agent_session_key("AGENT:1:DISCORD:CHANNEL:abc")
        assert result is not None
        assert result.agent_id == "1"
        assert result.rest == "discord:channel:abc"

    def test_signal_group_segment_preserved(self) -> None:
        """Signal group peer-id is preserved (case-preserving peer)."""
        result = parse_agent_session_key("agent:1:signal:group:ABCdef")
        assert result is not None
        assert result.rest == "signal:group:ABCdef"


# ── cron key predicates ──────────────────────────────────────────


class TestCronPredicates:
    def test_is_cron_run(self) -> None:
        assert is_cron_run_session_key("agent:1:cron:daily:run:abc123") is True

    def test_is_not_cron_run(self) -> None:
        assert is_cron_run_session_key("agent:1:discord:channel:abc") is False

    def test_is_cron_session(self) -> None:
        assert is_cron_session_key("agent:1:cron:daily:run:abc") is True
        assert is_cron_session_key("agent:1:cron:daily") is True

    def test_is_not_cron_session(self) -> None:
        assert is_cron_session_key("agent:1:discord:channel:abc") is False

    def test_parse_cron_run_scope(self) -> None:
        result = parse_cron_run_scope_suffix("agent:1:cron:daily:run:abc")
        assert result == ParsedCronRunScopeSuffix(
            base_session_key="agent:1:cron:daily", run_id="abc"
        )

    def test_parse_cron_run_scope_non_cron_key(self) -> None:
        """Non-cron keys return input unchanged + None run id."""
        result = parse_cron_run_scope_suffix("agent:1:discord:channel:abc")
        assert result == ParsedCronRunScopeSuffix(
            base_session_key="agent:1:discord:channel:abc", run_id=None
        )


# ── subagent + ACP ────────────────────────────────────────────────


class TestSubagentAndAcp:
    def test_is_subagent(self) -> None:
        assert is_subagent_session_key("agent:1:subagent:abc") is True
        assert is_subagent_session_key("subagent:abc") is True

    def test_is_not_subagent(self) -> None:
        assert is_subagent_session_key("agent:1:discord:channel:abc") is False

    def test_get_subagent_depth(self) -> None:
        assert get_subagent_depth("agent:1:discord:channel:abc") == 0
        assert get_subagent_depth("agent:1:subagent:abc") == 1
        assert get_subagent_depth("agent:1:subagent:abc:subagent:def") == 2
        assert get_subagent_depth(None) == 0

    def test_is_acp(self) -> None:
        assert is_acp_session_key("acp:session-1") is True
        assert is_acp_session_key("agent:1:acp:session-1") is True

    def test_is_not_acp(self) -> None:
        assert is_acp_session_key("agent:1:discord:channel:abc") is False


# ── thread suffix ────────────────────────────────────────────────


class TestThreadSuffix:
    def test_with_thread(self) -> None:
        result = parse_thread_session_suffix("agent:1:discord:channel:abc:thread:t1")
        assert result == ParsedThreadSessionSuffix(
            base_session_key="agent:1:discord:channel:abc",
            thread_id="t1",
        )

    def test_without_thread(self) -> None:
        result = parse_thread_session_suffix("agent:1:discord:channel:abc")
        assert result.base_session_key == "agent:1:discord:channel:abc"
        assert result.thread_id is None

    def test_case_insensitive_marker(self) -> None:
        """The ``:thread:`` marker is matched case-insensitively."""
        result = parse_thread_session_suffix("agent:1:discord:channel:abc:Thread:t1")
        assert result.thread_id == "t1"


# ── delivery route + raw ref ──────────────────────────────────────


class TestParseSessionDeliveryRoute:
    def test_channel_route(self) -> None:
        result = parse_session_delivery_route("agent:1:discord:channel:abc")
        assert result is not None
        assert result.channel == "discord"
        assert result.peer_id == "abc"
        assert result.peer_kind == "channel"
        assert result.account_id is None
        assert result.thread_id is None

    def test_direct_route(self) -> None:
        result = parse_session_delivery_route("agent:1:slack:account-1:direct:user-1")
        assert result is not None
        assert result.channel == "slack"
        assert result.account_id == "account-1"
        assert result.peer_id == "user-1"
        assert result.peer_kind == "direct"

    def test_with_thread(self) -> None:
        result = parse_session_delivery_route(
            "agent:1:discord:channel:abc:thread:t1"
        )
        assert result is not None
        assert result.thread_id == "t1"

    def test_invalid(self) -> None:
        assert parse_session_delivery_route("agent:1") is None
        assert parse_session_delivery_route(None) is None


class TestParseRawSessionConversationRef:
    def test_channel(self) -> None:
        result = parse_raw_session_conversation_ref("discord:channel:abc")
        assert result is not None
        assert result.channel == "discord"
        assert result.kind == "channel"
        assert result.raw_id == "abc"

    def test_group(self) -> None:
        result = parse_raw_session_conversation_ref("whatsapp:group:g1")
        assert result is not None
        assert result.kind == "group"

    def test_with_agent_prefix(self) -> None:
        result = parse_raw_session_conversation_ref("agent:1:discord:channel:abc")
        assert result is not None
        # OpenClaw's prefix is rawParts[:bodyStartIndex + 2] joined
        # — for bodyStartIndex=2 that's 4 segments, so the prefix
        # includes the agent wrapper + channel.
        assert result.prefix == "agent:1:discord:channel"
        assert result.channel == "discord"

    def test_invalid(self) -> None:
        assert parse_raw_session_conversation_ref("") is None
        assert parse_raw_session_conversation_ref("discord") is None
        assert parse_raw_session_conversation_ref("discord:direct:abc") is None


# ── requires_folded_session_key_alias_proof ──────────────────────


class TestRequiresFoldedSessionKeyAliasProof:
    def test_matrix_tail(self) -> None:
        """Matrix channel key requires the proof (tail span)."""
        assert requires_folded_session_key_alias_proof(
            "agent:1:matrix:channel:!Abc:Org"
        ) is True

    def test_signal_segment_no_proof(self) -> None:
        """Signal group key uses segment span (not tail), so no proof."""
        assert requires_folded_session_key_alias_proof(
            "agent:1:signal:group:abc"
        ) is False

    def test_discord_no_proof(self) -> None:
        assert requires_folded_session_key_alias_proof(
            "agent:1:discord:channel:abc"
        ) is False

    def test_empty(self) -> None:
        assert requires_folded_session_key_alias_proof(None) is False
        assert requires_folded_session_key_alias_proof("") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
