"""Tests for Phase 8.1f — src/shared/ medium-small batch (16 files)."""
from __future__ import annotations

import asyncio
import json
import math
import sys

import pytest

from src.shared.device_auth_store import (
    clear_device_auth_token_from_store,
    coerce_device_auth_store,
    load_device_auth_token_from_store,
    store_device_auth_token_in_store,
)
from src.shared.device_pairing_access import (
    resolve_pending_device_approval_state,
)
from src.shared.entry_metadata import resolve_emoji_and_homepage
from src.shared.node_list_parse import parse_node_list, parse_pairing_list
from src.shared.node_match import resolve_node_id_from_candidates
from src.shared.node_presence import (
    NODE_PRESENCE_ACTIVITY_EVENT,
    NODE_PRESENCE_ALIVE_EVENT,
    normalize_node_presence_alive_reason,
)
from src.shared.node_resolve import (
    resolve_node_from_node_list,
    resolve_node_id_from_node_list,
)
from src.shared.safe_record import (
    copy_array_entries,
    copy_record_entries,
    is_record_without_throwing,
    read_record_value,
)
from src.shared.session_types import (
    GatewayAgentRow,
    SessionsListResultBase,
    SessionsPatchResultBase,
)
from src.shared.session_usage_timeseries_types import (
    SessionUsageTimePoint,
    SessionUsageTimeSeries,
)
from src.shared.silent_reply_policy import (
    DEFAULT_SILENT_REPLY_POLICY,
    classify_silent_reply_conversation_type,
    resolve_silent_reply_policy_from_policies,
)
from src.shared.string_sample import summarize_string_entries
from src.shared.subagents_format import (
    format_token_usage_display,
    resolve_total_tokens,
    truncate_line,
)
from src.shared.text_chunking import (
    avoid_trailing_high_surrogate_break,
    chunk_text_by_break_resolver,
)
from src.shared.transcript_only_openclaw_assistant import (
    OPENCLAW_DELIVERY_MIRROR_MODEL,
    OPENCLAW_TRANSCRIPT_ARTIFACT_PROVIDER,
    is_openclaw_delivery_mirror_assistant_message,
    is_openclaw_internal_source_reply_mirror_assistant_message,
    is_openclaw_message_tool_mirror_assistant_message,
    is_transcript_only_openclaw_assistant_message,
    is_transcript_only_openclaw_assistant_model,
)
from src.shared.usage_aggregates import (
    build_usage_aggregate_tail,
    merge_usage_daily_latency,
    merge_usage_latency,
)
from src.shared.usage_types import (
    SessionUsageEntry,
    SessionsUsageAggregates,
    SessionsUsageResult,
)


# ============================================================================
# entry-metadata
# ============================================================================


class TestEntryMetadata:
    def test_metadata_wins(self) -> None:
        out = resolve_emoji_and_homepage({
            "metadata": {"emoji": "🤖", "homepage": "https://a.example"},
            "frontmatter": {"emoji": "X", "homepage": "https://b.example"},
        })
        assert out == {"emoji": "🤖", "homepage": "https://a.example"}

    def test_frontmatter_fallback(self) -> None:
        out = resolve_emoji_and_homepage({
            "metadata": None,
            "frontmatter": {"emoji": "X", "website": "https://b.example"},
        })
        assert out == {"emoji": "X", "homepage": "https://b.example"}

    def test_url_alias(self) -> None:
        out = resolve_emoji_and_homepage({
            "frontmatter": {"url": "https://c.example"},
        })
        assert out == {"homepage": "https://c.example"}

    def test_empty(self) -> None:
        out = resolve_emoji_and_homepage({})
        assert out == {}

    def test_normalizes_whitespace(self) -> None:
        out = resolve_emoji_and_homepage({"frontmatter": {"homepage": "  https://x.example  "}})
        assert out == {"homepage": "https://x.example"}


# ============================================================================
# node-presence
# ============================================================================


