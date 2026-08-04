"""Tests for Phase 8.2b — src/config/ medium file batch (8 files)."""
from __future__ import annotations

import os
import tempfile

import pytest

from src.config.channel_config_metadata import (
    PLUGIN_ORIGIN_RANK,
    collect_channel_dm_policy_metadata,
    collect_channel_schema_metadata,
    collect_plugin_schema_metadata,
)
from src.config.config_journal_snapshot import (
    CONFIG_JOURNAL_REDACTION_MARKER,
    config_snapshot_audit_record_matches_path,
    fingerprint_config_snapshot_authored_config,
)
from src.config.env_substitution import (
    MissingEnvVarError,
    contains_env_var_reference,
    resolve_config_env_vars,
)
from src.config.env_vars import (
    clone_env_with_platform_semantics,
    collect_config_runtime_env_vars,
    create_config_runtime_env,
    is_config_runtime_env_var_allowed,
)
from src.config.exec_command_highlighting import (
    resolve_exec_command_highlighting,
)
from src.config.future_version_guard import (
    ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV,
    format_future_config_action_block,
    resolve_future_config_action_block,
)
from src.config.gateway_control_ui_origins import (
    DEFAULT_GATEWAY_PORT,
    build_default_control_ui_allowed_origins,
    ensure_control_ui_allowed_origins_for_non_loopback_bind,
    has_configured_control_ui_allowed_origins,
    is_gateway_non_loopback_bind_mode,
    resolve_gateway_port_with_default,
)
from src.config.gateway_dispatch_config import (
    apply_gateway_dispatch_session_defaults,
    project_gateway_dispatch_config,
    read_gateway_dispatch_config,
)


# ============================================================================
# channel-config-metadata
# ============================================================================


class _FakePlugin:
    def __init__(self, **kw) -> None:
        self.id = kw.get("id")
        self.name = kw.get("name")
        self.description = kw.get("description")
        self.origin = kw.get("origin", "bundled")
        self.channels = kw.get("channels", [])
        self.channelConfigs = kw.get("channelConfigs", {})
        self.channelCatalogMeta = kw.get("channelCatalogMeta")
        self.packageChannel = kw.get("packageChannel")
        self.configSchema = kw.get("configSchema")
        self.configUiHints = kw.get("configUiHints")
        # Generic attribute storage for catalog/package objects that need
        # extra fields (label, blurb, doctorCapabilities, etc.).
        for k, v in kw.items():
            if not hasattr(self, k) or getattr(self, k) is None:
                setattr(self, k, v)


class _FakeRegistry:
    def __init__(self, plugins) -> None:
        self.plugins = plugins


class TestChannelConfigMetadata:
    def test_origin_rank_constants(self) -> None:
        assert PLUGIN_ORIGIN_RANK["config"] == 0
        assert PLUGIN_ORIGIN_RANK["workspace"] == 1
        assert PLUGIN_ORIGIN_RANK["global"] == 2
        assert PLUGIN_ORIGIN_RANK["bundled"] == 3

    def test_collect_plugin_dedup_closer_origin_wins(self) -> None:
        reg = _FakeRegistry([
            _FakePlugin(id="telegram", origin="bundled", name="Bundled"),
            _FakePlugin(id="telegram", origin="config", name="Config"),
        ])
        out = collect_plugin_schema_metadata(reg)
        assert len(out) == 1
        assert out[0]["name"] == "Config"

    def test_collect_plugin_sorted(self) -> None:
        reg = _FakeRegistry([
            _FakePlugin(id="b", origin="bundled"),
            _FakePlugin(id="a", origin="bundled"),
        ])
        out = collect_plugin_schema_metadata(reg)
        assert [entry["id"] for entry in out] == ["a", "b"]

    def test_collect_channel_from_channels(self) -> None:
        reg = _FakeRegistry([
            _FakePlugin(
                id="telegram",
                origin="bundled",
                channels=["telegram"],
                channelCatalogMeta=_FakePlugin(label="Telegram", blurb="TG"),
            ),
        ])
        out = collect_channel_schema_metadata(reg)
        assert len(out) == 1
        assert out[0]["label"] == "Telegram"
        assert out[0]["description"] == "TG"

    def test_collect_channel_sorts(self) -> None:
        reg = _FakeRegistry([
            _FakePlugin(id="x", origin="bundled", channels=["zeta"]),
            _FakePlugin(id="y", origin="bundled", channels=["alpha"]),
        ])
        out = collect_channel_schema_metadata(reg)
        assert [entry["id"] for entry in out] == ["alpha", "zeta"]

    def test_collect_dm_policy(self) -> None:
        pkg = _FakePlugin(id="telegram", doctorCapabilities=_FakePlugin(dmAllowFromMode="topOnly"))
        reg = _FakeRegistry([
            _FakePlugin(
                id="telegram",
                origin="bundled",
                channels=["telegram"],
                packageChannel=pkg,
            ),
        ])
        out = collect_channel_dm_policy_metadata(reg)
        assert out[0]["dmAllowFromMode"] == "topOnly"


