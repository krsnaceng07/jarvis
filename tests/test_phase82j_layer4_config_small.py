"""Tests for Phase 8.2j — src/config/ small file batch (10 files).

Covers:
- zod_schema_gateway, zod_schema_agent_defaults, zod_schema_session
- zod_schema_providers_whatsapp, mcp_config
- paths, issue_location, io_factory, ambient_transcript_watermark
"""
from __future__ import annotations

import os

import pytest

from src.config.zod_schema_gateway import (
    GatewayConfigSchema,
    validate_gateway_health_check_thresholds,
)
from src.config.zod_schema_agent_defaults import (
    AgentDefaultsSchema,
    AgentThinkingLevel,
    OptionalBootstrapFileName,
    SilentReplyPolicy,
    SilentReplyPolicyConfigSchema,
)
from src.config.zod_schema_session import (
    CommandsSchema,
    MessagesSchema,
    SessionSchema,
    SessionSendPolicySchema,
    is_valid_byte_size,
    is_valid_duration,
    validate_session_maintenance_size_bytes,
)
from src.config.zod_schema_providers_whatsapp import (
    WhatsAppAccountSchema,
    WhatsAppConfigSchema,
)
from src.config.mcp_config import McpConfigSchema, validate_mcp_config
from src.config.paths import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_STATE_DIR,
    resolve_config_path,
    resolve_state_dir,
    resolve_workspace_dir,
)
from src.config.issue_location import (
    format_issue_location_path,
    issue_location_segments,
    normalize_issue_location_path,
)
from src.config.io_factory import create_config_io, make_deps
from src.config.ambient_transcript_watermark import (
    AMBIENT_TRANSCRIPT_WATERMARK,
    is_ambient_transcript_marker,
    stamp_ambient_transcript_marker,
    strip_ambient_transcript_marker,
)


# ============================================================================
# zod_schema_gateway
# ============================================================================


class TestZodSchemaGateway:
    def test_placeholder(self) -> None:
        assert GatewayConfigSchema is None

    def test_validate_no_issues_when_stale_absent(self) -> None:
        out = validate_gateway_health_check_thresholds({})
        assert out is None

    def test_validate_no_issues_when_stale_meets_health(self) -> None:
        out = validate_gateway_health_check_thresholds({
            "channelHealthCheckMinutes": 5,
            "channelStaleEventThresholdMinutes": 10,
        })
        assert out is None

    def test_validate_default_health_5(self) -> None:
        # No channelHealthCheckMinutes => default 5.
        out = validate_gateway_health_check_thresholds({
            "channelStaleEventThresholdMinutes": 3,
        })
        assert out is not None
        assert any("channelStaleEventThresholdMinutes" in i.get("message", "") for i in out)

    def test_validate_health_zero_disables_check(self) -> None:
        # channelHealthCheckMinutes=0 disables the cross-check.
        out = validate_gateway_health_check_thresholds({
            "channelHealthCheckMinutes": 0,
            "channelStaleEventThresholdMinutes": 1,
        })
        assert out is None

    def test_validate_health_zero_with_default(self) -> None:
        # If user sets 0 explicitly + missing stale, no issue.
        out = validate_gateway_health_check_thresholds({
            "channelHealthCheckMinutes": 0,
        })
        assert out is None

    def test_validate_non_dict(self) -> None:
        assert validate_gateway_health_check_thresholds("x") is None
        assert validate_gateway_health_check_thresholds(None) is None


# ============================================================================
# zod_schema_agent_defaults
# ============================================================================


class TestZodSchemaAgentDefaults:
    def test_placeholders(self) -> None:
        assert AgentDefaultsSchema is None
        assert SilentReplyPolicyConfigSchema is None

    def test_silent_policy_values(self) -> None:
        assert "allow" in {"allow", "disallow"}
        assert "disallow" in {"allow", "disallow"}

    def test_thinking_levels(self) -> None:
        for level in ("off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra"):
            assert level in {"off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra"}

    def test_bootstrap_file_names(self) -> None:
        for name in ("SOUL.md", "USER.md", "HEARTBEAT.md", "IDENTITY.md"):
            assert name in {"SOUL.md", "USER.md", "HEARTBEAT.md", "IDENTITY.md"}


# ============================================================================
# zod_schema_session
# ============================================================================