class TestNodePresence:
    def test_constants(self) -> None:
        assert NODE_PRESENCE_ALIVE_EVENT == "node.presence.alive"
        assert NODE_PRESENCE_ACTIVITY_EVENT == "node.presence.activity"

    def test_known_reason(self) -> None:
        assert normalize_node_presence_alive_reason("background") == "background"
        assert normalize_node_presence_alive_reason("MANUAL") == "manual"
        assert normalize_node_presence_alive_reason(" connect ") == "connect"

    def test_unknown_falls_back(self) -> None:
        assert normalize_node_presence_alive_reason("alien") == "background"
        assert normalize_node_presence_alive_reason(None) == "background"
        assert normalize_node_presence_alive_reason(42) == "background"

    def test_empty_falls_back(self) -> None:
        assert normalize_node_presence_alive_reason("") == "background"


# ============================================================================
# node-resolve
# ============================================================================


class TestNodeResolve:
    NODES = [
        {"nodeId": "n1", "displayName": "alpha", "remoteIp": "10.0.0.1"},
        {"nodeId": "n2", "displayName": "beta", "remoteIp": "10.0.0.2"},
    ]

    def test_exact_id(self) -> None:
        assert resolve_node_id_from_node_list(self.NODES, "n1") == "n1"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="node required"):
            resolve_node_id_from_node_list(self.NODES, "")

    def test_default_picker(self) -> None:
        picked = resolve_node_id_from_node_list(
            self.NODES,
            "",
            {"allowDefault": True, "pickDefaultNode": lambda nodes: nodes[0]},
        )
        assert picked == "n1"

    def test_default_no_picker_raises(self) -> None:
        with pytest.raises(ValueError, match="node required"):
            resolve_node_id_from_node_list(self.NODES, "", {"allowDefault": True})

    def test_resolve_node_preserves_synthetic(self) -> None:
        node = resolve_node_from_node_list(self.NODES, "n1")
        assert node["nodeId"] == "n1"

    def test_resolve_node_synthetic_fallback(self) -> None:
        # Default picker returns a node not in the original list; OpenClaw
        # keeps only its nodeId (the synthetic record is dropped).
        synthetic = {"nodeId": "n3", "displayName": "synthetic"}
        node = resolve_node_from_node_list(
            self.NODES, "", {"allowDefault": True, "pickDefaultNode": lambda _n: synthetic}
        )
        assert node == {"nodeId": "n3"}

    def test_unknown_node_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown node"):
            resolve_node_id_from_node_list(self.NODES, "ghost")


# ============================================================================
# safe-record
# ============================================================================


class TestSafeRecord:
    def test_is_record(self) -> None:
        assert is_record_without_throwing({}) is True
        assert is_record_without_throwing({"a": 1}) is True
        assert is_record_without_throwing([]) is False
        assert is_record_without_throwing(None) is False
        assert is_record_without_throwing("string") is False
        assert is_record_without_throwing(42) is False

    def test_read_value(self) -> None:
        assert read_record_value({"a": 1}, "a") == 1
        assert read_record_value({"a": 1}, "missing") is None
        assert read_record_value(None, "a") is None
        assert read_record_value("string", "a") is None

    def test_copy_array_entries(self) -> None:
        assert copy_array_entries([1, 2, 3]) == [1, 2, 3]
        assert copy_array_entries("not array") == []
        assert copy_array_entries(None) == []
        assert copy_array_entries([]) == []

    def test_copy_record_entries(self) -> None:
        out = copy_record_entries({"a": {"x": 1}, "b": {"y": 2}, "c": "string"})
        keys = [k for k, _ in out]
        assert "a" in keys
        assert "b" in keys
        assert "c" not in keys

    def test_copy_record_entries_empty(self) -> None:
        assert copy_record_entries(None) == []
        assert copy_record_entries([]) == []


# ============================================================================
# session-types
# ============================================================================


class TestSessionTypes:
    def test_agent_row(self) -> None:
        row: GatewayAgentRow = {"id": "a1", "name": "Alice"}
        assert row["id"] == "a1"

    def test_sessions_list_result_base(self) -> None:
        r: SessionsListResultBase = {"ts": 1, "path": "/x", "count": 0, "sessions": []}
        assert r["count"] == 0

    def test_sessions_patch_result_base(self) -> None:
        r: SessionsPatchResultBase = {"ok": True, "path": "/x", "key": "k", "entry": {}}
        assert r["ok"] is True


# ============================================================================
# session-usage-timeseries-types
# ============================================================================


