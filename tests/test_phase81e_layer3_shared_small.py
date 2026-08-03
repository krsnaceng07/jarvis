"""Tests for Phase 8.1e — src/shared/ small file batch (30 files).

Mirrors the public surface of each OpenClaw ``src/shared/`` file in this batch.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime, timezone

import pytest

from src.shared.account_enabled import is_account_enabled
from src.shared.agent_liveness import (
    format_abandoned_liveness_error,
    format_blocked_liveness_error,
    is_abandoned_liveness_state,
    is_blocked_liveness_state,
    normalize_blocked_liveness_wait_status,
)
from src.shared.agent_run_status import is_non_terminal_agent_run_status
from src.shared.avatar_limits import (
    AVATAR_MAX_BYTES,
    AVATAR_MAX_DATA_URL_CHARS,
    is_renderable_avatar_image_data_url,
)
from src.shared.bounded_buffer import (
    BoundedBuffer,
    BoundedBufferDropOldest,
    BoundedBufferFailClosed,
    BoundedBufferLatch,
)
from src.shared.chat_content import (
    coerce_chat_content_text,
    extract_text_from_chat_content,
)
from src.shared.chat_envelope import strip_envelope, strip_message_id_hints
from src.shared.config_ui_hints_types import ConfigUiHint, ConfigUiHints
from src.shared.custom_command_config import (
    normalize_command_description,
    normalize_slash_command_name,
    resolve_custom_commands,
)
from src.shared.deferred import Deferred, create_deferred
from src.shared.device_auth import (
    DeviceAuthEntry,
    DeviceAuthStore,
    normalize_device_auth_role,
    normalize_device_auth_scopes,
)
from src.shared.env_var_candidates import append_unique_env_var_candidates
from src.shared.gateway_bind_url import resolve_gateway_bind_url
from src.shared.gateway_method_policy import (
    RESERVED_ADMIN_GATEWAY_METHOD_SCOPE,
    normalize_plugin_gateway_method_scope,
    resolve_reserved_gateway_method_scope,
)
from src.shared.gateway_tailscale_auth_policy import (
    format_unsafe_gateway_tailscale_no_auth_message,
    is_unsafe_gateway_tailscale_no_auth,
)
from src.shared.global_singleton import resolve_global_map, resolve_global_singleton
from src.shared.google_turn_ordering import sanitize_google_assistant_first_ordering
from src.shared.html_entities import decode_html_entities
from src.shared.human_list import format_human_list
from src.shared.import_specifier import to_safe_import_path
from src.shared.iso_time import has_valid_iso_calendar_components
from src.shared.lazy_runtime import (
    create_lazy_runtime_method,
    create_lazy_runtime_method_binder,
    create_lazy_runtime_module,
    create_lazy_runtime_named_export,
    create_lazy_runtime_surface,
)
from src.shared.listeners import notify_listeners, register_listener
from src.shared.lobster_day import is_lobster_day, lobster_day_hash
from src.shared.markdown_code import format_fenced_code_block, format_inline_code_span
from src.shared.message_content_blocks import visit_object_content_blocks
from src.shared.model_key import model_key
from src.shared.model_param_b import infer_param_b_from_id_or_name
from src.shared.node_list_types import NodeListNode, PairingList, PairedNode, PendingRequest
from src.shared.node_skill_constraints import (
    NODE_SKILL_MAX_CONTENT_BYTES,
    NODE_SKILL_MAX_COUNT,
    NODE_SKILL_MAX_DESCRIPTION_LENGTH,
    NODE_SKILL_MAX_TOTAL_BYTES,
    NODE_SKILL_NAME_RE,
)
from src.shared.number_coercion import resolve_non_negative_number
from src.shared.path_array_index import (
    MAX_CONFIG_PATH_ARRAY_INDEX,
    parse_config_path_array_index,
)
from src.shared.progress_labels import (
    DEFAULT_PROGRESS_DRAFT_LABELS,
    select_progress_label,
)
from src.shared.regexp import escape_reg_exp
from src.shared.tilde_path import expand_tilde_path
from src.shared.tool_activity_heartbeat import (
    clear_tool_activity_run,
    get_last_tool_activity_ms,
    notify_tool_activity,
    on_tool_activity,
)


# ============================================================================
# account-enabled
# ============================================================================


class TestAccountEnabled:
    def test_none(self) -> None:
        assert is_account_enabled(None) is True

    def test_no_enabled_field(self) -> None:
        assert is_account_enabled({"id": "x"}) is True

    def test_enabled_true(self) -> None:
        assert is_account_enabled({"enabled": True}) is True

    def test_enabled_false(self) -> None:
        assert is_account_enabled({"enabled": False}) is False

    def test_non_object(self) -> None:
        assert is_account_enabled("not a dict") is True
        assert is_account_enabled(42) is True


# ============================================================================
# agent-liveness
# ============================================================================


class TestAgentLiveness:
    def test_blocked(self) -> None:
        assert is_blocked_liveness_state("blocked") is True
        assert is_blocked_liveness_state(" BLOCKED ") is True
        assert is_blocked_liveness_state("active") is False
        assert is_blocked_liveness_state(None) is False

    def test_abandoned(self) -> None:
        assert is_abandoned_liveness_state("abandoned") is True
        assert is_abandoned_liveness_state(" ABANDONED ") is True
        assert is_abandoned_liveness_state("blocked") is False
        assert is_abandoned_liveness_state(None) is False

    def test_format_blocked(self) -> None:
        assert format_blocked_liveness_error("bad") == "bad"
        assert format_blocked_liveness_error("") == "Agent run blocked before producing a usable result."
        assert format_blocked_liveness_error(None) == "Agent run blocked before producing a usable result."

    def test_format_abandoned(self) -> None:
        assert format_abandoned_liveness_error("err") == "err"
        assert format_abandoned_liveness_error("") == "Agent run ended before producing a complete result."
        assert format_abandoned_liveness_error(None) == "Agent run ended before producing a complete result."

    def test_normalize_passthrough(self) -> None:
        out = normalize_blocked_liveness_wait_status({
            "status": "ok",
            "livenessState": "active",
            "error": "x",
        })
        assert out == {"status": "ok", "error": "x"}

    def test_normalize_blocked(self) -> None:
        out = normalize_blocked_liveness_wait_status({
            "status": "ok",
            "livenessState": "blocked",
            "error": "reason",
        })
        assert out == {"status": "error", "error": "reason"}


# ============================================================================
# agent-run-status
# ============================================================================


class TestAgentRunStatus:
    def test_non_terminal(self) -> None:
        assert is_non_terminal_agent_run_status("accepted") is True
        assert is_non_terminal_agent_run_status("started") is True
        assert is_non_terminal_agent_run_status("in_flight") is True
        assert is_non_terminal_agent_run_status("ok") is False
        assert is_non_terminal_agent_run_status("error") is False
        assert is_non_terminal_agent_run_status(None) is False


# ============================================================================
# avatar-limits
# ============================================================================


class TestAvatarLimits:
    def test_constants(self) -> None:
        assert AVATAR_MAX_BYTES == 2 * 1024 * 1024
        assert AVATAR_MAX_DATA_URL_CHARS > AVATAR_MAX_BYTES

    def test_image_data_url_ok(self) -> None:
        short = "data:image/png;base64,abc"
        assert is_renderable_avatar_image_data_url(short) is True

    def test_image_data_url_too_long(self) -> None:
        too_long = "data:image/png;base64," + "a" * (AVATAR_MAX_DATA_URL_CHARS + 1)
        assert is_renderable_avatar_image_data_url(too_long) is False

    def test_non_image_data_url(self) -> None:
        assert is_renderable_avatar_image_data_url("data:text/plain,hello") is False

    def test_non_data_url(self) -> None:
        assert is_renderable_avatar_image_data_url("https://example.com") is False


# ============================================================================
# bounded-buffer
# ============================================================================


class TestBoundedBuffer:
    def test_latch_overflow(self) -> None:
        b = BoundedBuffer[int](3, BoundedBufferLatch())
        assert b.push(1) is True
        assert b.push(2) is True
        assert b.push(3) is True
        # At capacity, next push should latch the buffer.
        assert b.push(4) is False
        assert b.closed is True
        # Further pushes are rejected.
        assert b.push(5) is False

    def test_drain(self) -> None:
        b = BoundedBuffer[str](10, BoundedBufferLatch())
        b.push("a")
        b.push("b")
        out = b.drain()
        assert out == ["a", "b"]
        assert b.size == 0

    def test_drop_oldest(self) -> None:
        b = BoundedBuffer[int](3, BoundedBufferDropOldest())
        b.push(1)
        b.push(2)
        b.push(3)
        b.push(4)  # drops 1
        assert b.drain() == [2, 3, 4]

    def test_drop_oldest_fit(self) -> None:
        # Single oversized value: try to fit via custom fit() callback.
        b = BoundedBuffer[int](3, BoundedBufferDropOldest(fit=lambda v, c: 9), measure=lambda v: v)
        b.push(1)
        b.push(2)
        b.push(3)
        b.push(100)  # 1+2+3+100=106 > 3, drop all, then fit → 9
        assert b.drain() == [9]

    def test_fail_closed(self) -> None:
        triggered = []
        b = BoundedBuffer[int](3, BoundedBufferFailClosed(on_overflow=lambda: triggered.append(1)))
        b.push(1)
        b.push(2)
        b.push(3)
        assert b.push(4) is False
        assert triggered == [1]
        assert b.closed is True
        assert b.drain() == []

    def test_measure(self) -> None:
        b = BoundedBuffer[str](6, BoundedBufferLatch(), measure=len)
        assert b.push("abc") is True
        assert b.push("def") is True
        assert b.push("g") is False  # 3+3+1=7 > 6


# ============================================================================
# chat-content
# ============================================================================


class TestChatContent:
    def test_coerce_string(self) -> None:
        assert coerce_chat_content_text("hello") == "hello"

    def test_coerce_none(self) -> None:
        assert coerce_chat_content_text(None) == ""

    def test_coerce_numbers(self) -> None:
        assert coerce_chat_content_text(42) == "42"
        assert coerce_chat_content_text(3.14) == "3.14"
        assert coerce_chat_content_text(True) == "True"

    def test_coerce_object(self) -> None:
        out = coerce_chat_content_text({"a": 1})
        assert "a" in out and "1" in out

    def test_extract_string(self) -> None:
        assert extract_text_from_chat_content("  hello   world  ") == "hello world"

    def test_extract_blocks(self) -> None:
        out = extract_text_from_chat_content([
            {"type": "text", "text": "alpha"},
            {"type": "image", "url": "x"},
            {"type": "text", "text": "beta"},
        ])
        assert out == "alpha beta"

    def test_extract_empty(self) -> None:
        assert extract_text_from_chat_content("") is None
        assert extract_text_from_chat_content([{"type": "image"}]) is None

    def test_extract_sanitize(self) -> None:
        out = extract_text_from_chat_content(
            "hello",
            sanitize_text=lambda s: s.replace("l", "1"),
        )
        assert out == "he11o"


# ============================================================================
# chat-envelope
# ============================================================================


class TestChatEnvelope:
    def test_strip_envelope_telegram(self) -> None:
        out = strip_envelope("[Telegram alice 2026-08-01T12:00Z] hi")
        assert out == "hi"

    def test_strip_envelope_iso(self) -> None:
        out = strip_envelope("[Telegram 2026-08-01T12:00Z] hi")
        assert out == "hi"

    def test_strip_envelope_keeps_user_bracket(self) -> None:
        # [hello] is not a known envelope header — keep as-is.
        assert strip_envelope("[hello] world") == "[hello] world"

    def test_strip_envelope_no_bracket(self) -> None:
        assert strip_envelope("hello world") == "hello world"

    def test_strip_message_id_hints(self) -> None:
        text = "alpha\n[message_id: 123]\nbeta"
        out = strip_message_id_hints(text)
        assert "[message_id" not in out
        assert "alpha" in out and "beta" in out

    def test_strip_message_id_no_hints(self) -> None:
        text = "plain text"
        assert strip_message_id_hints(text) == "plain text"


# ============================================================================
# config-ui-hints-types
# ============================================================================


class TestConfigUiHintsTypes:
    def test_hint(self) -> None:
        hint: ConfigUiHint = {"label": "URL", "sensitive": True}
        assert hint["label"] == "URL"

    def test_hints_map(self) -> None:
        hints: ConfigUiHints = {"foo.bar": {"label": "Foo"}}
        assert hints["foo.bar"]["label"] == "Foo"


# ============================================================================
# custom-command-config
# ============================================================================


class TestCustomCommandConfig:
    def test_normalize_name(self) -> None:
        assert normalize_slash_command_name("/Hello-World") == "hello_world"
        assert normalize_slash_command_name("plain") == "plain"
        assert normalize_slash_command_name("") == ""
        assert normalize_slash_command_name("  /  ") == ""

    def test_normalize_description(self) -> None:
        assert normalize_command_description("  hello  ") == "hello"

    def test_resolve_valid(self) -> None:
        result = resolve_custom_commands({
            "commands": [
                {"command": "/foo", "description": "Foo command"},
                {"command": "bar", "description": "Bar command"},
            ],
            "config": {"label": "Test", "pattern": r"^[a-z][a-z0-9_]*$"},
        })
        assert [c["command"] for c in result["commands"]] == ["foo", "bar"]
        assert result["issues"] == []

    def test_resolve_missing_command(self) -> None:
        result = resolve_custom_commands({
            "commands": [{"description": "missing command"}],
            "config": {"label": "Test", "pattern": r"^[a-z]+$"},
        })
        assert result["commands"] == []
        assert any(i["field"] == "command" for i in result["issues"])

    def test_resolve_invalid_pattern(self) -> None:
        result = resolve_custom_commands({
            "commands": [{"command": "/BAD!", "description": "x"}],
            "config": {"label": "Test", "pattern": r"^[a-z]+$"},
        })
        assert result["commands"] == []
        assert any("invalid" in i["message"] for i in result["issues"])

    def test_resolve_duplicate(self) -> None:
        result = resolve_custom_commands({
            "commands": [
                {"command": "/foo", "description": "a"},
                {"command": "/foo", "description": "b"},
            ],
            "config": {"label": "Test", "pattern": r"^[a-z]+$"},
        })
        assert len(result["commands"]) == 1
        assert any("duplicated" in i["message"] for i in result["issues"])

    def test_resolve_reserved(self) -> None:
        result = resolve_custom_commands({
            "commands": [{"command": "/foo", "description": "x"}],
            "reservedCommands": {"foo"},
            "config": {"label": "Test", "pattern": r"^[a-z]+$"},
        })
        assert result["commands"] == []
        assert any("conflicts" in i["message"] for i in result["issues"])

    def test_resolve_missing_description(self) -> None:
        result = resolve_custom_commands({
            "commands": [{"command": "/foo", "description": ""}],
            "config": {"label": "Test", "pattern": r"^[a-z]+$"},
        })
        assert result["commands"] == []
        assert any(i["field"] == "description" for i in result["issues"])


# ============================================================================
# deferred
# ============================================================================


class TestDeferred:
    def test_create_returns_deferred(self) -> None:
        d = create_deferred()
        assert isinstance(d, Deferred)
        assert d.promise is not None

    def test_resolve_via_async(self) -> None:
        async def _run() -> str:
            d = create_deferred()
            d.resolve("done")
            return await d.promise

        result = asyncio.run(_run())
        assert result == "done"


# ============================================================================
# device-auth
# ============================================================================


class TestDeviceAuth:
    def test_normalize_role(self) -> None:
        assert normalize_device_auth_role("  operator  ") == "operator"

    def test_normalize_scopes_basic(self) -> None:
        out = normalize_device_auth_scopes(["a", "b", "  ", "a"])
        assert out == ["a", "b"]

    def test_normalize_scopes_non_string(self) -> None:
        out = normalize_device_auth_scopes(["a", 1, None, "b"])
        assert out == ["a", "b"]

    def test_admin_implies_read_write(self) -> None:
        out = normalize_device_auth_scopes(["operator.admin"])
        assert "operator.read" in out
        assert "operator.write" in out

    def test_write_implies_read(self) -> None:
        out = normalize_device_auth_scopes(["operator.write"])
        assert "operator.read" in out
        assert "operator.write" in out

    def test_none_input(self) -> None:
        assert normalize_device_auth_scopes(None) == []

    def test_types(self) -> None:
        e: DeviceAuthEntry = {"token": "t", "role": "r", "scopes": ["a"], "updatedAtMs": 1}
        s: DeviceAuthStore = {"version": 1, "deviceId": "d", "tokens": {"k": e}}
        assert s["version"] == 1


# ============================================================================
# env-var-candidates
# ============================================================================


class TestEnvVarCandidates:
    def test_basic(self) -> None:
        target: dict = {}
        append_unique_env_var_candidates(target, "owner1", ["FOO", "BAR"])
        assert target == {"owner1": ["FOO", "BAR"]}

    def test_dedup(self) -> None:
        target: dict = {"owner1": ["FOO"]}
        append_unique_env_var_candidates(target, "owner1", ["FOO", "BAR"])
        assert target == {"owner1": ["FOO", "BAR"]}

    def test_empty_keys(self) -> None:
        target: dict = {}
        append_unique_env_var_candidates(target, "owner1", [])
        assert target == {}

    def test_empty_owner(self) -> None:
        target: dict = {}
        append_unique_env_var_candidates(target, "", ["FOO"])
        assert target == {}

    def test_normalizes_whitespace(self) -> None:
        target: dict = {}
        append_unique_env_var_candidates(target, " owner1 ", [" FOO "])
        assert target == {"owner1": ["FOO"]}

    def test_creates_bucket(self) -> None:
        target: dict = {"other": ["X"]}
        append_unique_env_var_candidates(target, "owner1", ["FOO"])
        assert target == {"other": ["X"], "owner1": ["FOO"]}


# ============================================================================
# gateway-bind-url
# ============================================================================


class TestGatewayBindUrl:
    def test_custom_with_host(self) -> None:
        out = resolve_gateway_bind_url({
            "bind": "custom",
            "customBindHost": "example.com",
            "scheme": "wss",
            "port": 443,
        })
        assert out == {"url": "wss://example.com:443", "source": "gateway.bind=custom"}

    def test_custom_without_host(self) -> None:
        out = resolve_gateway_bind_url({
            "bind": "custom",
            "scheme": "wss",
            "port": 443,
        })
        assert "error" in out

    def test_tailnet_with_host(self) -> None:
        out = resolve_gateway_bind_url({
            "bind": "tailnet",
            "scheme": "ws",
            "port": 7433,
            "pickTailnetHost": lambda: "100.64.0.1",
        })
        assert out == {"url": "ws://100.64.0.1:7433", "source": "gateway.bind=tailnet"}

    def test_tailnet_no_host(self) -> None:
        out = resolve_gateway_bind_url({
            "bind": "tailnet",
            "scheme": "ws",
            "port": 7433,
            "pickTailnetHost": lambda: None,
        })
        assert "error" in out

    def test_lan(self) -> None:
        out = resolve_gateway_bind_url({
            "bind": "lan",
            "scheme": "ws",
            "port": 7433,
            "pickLanHost": lambda: "192.168.1.10",
        })
        assert out == {"url": "ws://192.168.1.10:7433", "source": "gateway.bind=lan"}

    def test_loopback_returns_none(self) -> None:
        out = resolve_gateway_bind_url({
            "bind": "loopback",
            "scheme": "ws",
            "port": 7433,
        })
        assert out is None


# ============================================================================
# gateway-method-policy
# ============================================================================


class TestGatewayMethodPolicy:
    def test_reserved_scopes(self) -> None:
        for m in ("exec.approvals.list", "config.get", "wizard.next", "update.run"):
            assert resolve_reserved_gateway_method_scope(m) == RESERVED_ADMIN_GATEWAY_METHOD_SCOPE

    def test_non_reserved(self) -> None:
        assert resolve_reserved_gateway_method_scope("chat.send") is None
        assert resolve_reserved_gateway_method_scope("node.list") is None

    def test_normalize_passthrough(self) -> None:
        out = normalize_plugin_gateway_method_scope("chat.send", "operator.read")
        assert out == {"scope": "operator.read", "coercedToReservedAdmin": False}

    def test_normalize_coerced(self) -> None:
        out = normalize_plugin_gateway_method_scope("config.get", "operator.read")
        assert out == {"scope": "operator.admin", "coercedToReservedAdmin": True}

    def test_normalize_matching_scope(self) -> None:
        out = normalize_plugin_gateway_method_scope("config.get", "operator.admin")
        assert out == {"scope": "operator.admin", "coercedToReservedAdmin": False}


# ============================================================================
# gateway-tailscale-auth-policy
# ============================================================================


class TestGatewayTailscaleAuthPolicy:
    def test_unsafe_none_serve(self) -> None:
        assert is_unsafe_gateway_tailscale_no_auth({"authMode": "none", "tailscaleMode": "serve"}) is True

    def test_unsafe_none_funnel(self) -> None:
        assert is_unsafe_gateway_tailscale_no_auth({"authMode": "none", "tailscaleMode": "funnel"}) is True

    def test_safe_with_password(self) -> None:
        assert is_unsafe_gateway_tailscale_no_auth({"authMode": "password", "tailscaleMode": "funnel"}) is False

    def test_safe_off(self) -> None:
        assert is_unsafe_gateway_tailscale_no_auth({"authMode": "none", "tailscaleMode": "off"}) is False

    def test_format_funnel(self) -> None:
        out = format_unsafe_gateway_tailscale_no_auth_message("funnel")
        assert "funnel" in out and "password" in out

    def test_format_serve(self) -> None:
        out = format_unsafe_gateway_tailscale_no_auth_message("serve")
        assert "serve" in out


# ============================================================================
# global-singleton
# ============================================================================


class TestGlobalSingleton:
    def test_singleton(self) -> None:
        key = object()  # unique key for this test
        calls = []

        def _create():
            calls.append(1)
            return "value"

        a = resolve_global_singleton(key, _create)
        b = resolve_global_singleton(key, _create)
        assert a is b
        assert calls == [1]

    def test_global_map(self) -> None:
        key = object()
        m = resolve_global_map(key)
        assert isinstance(m, dict)
        m["x"] = 1
        # Same key returns same dict.
        assert resolve_global_map(key) is m


# ============================================================================
# google-turn-ordering
# ============================================================================


class TestGoogleTurnOrdering:
    def test_assistant_first(self) -> None:
        msgs = [{"role": "assistant", "content": "hi"}]
        out = sanitize_google_assistant_first_ordering(msgs)
        assert out[0]["role"] == "user"
        assert out[0]["content"] == "(session bootstrap)"
        assert out[1:] == msgs

    def test_user_first(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        out = sanitize_google_assistant_first_ordering(msgs)
        assert out == msgs

    def test_idempotent(self) -> None:
        msgs = [{"role": "assistant", "content": "hi"}]
        once = sanitize_google_assistant_first_ordering(msgs)
        twice = sanitize_google_assistant_first_ordering(once)
        assert once == twice

    def test_empty(self) -> None:
        assert sanitize_google_assistant_first_ordering([]) == []


# ============================================================================
# html-entities
# ============================================================================


class TestHtmlEntities:
    def test_no_amp(self) -> None:
        assert decode_html_entities("hello") == "hello"

    def test_named(self) -> None:
        assert decode_html_entities("&amp;") == "&"
        assert decode_html_entities("&lt;") == "<"
        assert decode_html_entities("&gt;") == ">"
        assert decode_html_entities("&quot;") == '"'

    def test_numeric_decimal(self) -> None:
        assert decode_html_entities("&#65;") == "A"

    def test_numeric_hex(self) -> None:
        assert decode_html_entities("&#x41;") == "A"

    def test_legacy_mixed_case(self) -> None:
        assert decode_html_entities("&QUOT;") == '"'
        assert decode_html_entities("&Amp;") == "&"

    def test_unicode_scalar(self) -> None:
        assert decode_html_entities("&#x1F600;") == "\U0001F600"  # emoji

    def test_invalid_keeps(self) -> None:
        assert decode_html_entities("&unknown;") == "&unknown;"

    def test_only_single_pass(self) -> None:
        # After decoding, ampersands should not re-trigger.
        assert decode_html_entities("&amp;amp;") == "&amp;"


# ============================================================================
# human-list
# ============================================================================


class TestHumanList:
    def test_empty(self) -> None:
        assert format_human_list([]) == ""

    def test_single(self) -> None:
        assert format_human_list(["A"]) == "A"

    def test_two(self) -> None:
        assert format_human_list(["A", "B"]) == "A or B"

    def test_three(self) -> None:
        assert format_human_list(["A", "B", "C"]) == "A, B, or C"

    def test_four(self) -> None:
        assert format_human_list(["A", "B", "C", "D"]) == "A, B, C, or D"


# ============================================================================
# import-specifier
# ============================================================================


class TestImportSpecifier:
    def test_non_windows_passthrough(self) -> None:
        original = sys.platform
        try:
            # Force non-windows path branch in this test.
            import src.shared.import_specifier as mod
            mod.sys.platform = "linux"
            assert to_safe_import_path("/abs/path") == "/abs/path"
        finally:
            mod.sys.platform = original

    def test_file_url_passthrough(self) -> None:
        original = sys.platform
        try:
            import src.shared.import_specifier as mod
            mod.sys.platform = "win32"
            assert to_safe_import_path("file:///C:/abs/path") == "file:///C:/abs/path"
        finally:
            mod.sys.platform = original

    def test_relative_passthrough(self) -> None:
        original = sys.platform
        try:
            import src.shared.import_specifier as mod
            mod.sys.platform = "win32"
            assert to_safe_import_path("relative/path") == "relative/path"
        finally:
            mod.sys.platform = original

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only conversion path")
    def test_windows_absolute_converts(self) -> None:
        out = to_safe_import_path("C:\\Users\\foo")
        assert out.startswith("file:///")


# ============================================================================
# iso-time
# ============================================================================


class TestIsoTime:
    def test_date_only(self) -> None:
        assert has_valid_iso_calendar_components("2026-08-01") is True

    def test_invalid_date(self) -> None:
        assert has_valid_iso_calendar_components("2026-13-01") is False
        assert has_valid_iso_calendar_components("2026-02-30") is False

    def test_with_time(self) -> None:
        assert has_valid_iso_calendar_components("2026-08-01T12:30:45Z") is True
        assert has_valid_iso_calendar_components("2026-08-01T12:30:45.123Z") is True

    def test_with_offset(self) -> None:
        assert has_valid_iso_calendar_components("2026-08-01T12:30:45+05:30") is True
        assert has_valid_iso_calendar_components("2026-08-01T12:30:45-0800") is True

    def test_end_of_day(self) -> None:
        # 24:00:00 == 00:00:00 next day; both valid in ISO 8601.
        assert has_valid_iso_calendar_components("2026-08-01T24:00:00") is True

    def test_non_string(self) -> None:
        assert has_valid_iso_calendar_components(None) is False
        assert has_valid_iso_calendar_components(42) is False

    def test_empty(self) -> None:
        assert has_valid_iso_calendar_components("") is False

    def test_invalid_format(self) -> None:
        assert has_valid_iso_calendar_components("2026/08/01") is False
        assert has_valid_iso_calendar_components("01-08-2026") is False


# ============================================================================
# lazy-runtime
# ============================================================================


class TestLazyRuntime:
    def test_module_caches_within_loader(self) -> None:
        calls = []

        def _importer():
            calls.append(1)
            async def _mod() -> dict:
                return {"name": "mod"}
            return _mod()

        # Same loader → second call returns the cached module.
        m = create_lazy_runtime_module(_importer)
        a = asyncio.run(m())
        b = asyncio.run(m())
        assert a == b == {"name": "mod"}
        assert len(calls) == 1  # cached within one loader

    def test_named_export(self) -> None:
        async def _importer() -> dict:
            return {"foo": 42, "bar": 7}
        f = create_lazy_runtime_named_export(_importer, "foo")
        assert asyncio.run(f()) == 42

    def test_method(self) -> None:
        async def _greet(name: str) -> str:
            return f"hi {name}"

        async def _load() -> dict:
            return {"greet": _greet}
        greet = create_lazy_runtime_method(_load, lambda s: s["greet"])
        result = asyncio.run(greet("alice"))
        assert result == "hi alice"

    def test_method_binder(self) -> None:
        async def _add(a: int, b: int) -> int:
            return a + b

        async def _load() -> dict:
            return {"add": _add}
        binder = create_lazy_runtime_method_binder(_load)
        add = binder(lambda s: s["add"])
        assert asyncio.run(add(2, 3)) == 5

    def test_surface(self) -> None:
        async def _importer() -> dict:
            return {"a": 1, "b": 2}
        s = create_lazy_runtime_surface(_importer, lambda m: m["a"])
        assert asyncio.run(s()) == 1


# ============================================================================
# listeners
# ============================================================================


class TestListeners:
    def test_notify(self) -> None:
        seen = []
        listeners = [lambda e: seen.append(("a", e)), lambda e: seen.append(("b", e))]
        notify_listeners(listeners, "event")
        assert seen == [("a", "event"), ("b", "event")]

    def test_notify_isolates_error(self) -> None:
        seen = []

        def _bad(e):
            raise ValueError("boom")

        def _good(e):
            seen.append(e)

        errors = []
        notify_listeners([_bad, _good], "x", on_error=errors.append)
        assert seen == ["x"]
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)

    def test_register_unsubscribe(self) -> None:
        listeners: set = set()
        cb = lambda e: None
        unsub = register_listener(listeners, cb)
        assert cb in listeners
        unsub()
        assert cb not in listeners

    def test_register_idempotent(self) -> None:
        listeners: set = set()
        cb = lambda e: None
        unsub1 = register_listener(listeners, cb)
        unsub2 = register_listener(listeners, cb)
        # set dedupes; still one entry.
        assert len(listeners) == 1
        unsub1()
        assert len(listeners) == 0
        # Calling unsub2 again is a no-op.
        unsub2()
        assert len(listeners) == 0


# ============================================================================
# lobster-day
# ============================================================================


class TestLobsterDay:
    def test_hash_stable(self) -> None:
        d = datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert lobster_day_hash(d) == lobster_day_hash(d)

    def test_hash_different_dates(self) -> None:
        a = lobster_day_hash(datetime(2026, 8, 1, tzinfo=timezone.utc))
        b = lobster_day_hash(datetime(2026, 8, 2, tzinfo=timezone.utc))
        assert a != b

    def test_is_lobster_day_returns_bool(self) -> None:
        out = is_lobster_day(datetime(2026, 8, 1, tzinfo=timezone.utc))
        assert isinstance(out, bool)

    def test_modulus(self) -> None:
        # is_lobster_day iff hash % 16 == 3.
        h = lobster_day_hash(datetime(2026, 8, 1, tzinfo=timezone.utc))
        assert is_lobster_day(datetime(2026, 8, 1, tzinfo=timezone.utc)) is (h % 16 == 3)


# ============================================================================
# markdown-code
# ============================================================================


class TestMarkdownCode:
    def test_inline_no_backticks(self) -> None:
        assert format_inline_code_span("hello") == "`hello`"

    def test_inline_with_backticks(self) -> None:
        out = format_inline_code_span("a`b")
        assert out.startswith("``")
        assert "a`b" in out

    def test_inline_padding_edge_backticks(self) -> None:
        out = format_inline_code_span("`hello`")
        # Edge backticks → spacer padding.
        assert out.startswith("`` ")

    def test_inline_padding_newline(self) -> None:
        out = format_inline_code_span("line1\nline2")
        assert " " in out

    def test_fenced_basic(self) -> None:
        out = format_fenced_code_block("hello", "py")
        assert out.startswith("```py\n")
        assert out.endswith("\n```")
        assert "hello" in out

    def test_fenced_no_language(self) -> None:
        out = format_fenced_code_block("hello")
        assert out.startswith("```\n")


# ============================================================================
# message-content-blocks
# ============================================================================


class TestMessageContentBlocks:
    def test_visits_blocks(self) -> None:
        seen = []
        msg = {"content": [{"type": "text"}, {"type": "image"}]}
        visit_object_content_blocks(msg, lambda b: seen.append(b))
        assert len(seen) == 2

    def test_non_dict_message(self) -> None:
        seen = []
        visit_object_content_blocks(None, lambda b: seen.append(b))
        visit_object_content_blocks("string", lambda b: seen.append(b))
        assert seen == []

    def test_non_array_content(self) -> None:
        seen = []
        visit_object_content_blocks({"content": "not array"}, lambda b: seen.append(b))
        assert seen == []

    def test_skips_non_object_blocks(self) -> None:
        seen = []
        msg = {"content": [{"type": "text"}, "string", None, 42]}
        visit_object_content_blocks(msg, lambda b: seen.append(b))
        assert len(seen) == 1


# ============================================================================
# model-key
# ============================================================================


class TestModelKey:
    def test_basic(self) -> None:
        assert model_key("openai", "gpt-4") == "openai/gpt-4"

    def test_already_prefixed(self) -> None:
        assert model_key("openai", "openai/gpt-4") == "openai/gpt-4"

    def test_empty_provider(self) -> None:
        assert model_key("", "gpt-4") == "gpt-4"

    def test_empty_model(self) -> None:
        assert model_key("openai", "") == "openai"

    def test_strips_whitespace(self) -> None:
        assert model_key(" openai ", " gpt-4 ") == "openai/gpt-4"

    def test_case_insensitive_match(self) -> None:
        # OpenAI/GPT-4 is already prefixed; case mismatch still dedupes.
        assert model_key("openai", "OpenAI/gpt-4") == "OpenAI/gpt-4"


# ============================================================================
# model-param-b
# ============================================================================


class TestModelParamB:
    def test_basic(self) -> None:
        assert infer_param_b_from_id_or_name("llama-8b") == 8.0

    def test_decimal(self) -> None:
        assert infer_param_b_from_id_or_name("model-1.5b") == 1.5

    def test_largest(self) -> None:
        assert infer_param_b_from_id_or_name("8b 70b") == 70.0

    def test_dash_separator(self) -> None:
        assert infer_param_b_from_id_or_name("8b-70b") == 70.0

    def test_no_match(self) -> None:
        assert infer_param_b_from_id_or_name("plain model") is None

    def test_non_string(self) -> None:
        assert infer_param_b_from_id_or_name(None) is None
        assert infer_param_b_from_id_or_name(42) is None

    def test_trailing_b_only(self) -> None:
        # 5b is a valid match (just the unit).
        assert infer_param_b_from_id_or_name("5b") == 5.0


# ============================================================================
# node-list-types
# ============================================================================


class TestNodeListTypes:
    def test_node(self) -> None:
        n: NodeListNode = {"nodeId": "n1", "platform": "win32"}
        assert n["nodeId"] == "n1"

    def test_pending(self) -> None:
        p: PendingRequest = {"requestId": "r1", "nodeId": "n1", "ts": 1}
        assert p["ts"] == 1

    def test_paired(self) -> None:
        p: PairedNode = {"nodeId": "n1"}
        assert p["nodeId"] == "n1"

    def test_pairing_list(self) -> None:
        pl: PairingList = {"pending": [], "paired": []}
        assert pl["pending"] == []


# ============================================================================
# node-skill-constraints
# ============================================================================


class TestNodeSkillConstraints:
    def test_constants(self) -> None:
        assert NODE_SKILL_MAX_COUNT == 64
        assert NODE_SKILL_MAX_CONTENT_BYTES == 64 * 1024
        assert NODE_SKILL_MAX_TOTAL_BYTES == 512 * 1024
        assert NODE_SKILL_MAX_DESCRIPTION_LENGTH == 1024

    def test_name_pattern_valid(self) -> None:
        assert NODE_SKILL_NAME_RE.match("foo") is not None
        assert NODE_SKILL_NAME_RE.match("foo-bar") is not None
        assert NODE_SKILL_NAME_RE.match("abc123") is not None

    def test_name_pattern_double_dash(self) -> None:
        assert NODE_SKILL_NAME_RE.match("foo--bar") is None

    def test_name_pattern_leading_dash(self) -> None:
        assert NODE_SKILL_NAME_RE.match("-foo") is None

    def test_name_pattern_uppercase(self) -> None:
        assert NODE_SKILL_NAME_RE.match("Foo") is None


# ============================================================================
# number-coercion
# ============================================================================


class TestNumberCoercion:
    def test_int(self) -> None:
        assert resolve_non_negative_number(5) == 5

    def test_zero(self) -> None:
        assert resolve_non_negative_number(0) == 0

    def test_float(self) -> None:
        assert resolve_non_negative_number(3.14) == 3.14

    def test_negative(self) -> None:
        assert resolve_non_negative_number(-1) is None

    def test_none(self) -> None:
        assert resolve_non_negative_number(None) is None

    def test_string(self) -> None:
        assert resolve_non_negative_number("5") is None

    def test_bool(self) -> None:
        # Booleans are not treated as numbers in the facade.
        assert resolve_non_negative_number(True) is None
        assert resolve_non_negative_number(False) is None


# ============================================================================
# path-array-index
# ============================================================================


class TestPathArrayIndex:
    def test_constants(self) -> None:
        assert MAX_CONFIG_PATH_ARRAY_INDEX == 100_000

    def test_zero(self) -> None:
        assert parse_config_path_array_index("0") == 0

    def test_positive(self) -> None:
        assert parse_config_path_array_index("42") == 42

    def test_max(self) -> None:
        assert parse_config_path_array_index("100000") == 100_000

    def test_too_large(self) -> None:
        assert parse_config_path_array_index("100001") is None

    def test_leading_zero(self) -> None:
        # "012" is not canonical (leading zero).
        assert parse_config_path_array_index("012") is None

    def test_negative(self) -> None:
        assert parse_config_path_array_index("-1") is None

    def test_empty(self) -> None:
        assert parse_config_path_array_index("") is None

    def test_non_string(self) -> None:
        assert parse_config_path_array_index(None) is None
        assert parse_config_path_array_index(42) is None


# ============================================================================
# progress-labels
# ============================================================================


class TestProgressLabels:
    def test_default(self) -> None:
        assert DEFAULT_PROGRESS_DRAFT_LABELS == ["Working"]

    def test_empty(self) -> None:
        assert select_progress_label({"labels": []}) is None

    def test_no_seed_no_random(self) -> None:
        out = select_progress_label({"labels": ["A", "B", "C"]})
        assert out in ("A", "B", "C")

    def test_seed_deterministic(self) -> None:
        a = select_progress_label({"labels": ["A", "B", "C"], "seed": "session-1"})
        b = select_progress_label({"labels": ["A", "B", "C"], "seed": "session-1"})
        assert a == b

    def test_seed_in_range(self) -> None:
        out = select_progress_label({"labels": ["A", "B", "C"], "seed": "session-1"})
        assert out in ("A", "B", "C")

    def test_random(self) -> None:
        # Random with specific values.
        out = select_progress_label({"labels": ["A", "B", "C"], "random": lambda: 0.0})
        assert out == "A"
        out = select_progress_label({"labels": ["A", "B", "C"], "random": lambda: 0.99})
        assert out == "C"


# ============================================================================
# regexp
# ============================================================================


class TestRegExp:
    def test_basic(self) -> None:
        assert escape_reg_exp("hello") == "hello"

    def test_specials(self) -> None:
        assert escape_reg_exp("a.b") == r"a\.b"
        assert escape_reg_exp("a*b") == r"a\*b"
        assert escape_reg_exp("a+b") == r"a\+b"
        assert escape_reg_exp("a?b") == r"a\?b"
        assert escape_reg_exp("(a)") == r"\(a\)"
        assert escape_reg_exp("[a]") == r"\[a\]"
        assert escape_reg_exp("{a}") == r"\{a\}"
        assert escape_reg_exp("a|b") == r"a\|b"
        assert escape_reg_exp("a^b") == r"a\^b"
        assert escape_reg_exp("a$b") == r"a\$b"
        assert escape_reg_exp("a\\b") == r"a\\b"

    def test_usable_in_regex(self) -> None:
        pattern = escape_reg_exp("a.b")
        m = re.match(pattern, "a.b")
        assert m is not None
        m = re.match(pattern, "axb")
        assert m is None

    def test_non_string(self) -> None:
        assert escape_reg_exp(None) is None
        assert escape_reg_exp(42) == 42


# ============================================================================
# tilde-path
# ============================================================================


class TestTildePath:
    def test_just_tilde(self) -> None:
        assert expand_tilde_path("~") == os.path.expanduser("~")

    def test_tilde_slash(self) -> None:
        out = expand_tilde_path("~/foo")
        assert out.endswith("foo") or out.endswith(os.path.join("foo"))

    def test_tilde_name(self) -> None:
        out = expand_tilde_path("~foo")
        assert out.endswith("foo")

    def test_no_tilde(self) -> None:
        assert expand_tilde_path("/abs/path") == "/abs/path"

    def test_relative(self) -> None:
        assert expand_tilde_path("relative/path") == "relative/path"

    def test_strips_whitespace(self) -> None:
        out = expand_tilde_path("  ~  ")
        assert out == os.path.expanduser("~")


# ============================================================================
# tool-activity-heartbeat
# ============================================================================


class TestToolActivityHeartbeat:
    def setup_method(self) -> None:
        clear_tool_activity_run("test-run")

    def teardown_method(self) -> None:
        clear_tool_activity_run("test-run")

    def test_notify_records(self) -> None:
        notify_tool_activity("test-run")
        assert get_last_tool_activity_ms("test-run") > 0

    def test_notify_calls_listeners(self) -> None:
        seen = []
        on_tool_activity("test-run", lambda: seen.append(1))
        notify_tool_activity("test-run")
        notify_tool_activity("test-run")
        assert seen == [1, 1]

    def test_unsubscribe(self) -> None:
        seen = []
        unsub = on_tool_activity("test-run", lambda: seen.append(1))
        notify_tool_activity("test-run")
        unsub()
        notify_tool_activity("test-run")
        assert seen == [1]

    def test_clear(self) -> None:
        notify_tool_activity("test-run")
        assert get_last_tool_activity_ms("test-run") > 0
        clear_tool_activity_run("test-run")
        assert get_last_tool_activity_ms("test-run") == 0

    def test_empty_run_id(self) -> None:
        # Should be a no-op for empty/invalid run_id.
        notify_tool_activity("")
        notify_tool_activity(None)  # type: ignore[arg-type]

    def test_unknown_run_id(self) -> None:
        assert get_last_tool_activity_ms("never-notified") == 0
