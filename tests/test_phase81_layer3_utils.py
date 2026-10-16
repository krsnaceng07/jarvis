"""Phase 8.1 tests — src/utils/ (31 files ported)."""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, List

import pytest

# Ensure src/ is on sys.path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.utils.account_id import normalize_account_id  # noqa: E402
from src.utils.boolean import (  # noqa: E402
    DEFAULT_FALSY,
    DEFAULT_TRUTHY,
    as_boolean,
    parse_boolean_value,
)
from src.utils.chunk_items import chunk_items  # noqa: E402
from src.utils.cjk_chars import (  # noqa: E402
    CHARS_PER_TOKEN_ESTIMATE,
    estimate_string_chars,
    estimate_tokens_from_chars,
)
from src.utils.conversation_target import (  # noqa: E402
    ConversationTargetParams,
    normalize_conversation_target_params,
)
from src.utils.delivery_context import (  # noqa: E402
    DeliveryContext,
    delivery_context_from_session,
    delivery_context_key,
    merge_delivery_context,
    normalize_delivery_context,
)
from src.utils.delivery_context.shared import (  # noqa: E402
    set_delivery_context_from_session_hook,
    set_delivery_context_key_hook,
    set_merge_delivery_context_hook,
    set_normalize_delivery_channel_route_hook,
    set_normalize_delivery_context_hook,
    set_normalize_session_delivery_fields_hook,
)
from src.utils.directive_tags import (  # noqa: E402
    MAX_REPLY_DIRECTIVE_ID_LENGTH,
    parse_inline_directives,
    sanitize_reply_directive_id,
    strip_inline_directive_tags_for_delivery,
    strip_inline_directive_tags_for_display,
    strip_inline_directive_tags_from_message_for_display,
)
from src.utils.fetch_timeout import (  # noqa: E402
    DEFAULT_FETCH_TIMEOUT_MS,
    LOG_URL_MAX_CHARS,
    bind_abort_relay,
    build_timeout_abort_signal,
)
from src.utils.message_channel import (  # noqa: E402
    GATEWAY_CLIENT_MODES,
    GATEWAY_CLIENT_NAMES,
    INTERNAL_MESSAGE_CHANNEL,
    is_browser_copilot_client,
    is_browser_operator_ui_client,
    is_ephemeral_gateway_client,
    is_gateway_cli_client,
    is_gateway_message_channel,
    is_internal_message_channel,
    is_markdown_capable_message_channel,
    is_native_approval_channel,
    is_operator_ui_client,
    is_webchat_client,
    list_deliverable_message_channels,
    normalize_message_channel,
    resolve_message_channel,
)
from src.utils.message_channel_constants import (  # noqa: E402
    INTERNAL_NON_DELIVERY_CHANNELS,
    internal_session_conversation_id,
    is_internal_non_delivery_channel,
)
from src.utils.normalize_secret_input import (  # noqa: E402
    normalize_optional_secret_input,
    normalize_secret_input,
)
from src.utils.parse_json_compat import parse_json_with_json5_fallback  # noqa: E402
from src.utils.provider_utils import (  # noqa: E402
    is_reasoning_tag_provider,
    set_is_reasoning_tag_provider_hook,
    set_resolve_reasoning_output_mode_hook,
)
from src.utils.queue_helpers import (  # noqa: E402
    apply_queue_runtime_settings,
    build_queue_summary_prompt,
    count_pending_queue_items,
    drain_queue_collection,
    drain_queue_items,
    merge_queue_summary,
    resolve_debounce_ms,
    should_skip_queue_item,
    summarize_dropped_queue_items,
    set_apply_queue_runtime_settings_hook,
    set_build_queue_summary_prompt_hook,
    set_count_pending_queue_items_hook,
    set_drain_queue_collection_hook,
    set_drain_queue_items_hook,
    set_merge_queue_summary_hook,
    set_preview_queue_summary_prompt_hook,
    set_resolve_debounce_ms_hook,
    set_should_skip_queue_item_hook,
    set_summarize_dropped_queue_items_hook,
)
from src.utils.reaction_level import (  # noqa: E402
    resolve_reaction_level,
)
from src.utils.run_with_concurrency import (  # noqa: E402
    run_tasks_with_concurrency,
)
from src.utils.safe_json import safe_json_stringify  # noqa: E402
from src.utils.sleep import sleep  # noqa: E402
from src.utils.string_readers import (  # noqa: E402
    is_string_option,
    read_string_alias,
    read_string_value,
    read_trimmed_string_alias,
    strip_channel_prefix,
)
from src.utils.timer_delay import (  # noqa: E402
    MAX_SAFE_TIMEOUT_DELAY_MS,
    add_safe_timeout_delay_grace_ms,
    resolve_safe_timeout_delay_ms,
)
from src.utils.token_format import format_token_count  # noqa: E402
from src.utils.transcript_tools import (  # noqa: E402
    count_tool_results,
    extract_tool_call_names,
    has_tool_call,
)
from src.utils.usage_format import (  # noqa: E402
    format_usage_cost_usd,
    format_usage_tokens,
    set_format_usage_cost_usd_hook,
    set_format_usage_tokens_hook,
)
from src.utils.utf8_truncate import (  # noqa: E402
    truncate_utf8_prefix,
    truncate_utf8_suffix,
)
from src.utils.with_timeout import with_timeout  # noqa: E402
from src.utils.zod_parse import (  # noqa: E402
    safe_parse_json_with_schema,
    safe_parse_with_schema,
)