class TestSessionUsageTimeSeriesTypes:
    def test_point(self) -> None:
        p: SessionUsageTimePoint = {
            "timestamp": 1,
            "input": 10,
            "output": 20,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 30,
            "cost": 0.001,
            "cumulativeTokens": 30,
            "cumulativeCost": 0.001,
        }
        assert p["totalTokens"] == 30

    def test_series(self) -> None:
        s: SessionUsageTimeSeries = {"sessionId": "s1", "points": []}
        assert s["sessionId"] == "s1"


# ============================================================================
# silent-reply-policy
# ============================================================================


class TestSilentReplyPolicy:
    def test_classify_explicit(self) -> None:
        assert classify_silent_reply_conversation_type({"conversationType": "direct"}) == "direct"
        assert classify_silent_reply_conversation_type({"conversationType": "group"}) == "group"
        assert classify_silent_reply_conversation_type({"conversationType": "internal"}) == "internal"

    def test_classify_from_session_key(self) -> None:
        assert classify_silent_reply_conversation_type({"sessionKey": "x:group:abc"}) == "group"
        assert classify_silent_reply_conversation_type({"sessionKey": "x:channel:abc"}) == "group"
        assert classify_silent_reply_conversation_type({"sessionKey": "x:direct:abc"}) == "direct"
        assert classify_silent_reply_conversation_type({"sessionKey": "x:dm:abc"}) == "direct"

    def test_classify_from_surface(self) -> None:
        assert classify_silent_reply_conversation_type({"surface": "webchat"}) == "direct"

    def test_classify_default_internal(self) -> None:
        assert classify_silent_reply_conversation_type({}) == "internal"

    def test_resolve_direct_always_disallow(self) -> None:
        out = resolve_silent_reply_policy_from_policies({
            "conversationType": "direct",
            "surfacePolicy": {"group": "disallow"},
        })
        assert out == "disallow"

    def test_resolve_surface_over_default(self) -> None:
        out = resolve_silent_reply_policy_from_policies({
            "conversationType": "group",
            "defaultPolicy": {"group": "allow"},
            "surfacePolicy": {"group": "disallow"},
        })
        assert out == "disallow"

    def test_resolve_default_fallback(self) -> None:
        out = resolve_silent_reply_policy_from_policies({"conversationType": "group"})
        assert out == DEFAULT_SILENT_REPLY_POLICY["group"]

    def test_constants(self) -> None:
        assert DEFAULT_SILENT_REPLY_POLICY["direct"] == "disallow"
        assert DEFAULT_SILENT_REPLY_POLICY["group"] == "allow"


# ============================================================================
# string-sample
# ============================================================================


class TestStringSample:
    def test_basic(self) -> None:
        out = summarize_string_entries({"entries": ["a", "b", "c"]})
        assert out == "a, b, c"

    def test_limit(self) -> None:
        out = summarize_string_entries({"entries": ["a", "b", "c", "d", "e"], "limit": 2})
        assert out == "a, b (+3)"

    def test_empty(self) -> None:
        assert summarize_string_entries({"entries": []}) == ""
        assert summarize_string_entries({"entries": [], "emptyText": "none"}) == "none"
        assert summarize_string_entries({}) == ""

    def test_bad_limit_clamps(self) -> None:
        # limit=0 clamps to 1 (Math.max(1, 0) === 1).
        out = summarize_string_entries({"entries": ["a", "b"], "limit": 0})
        assert out == "a (+1)"
        # NaN falls back to default 6.
        out = summarize_string_entries({"entries": ["a", "b"], "limit": math.nan})
        assert out == "a, b"


# ============================================================================
# text-chunking
# ============================================================================