# ============================================================================
# config-journal-snapshot
# ============================================================================


class TestConfigJournalSnapshot:
    def test_redaction_marker(self) -> None:
        assert CONFIG_JOURNAL_REDACTION_MARKER == "***"

    def test_fingerprint_deterministic(self) -> None:
        # Same value → same fingerprint; different value → different fingerprint.
        env = {"HOME": "/tmp/test_home"}
        a = fingerprint_config_snapshot_authored_config({"k": 1}, env)
        b = fingerprint_config_snapshot_authored_config({"k": 1}, env)
        assert a == b
        c = fingerprint_config_snapshot_authored_config({"k": 2}, env)
        assert a != c

    def test_fingerprint_type_distinguishing(self) -> None:
        env = {"HOME": "/tmp/test_home"}
        a = fingerprint_config_snapshot_authored_config({"k": "1"}, env)
        b = fingerprint_config_snapshot_authored_config({"k": 1}, env)
        # OpenClaw JSON-encodes before HMAC; "1" vs 1 are distinct.
        assert a != b

    def test_match_path_normalizes(self) -> None:
        assert config_snapshot_audit_record_matches_path(
            {"configPath": "/x/config.json"}, "/x/./config.json"
        )

    def test_match_path_mismatch(self) -> None:
        assert not config_snapshot_audit_record_matches_path(
            {"configPath": "/x/config.json"}, "/y/config.json"
        )

    def test_match_null(self) -> None:
        assert not config_snapshot_audit_record_matches_path(None, "/x/config.json")


# ============================================================================
# env-substitution
# ============================================================================


class TestEnvSubstitution:
    def test_no_substitution(self) -> None:
        out = resolve_config_env_vars({"key": "plain"}, {"FOO": "bar"})
        assert out == {"key": "plain"}

    def test_simple_substitution(self) -> None:
        out = resolve_config_env_vars(
            {"key": "${FOO}"}, {"FOO": "bar"},
        )
        assert out == {"key": "bar"}

    def test_missing_throws(self) -> None:
        with pytest.raises(MissingEnvVarError):
            resolve_config_env_vars({"key": "${MISSING}"}, {})

    def test_missing_with_callback(self) -> None:
        warnings = []
        out = resolve_config_env_vars(
            {"key": "${MISSING}"},
            {},
            on_missing=warnings.append,
        )
        assert out == {"key": "${MISSING}"}  # placeholder preserved
        assert len(warnings) == 1
        assert warnings[0]["varName"] == "MISSING"

    def test_escaped(self) -> None:
        out = resolve_config_env_vars(
            {"key": "$${FOO}"}, {"FOO": "bar"},
        )
        assert out == {"key": "${FOO}"}

    def test_nested(self) -> None:
        out = resolve_config_env_vars(
            {"a": {"b": "${FOO}"}, "list": ["${BAR}"]},
            {"FOO": "x", "BAR": "y"},
        )
        assert out == {"a": {"b": "x"}, "list": ["y"]}

    def test_lowercase_not_substituted(self) -> None:
        # OpenClaw requires uppercase-only env var names.
        out = resolve_config_env_vars({"k": "${lowercase}"}, {"lowercase": "x"})
        assert out == {"k": "${lowercase}"}

    def test_contains_env_var_reference(self) -> None:
        assert contains_env_var_reference("${FOO}") is True
        assert contains_env_var_reference("$${FOO}") is False
        assert contains_env_var_reference("plain") is False
        assert contains_env_var_reference("$") is False
        assert contains_env_var_reference("plain ${FOO} text") is True


# ============================================================================
# env-vars
# ============================================================================