# ============================================================================
# account_id
# ============================================================================


class TestAccountId:
    def test_basic(self) -> None:
        assert normalize_account_id("acc-1") == "acc-1"

    def test_blank(self) -> None:
        assert normalize_account_id("") is None
        assert normalize_account_id(None) is None
        assert normalize_account_id("   ") is None


# ============================================================================
# boolean
# ============================================================================


class TestBoolean:
    def test_constants(self) -> None:
        assert "true" in DEFAULT_TRUTHY
        assert "false" in DEFAULT_FALSY

    def test_as_boolean(self) -> None:
        assert as_boolean(True) is True
        assert as_boolean(False) is False
        assert as_boolean("true") is None
        assert as_boolean(1) is None

    def test_parse_true(self) -> None:
        assert parse_boolean_value("true") is True
        assert parse_boolean_value("1") is True
        assert parse_boolean_value("yes") is True
        assert parse_boolean_value("on") is True

    def test_parse_false(self) -> None:
        assert parse_boolean_value("false") is False
        assert parse_boolean_value("0") is False

    def test_parse_ambiguous(self) -> None:
        assert parse_boolean_value("maybe") is None
        assert parse_boolean_value(None) is None
        assert parse_boolean_value("") is None

    def test_parse_custom(self) -> None:
        assert parse_boolean_value("foo", {"truthy": ["foo"], "falsy": ["bar"]}) is True
        assert parse_boolean_value("bar", {"truthy": ["foo"], "falsy": ["bar"]}) is False


# ============================================================================
# chunk_items
# ============================================================================