class TestTextChunking:
    def test_empty(self) -> None:
        assert chunk_text_by_break_resolver("", 10, lambda w: 0) == []

    def test_short_text(self) -> None:
        assert chunk_text_by_break_resolver("hello", 100, lambda w: 0) == ["hello"]

    def test_zero_limit(self) -> None:
        assert chunk_text_by_break_resolver("hello", 0, lambda w: 0) == ["hello"]

    def test_basic_chunking(self) -> None:
        text = "abcdefghij" * 5  # 50 chars
        out = chunk_text_by_break_resolver(text, 15, lambda w: 10)
        assert len(out) >= 2

    def test_soft_break_used(self) -> None:
        text = "abc def ghi jkl mno pqr"
        # Resolver picks break after "ghi" (position 8 in window).
        out = chunk_text_by_break_resolver(text, 12, lambda w: 8)
        # First chunk is "abc def" (trimmed), remainder "ghi jkl mno pqr".
        assert out[0] == "abc def"

    def test_invalid_break_falls_back(self) -> None:
        text = "abcdefghij" * 3
        out = chunk_text_by_break_resolver(text, 10, lambda w: -1)
        # Falls back to limit.
        assert all(len(c) <= 10 for c in out)

    def test_avoid_surrogate_break(self) -> None:
        # High surrogate at index 4, low at 5 (a real surrogate pair).
        # `end=5` sits on the low half; backing off to 4 leaves the high
        # half unpaired. Wait — OpenClaw backs off `end-1` to 4 in that
        # case (the function's own semantics; the sliceUtf16Safe caller
        # combines it with end-inclusive slicing).
        text = "abcd\ud83d\ude00efghij"
        out = avoid_trailing_high_surrogate_break(text, 0, 5)
        # text[4] is high surrogate, text[5] is low → back off to 4.
        assert out == 4

    def test_avoid_surrogate_break_passes_through(self) -> None:
        # When end does not land on a surrogate pair, return end unchanged.
        text = "abcdefghij"
        out = avoid_trailing_high_surrogate_break(text, 0, 6)
        assert out == 6


# ============================================================================
# node-list-parse
# ============================================================================


class TestNodeListParse:
    def test_pairing_valid(self) -> None:
        result = parse_pairing_list({
            "pending": [
                {"requestId": "r1", "nodeId": "n1", "displayName": "  alpha  "},
                {"requestId": "r2", "nodeId": "n2"},
            ],
            "paired": [
                {"nodeId": "n3", "platform": "linux"},
            ],
        })
        assert len(result["pending"]) == 2
        assert result["pending"][0]["displayName"] == "alpha"
        assert len(result["paired"]) == 1
        assert result["paired"][0]["platform"] == "linux"

    def test_pairing_drops_invalid(self) -> None:
        result = parse_pairing_list({
            "pending": [
                {"requestId": "", "nodeId": "n1"},  # empty requestId
                {"requestId": "r2", "nodeId": "n2"},
                {"requestId": 42, "nodeId": "n3"},  # non-string requestId
                "not a dict",
            ],
        })
        assert len(result["pending"]) == 1

    def test_pairing_empty(self) -> None:
        assert parse_pairing_list(None) == {"pending": [], "paired": []}
        assert parse_pairing_list({}) == {"pending": [], "paired": []}

    def test_node_list(self) -> None:
        out = parse_node_list({"nodes": [{"nodeId": "n1"}, {"nodeId": "n2"}]})
        assert len(out) == 2

    def test_node_list_empty(self) -> None:
        assert parse_node_list(None) == []
        assert parse_node_list({}) == []
        assert parse_node_list({"nodes": "not a list"}) == []


# ============================================================================
# node-match
# ============================================================================


class TestNodeMatch:
    NODES = [
        {"nodeId": "long-id-1", "displayName": "Alpha", "remoteIp": "10.0.0.1"},
        {"nodeId": "long-id-2", "displayName": "Beta", "remoteIp": "10.0.0.2"},
    ]

    def test_exact_id(self) -> None:
        assert resolve_node_id_from_candidates(self.NODES, "long-id-1") == "long-id-1"

    def test_remote_ip(self) -> None:
        assert resolve_node_id_from_candidates(self.NODES, "10.0.0.1") == "long-id-1"

    def test_display_name(self) -> None:
        assert resolve_node_id_from_candidates(self.NODES, "alpha") == "long-id-1"

    def test_id_prefix(self) -> None:
        assert resolve_node_id_from_candidates(self.NODES, "long-id-1") == "long-id-1"

    def test_unknown(self) -> None:
        with pytest.raises(ValueError, match="unknown node"):
            resolve_node_id_from_candidates(self.NODES, "ghost")

    def test_ambiguous(self) -> None:
        nodes = [
            {"nodeId": "id-1", "displayName": "alpha"},
            {"nodeId": "id-2", "displayName": "alpha"},
        ]
        with pytest.raises(ValueError, match="ambiguous"):
            resolve_node_id_from_candidates(nodes, "alpha")

    def test_connected_tiebreak(self) -> None:
        nodes = [
            {"nodeId": "id-1", "displayName": "alpha", "connected": False},
            {"nodeId": "id-2", "displayName": "alpha", "connected": True},
        ]
        assert resolve_node_id_from_candidates(nodes, "alpha") == "id-2"

    def test_empty_query_raises(self) -> None:
        with pytest.raises(ValueError, match="node required"):
            resolve_node_id_from_candidates(self.NODES, "")