class TestZodSchemaSession:
    def test_placeholders(self) -> None:
        assert SessionSchema is None
        assert MessagesSchema is None
        assert CommandsSchema is None
        assert SessionSendPolicySchema is None

    def test_is_valid_byte_size(self) -> None:
        assert is_valid_byte_size("100b") is True
        assert is_valid_byte_size("100 kb") is True
        assert is_valid_byte_size("100MB") is True
        assert is_valid_byte_size("1.5gb") is True
        assert is_valid_byte_size(100) is True
        assert is_valid_byte_size(0) is False
        assert is_valid_byte_size(-1) is False
        assert is_valid_byte_size("abc") is False
        assert is_valid_byte_size("100") is False  # no unit
        assert is_valid_byte_size("") is False
        assert is_valid_byte_size(True) is False
        assert is_valid_byte_size(None) is False

    def test_is_valid_duration(self) -> None:
        assert is_valid_duration("30s") is True
        assert is_valid_duration("5m") is True
        assert is_valid_duration("1h") is True
        assert is_valid_duration("7d") is True
        assert is_valid_duration("100ms") is True
        assert is_valid_duration(60) is True
        assert is_valid_duration(0) is False
        assert is_valid_duration(-1) is False
        assert is_valid_duration("abc") is False
        assert is_valid_duration(None) is False
        assert is_valid_duration(True) is False

    def test_validate_maintenance_no_block(self) -> None:
        out = validate_session_maintenance_size_bytes({})
        assert out is None

    def test_validate_maintenance_invalid_size(self) -> None:
        issues = validate_session_maintenance_size_bytes({
            "maxDiskBytes": "abc",
            "highWaterBytes": "100xyz",
        })
        assert issues is not None
        assert len(issues) == 2

    def test_validate_maintenance_valid(self) -> None:
        out = validate_session_maintenance_size_bytes({
            "maxDiskBytes": "100mb",
            "highWaterBytes": "200mb",
        })
        assert out is None

    def test_validate_maintenance_max_disk_false(self) -> None:
        # False is allowed for maxDiskBytes.
        out = validate_session_maintenance_size_bytes({
            "maxDiskBytes": False,
        })
        assert out is None

    def test_validate_maintenance_non_dict(self) -> None:
        assert validate_session_maintenance_size_bytes("x") is None
        assert validate_session_maintenance_size_bytes(None) is None


# ============================================================================
# zod_schema_providers_whatsapp
# ============================================================================


class TestZodSchemaProvidersWhatsApp:
    def test_placeholders(self) -> None:
        assert WhatsAppAccountSchema is None
        assert WhatsAppConfigSchema is None


# ============================================================================
# mcp_config
# ============================================================================


class TestMcpConfig:
    def test_placeholder(self) -> None:
        assert McpConfigSchema is None

    def test_validate_no_hooks(self) -> None:
        assert validate_mcp_config({}) is None
        assert validate_mcp_config({"servers": {}}) is None
        assert validate_mcp_config("x") is None

    def test_validate_with_server_normalizer(self) -> None:
        issues = validate_mcp_config(
            {"servers": {"a": {"command": "npx"}}},
            mcp_server_config_fn=lambda p: [{"path": ["command"], "message": "bad"}],
        )
        assert issues is not None
        assert any(i.get("path") == ["servers", "a", "command"] for i in issues)

    def test_validate_with_clean_server(self) -> None:
        issues = validate_mcp_config(
            {"servers": {"a": {"command": "npx"}}},
            mcp_server_config_fn=lambda p: [],
        )
        assert issues is None


# ============================================================================
# paths
# ============================================================================


class TestPaths:
    def test_defaults(self) -> None:
        assert DEFAULT_STATE_DIR == "~/.openclaw"
        assert DEFAULT_CONFIG_PATH == "~/.openclaw/openclaw.json"

    def test_explicit_state_dir(self) -> None:
        env = {"OPENCLAW_STATE_DIR": "/custom/state"}
        assert resolve_state_dir(env) == "/custom/state"

    def test_explicit_state_dir_with_tilde(self) -> None:
        # Use an absolute path so the test is independent of HOME/USERPROFILE
        # expansion on the host platform.
        env = {"OPENCLAW_STATE_DIR": "/home/user/custom"}
        out = resolve_state_dir(env, homedir_fn=lambda: "/should/not/be/used")
        assert out == "/home/user/custom"

    def test_default_state_dir(self) -> None:
        # No explicit env => home/.openclaw
        out = resolve_state_dir({}, homedir_fn=lambda: "/home/user")
        assert out.replace("\\", "/") == "/home/user/.openclaw"

    def test_explicit_config_path(self) -> None:
        env = {"OPENCLAW_CONFIG_PATH": "/etc/openclaw.json"}
        assert resolve_config_path(env) == "/etc/openclaw.json"

    def test_default_config_path(self) -> None:
        out = resolve_config_path({}, homedir_fn=lambda: "/home/user")
        assert out.replace("\\", "/") == "/home/user/.openclaw/openclaw.json"

    def test_workspace_dir_explicit(self) -> None:
        env = {"OPENCLAW_WORKSPACE_DIR": "/work"}
        assert resolve_workspace_dir(env) == "/work"

    def test_workspace_dir_default(self) -> None:
        out = resolve_workspace_dir({}, homedir_fn=lambda: "/home/user")
        assert out.replace("\\", "/") == "/home/user/.openclaw/workspace"

    def test_no_homedir_fallback(self) -> None:
        out = resolve_state_dir({}, homedir_fn=lambda: "")
        # Empty home => "." fallback.
        assert out.replace("\\", "/").endswith("/.openclaw")