class TestChunkItems:
    def test_basic(self) -> None:
        assert chunk_items([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_empty(self) -> None:
        assert chunk_items([], 2) == []

    def test_zero_size(self) -> None:
        assert chunk_items([1, 2, 3], 0) == [[1, 2, 3]]

    def test_negative_size(self) -> None:
        assert chunk_items([1, 2, 3], -1) == [[1, 2, 3]]

    def test_even(self) -> None:
        assert chunk_items([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


# ============================================================================
# cjk_chars
# ============================================================================


class TestCjkChars:
    def test_constant(self) -> None:
        assert CHARS_PER_TOKEN_ESTIMATE == 4

    def test_empty(self) -> None:
        assert estimate_string_chars("") == 0

    def test_ascii(self) -> None:
        # ASCII text: 1 char each
        assert estimate_string_chars("hello") == 5

    def test_cjk(self) -> None:
        # CJK: each char counts as CHARS_PER_TOKEN_ESTIMATE (4)
        text = "你好"
        assert estimate_string_chars(text) == 2 * CHARS_PER_TOKEN_ESTIMATE

    def test_mixed(self) -> None:
        text = "hi你好"
        # "hi" = 2 ASCII
        # "你好" = 2 CJK * 4 = 8
        assert estimate_string_chars(text) == 10

    def test_estimate_tokens(self) -> None:
        assert estimate_tokens_from_chars(8) == 2  # 8/4 = 2
        assert estimate_tokens_from_chars(7) == 2  # ceil(7/4) = 2
        assert estimate_tokens_from_chars(0) == 0
        assert estimate_tokens_from_chars(-5) == 0


# ============================================================================
# conversation_target
# ============================================================================


class TestConversationTarget:
    def test_basic(self) -> None:
        out = normalize_conversation_target_params(
            {"channel": "telegram", "conversationId": 123, "parentConversationId": "456"}
        )
        assert out["channel"] == "telegram"
        assert out["conversationId"] == "123"
        assert out["parentConversationId"] == "456"

    def test_string_id(self) -> None:
        out = normalize_conversation_target_params(
            {"channel": "telegram", "conversationId": "abc"}
        )
        assert out["conversationId"] == "abc"

    def test_blank(self) -> None:
        out = normalize_conversation_target_params({})
        assert out["channel"] is None
        assert out["conversationId"] is None
        assert out["parentConversationId"] is None

    def test_typed_input(self) -> None:
        params = ConversationTargetParams(
            channel="telegram", conversation_id=99
        )
        out = normalize_conversation_target_params(params)
        assert out["conversationId"] == "99"


# ============================================================================
# delivery_context
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_delivery_hooks() -> None:
    set_normalize_delivery_context_hook(None)
    set_merge_delivery_context_hook(None)
    set_delivery_context_from_session_hook(None)
    set_delivery_context_key_hook(None)
    set_normalize_delivery_channel_route_hook(None)
    set_normalize_session_delivery_fields_hook(None)
    yield
    set_normalize_delivery_context_hook(None)
    set_merge_delivery_context_hook(None)
    set_delivery_context_from_session_hook(None)
    set_delivery_context_key_hook(None)
    set_normalize_delivery_channel_route_hook(None)
    set_normalize_session_delivery_fields_hook(None)


class TestDeliveryContext:
    def test_normalize_basic(self) -> None:
        out = normalize_delivery_context(
            {"channel": "telegram", "to": "user-1", "accountId": "acc-1"}
        )
        assert out is not None
        assert out["channel"] == "telegram"
        assert out["to"] == "user-1"
        assert out["accountId"] == "acc-1"

    def test_normalize_blank(self) -> None:
        assert normalize_delivery_context(None) is None
        assert normalize_delivery_context({}) is None

    def test_normalize_with_typed(self) -> None:
        ctx = DeliveryContext(channel="discord", to="u1")
        out = normalize_delivery_context(ctx)
        assert out is not None
        assert out["channel"] == "discord"

    def test_merge_complementary(self) -> None:
        a = {"channel": "telegram", "to": "u1"}
        b = {"channel": "telegram", "accountId": "acc-1"}
        out = merge_delivery_context(a, b)
        assert out["channel"] == "telegram"
        assert out["to"] == "u1"
        assert out["accountId"] == "acc-1"

    def test_merge_conflict_keeps_primary(self) -> None:
        a = {"channel": "telegram", "accountId": "a1", "to": "u1"}
        b = {"channel": "discord", "accountId": "a2", "to": "u2"}
        out = merge_delivery_context(a, b)
        # Channel conflict → keep primary channel, but route fields also stick to primary
        assert out["channel"] == "telegram"
        assert out["accountId"] == "a1"

    def test_from_session(self) -> None:
        out = delivery_context_from_session(
            {
                "lastChannel": "telegram",
                "lastTo": "u1",
                "lastAccountId": "a1",
            }
        )
        assert out is not None
        assert out["channel"] == "telegram"
        assert out["to"] == "u1"

    def test_from_session_none(self) -> None:
        assert delivery_context_from_session(None) is None

    def test_key(self) -> None:
        k = delivery_context_key(
            {"channel": "telegram", "to": "u1", "accountId": "a1"}
        )
        assert k is not None
        assert "telegram" in k
        assert "u1" in k

    def test_key_blank(self) -> None:
        assert delivery_context_key(None) is None


# ============================================================================
# directive_tags
# ============================================================================


class TestDirectiveTags:
    def test_constants(self) -> None:
        assert MAX_REPLY_DIRECTIVE_ID_LENGTH == 256

    def test_sanitize(self) -> None:
        assert sanitize_reply_directive_id("abc") == "abc"
        assert sanitize_reply_directive_id("  abc  ") == "abc"
        assert sanitize_reply_directive_id("") is None
        assert sanitize_reply_directive_id(None) is None

    def test_sanitize_strips_unsafe(self) -> None:
        # Control chars are stripped
        assert sanitize_reply_directive_id("a\x00b") == "ab"
        # Square brackets are stripped
        assert sanitize_reply_directive_id("a[b]c") == "abc"

    def test_sanitize_truncates(self) -> None:
        long = "a" * 500
        out = sanitize_reply_directive_id(long)
        assert out is not None
        assert len(out) == MAX_REPLY_DIRECTIVE_ID_LENGTH

    def test_strip_for_display(self) -> None:
        out = strip_inline_directive_tags_for_display("hello [[audio_as_voice]] world")
        assert "audio_as_voice" not in out["text"]
        assert out["changed"] is True

    def test_strip_for_display_no_tags(self) -> None:
        out = strip_inline_directive_tags_for_display("plain text")
        assert out["text"] == "plain text"
        assert out["changed"] is False

    def test_strip_for_delivery(self) -> None:
        out = strip_inline_directive_tags_for_delivery("hello [[audio_as_voice]] world")
        assert "audio_as_voice" not in out["text"]
        assert out["changed"] is True

    def test_parse_audio_tag(self) -> None:
        out = parse_inline_directives("hello [[audio_as_voice]] world")
        assert out.audio_as_voice is True
        assert out.has_audio_tag is True
        assert "audio_as_voice" not in out.text

    def test_parse_reply_to_current(self) -> None:
        out = parse_inline_directives(
            "hello [[reply_to_current]]",
            {"currentMessageId": "msg-1"},
        )
        assert out.reply_to_current is True
        assert out.reply_to_id == "msg-1"

    def test_parse_reply_to_specific(self) -> None:
        out = parse_inline_directives("hi [[reply_to:msg-42]]")
        assert out.reply_to_explicit_id == "msg-42"
        assert out.reply_to_id == "msg-42"

    def test_parse_empty(self) -> None:
        out = parse_inline_directives("")
        assert out.audio_as_voice is False
        assert out.text == ""

    def test_parse_no_tags(self) -> None:
        out = parse_inline_directives("plain message")
        assert out.audio_as_voice is False
        assert out.text == "plain message"

    def test_strip_from_message(self) -> None:
        msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello [[audio_as_voice]]"},
            ],
        }
        out = strip_inline_directive_tags_from_message_for_display(msg)
        assert "audio_as_voice" not in out["content"][0]["text"]


# ============================================================================
# fetch_timeout
# ============================================================================


class TestFetchTimeout:
    def test_constants(self) -> None:
        assert LOG_URL_MAX_CHARS == 500
        assert DEFAULT_FETCH_TIMEOUT_MS == 30_000

    def test_bind_abort_relay(self) -> None:
        called = {"aborted": False}

        class _C:
            def abort(self) -> None:
                called["aborted"] = True

        relay = bind_abort_relay(_C())
        relay()
        assert called["aborted"] is True

    def test_build_no_timeout_no_parent(self) -> None:
        out = build_timeout_abort_signal({})
        assert out["signal"] is None
        out["cleanup"]()

    def test_build_with_parent(self) -> None:
        parent = type("_S", (), {"aborted": False})()
        out = build_timeout_abort_signal({"signal": parent})
        assert out["signal"] is parent

    def test_build_with_timeout(self) -> None:
        out = build_timeout_abort_signal({"timeoutMs": 5000})
        assert out["signal"] is not None
        out["cleanup"]()

    def test_refresh(self) -> None:
        out = build_timeout_abort_signal({"timeoutMs": 5000})
        # refresh should not throw
        out["refresh"]()
        out["cleanup"]()


# ============================================================================
# message_channel
# ============================================================================


class TestMessageChannel:
    def test_constants(self) -> None:
        assert INTERNAL_MESSAGE_CHANNEL == "webchat"
        assert GATEWAY_CLIENT_MODES["CLI"] == "cli"
        assert GATEWAY_CLIENT_NAMES["CONTROL_UI"] == "control-ui"

    def test_normalize_basic(self) -> None:
        assert normalize_message_channel("telegram") == "telegram"
        assert normalize_message_channel("webchat") == "webchat"
        assert normalize_message_channel(None) is None
        assert normalize_message_channel("") is None

    def test_is_internal(self) -> None:
        assert is_internal_message_channel("webchat") is True
        assert is_internal_message_channel("telegram") is False

    def test_gateway_cli_client(self) -> None:
        assert is_gateway_cli_client({"mode": "cli"}) is True
        assert is_gateway_cli_client({"mode": "tui"}) is False

    def test_ephemeral_client(self) -> None:
        assert is_ephemeral_gateway_client({"mode": "cli"}) is True
        assert is_ephemeral_gateway_client({"mode": "backend"}) is True
        assert is_ephemeral_gateway_client({"mode": "tui"}) is False

    def test_operator_ui_client(self) -> None:
        assert is_operator_ui_client({"id": "tui"}) is True
        assert is_operator_ui_client({"id": "control-ui"}) is True
        assert is_operator_ui_client({"id": "cli"}) is False

    def test_browser_clients(self) -> None:
        assert is_browser_operator_ui_client({"id": "control-ui"}) is True
        assert is_browser_copilot_client({"id": "browser-copilot"}) is True
        assert is_browser_copilot_client({"id": "control-ui"}) is False

    def test_webchat_client(self) -> None:
        assert is_webchat_client({"mode": "webchat"}) is True
        assert is_webchat_client({"id": "webchat-ui"}) is True
        assert is_webchat_client({"mode": "tui"}) is False

    def test_markdown_capable(self) -> None:
        assert is_markdown_capable_message_channel("webchat") is True
        assert is_markdown_capable_message_channel("tui") is True
        assert is_markdown_capable_message_channel("unknown") is False
        assert is_markdown_capable_message_channel(None) is False

    def test_native_approval(self) -> None:
        assert is_native_approval_channel("webchat") is True
        assert is_native_approval_channel(None) is False

    def test_list_deliverable(self) -> None:
        channels = list_deliverable_message_channels()
        assert "telegram" in channels
        assert "discord" in channels

    def test_is_gateway(self) -> None:
        assert is_gateway_message_channel("telegram") is True
        assert is_gateway_message_channel("webchat") is True
        assert is_gateway_message_channel("invalid") is False

    def test_resolve(self) -> None:
        assert resolve_message_channel("telegram") == "telegram"
        assert resolve_message_channel(None, "discord") == "discord"
        assert resolve_message_channel(None, None) is None

    def test_internal_non_delivery(self) -> None:
        assert is_internal_non_delivery_channel("heartbeat") is True
        assert is_internal_non_delivery_channel("cron") is True
        assert is_internal_non_delivery_channel("telegram") is False
        assert "heartbeat" in INTERNAL_NON_DELIVERY_CHANNELS

    def test_internal_session_conversation_id(self) -> None:
        assert internal_session_conversation_id("webchat", "k1") == "k1"
        assert internal_session_conversation_id("telegram", "k1") is None


# ============================================================================
# normalize_secret_input
# ============================================================================


class TestNormalizeSecretInput:
    def test_basic(self) -> None:
        assert normalize_secret_input("abc") == "abc"
        assert normalize_secret_input("  abc  ") == "abc"

    def test_strips_linebreaks(self) -> None:
        assert normalize_secret_input("abc\ndef") == "abcdef"
        assert normalize_secret_input("abc\r\ndef") == "abcdef"

    def test_strips_unicode_whitespace(self) -> None:
        assert normalize_secret_input("abc\u2028def") == "abcdef"
        assert normalize_secret_input("abc\u2029def") == "abcdef"

    def test_strips_control_chars(self) -> None:
        assert normalize_secret_input("a\x00b\x01c") == "abc"

    def test_strips_non_latin1(self) -> None:
        # 高 (U+9AD8) is non-Latin1
        assert normalize_secret_input("high\u9AD8") == "high"

    def test_empty(self) -> None:
        assert normalize_secret_input("") == ""
        assert normalize_secret_input(None) == ""

    def test_optional(self) -> None:
        assert normalize_optional_secret_input("abc") == "abc"
        assert normalize_optional_secret_input("") is None
        assert normalize_optional_secret_input(None) is None


# ============================================================================
# parse_json_compat
# ============================================================================


class TestParseJsonCompat:
    def test_strict_json(self) -> None:
        assert parse_json_with_json5_fallback('{"a": 1}') == {"a": 1}

    def test_with_trailing_comma(self) -> None:
        assert parse_json_with_json5_fallback('{"a": 1,}') == {"a": 1}

    def test_with_comment(self) -> None:
        assert parse_json_with_json5_fallback('{"a": 1, // x\n"b": 2}') == {"a": 1, "b": 2}

    def test_invalid(self) -> None:
        with pytest.raises(Exception):
            parse_json_with_json5_fallback("not json at all {")


# ============================================================================
# provider_utils
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_provider_utils_hooks() -> None:
    set_is_reasoning_tag_provider_hook(None)
    set_resolve_reasoning_output_mode_hook(None)
    yield
    set_is_reasoning_tag_provider_hook(None)
    set_resolve_reasoning_output_mode_hook(None)


class TestProviderUtils:
    def test_native_default(self) -> None:
        assert is_reasoning_tag_provider("openai") is False

    def test_no_provider(self) -> None:
        assert is_reasoning_tag_provider(None) is False

    def test_with_hook(self) -> None:
        set_is_reasoning_tag_provider_hook(lambda _p: True)
        assert is_reasoning_tag_provider("p") is True

    def test_with_mode_hook(self) -> None:
        set_resolve_reasoning_output_mode_hook(lambda _p: "tagged")
        assert is_reasoning_tag_provider("p") is True


# ============================================================================
# queue_helpers
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_queue_helpers_hooks() -> None:
    for fn in (
        set_drain_queue_items_hook,
        set_summarize_dropped_queue_items_hook,
        set_build_queue_summary_prompt_hook,
        set_resolve_debounce_ms_hook,
        set_merge_queue_summary_hook,
        set_drain_queue_collection_hook,
        set_preview_queue_summary_prompt_hook,
        set_apply_queue_runtime_settings_hook,
        set_should_skip_queue_item_hook,
        set_count_pending_queue_items_hook,
    ):
        fn(None)
    yield
    for fn in (
        set_drain_queue_items_hook,
        set_summarize_dropped_queue_items_hook,
        set_build_queue_summary_prompt_hook,
        set_resolve_debounce_ms_hook,
        set_merge_queue_summary_hook,
        set_drain_queue_collection_hook,
        set_preview_queue_summary_prompt_hook,
        set_apply_queue_runtime_settings_hook,
        set_should_skip_queue_item_hook,
        set_count_pending_queue_items_hook,
    ):
        fn(None)


class TestQueueHelpers:
    def test_resolve_debounce(self) -> None:
        assert resolve_debounce_ms(100) == 100
        assert resolve_debounce_ms(0) == 0
        assert resolve_debounce_ms(-1) == 0
        assert resolve_debounce_ms(None) == 0
        assert resolve_debounce_ms(None, default_ms=200) == 200

    def test_should_skip_no_dedupe(self) -> None:
        assert should_skip_queue_item({"item": "a", "items": []}) is False

    def test_should_skip_with_dedupe(self) -> None:
        assert (
            should_skip_queue_item(
                {"item": "a", "items": ["a", "b"], "dedupe": lambda i, items: i in items}
            )
            is True
        )
        assert (
            should_skip_queue_item(
                {"item": "c", "items": ["a", "b"], "dedupe": lambda i, items: i in items}
            )
            is False
        )

    def test_count_pending(self) -> None:
        assert count_pending_queue_items([]) == 0
        assert count_pending_queue_items([1, 2, 3]) == 3
        assert count_pending_queue_items([1, 2, 3], {2}) == 2

    def test_summarize(self) -> None:
        out = summarize_dropped_queue_items(
            [{"text": "first"}, {"text": "second"}], limit=2
        )
        assert len(out) == 2
        assert "first" in out[0]

    def test_merge_summary(self) -> None:
        state = {"droppedCount": 1, "summaryLines": ["old"]}
        out = merge_queue_summary(state, [{"text": "new"}], limit=3)
        assert out["droppedCount"] == 2
        assert "new" in out["summaryLines"]

    def test_apply_runtime(self) -> None:
        target = {"mode": "old", "debounceMs": 0, "cap": 10, "dropPolicy": "old"}
        apply_queue_runtime_settings(
            {
                "target": target,
                "settings": {"mode": "new", "debounceMs": 500, "cap": 5, "dropPolicy": "new"},
            }
        )
        assert target["mode"] == "new"
        assert target["debounceMs"] == 500
        assert target["cap"] == 5
        assert target["dropPolicy"] == "new"

    def test_apply_runtime_preserves(self) -> None:
        target = {"mode": "old", "debounceMs": 0, "cap": 10, "dropPolicy": "old"}
        apply_queue_runtime_settings({"target": target, "settings": {"mode": "new"}})
        assert target["mode"] == "new"
        assert target["debounceMs"] == 0  # preserved
        assert target["cap"] == 10  # preserved

    def test_build_summary_prompt(self) -> None:
        out = build_queue_summary_prompt(
            {
                "state": {"droppedCount": 2, "summaryLines": ["item1", "item2"]},
                "noun": "message",
            }
        )
        assert out is not None
        assert "message" in out.lower() or "Earlier" in out

    def test_build_summary_no_drops(self) -> None:
        out = build_queue_summary_prompt(
            {"state": {"droppedCount": 0, "summaryLines": []}, "noun": "msg"}
        )
        assert out is None

    def test_drain_basic(self) -> None:
        delivered = []
        result = drain_queue_items([1, 2, 3], delivered.append)
        assert result["delivered"] == [1, 2, 3]
        assert delivered == [1, 2, 3]

    def test_drain_with_cap(self) -> None:
        delivered = []
        result = drain_queue_items(
            [1, 2, 3, 4, 5], delivered.append, cap=2, drop_policy="summarize"
        )
        assert len(result["delivered"]) == 2
        assert result["summary"]["droppedCount"] == 3

    def test_drain_with_cap_new(self) -> None:
        delivered = []
        result = drain_queue_items(
            [1, 2, 3, 4, 5], delivered.append, cap=2, drop_policy="new"
        )
        assert len(result["delivered"]) == 2
        assert result["summary"]["droppedCount"] == 3

    def test_drain_collection(self) -> None:
        captured: List[tuple] = []
        result = drain_queue_collection(
            {"a": [1, 2], "b": [3]},
            lambda src, item: captured.append((src, item)),
        )
        assert result["a"]["delivered"] == [1, 2]
        assert result["b"]["delivered"] == [3]
        assert ("a", 1) in captured


# ============================================================================
# reaction_level
# ============================================================================


class TestReactionLevel:
    def test_off(self) -> None:
        out = resolve_reaction_level(
            {"value": "off", "defaultLevel": "ack", "invalidFallback": "ack"}
        )
        assert out.level == "off"
        assert out.ack_enabled is False
        assert out.agent_reactions_enabled is False

    def test_ack(self) -> None:
        out = resolve_reaction_level(
            {"value": "ack", "defaultLevel": "off", "invalidFallback": "minimal"}
        )
        assert out.level == "ack"
        assert out.ack_enabled is True

    def test_minimal(self) -> None:
        out = resolve_reaction_level(
            {"value": "minimal", "defaultLevel": "off", "invalidFallback": "ack"}
        )
        assert out.level == "minimal"
        assert out.agent_reactions_enabled is True
        assert out.agent_reaction_guidance == "minimal"

    def test_extensive(self) -> None:
        out = resolve_reaction_level(
            {"value": "extensive", "defaultLevel": "off", "invalidFallback": "ack"}
        )
        assert out.level == "extensive"
        assert out.agent_reaction_guidance == "extensive"

    def test_missing_uses_default(self) -> None:
        out = resolve_reaction_level(
            {"value": None, "defaultLevel": "ack", "invalidFallback": "minimal"}
        )
        assert out.level == "ack"

    def test_invalid_uses_fallback(self) -> None:
        out = resolve_reaction_level(
            {"value": "garbage", "defaultLevel": "ack", "invalidFallback": "minimal"}
        )
        assert out.level == "minimal"


# ============================================================================
# run_with_concurrency
# ============================================================================


class TestRunWithConcurrency:
    def test_empty(self) -> None:
        out = asyncio.run(
            run_tasks_with_concurrency({"tasks": [], "limit": 5})
        )
        assert out["results"] == []
        assert out["hasError"] is False

    def test_basic(self) -> None:
        async def make(x):
            return x * 2
        out = asyncio.run(
            run_tasks_with_concurrency(
                {
                    "tasks": [lambda: make(1), lambda: make(2), lambda: make(3)],
                    "limit": 2,
                }
            )
        )
        assert out["results"] == [2, 4, 6]
        assert out["hasError"] is False

    def test_with_error(self) -> None:
        async def ok():
            return 1
        async def bad():
            raise ValueError("nope")
        out = asyncio.run(
            run_tasks_with_concurrency(
                {
                    "tasks": [ok, bad, ok],
                    "limit": 2,
                    "onTaskError": lambda e, i: None,
                }
            )
        )
        assert out["hasError"] is True
        assert out["firstError"] is not None

    def test_limit_clamped(self) -> None:
        async def make(x):
            return x
        out = asyncio.run(
            run_tasks_with_concurrency(
                {"tasks": [lambda: make(1)], "limit": 100}
            )
        )
        assert out["results"] == [1]

    def test_error_mode_stop(self) -> None:
        # When error_mode=stop, in-flight tasks still complete but no new ones start
        async def slow():
            await asyncio.sleep(0.05)
            return "slow"
        async def fast_bad():
            raise ValueError("fast")
        async def never_runs():
            return "never"
        out = asyncio.run(
            run_tasks_with_concurrency(
                {
                    "tasks": [slow, fast_bad, never_runs],
                    "limit": 3,
                    "errorMode": "stop",
                }
            )
        )
        # The first error marks hasError=True but the slow task may still complete
        assert out["hasError"] is True


# ============================================================================
# safe_json
# ============================================================================


class TestSafeJson:
    def test_basic(self) -> None:
        assert safe_json_stringify({"a": 1}) is not None
        assert "a" in safe_json_stringify({"a": 1})

    def test_handles_functions(self) -> None:
        out = safe_json_stringify({"fn": lambda: None})
        assert out is not None
        assert "[Function]" in out

    def test_handles_bytes(self) -> None:
        out = safe_json_stringify({"data": b"hello"})
        assert out is not None
        assert "bytes" in out


# ============================================================================
# sleep
# ============================================================================


class TestSleep:
    def test_sleep_basic(self) -> None:
        async def _test():
            await sleep(10)
        # Just check it doesn't throw
        asyncio.run(_test())

    def test_sleep_zero(self) -> None:
        async def _test():
            await sleep(0)
        asyncio.run(_test())

    def test_sleep_negative(self) -> None:
        async def _test():
            await sleep(-100)
        asyncio.run(_test())


# ============================================================================
# string_readers
# ============================================================================


class TestStringReaders:
    def test_is_string_option(self) -> None:
        assert is_string_option("a", ["a", "b"]) is True
        assert is_string_option("c", ["a", "b"]) is False
        assert is_string_option(123, ["a"]) is False
        assert is_string_option("a", frozenset(["a", "b"])) is True

    def test_read_string_value(self) -> None:
        assert read_string_value("hello") == "hello"
        assert read_string_value("") is None
        assert read_string_value(None) is None
        assert read_string_value(123) is None

    def test_read_string_alias(self) -> None:
        assert read_string_alias({"a": "x"}, ["a"]) == "x"
        assert read_string_alias({"a": "", "b": "y"}, ["a", "b"]) == "y"
        assert read_string_alias({}, ["a"]) is None
        assert read_string_alias(None, ["a"]) is None

    def test_read_trimmed_string_alias(self) -> None:
        assert read_trimmed_string_alias({"a": "  x  "}, ["a"]) == "x"
        assert read_trimmed_string_alias({"a": "   "}, ["a"]) is None

    def test_strip_channel_prefix(self) -> None:
        assert strip_channel_prefix("channel:telegram:user1", "telegram") == "telegram:user1"
        assert strip_channel_prefix("chat:user1", "telegram") == "user1"
        assert strip_channel_prefix("user:u1", "telegram") == "u1"
        assert strip_channel_prefix("telegram:u1", "telegram") == "u1"
        assert strip_channel_prefix("plain", "telegram") == "plain"
        assert strip_channel_prefix(None, "telegram") is None


# ============================================================================
# timer_delay
# ============================================================================


class TestTimerDelay:
    def test_constant(self) -> None:
        assert MAX_SAFE_TIMEOUT_DELAY_MS == 60 * 60 * 1000

    def test_resolve_basic(self) -> None:
        assert resolve_safe_timeout_delay_ms(1000) == 1000
        assert resolve_safe_timeout_delay_ms(0) == 0

    def test_resolve_negative(self) -> None:
        assert resolve_safe_timeout_delay_ms(-1) == 0

    def test_resolve_too_big(self) -> None:
        assert resolve_safe_timeout_delay_ms(MAX_SAFE_TIMEOUT_DELAY_MS + 1) == MAX_SAFE_TIMEOUT_DELAY_MS

    def test_resolve_nan(self) -> None:
        assert resolve_safe_timeout_delay_ms(float("nan")) == 0

    def test_resolve_invalid(self) -> None:
        assert resolve_safe_timeout_delay_ms(None) == 0
        assert resolve_safe_timeout_delay_ms("abc") == 0

    def test_add_grace(self) -> None:
        assert add_safe_timeout_delay_grace_ms(1000, 100) == 1100
        assert add_safe_timeout_delay_grace_ms(1000, 0) == 1000
        assert add_safe_timeout_delay_grace_ms(0, 100) == 100


# ============================================================================
# token_format
# ============================================================================


class TestTokenFormat:
    def test_zero(self) -> None:
        assert format_token_count(0) == "0"
        assert format_token_count(None) == "0"

    def test_small(self) -> None:
        assert format_token_count(500) == "500"
        assert format_token_count(999) == "999"

    def test_thousands(self) -> None:
        assert format_token_count(1500) == "1.5k"
        assert format_token_count(50_000) == "50k"

    def test_millions(self) -> None:
        assert format_token_count(2_500_000) == "2.5m"
        assert format_token_count(1_500_000) == "1.5m"


# ============================================================================
# transcript_tools
# ============================================================================


class TestTranscriptTools:
    def test_extract_names_empty(self) -> None:
        assert extract_tool_call_names({}) == []

    def test_extract_names_from_field(self) -> None:
        out = extract_tool_call_names({"toolName": "read"})
        assert out == ["read"]

    def test_extract_names_from_snake(self) -> None:
        out = extract_tool_call_names({"tool_name": "write"})
        assert out == ["write"]

    def test_extract_names_from_content(self) -> None:
        msg = {
            "content": [
                {"type": "tool_use", "name": "exec"},
                {"type": "text", "text": "hi"},
                {"type": "toolcall", "name": "read"},
            ]
        }
        out = extract_tool_call_names(msg)
        assert "exec" in out
        assert "read" in out
        assert "text" not in out

    def test_extract_names_dedup(self) -> None:
        msg = {
            "toolName": "read",
            "content": [
                {"type": "tool_use", "name": "read"},
                {"type": "tool_use", "name": "write"},
            ],
        }
        out = extract_tool_call_names(msg)
        assert out.count("read") == 1
        assert "write" in out

    def test_has_tool_call(self) -> None:
        assert has_tool_call({"toolName": "x"}) is True
        assert has_tool_call({"content": [{"type": "text", "text": "hi"}]}) is False

    def test_count_tool_results(self) -> None:
        out = count_tool_results(
            {
                "content": [
                    {"type": "tool_result", "is_error": False},
                    {"type": "tool_result", "is_error": True},
                    {"type": "text", "text": "x"},
                ]
            }
        )
        assert out["total"] == 2
        assert out["errors"] == 1

    def test_count_tool_results_empty(self) -> None:
        assert count_tool_results({}) == {"total": 0, "errors": 0}


# ============================================================================
# usage_format
# ============================================================================


class TestUsageFormat:
    def test_zero(self) -> None:
        assert format_usage_cost_usd(0) == "$0.00"
        assert format_usage_tokens(0) == "0"

    def test_none(self) -> None:
        assert format_usage_cost_usd(None) == ""
        assert format_usage_tokens(None) == ""

    def test_small_cost(self) -> None:
        assert format_usage_cost_usd(0.005) == "$0.0050"
        assert format_usage_cost_usd(0.5) == "$0.50"

    def test_medium_cost(self) -> None:
        assert format_usage_cost_usd(50) == "$50.00"

    def test_tokens_small(self) -> None:
        assert format_usage_tokens(500) == "500"

    def test_tokens_thousands(self) -> None:
        assert format_usage_tokens(5000) == "5.0K"
        assert format_usage_tokens(50_000) == "50K"

    def test_tokens_millions(self) -> None:
        assert format_usage_tokens(5_000_000) == "5.0M"
        assert format_usage_tokens(50_000_000) == "50M"

    def test_tokens_billions(self) -> None:
        assert format_usage_tokens(5_000_000_000) == "5.0B"

    def test_with_hook(self) -> None:
        set_format_usage_cost_usd_hook(lambda _v: "HOOKED")
        assert format_usage_cost_usd(100) == "HOOKED"
        set_format_usage_tokens_hook(lambda _v: "HOOKED_T")
        assert format_usage_tokens(100) == "HOOKED_T"


# ============================================================================
# utf8_truncate
# ============================================================================


class TestUtf8Truncate:
    def test_prefix_basic(self) -> None:
        assert truncate_utf8_prefix("hello", 3) == "hel"

    def test_prefix_zero(self) -> None:
        assert truncate_utf8_prefix("hello", 0) == ""

    def test_prefix_no_truncation_needed(self) -> None:
        assert truncate_utf8_prefix("hi", 10) == "hi"

    def test_prefix_continuation_byte(self) -> None:
        # '你' is 3 bytes in UTF-8 (E4 BD A0); truncating to 1 byte should drop the whole char
        out = truncate_utf8_prefix("你", 1)
        assert out == ""

    def test_suffix_basic(self) -> None:
        assert truncate_utf8_suffix("hello", 3) == "llo"

    def test_suffix_zero(self) -> None:
        assert truncate_utf8_suffix("hello", 0) == ""

    def test_suffix_continuation_byte(self) -> None:
        out = truncate_utf8_suffix("你", 1)
        assert out == ""


# ============================================================================
# with_timeout
# ============================================================================


class TestWithTimeout:
    def test_basic(self) -> None:
        async def _ok():
            return "done"
        out = asyncio.run(with_timeout(_ok(), 1000))
        assert out == "done"

    def test_timeout_zero(self) -> None:
        async def _ok():
            return "x"
        out = asyncio.run(with_timeout(_ok(), 0))
        assert out == "x"

    def test_timeout_negative(self) -> None:
        async def _ok():
            return "x"
        out = asyncio.run(with_timeout(_ok(), -100))
        assert out == "x"

    def test_timeout_raises(self) -> None:
        async def _slow():
            await asyncio.sleep(0.2)
            return "x"
        with pytest.raises(Exception):
            asyncio.run(with_timeout(_slow(), 50))


# ============================================================================
# zod_parse
# ============================================================================


class _FakeZodSchema:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    def safe_parse(self, value: Any) -> Any:
        if self.ok:
            return _FakeParseResult(True, value)
        return _FakeParseResult(False, None)


class _FakeParseResult:
    def __init__(self, success: bool, data: Any) -> None:
        self.success = success
        self.data = data


class TestZodParse:
    def test_safe_parse_ok(self) -> None:
        out = safe_parse_with_schema(_FakeZodSchema(ok=True), "x")
        assert out == "x"

    def test_safe_parse_fail(self) -> None:
        out = safe_parse_with_schema(_FakeZodSchema(ok=False), "x")
        assert out is None

    def test_safe_parse_no_schema(self) -> None:
        assert safe_parse_with_schema(None, "x") is None

    def test_safe_parse_dict_result(self) -> None:
        # Dict-style result
        class _DictSchema:
            def safe_parse(self, _v):
                return {"success": True, "data": "y"}

        assert safe_parse_with_schema(_DictSchema(), "x") == "y"

    def test_safe_parse_json(self) -> None:
        out = safe_parse_json_with_schema(_FakeZodSchema(ok=True), '"hello"')
        assert out == "hello"

    def test_safe_parse_json_invalid(self) -> None:
        out = safe_parse_json_with_schema(_FakeZodSchema(ok=True), "not json")
        assert out is None