# ============================================================================
# device-auth-store
# ============================================================================


class _Adapter:
    def __init__(self) -> None:
        self.store = None
        self.reads = 0
        self.writes = 0

    def readStore(self):
        self.reads += 1
        return self.store

    def writeStore(self, store):
        self.writes += 1
        self.store = store


class TestDeviceAuthStore:
    def test_coerce_valid(self) -> None:
        store = coerce_device_auth_store({
            "version": 1,
            "deviceId": "d1",
            "tokens": {
                "operator": {"token": "t1", "scopes": ["operator.read"], "updatedAtMs": 100},
            },
        })
        assert store is not None
        assert store["deviceId"] == "d1"
        assert store["tokens"]["operator"]["token"] == "t1"

    def test_coerce_invalid_version(self) -> None:
        assert coerce_device_auth_store({"version": 2, "deviceId": "d1"}) is None

    def test_coerce_missing_tokens(self) -> None:
        assert coerce_device_auth_store({"version": 1, "deviceId": "d1"}) is None

    def test_coerce_drops_invalid_token(self) -> None:
        store = coerce_device_auth_store({
            "version": 1,
            "deviceId": "d1",
            "tokens": {
                "operator": {"token": "t1", "scopes": ["operator.read"]},
                "node": {"scopes": []},  # missing token
            },
        })
        assert store is not None
        assert "operator" in store["tokens"]
        assert "node" not in store["tokens"]

    def test_load_wrong_device(self) -> None:
        adapter = _Adapter()
        adapter.store = {"version": 1, "deviceId": "other", "tokens": {}}
        assert load_device_auth_token_from_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator",
        }) is None

    def test_store_and_load(self) -> None:
        adapter = _Adapter()
        entry = store_device_auth_token_in_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator",
            "token": "t1", "scopes": ["operator.admin", "operator.admin", "operator.read"],
        })
        assert entry["role"] == "operator"
        assert "operator.read" in entry["scopes"]  # admin implies read
        assert "operator.write" in entry["scopes"]
        loaded = load_device_auth_token_from_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator",
        })
        assert loaded["token"] == "t1"

    def test_clear(self) -> None:
        adapter = _Adapter()
        store_device_auth_token_in_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator", "token": "t1",
        })
        clear_device_auth_token_from_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator",
        })
        loaded = load_device_auth_token_from_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator",
        })
        assert loaded is None

    def test_clear_wrong_device(self) -> None:
        adapter = _Adapter()
        adapter.store = {"version": 1, "deviceId": "other", "tokens": {}}
        clear_device_auth_token_from_store({
            "adapter": adapter, "deviceId": "d1", "role": "operator",
        })
        assert adapter.writes == 0


# ============================================================================
# device-pairing-access
# ============================================================================


class TestDevicePairingAccess:
    def test_new_pairing(self) -> None:
        out = resolve_pending_device_approval_state({"roles": ["node"], "scopes": []})
        assert out["kind"] == "new-pairing"
        assert out["approved"] is None

    def test_role_upgrade(self) -> None:
        out = resolve_pending_device_approval_state(
            {"roles": ["node", "operator"], "scopes": []},
            {"roles": ["node"], "scopes": []},
        )
        assert out["kind"] == "role-upgrade"

    def test_scope_upgrade(self) -> None:
        out = resolve_pending_device_approval_state(
            {"roles": ["node"], "scopes": ["operator.read"]},
            {"roles": ["node"], "scopes": []},
        )
        assert out["kind"] == "scope-upgrade"

    def test_re_approval(self) -> None:
        out = resolve_pending_device_approval_state(
            {"roles": ["node"], "scopes": []},
            {"roles": ["node"], "scopes": []},
        )
        assert out["kind"] == "re-approval"

    def test_revoked_token_excluded(self) -> None:
        out = resolve_pending_device_approval_state(
            {"roles": ["node"], "scopes": []},
            {
                "roles": ["node", "operator"],
                "scopes": [],
                "tokens": [{"role": "operator", "revokedAtMs": 100}],
            },
        )
        # operator role's token is revoked, so approved.roles is []. The
        # pending request needs a new "node" role grant → role-upgrade.
        assert out["kind"] == "role-upgrade"
        assert out["approved"]["roles"] == []

    def test_legacy_singular_role(self) -> None:
        out = resolve_pending_device_approval_state(
            {"role": "operator", "scopes": []},
            {"role": "operator", "scopes": []},
        )
        assert out["kind"] == "re-approval"