class TestEnvVars:
    def test_clone(self) -> None:
        env = {"A": "1", "B": "2"}
        cloned = clone_env_with_platform_semantics(env)
        assert cloned == env
        cloned["C"] = "3"
        assert "C" not in env

    def test_collect_stub(self) -> None:
        assert collect_config_runtime_env_vars({}, {}) == []

    def test_create_stub(self) -> None:
        env = {"A": "1"}
        assert create_config_runtime_env(env, {}) == env

    def test_is_allowed_stub(self) -> None:
        assert is_config_runtime_env_var_allowed("FOO") is True
        assert is_config_runtime_env_var_allowed("") is False


# ============================================================================
# exec-command-highlighting
# ============================================================================


class TestExecCommandHighlighting:
    def test_disabled_by_default(self) -> None:
        assert resolve_exec_command_highlighting({}) is False

    def test_global_enabled(self) -> None:
        cfg = {"tools": {"exec": {"commandHighlighting": True}}}
        assert resolve_exec_command_highlighting({"config": cfg}) is True

    def test_agent_overrides_global(self) -> None:
        cfg = {
            "tools": {"exec": {"commandHighlighting": False}},
            "agents": {
                "list": [
                    {"id": "main", "tools": {"exec": {"commandHighlighting": True}}}
                ]
            },
        }
        assert resolve_exec_command_highlighting({"config": cfg, "agentId": "main"}) is True

    def test_agent_falls_back_to_global(self) -> None:
        cfg = {
            "tools": {"exec": {"commandHighlighting": True}},
            "agents": {"list": [{"id": "main"}]},
        }
        assert resolve_exec_command_highlighting({"config": cfg, "agentId": "main"}) is True


# ============================================================================
# future-version-guard
# ============================================================================


class TestFutureVersionGuard:
    def test_constants(self) -> None:
        assert ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV == "OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS"

    def test_no_block_same_version(self) -> None:
        out = resolve_future_config_action_block({
            "action": "write",
            "currentVersion": "1.0.0",
            "config": {"meta": {"lastTouchedVersion": "1.0.0"}},
        })
        assert out is None

    def test_blocks_older_binary(self) -> None:
        out = resolve_future_config_action_block({
            "action": "write",
            "currentVersion": "1.0.0",
            "config": {"meta": {"lastTouchedVersion": "1.1.0"}},
        })
        assert out is not None
        assert out["action"] == "write"
        assert out["touchedVersion"] == "1.1.0"

    def test_no_block_newer_binary(self) -> None:
        out = resolve_future_config_action_block({
            "action": "write",
            "currentVersion": "2.0.0",
            "config": {"meta": {"lastTouchedVersion": "1.0.0"}},
        })
        assert out is None

    def test_allow_override(self) -> None:
        out = resolve_future_config_action_block({
            "action": "write",
            "currentVersion": "1.0.0",
            "env": {ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS_ENV: "1"},
            "config": {"meta": {"lastTouchedVersion": "2.0.0"}},
        })
        assert out is None

    def test_snapshot_takes_precedence(self) -> None:
        out = resolve_future_config_action_block({
            "action": "write",
            "currentVersion": "1.0.0",
            "snapshot": {
                "config": {"meta": {"lastTouchedVersion": "1.0.0"}},
                "sourceConfig": {"meta": {"lastTouchedVersion": "2.0.0"}},
            },
        })
        assert out is not None
        assert out["touchedVersion"] == "2.0.0"

    def test_format(self) -> None:
        block = {
            "message": "Refusing to write",
            "hints": ["hint 1", "hint 2"],
        }
        out = format_future_config_action_block(block)
        assert "Refusing to write" in out
        assert "hint 1" in out


# ============================================================================
# gateway-control-ui-origins
# ============================================================================