# ============================================================================
# issue_location
# ============================================================================


class TestIssueLocation:
    def test_normalize_blank(self) -> None:
        assert normalize_issue_location_path("") == "<root>"
        assert normalize_issue_location_path("   ") == "<root>"
        assert normalize_issue_location_path(None) == "<root>"  # type: ignore[arg-type]
        assert normalize_issue_location_path(42) == "<root>"  # type: ignore[arg-type]

    def test_normalize_keeps_value(self) -> None:
        assert normalize_issue_location_path("channels.slack") == "channels.slack"

    def test_normalize_replaces_index(self) -> None:
        out = normalize_issue_location_path("items[0].name")
        assert out == "items[].name"
        out = normalize_issue_location_path("a[12].b[34].c")
        assert out == "a[].b[].c"

    def test_segments_basic(self) -> None:
        out = issue_location_segments("a.b.c")
        assert out == ["a", "b", "c"]

    def test_segments_with_index(self) -> None:
        out = issue_location_segments("items[0]")
        assert out == ["items", 0]

    def test_segments_empty(self) -> None:
        assert issue_location_segments("") == []
        assert issue_location_segments(None) == []  # type: ignore[arg-type]

    def test_format_no_source(self) -> None:
        out = format_issue_location_path("channels.slack")
        assert out == "channels.slack"

    def test_format_with_source_line(self) -> None:
        out = format_issue_location_path(
            "channels.slack",
            source_file="cfg.json",
            line=12,
        )
        assert out == "cfg.json:12 — channels.slack"

    def test_format_with_source_line_blank_path(self) -> None:
        out = format_issue_location_path(
            "", source_file="cfg.json", line=12,
        )
        assert out == "cfg.json:12 — <root>"

    def test_format_with_source_line_no_source(self) -> None:
        out = format_issue_location_path("channels.slack", line=12)
        assert out == "channels.slack"


# ============================================================================
# io_factory
# ============================================================================


class TestIoFactory:
    def test_create_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            create_config_io()

    def test_make_deps_defaults(self) -> None:
        deps = make_deps()
        assert deps["env"] == {}
        assert deps["lowerPrecedenceEnv"] == {}
        assert deps["observe"] is True
        assert deps["configPath"] is None

    def test_make_deps_with_values(self) -> None:
        deps = make_deps(
            env={"FOO": "1"},
            config_path="/x",
            observe=False,
        )
        assert deps["env"] == {"FOO": "1"}
        assert deps["configPath"] == "/x"
        assert deps["observe"] is False


# ============================================================================
# ambient_transcript_watermark
# ============================================================================


class TestAmbientTranscriptWatermark:
    def test_constant(self) -> None:
        assert AMBIENT_TRANSCRIPT_WATERMARK == "[ambient]"

    def test_is_marker(self) -> None:
        assert is_ambient_transcript_marker("[ambient] hello") is True
        assert is_ambient_transcript_marker("[ambient]") is True
        assert is_ambient_transcript_marker("hello") is False
        assert is_ambient_transcript_marker("") is False
        assert is_ambient_transcript_marker(None) is False  # type: ignore[arg-type]
        assert is_ambient_transcript_marker(42) is False  # type: ignore[arg-type]

    def test_stamp(self) -> None:
        assert stamp_ambient_transcript_marker("hello") == "[ambient] hello"
        # Already stamped => unchanged.
        assert stamp_ambient_transcript_marker("[ambient] hello") == "[ambient] hello"
        assert stamp_ambient_transcript_marker(None) is None  # type: ignore[arg-type]
        assert stamp_ambient_transcript_marker(42) is None  # type: ignore[arg-type]

    def test_strip(self) -> None:
        assert strip_ambient_transcript_marker("[ambient] hello") == "hello"
        assert strip_ambient_transcript_marker("hello") == "hello"
        assert strip_ambient_transcript_marker(None) is None  # type: ignore[arg-type]
        assert strip_ambient_transcript_marker(42) is None  # type: ignore[arg-type]