# ============================================================================
# subagents-format
# ============================================================================


class TestSubagentsFormat:
    def test_truncate_basic(self) -> None:
        assert truncate_line("hello world", 8) == "hello..."

    def test_truncate_short(self) -> None:
        assert truncate_line("hi", 10) == "hi"

    def test_truncate_strips(self) -> None:
        assert truncate_line("hello   ", 10) == "hello"

    def test_truncate_zero(self) -> None:
        assert truncate_line("hello", 0) == ""

    def test_truncate_marker_only(self) -> None:
        assert truncate_line("hello", 2) == ".."

    def test_resolve_total_tokens_explicit(self) -> None:
        assert resolve_total_tokens({"totalTokens": 100, "inputTokens": 50, "outputTokens": 50}) == 100

    def test_resolve_total_tokens_fallback(self) -> None:
        assert resolve_total_tokens({"inputTokens": 50, "outputTokens": 30}) == 80

    def test_resolve_total_tokens_zero(self) -> None:
        assert resolve_total_tokens({"inputTokens": 0, "outputTokens": 0}) is None

    def test_resolve_total_tokens_none(self) -> None:
        assert resolve_total_tokens(None) is None
        assert resolve_total_tokens("not dict") is None

    def test_format_token_usage(self) -> None:
        out = format_token_usage_display({"inputTokens": 500, "outputTokens": 200})
        assert "tokens" in out
        assert "in 500" in out
        assert "out 200" in out

    def test_format_token_usage_empty(self) -> None:
        assert format_token_usage_display(None) == ""
        assert format_token_usage_display({}) == ""

    def test_format_token_usage_prompt_cache(self) -> None:
        out = format_token_usage_display({"totalTokens": 100})
        assert "prompt/cache" in out


# ============================================================================
# transcript-only-openclaw-assistant
# ============================================================================


class TestTranscriptOnlyOpenClawAssistant:
    def test_constants(self) -> None:
        assert OPENCLAW_TRANSCRIPT_ARTIFACT_PROVIDER == "openclaw"
        assert OPENCLAW_DELIVERY_MIRROR_MODEL == "delivery-mirror"

    def test_model_match(self) -> None:
        assert is_transcript_only_openclaw_assistant_model("openclaw", "delivery-mirror") is True
        assert is_transcript_only_openclaw_assistant_model("openclaw", "gateway-injected") is True

    def test_model_mismatch(self) -> None:
        assert is_transcript_only_openclaw_assistant_model("openai", "delivery-mirror") is False
        assert is_transcript_only_openclaw_assistant_model("openclaw", "gpt-4") is False

    def test_message_match(self) -> None:
        msg = {"role": "assistant", "provider": "openclaw", "model": "delivery-mirror"}
        assert is_transcript_only_openclaw_assistant_message(msg) is True

    def test_message_user_role(self) -> None:
        msg = {"role": "user", "provider": "openclaw", "model": "delivery-mirror"}
        assert is_transcript_only_openclaw_assistant_message(msg) is False

    def test_message_mirror_marker(self) -> None:
        msg = {"role": "assistant", "openclawDeliveryMirror": {"kind": "channel-final"}}
        assert is_transcript_only_openclaw_assistant_message(msg) is True

    def test_message_tool_mirror(self) -> None:
        msg = {"role": "assistant", "openclawMessageToolMirror": {}}
        assert is_openclaw_message_tool_mirror_assistant_message(msg) is True
        assert is_transcript_only_openclaw_assistant_message(msg) is False

    def test_internal_source_reply(self) -> None:
        msg = {
            "role": "assistant",
            "openclawMessageToolMirror": {"sourceReplySink": "internal-ui"},
        }
        assert is_openclaw_internal_source_reply_mirror_assistant_message(msg) is True

    def test_delivery_mirror(self) -> None:
        msg = {"role": "assistant", "provider": "openclaw", "model": "delivery-mirror"}
        assert is_openclaw_delivery_mirror_assistant_message(msg) is True

    def test_non_object(self) -> None:
        assert is_transcript_only_openclaw_assistant_message(None) is False
        assert is_transcript_only_openclaw_assistant_message("string") is False
        assert is_transcript_only_openclaw_assistant_message([1, 2]) is False