class TestGatewayControlUiOrigins:
    def test_default_port(self) -> None:
        assert DEFAULT_GATEWAY_PORT == 7433

    def test_is_non_loopback_bind(self) -> None:
        assert is_gateway_non_loopback_bind_mode("lan") is True
        assert is_gateway_non_loopback_bind_mode("tailnet") is True
        assert is_gateway_non_loopback_bind_mode("custom") is True
        assert is_gateway_non_loopback_bind_mode("auto") is True
        assert is_gateway_non_loopback_bind_mode("loopback") is False
        assert is_gateway_non_loopback_bind_mode("") is False

    def test_has_configured_origins(self) -> None:
        assert has_configured_control_ui_allowed_origins({"allowedOrigins": []}) is False
        assert has_configured_control_ui_allowed_origins({"allowedOrigins": ["https://x"]}) is True
        assert has_configured_control_ui_allowed_origins({
            "allowedOrigins": [""], "dangerouslyAllowHostHeaderOriginFallback": True,
        }) is True

    def test_resolve_port(self) -> None:
        assert resolve_gateway_port_with_default(8000) == 8000
        assert resolve_gateway_port_with_default(0) == DEFAULT_GATEWAY_PORT
        assert resolve_gateway_port_with_default(None) == DEFAULT_GATEWAY_PORT
        assert resolve_gateway_port_with_default(8000, 9999) == 8000

    def test_build_origins(self) -> None:
        out = build_default_control_ui_allowed_origins({"port": 7433, "bind": "loopback"})
        assert "http://localhost:7433" in out
        assert "http://127.0.0.1:7433" in out

    def test_build_custom_bind(self) -> None:
        out = build_default_control_ui_allowed_origins({
            "port": 7433, "bind": "custom", "customBindHost": "10.0.0.1",
        })
        assert "http://10.0.0.1:7433" in out

    def test_ensure_passthrough(self) -> None:
        cfg: dict = {}
        out = ensure_control_ui_allowed_origins_for_non_loopback_bind(cfg)
        assert out["seededOrigins"] is None

    def test_ensure_seeds_for_auto(self) -> None:
        cfg: dict = {}
        out = ensure_control_ui_allowed_origins_for_non_loopback_bind(
            cfg, runtime_bind="auto"
        )
        assert out["seededOrigins"] is not None
        assert out["bind"] == "auto"
        # Origins were seeded into the config.
        assert cfg == {}  # original not mutated
        seeded_config = out["config"]
        assert seeded_config["gateway"]["controlUi"]["allowedOrigins"] == out["seededOrigins"]

    def test_ensure_skips_when_already_configured(self) -> None:
        cfg = {"gateway": {"controlUi": {"allowedOrigins": ["https://existing"]}}}
        out = ensure_control_ui_allowed_origins_for_non_loopback_bind(
            cfg, runtime_bind="auto"
        )
        assert out["seededOrigins"] is None

    def test_ensure_respects_disabled(self) -> None:
        cfg = {"gateway": {"controlUi": {"enabled": False}}}
        out = ensure_control_ui_allowed_origins_for_non_loopback_bind(
            cfg,
            runtime_bind="auto",
            require_control_ui_enabled=True,
        )
        assert out["seededOrigins"] is None


# ============================================================================
# gateway-dispatch-config
# ============================================================================


class TestGatewayDispatchConfig:
    def test_project_top_level_only(self) -> None:
        cfg = {
            "agents": {"a": 1},
            "gateway": {"port": 7433},
            "tools": {"foo": "bar"},  # not in top-level set
            "session": {"mainKey": "x"},
        }
        out = project_gateway_dispatch_config(cfg)
        assert "agents" in out
        assert "gateway" in out
        assert "session" in out
        assert "tools" not in out

    def test_project_empty(self) -> None:
        assert project_gateway_dispatch_config({}) == {}
        assert project_gateway_dispatch_config(None) == {}

    def test_session_main_key_pinned(self) -> None:
        cfg = {"session": {"mainKey": "operator"}}
        out = apply_gateway_dispatch_session_defaults(cfg)
        assert out["session"]["mainKey"] == "main"

    def test_session_no_main_key_unchanged(self) -> None:
        cfg = {"session": {"foo": "bar"}}
        out = apply_gateway_dispatch_session_defaults(cfg)
        assert out == cfg

    def test_read_missing_file(self) -> None:
        out = read_gateway_dispatch_config(
            config_path="/nonexistent/path/config.json",
            env={},
        )
        assert out == {}

    def test_read_basic(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"agents": {"a": 1}, "gateway": {"port": 7433}, "tools": {"ignored": true}}')
            path = f.name
        try:
            out = read_gateway_dispatch_config(config_path=path, env={})
            assert "agents" in out
            assert "gateway" in out
            assert "tools" not in out
        finally:
            os.unlink(path)

    def test_read_with_env_substitution(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"key": "${MY_VAR}"}')
            path = f.name
        try:
            out = read_gateway_dispatch_config(config_path=path, env={"MY_VAR": "value"})
            # Note: top-level keys not in the dispatch set are dropped, so
            # `key` is not present in the projected config.
            assert "key" not in out
        finally:
            os.unlink(path)