# ============================================================================
# usage-aggregates
# ============================================================================


class TestUsageAggregates:
    def test_merge_latency(self) -> None:
        totals = {"count": 0, "sum": 0, "min": math.inf, "max": 0, "p95Max": 0}
        merge_usage_latency(totals, {"count": 2, "avgMs": 100, "minMs": 50, "maxMs": 200, "p95Ms": 180})
        assert totals["count"] == 2
        assert totals["sum"] == 200
        assert totals["min"] == 50
        assert totals["max"] == 200
        assert totals["p95Max"] == 180

    def test_merge_latency_zero_count(self) -> None:
        totals = {"count": 0, "sum": 0, "min": math.inf, "max": 0, "p95Max": 0}
        merge_usage_latency(totals, {"count": 0, "avgMs": 100})
        assert totals["count"] == 0

    def test_merge_daily_latency(self) -> None:
        m: dict = {}
        merge_usage_daily_latency(m, [
            {"date": "2026-08-01", "count": 1, "avgMs": 100, "minMs": 100, "maxMs": 100, "p95Ms": 100},
            {"date": "2026-08-01", "count": 1, "avgMs": 200, "minMs": 200, "maxMs": 200, "p95Ms": 200},
            {"date": "2026-08-02", "count": 1, "avgMs": 300, "minMs": 300, "maxMs": 300, "p95Ms": 300},
        ])
        assert m["2026-08-01"]["count"] == 2
        assert m["2026-08-01"]["sum"] == 300
        assert m["2026-08-02"]["count"] == 1

    def test_build_aggregate_tail(self) -> None:
        out = build_usage_aggregate_tail({
            "byChannelMap": {
                "telegram": {"totalCost": 1.0},
                "discord": {"totalCost": 0.5},
            },
            "latencyTotals": {"count": 2, "sum": 200, "min": 50, "max": 200, "p95Max": 180},
            "dailyLatencyMap": {
                "2026-08-01": {"date": "2026-08-01", "count": 2, "sum": 200, "min": 50, "max": 200, "p95Max": 180},
            },
            "modelDailyMap": {
                "k1": {"date": "2026-08-01", "cost": 1.0},
            },
            "dailyMap": {
                "2026-08-01": {"date": "2026-08-01"},
            },
        })
        # byChannel sorted by totalCost desc.
        assert [c["channel"] for c in out["byChannel"]] == ["telegram", "discord"]
        # latency summary.
        assert out["latency"]["avgMs"] == 100
        assert out["latency"]["minMs"] == 50
        # daily latency ordered.
        assert [d["date"] for d in out["dailyLatency"]] == ["2026-08-01"]

    def test_build_no_latency(self) -> None:
        out = build_usage_aggregate_tail({
            "byChannelMap": {},
            "latencyTotals": {"count": 0, "sum": 0, "min": math.inf, "max": 0, "p95Max": 0},
            "dailyLatencyMap": {},
            "modelDailyMap": {},
            "dailyMap": {},
        })
        assert out["latency"] is None
        assert out["byChannel"] == []


# ============================================================================
# usage-types
# ============================================================================


class TestUsageTypes:
    def test_entry(self) -> None:
        e: SessionUsageEntry = {
            "key": "k1",
            "scope": "instance",
            "usage": None,
        }
        assert e["key"] == "k1"

    def test_aggregates(self) -> None:
        a: SessionsUsageAggregates = {"messages": {}, "tools": {}, "daily": []}
        assert a["messages"] == {}

    def test_result(self) -> None:
        r: SessionsUsageResult = {
            "updatedAt": 1,
            "startDate": "2026-08-01",
            "endDate": "2026-08-01",
            "sessions": [],
            "totals": {},
            "aggregates": {"messages": {}, "tools": {}, "daily": []},
        }
        assert r["startDate"] == "2026-08-01"
