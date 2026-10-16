"""Tests for Phase 8.2g — src/config/ small file batch (19 files).

Covers:
- redact_snapshot_raw, redact_snapshot_secret_ref
- plugin_auto_enable, mcp_config_normalize
- io_meta, io_invalid_config, runtime_overrides
- io_recovery, model_policy_allowlist_migration
- plugin_install_config_migration, schema_shared
- types_plugins, types_hooks, types_skills, types_sandbox
- io_health_state, plugin_auto_enable_apply
- types_browser, types_mcp
"""
from __future__ import annotations

import pytest

from src.config.redact_snapshot_raw import (
    replace_sensitive_values_in_raw,
    should_fallback_to_structured_raw_redaction,
)
from src.config.redact_snapshot_secret_ref import (
    is_secret_ref_shape,
    redact_secret_ref_id,
)
from src.config.plugin_auto_enable import (
    detect_plugin_auto_enable_candidates,
)
from src.config.mcp_config_normalize import (
    CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT,
    canonicalize_configured_mcp_server,
    is_known_cli_mcp_type_alias,
    normalize_configured_mcp_servers,
    resolve_openclaw_mcp_transport_alias,
)
from src.config.io_meta import (
    AUTO_MANAGED_CONFIG_META_FIELDS,
    AUTO_MANAGED_CONFIG_META_PATHS,
    stamp_config_write_metadata,
)
from src.config.io_invalid_config import (
    create_invalid_config_error,
    format_invalid_config_details,
    is_doctor_recoverable_invalid_config_error,
    is_invalid_config_error,
    log_invalid_config_once,
    throw_invalid_config,
)
from src.config.runtime_overrides import (
    apply_config_overrides,
    capture_config_override_applier,
    get_config_overrides,
    reset_config_overrides,
    set_config_override,
    unset_config_override,
)
from src.config.io_recovery import (
    find_json_root_suffix,
    recover_config_from_json_root_suffix_with_context,
)
from src.config.model_policy_allowlist_migration import (
    MODEL_POLICY_ALLOWLIST_MIGRATION_MARKER,
    collect_legacy_default_model_allow_refs,
    compute_model_policy_allowlist,
    has_explicit_model_policy_allow,
    has_model_policy_allowlist_migration_marker,
    is_explicit_model_policy,
)
from src.config.plugin_install_config_migration import (
    extract_shipped_plugin_install_config_records,
    strip_shipped_plugin_install_config_records,
)
from src.config.schema_shared import (
    as_schema_object,
    clone_schema,
    find_wildcard_hint_match,
    schema_has_children,
)
from src.config.types_plugins import (
    BundledDiscoveryMode,
    PluginEntryConfig,
    PluginEntryHooksConfig,
    PluginEntryLlmConfig,
    PluginEntrySubagentConfig,
    PluginInstallRecord,
    PluginSlotsConfig,
    PluginsConfig,
    PluginsLoadConfig,
)
from src.config.types_hooks import (
    HookAction,
    HookConfig,
    HookMappingConfig,
    HookMappingMatch,
    HookMappingTransform,
    HooksConfig,
    HooksGmailConfig,
    HooksGmailServeConfig,
    HooksGmailTailscaleConfig,
    HooksGmailTailscaleMode,
    InternalHooksConfig,
)
from src.config.types_skills import (
    SkillConfig,
    SkillsConfig,
    SkillsInstallConfig,
    SkillsLimitsConfig,
    SkillsLoadConfig,
    SkillsNodeManager,
    SkillsWorkshopAutonomousConfig,
    SkillsWorkshopConfig,
)
from src.config.types_sandbox import (
    SandboxBrowserSettings,
    SandboxDockerSettings,
    SandboxPruneSettings,
    SandboxSshSettings,
    SandboxUlimitEntry,
    SandboxUlimitValue,
)
from src.config.io_health_state import (
    CONFIG_IO_HEALTH_STATE_MAX_SIZE,
    clear_config_io_health_state,
    get_config_io_health_state,
    is_acceptable_config_health,
    set_config_io_health_state,
)
from src.config.plugin_auto_enable_apply import apply_plugin_auto_enable
from src.config.types_browser import (
    BrowserConfig,
    BrowserProfileConfig,
    BrowserProfileDriver,
    BrowserSnapshotDefaults,
    BrowserSsrfPolicyConfig,
    BrowserTabCleanupConfig,
)
from src.config.types_mcp import (
    McpAppsConfig,
    McpAuth,
    McpCodexToolApprovalMode,
    McpConfig,
    McpServerCodexConfig,
    McpServerConfig,
    McpServerOauthConfig,
    McpServerToolFilterConfig,
    McpTransport,
)


# ============================================================================
# redact-snapshot.raw
# ============================================================================


class TestRedactSnapshotRaw:
    def test_replaces_known_value(self) -> None:
        out = replace_sensitive_values_in_raw({
            "raw": "key: abc123",
            "sensitiveValues": ["abc123"],
            "redactedSentinel": "***",
        })
        assert "abc123" not in out
        assert "***" in out

    def test_replaces_longest_first(self) -> None:
        # The longer overlapping value should be replaced first.
        out = replace_sensitive_values_in_raw({
            "raw": "secret: abc-123-xyz",
            "sensitiveValues": ["abc", "abc-123-xyz"],
            "redactedSentinel": "***",
        })
        assert "abc-123-xyz" not in out
        assert "***" in out

    def test_empty_sensitive_skipped(self) -> None:
        # Empty string is treated as no-op (would otherwise corrupt raw).
        out = replace_sensitive_values_in_raw({
            "raw": "hello",
            "sensitiveValues": [""],
            "redactedSentinel": "***",
        })
        assert out == "hello"

    def test_should_fallback_when_parse_fails(self) -> None:
        def parse_json5(s):
            raise ValueError("invalid")

        assert should_fallback_to_structured_raw_redaction({
            "redactedRaw": "x",
            "originalConfig": {},
            "restoreParsed": lambda p: {"ok": True, "result": p},
            "parseJson5": parse_json5,
        }) is True

    def test_should_fallback_when_restore_fails(self) -> None:
        assert should_fallback_to_structured_raw_redaction({
            "redactedRaw": "{}",
            "originalConfig": {"a": 1},
            "restoreParsed": lambda p: {"ok": False},
            "parseJson5": lambda s: {},
        }) is True

    def test_should_fallback_when_different(self) -> None:
        assert should_fallback_to_structured_raw_redaction({
            "redactedRaw": "{}",
            "originalConfig": {"a": 1},
            "restoreParsed": lambda p: {"ok": True, "result": {"b": 2}},
            "parseJson5": lambda s: {},
        }) is True

    def test_no_fallback_when_equal(self) -> None:
        # Same shape returned => no fallback.
        result = should_fallback_to_structured_raw_redaction({
            "redactedRaw": "{}",
            "originalConfig": {"a": 1},
            "restoreParsed": lambda p: {"ok": True, "result": {"a": 1}},
            "parseJson5": lambda s: {},
        })
        assert result is False


# ============================================================================
# redact-snapshot.secret-ref
# ============================================================================


class TestRedactSnapshotSecretRef:
    def test_is_secret_ref_shape(self) -> None:
        assert is_secret_ref_shape({"source": "env", "id": "TOKEN"}) is True
        assert is_secret_ref_shape({"source": "env"}) is False  # missing id
        assert is_secret_ref_shape({"id": "TOKEN"}) is False  # missing source
        assert is_secret_ref_shape({}) is False
        assert is_secret_ref_shape("x") is False
        assert is_secret_ref_shape(None) is False

    def test_redact_concrete_id(self) -> None:
        values: list = []
        out = redact_secret_ref_id({
            "value": {"source": "env", "id": "MY_TOKEN"},
            "values": values,
            "redactedSentinel": "***",
            "isEnvVarPlaceholder": lambda s: s.startswith("${"),
        })
        assert out["id"] == "***"
        assert values == ["MY_TOKEN"]

    def test_redact_keeps_placeholder(self) -> None:
        values: list = []
        out = redact_secret_ref_id({
            "value": {"source": "env", "id": "${MY_TOKEN}"},
            "values": values,
            "redactedSentinel": "***",
            "isEnvVarPlaceholder": lambda s: s.startswith("${"),
        })
        # ${ENV} placeholders are not collected (already indirect).
        assert out["id"] == "${MY_TOKEN}"
        assert values == []


# ============================================================================
# plugin-auto-enable
# ============================================================================


class TestPluginAutoEnableFacade:
    def test_re_exports(self) -> None:
        assert callable(detect_plugin_auto_enable_candidates)

    def test_apply_raises_without_hooks(self) -> None:
        with pytest.raises(NotImplementedError):
            from src.config.plugin_auto_enable import apply_plugin_auto_enable
            apply_plugin_auto_enable({})


# ============================================================================
# mcp-config-normalize
# ============================================================================


class TestMcpConfigNormalize:
    def test_alias_map(self) -> None:
        assert CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT["http"] == "streamable-http"
        assert CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT["sse"] == "sse"
        assert CLI_MCP_TYPE_TO_OPENCLAW_TRANSPORT["stdio"] == "stdio"

    def test_resolve_alias(self) -> None:
        assert resolve_openclaw_mcp_transport_alias("http") == "streamable-http"
        assert resolve_openclaw_mcp_transport_alias("SSE") == "sse"
        # stdio is not an HTTP transport — returns empty.
        assert resolve_openclaw_mcp_transport_alias("stdio") == ""
        # Unknown returns empty.
        assert resolve_openclaw_mcp_transport_alias("unknown") == ""
        # Non-string returns empty.
        assert resolve_openclaw_mcp_transport_alias(123) == ""

    def test_is_known_alias(self) -> None:
        assert is_known_cli_mcp_type_alias("http") is True
        assert is_known_cli_mcp_type_alias("stdio") is True
        assert is_known_cli_mcp_type_alias("unknown") is False
        assert is_known_cli_mcp_type_alias(123) is False

    def test_canonicalize_promotes_type(self) -> None:
        out = canonicalize_configured_mcp_server({
            "name": "fs",
            "type": "http",
        })
        assert out["transport"] == "streamable-http"
        assert "type" not in out

    def test_canonicalize_promotes_legacy_keys(self) -> None:
        out = canonicalize_configured_mcp_server({
            "name": "fs",
            "connect_timeout": 5000,
            "ssl_verify": False,
            "client_cert": "/path/cert",
            "client_key": "/path/key",
            "supports_parallel_tool_calls": True,
        })
        assert out["connectTimeout"] == 5000
        assert out["sslVerify"] is False
        assert out["clientCert"] == "/path/cert"
        assert out["clientKey"] == "/path/key"
        assert out["supportsParallelToolCalls"] is True
        # Original snake_case keys are removed.
        assert "connect_timeout" not in out
        assert "ssl_verify" not in out

    def test_canonicalize_preserves_existing_canonical(self) -> None:
        out = canonicalize_configured_mcp_server({
            "name": "fs",
            "connectTimeout": 5000,
            "connect_timeout": 9999,  # different; canonical wins
        })
        assert out["connectTimeout"] == 5000

    def test_canonicalize_non_dict(self) -> None:
        assert canonicalize_configured_mcp_server("x") == {}  # type: ignore[arg-type]

    def test_normalize_servers(self) -> None:
        servers = normalize_configured_mcp_servers({
            "a": {"command": "npx"},
            "b": "not-a-record",
            "c": {"command": "node"},
        })
        assert "a" in servers
        assert "b" not in servers
        assert "c" in servers

    def test_normalize_servers_non_dict(self) -> None:
        assert normalize_configured_mcp_servers(None) == {}
        assert normalize_configured_mcp_servers([]) == {}


# ============================================================================
# io.meta
# ============================================================================


class TestIoMeta:
    def test_constants(self) -> None:
        assert "lastTouchedVersion" in AUTO_MANAGED_CONFIG_META_FIELDS
        assert "lastTouchedAt" in AUTO_MANAGED_CONFIG_META_FIELDS
        assert ("meta", "lastTouchedVersion") in AUTO_MANAGED_CONFIG_META_PATHS

    def test_stamp_basic(self) -> None:
        cfg = {"agents": {}}
        out = stamp_config_write_metadata(cfg, now="2026-01-01T00:00:00Z", version="1.0.0")
        assert out["meta"]["lastTouchedVersion"] == "1.0.0"
        assert out["meta"]["lastTouchedAt"] == "2026-01-01T00:00:00Z"

    def test_stamp_preserves_existing_meta(self) -> None:
        cfg = {"meta": {"foo": "bar"}}
        out = stamp_config_write_metadata(cfg, now="2026-01-01T00:00:00Z", version="1.0.0")
        assert out["meta"]["foo"] == "bar"
        assert out["meta"]["lastTouchedVersion"] == "1.0.0"

    def test_stamp_uses_defaults(self) -> None:
        cfg = {"agents": {}}
        out = stamp_config_write_metadata(cfg)
        assert "lastTouchedVersion" in out["meta"]
        assert "lastTouchedAt" in out["meta"]


# ============================================================================
# io.invalid-config
# ============================================================================


class TestIoInvalidConfig:
    def test_format_empty(self) -> None:
        assert format_invalid_config_details([]) == ""

    def test_format_basic(self) -> None:
        out = format_invalid_config_details([
            {"path": "agents", "message": "missing"},
        ])
        assert "- agents: missing" in out

    def test_format_root_default(self) -> None:
        out = format_invalid_config_details([
            {"path": "", "message": "bad"},
        ])
        assert "- <root>: bad" in out

    def test_format_strips_control_chars(self) -> None:
        out = format_invalid_config_details([
            {"path": "x", "message": "bad\x00text"},
        ])
        assert "\x00" not in out

    def test_create_error(self) -> None:
        err = create_invalid_config_error("/cfg.json", "details")
        assert err.name == "InvalidConfigError"
        assert err.code == "INVALID_CONFIG"  # type: ignore[attr-defined]
        assert err.details == "details"  # type: ignore[attr-defined]
        assert err.recovery == "doctor"  # type: ignore[attr-defined]

    def test_is_invalid_config_error(self) -> None:
        err = create_invalid_config_error("/x", "d")
        assert is_invalid_config_error(err) is True
        assert is_invalid_config_error(ValueError("x")) is False

    def test_doctor_recoverable(self) -> None:
        err = create_invalid_config_error("/x", "d")
        assert is_doctor_recoverable_invalid_config_error(err) is True
        err2 = create_invalid_config_error("/x", "d", {"recovery": "manual"})
        assert is_doctor_recoverable_invalid_config_error(err2) is False

    def test_log_dedup(self) -> None:
        calls = []
        logger = type("L", (), {"error": lambda self, m: calls.append(m)})()

        class _Cache:
            def __init__(self):
                self.seen = set()
            def check(self, key):
                if key in self.seen:
                    return True
                self.seen.add(key)
                return False

        cache = _Cache()
        log_invalid_config_once({"configPath": "p", "details": "d", "logger": logger, "loggedConfigPaths": cache})
        log_invalid_config_once({"configPath": "p", "details": "d", "logger": logger, "loggedConfigPaths": cache})
        # Second call is deduped.
        assert len(calls) == 1

    def test_throw_invalid_config(self) -> None:
        calls = []
        logger = type("L", (), {"error": lambda self, m: calls.append(m)})()

        class _Cache:
            def check(self, key):
                return False

        with pytest.raises(Exception) as exc_info:
            throw_invalid_config({
                "configPath": "/x.json",
                "issues": [{"path": "a", "message": "bad"}],
                "logger": logger,
                "loggedConfigPaths": _Cache(),
            })
        assert "Invalid config" in str(exc_info.value)


# ============================================================================
# runtime-overrides
# ============================================================================


class TestRuntimeOverrides:
    def setup_method(self) -> None:
        reset_config_overrides()

    def test_get_initial_empty(self) -> None:
        assert get_config_overrides() == {}

    def test_reset(self) -> None:
        # Set a value via the public surface.
        def parse(p):
            return {"ok": True, "path": p.split(".")} if p else {"ok": False, "error": "empty"}

        def setter(tree, path, value):
            cur = tree
            for k in path[:-1]:
                cur = cur.setdefault(k, {})
            cur[path[-1]] = value

        set_config_override("agents.defaults.model", "x",
                            parse_config_path_fn=parse, set_config_value_at_path_fn=setter)
        assert get_config_overrides() != {}
        reset_config_overrides()
        assert get_config_overrides() == {}

    def test_set_missing_hooks(self) -> None:
        out = set_config_override("a.b", "x")
        assert out.get("ok") is False

    def test_unset_missing_hooks(self) -> None:
        out = unset_config_override("a.b")
        assert out.get("ok") is False

    def test_apply_no_overrides_passthrough(self) -> None:
        cfg = {"a": 1}
        out = apply_config_overrides(cfg)
        # No overrides => returns input unchanged (same reference).
        assert out is cfg

    def test_capture_no_overrides(self) -> None:
        applier = capture_config_override_applier()
        cfg = {"a": 1}
        assert applier(cfg) is cfg


# ============================================================================
# io.recovery
# ============================================================================


class TestIoRecovery:
    def test_find_root_at_start(self) -> None:
        # JSON root at the very start => no recovery.
        out = find_json_root_suffix("{}", {})
        assert out is None

    def test_find_root_with_prefix(self) -> None:
        def parse(s):
            return {"x": 1}

        out = find_json_root_suffix("# comment\n{\"x\": 1}\n", parse)
        assert out is not None
        assert out["raw"].startswith("{\"x\": 1}")
        assert out["parsed"] == {"x": 1}

    def test_find_root_no_match(self) -> None:
        out = find_json_root_suffix("hello world\n", lambda s: {})
        assert out is None

    def test_find_root_parse_error(self) -> None:
        def parse(s):
            raise ValueError("bad")

        out = find_json_root_suffix("hello\n{invalid}", parse)
        assert out is None

    def test_find_root_no_parser(self) -> None:
        out = find_json_root_suffix("hello\n{}", "not-a-parser")
        assert out is None

    def test_recover_requires_hooks(self) -> None:
        import asyncio

        async def run() -> None:
            assert await recover_config_from_json_root_suffix_with_context(
                {"deps": {"json5": {}}, "configPath": "/x"}, {"exists": True, "valid": False, "raw": "{}"},
            ) is False

        asyncio.run(run())


# ============================================================================
# model-policy-allowlist-migration
# ============================================================================


class TestModelPolicyAllowlistMigration:
    def test_marker_constant(self) -> None:
        assert MODEL_POLICY_ALLOWLIST_MIGRATION_MARKER == "modelPolicyAllowlist"

    def test_has_marker_true(self) -> None:
        cfg = {"meta": {"migrations": {"modelPolicyAllowlist": True}}}
        assert has_model_policy_allowlist_migration_marker(cfg) is True

    def test_has_marker_false(self) -> None:
        assert has_model_policy_allowlist_migration_marker({}) is False
        assert has_model_policy_allowlist_migration_marker({"meta": {}}) is False
        assert has_model_policy_allowlist_migration_marker({"meta": {"migrations": {}}}) is False
        assert has_model_policy_allowlist_migration_marker(None) is False
        assert has_model_policy_allowlist_migration_marker("x") is False

    def test_is_explicit_model_policy(self) -> None:
        assert is_explicit_model_policy({}) is True  # empty dict is explicit
        assert is_explicit_model_policy({"allow": ["a"]}) is True
        assert is_explicit_model_policy(None) is False
        assert is_explicit_model_policy([]) is False

    def test_has_explicit_allow(self) -> None:
        assert has_explicit_model_policy_allow({"allow": ["a"]}) is True
        assert has_explicit_model_policy_allow({}) is False
        assert has_explicit_model_policy_allow({"deny": ["a"]}) is False

    def test_compute_allowlist(self) -> None:
        # Unmarked config with default models map => legacy allowlist.
        out = compute_model_policy_allowlist({
            "root": {"agents": {"defaults": {"models": {"a": {}, "b": {}}}}},
            "defaults": {"models": {"a": {}, "b": {}}},
        })
        assert out == ["a", "b"]

    def test_compute_allowlist_with_marker(self) -> None:
        # Marked config => no allowlist.
        out = compute_model_policy_allowlist({
            "root": {"meta": {"migrations": {"modelPolicyAllowlist": True}}},
            "defaults": {"models": {"a": {}}},
        })
        assert out is None

    def test_compute_allowlist_with_explicit_policy(self) -> None:
        # Explicit modelPolicy (even empty) opts into new semantics.
        out = compute_model_policy_allowlist({
            "root": {},
            "defaults": {"modelPolicy": {}, "models": {"a": {}}},
        })
        assert out is None

    def test_collect_legacy_default_allow_refs(self) -> None:
        # No models map.
        assert collect_legacy_default_model_allow_refs({}) is None
        # Empty models map.
        assert collect_legacy_default_model_allow_refs({"models": {}}) is None
        # Whitespace-only keys are filtered.
        assert collect_legacy_default_model_allow_refs({"models": {"  ": {}, "a": {}}}) == ["a"]


# ============================================================================
# plugin-install-config-migration
# ============================================================================


class TestPluginInstallConfigMigration:
    def test_extract_no_config(self) -> None:
        assert extract_shipped_plugin_install_config_records({}) == {}
        assert extract_shipped_plugin_install_config_records(None) == {}  # type: ignore[arg-type]

    def test_extract_with_installs(self) -> None:
        out = extract_shipped_plugin_install_config_records({
            "plugins": {
                "installs": {
                    "acme/foo": {"source": "npm", "spec": "acme/foo@1.0"},
                    "bad": "not-a-record",
                },
            },
        })
        assert "acme/foo" in out
        assert "bad" not in out
        assert out["acme/foo"]["source"] == "npm"

    def test_strip_no_installs(self) -> None:
        cfg = {"plugins": {"entries": {}}}
        out = strip_shipped_plugin_install_config_records(cfg)
        # No installs key, returned unchanged.
        assert out is cfg

    def test_strip_with_installs(self) -> None:
        cfg = {
            "plugins": {
                "installs": {"a": {"source": "npm"}},
                "entries": {"x": {}},
            },
        }
        out = strip_shipped_plugin_install_config_records(cfg)
        assert "installs" not in out["plugins"]
        # entries preserved.
        assert out["plugins"]["entries"] == {"x": {}}

    def test_strip_prunes_empty_plugins(self) -> None:
        cfg = {"plugins": {"installs": {"a": {"source": "npm"}}}}
        out = strip_shipped_plugin_install_config_records(cfg)
        # plugins key removed entirely when it only had installs.
        assert "plugins" not in out

    def test_strip_non_dict(self) -> None:
        assert strip_shipped_plugin_install_config_records(None) is None  # type: ignore[arg-type]
        assert strip_shipped_plugin_install_config_records("x") == "x"  # type: ignore[arg-type]


# ============================================================================
# schema.shared
# ============================================================================


class TestSchemaShared:
    def test_clone_schema(self) -> None:
        s = {"a": {"b": [1, 2]}}
        out = clone_schema(s)
        assert out == s
        assert out is not s
        assert out["a"] is not s["a"]

    def test_as_schema_object(self) -> None:
        assert as_schema_object({"a": 1}) == {"a": 1}
        assert as_schema_object([]) is None
        assert as_schema_object(None) is None
        assert as_schema_object("x") is None
        assert as_schema_object(42) is None

    def test_schema_has_children_props(self) -> None:
        assert schema_has_children({"properties": {"a": {}}}) is True

    def test_schema_has_children_additional(self) -> None:
        assert schema_has_children({"additionalProperties": {"type": "string"}}) is True

    def test_schema_has_children_items(self) -> None:
        assert schema_has_children({"items": {"type": "object"}}) is True

    def test_schema_has_children_one_of(self) -> None:
        assert schema_has_children({
            "oneOf": [{"properties": {"a": {}}}],
        }) is True

    def test_schema_no_children(self) -> None:
        assert schema_has_children({"type": "string"}) is False
        assert schema_has_children({}) is False
        assert schema_has_children("not-a-dict") is False  # type: ignore[arg-type]

    def test_find_wildcard_match_exact(self) -> None:
        out = find_wildcard_hint_match({
            "uiHints": {"a.b": "exact"},
            "path": "a.b",
            "splitPath": lambda p: p.split("."),
        })
        assert out == {"path": "a.b", "hint": "exact"}

    def test_find_wildcard_match_with_wildcard(self) -> None:
        out = find_wildcard_hint_match({
            "uiHints": {"*.b": "wild", "a.b": "exact"},
            "path": "a.b",
            "splitPath": lambda p: p.split("."),
        })
        # exact match wins (fewer wildcards).
        assert out == {"path": "a.b", "hint": "exact"}

    def test_find_wildcard_no_match(self) -> None:
        out = find_wildcard_hint_match({
            "uiHints": {"x.y": "wrong"},
            "path": "a.b",
            "splitPath": lambda p: p.split("."),
        })
        assert out is None

    def test_find_wildcard_length_mismatch(self) -> None:
        out = find_wildcard_hint_match({
            "uiHints": {"a": "len1"},
            "path": "a.b",
            "splitPath": lambda p: p.split("."),
        })
        assert out is None


# ============================================================================
# types.plugins
# ============================================================================


class TestTypesPlugins:
    def test_aliases(self) -> None:
        assert BundledDiscoveryMode is not None

    def test_entry_hooks(self) -> None:
        cfg = PluginEntryHooksConfig(
            allowPromptInjection=True,
            allowConversationAccess=False,
            timeoutMs=5000,
        )
        assert cfg["timeoutMs"] == 5000

    def test_entry_subagent(self) -> None:
        cfg = PluginEntrySubagentConfig(allowModelOverride=True, allowedModels=["*"])
        assert cfg["allowedModels"] == ["*"]

    def test_entry_llm(self) -> None:
        cfg = PluginEntryLlmConfig(allowAgentIdOverride=True)
        assert cfg["allowAgentIdOverride"] is True

    def test_entry(self) -> None:
        cfg = PluginEntryConfig(
            enabled=True,
            config={"key": "value"},
        )
        assert cfg["config"] == {"key": "value"}

    def test_slots(self) -> None:
        cfg = PluginSlotsConfig(memory="none", contextEngine="core")
        assert cfg["memory"] == "none"

    def test_plugins_load(self) -> None:
        cfg = PluginsLoadConfig(paths=["/p1", "/p2"])
        assert cfg["paths"] == ["/p1", "/p2"]

    def test_install_record_dict(self) -> None:
        rec: PluginInstallRecord = {
            "source": "npm",
            "spec": "acme/foo@1.0",
            "version": "1.0",
        }
        assert rec["source"] == "npm"

    def test_top_level(self) -> None:
        cfg = PluginsConfig(enabled=True, allow=["foo"], deny=["bar"])
        assert cfg["enabled"] is True
        assert cfg["allow"] == ["foo"]


# ============================================================================
# types.hooks
# ============================================================================


class TestTypesHooks:
    def test_aliases(self) -> None:
        assert HookAction is not None
        assert HooksGmailTailscaleMode is not None

    def test_match(self) -> None:
        cfg = HookMappingMatch(path="x", source="webhook")
        assert cfg["path"] == "x"

    def test_transform(self) -> None:
        cfg = HookMappingTransform(module="@openclaw/transform", export="default")
        assert cfg["module"] == "@openclaw/transform"

    def test_mapping(self) -> None:
        cfg = HookMappingConfig(
            id="h1",
            action="wake",
            wakeMode="now",
            agentId="main",
        )
        assert cfg["id"] == "h1"
        assert cfg["action"] == "wake"

    def test_gmail_serve(self) -> None:
        cfg = HooksGmailServeConfig(bind="127.0.0.1", port=8080, path="/hook")
        assert cfg["port"] == 8080

    def test_gmail_tailscale(self) -> None:
        cfg = HooksGmailTailscaleConfig(mode="funnel", path="/hook", target="https://x")
        assert cfg["mode"] == "funnel"

    def test_gmail(self) -> None:
        cfg = HooksGmailConfig(account="me@gmail.com", includeBody=True)
        assert cfg["includeBody"] is True

    def test_hook_config(self) -> None:
        cfg = HookConfig(enabled=True, env={"FOO": "bar"})
        assert cfg["env"]["FOO"] == "bar"

    def test_internal(self) -> None:
        cfg = InternalHooksConfig(enabled=True, load={"extraDirs": ["/d"]})
        assert cfg["load"]["extraDirs"] == ["/d"]

    def test_hooks_config(self) -> None:
        cfg = HooksConfig(enabled=True, allowedSessionKeyPrefixes=["hook:"])
        assert cfg["allowedSessionKeyPrefixes"] == ["hook:"]


# ============================================================================
# types.skills
# ============================================================================


class TestTypesSkills:
    def test_aliases(self) -> None:
        assert SkillsNodeManager is not None

    def test_skill_config(self) -> None:
        cfg = SkillConfig(enabled=True, env={"KEY": "VALUE"}, config={"x": 1})
        assert cfg["enabled"] is True

    def test_load(self) -> None:
        cfg = SkillsLoadConfig(extraDirs=["/d"], watch=True, watchDebounceMs=500)
        assert cfg["watch"] is True

    def test_install(self) -> None:
        cfg = SkillsInstallConfig(preferBrew=True, nodeManager="pnpm", allowUploadedArchives=False)
        assert cfg["nodeManager"] == "pnpm"

    def test_limits(self) -> None:
        cfg = SkillsLimitsConfig(maxSkillsInPrompt=10, maxSkillFileBytes=50000)
        assert cfg["maxSkillsInPrompt"] == 10

    def test_workshop_autonomous(self) -> None:
        cfg = SkillsWorkshopAutonomousConfig(enabled=False)
        assert cfg["enabled"] is False

    def test_workshop(self) -> None:
        cfg = SkillsWorkshopConfig(approvalPolicy="pending", maxPending=5)
        assert cfg["approvalPolicy"] == "pending"

    def test_top_level(self) -> None:
        cfg = SkillsConfig(allowBundled=["core"], entries={"x": SkillConfig(enabled=True)})
        assert cfg["allowBundled"] == ["core"]


# ============================================================================
# types.sandbox
# ============================================================================


class TestTypesSandbox:
    def test_docker(self) -> None:
        cfg = SandboxDockerSettings(
            image="alpine",
            containerPrefix="x-",
            pidsLimit=100,
            memory="512m",
            ulimits={"nofile": "1024:2048"},
        )
        assert cfg["image"] == "alpine"
        assert cfg["ulimits"]["nofile"] == "1024:2048"

    def test_browser(self) -> None:
        cfg = SandboxBrowserSettings(
            enabled=True, cdpPort=9222, vncPort=5900, noVncPort=6080,
        )
        assert cfg["cdpPort"] == 9222

    def test_prune(self) -> None:
        cfg = SandboxPruneSettings(idleHours=24, maxAgeDays=7)
        assert cfg["idleHours"] == 24

    def test_ssh(self) -> None:
        cfg = SandboxSshSettings(
            target="user@host",
            workspaceRoot="/remote",
            identityFile="/path/key",
        )
        assert cfg["target"] == "user@host"

    def test_ulimit_aliases(self) -> None:
        # Both string and structured forms are valid ulimit entries.
        assert SandboxUlimitValue is not None
        assert SandboxUlimitEntry is not None


# ============================================================================
# io.health-state
# ============================================================================


class TestIoHealthState:
    def setup_method(self) -> None:
        clear_config_io_health_state()

    def test_constants(self) -> None:
        assert CONFIG_IO_HEALTH_STATE_MAX_SIZE == 64

    def test_set_get(self) -> None:
        set_config_io_health_state("p1", {"ok": True})
        assert get_config_io_health_state("p1") == {"ok": True}

    def test_set_invalid_path(self) -> None:
        set_config_io_health_state(None, "x")  # type: ignore[arg-type]
        assert get_config_io_health_state("p1") is None

    def test_set_promotes_recent(self) -> None:
        set_config_io_health_state("a", 1)
        set_config_io_health_state("b", 2)
        set_config_io_health_state("a", 3)
        assert get_config_io_health_state("a") == 3
        assert get_config_io_health_state("b") == 2

    def test_clear(self) -> None:
        set_config_io_health_state("a", 1)
        clear_config_io_health_state()
        assert get_config_io_health_state("a") is None

    def test_is_acceptable_no_state(self) -> None:
        assert is_acceptable_config_health("p1") is False

    def test_is_acceptable_no_fn(self) -> None:
        set_config_io_health_state("p1", "anything")
        assert is_acceptable_config_health("p1") is False

    def test_is_acceptable_with_fn(self) -> None:
        set_config_io_health_state("p1", "ok")
        assert is_acceptable_config_health("p1", is_acceptable_fn=lambda s: s == "ok") is True
        assert is_acceptable_config_health("p1", is_acceptable_fn=lambda s: s == "bad") is False


# ============================================================================
# plugin-auto-enable.apply
# ============================================================================


class TestPluginAutoEnableApply:
    def test_apply_no_candidates(self) -> None:
        out = apply_plugin_auto_enable({"config": {}})
        assert out["changes"] == []
        assert out["autoEnabledReasons"] == {}

    def test_apply_with_candidates_no_readiness(self) -> None:
        # No detection happens unless the env/registry are passed, so the
        # result is still empty for a basic config.
        out = apply_plugin_auto_enable({
            "config": {"plugins": {"entries": {}}},
        })
        assert out["changes"] == []

    def test_apply_preserves_existing_enabled(self) -> None:
        # Candidate plugin already enabled => not re-enabled, no change.
        out = apply_plugin_auto_enable({
            "config": {
                "plugins": {
                    "entries": {
                        "telegram": {"enabled": True},
                    }
                }
            },
            "resolve_plugin_auto_enable_candidate_reason_fn": lambda c: "test",
        })
        # Detection doesn't run without env/registry, so no candidates.
        assert out["changes"] == []

    def test_apply_returns_dict(self) -> None:
        out = apply_plugin_auto_enable({"config": {"plugins": {"entries": {}}}})
        assert "config" in out
        assert "changes" in out
        assert "autoEnabledReasons" in out

    def test_public_facade_delegates_without_raising(self) -> None:
        from src.config.plugin_auto_enable import apply_plugin_auto_enable as facade_apply

        out = facade_apply({"config": {"plugins": {"entries": {}}}})
        assert out["config"] == {"plugins": {"entries": {}}}
        assert out["changes"] == []


# ============================================================================
# types.browser
# ============================================================================


class TestTypesBrowser:
    def test_aliases(self) -> None:
        assert BrowserProfileDriver is not None

    def test_profile_config(self) -> None:
        cfg = BrowserProfileConfig(
            cdpPort=9222,
            color="#FF4500",
            driver="openclaw",
            headless=False,
        )
        assert cfg["color"] == "#FF4500"

    def test_snapshot_defaults(self) -> None:
        cfg = BrowserSnapshotDefaults(mode="efficient")
        assert cfg["mode"] == "efficient"

    def test_tab_cleanup(self) -> None:
        cfg = BrowserTabCleanupConfig(enabled=True, idleMinutes=60)
        assert cfg["idleMinutes"] == 60

    def test_ssrf_policy(self) -> None:
        cfg = BrowserSsrfPolicyConfig(
            dangerouslyAllowPrivateNetwork=True,
            allowedHostnames=["localhost"],
        )
        assert cfg["allowedHostnames"] == ["localhost"]

    def test_top_level(self) -> None:
        cfg = BrowserConfig(
            enabled=True,
            headless=False,
            noSandbox=True,
            defaultProfile="chrome",
        )
        assert cfg["defaultProfile"] == "chrome"


# ============================================================================
# types.mcp
# ============================================================================


class TestTypesMcp:
    def test_aliases(self) -> None:
        assert McpCodexToolApprovalMode is not None
        assert McpTransport is not None
        assert McpAuth is not None

    def test_codex(self) -> None:
        cfg = McpServerCodexConfig(agents=["main"], defaultToolsApprovalMode="auto")
        assert cfg["agents"] == ["main"]

    def test_tool_filter(self) -> None:
        cfg = McpServerToolFilterConfig(include=["*"], exclude=["secret"])
        assert cfg["include"] == ["*"]

    def test_oauth(self) -> None:
        cfg = McpServerOauthConfig(authProfileId="ap-1", scope="read")
        assert cfg["authProfileId"] == "ap-1"

    def test_server(self) -> None:
        cfg = McpServerConfig(
            enabled=True,
            command="npx",
            args=["-y", "server"],
            transport="stdio",
            timeout=30,
        )
        assert cfg["command"] == "npx"
        assert cfg["transport"] == "stdio"

    def test_apps(self) -> None:
        cfg = McpAppsConfig(enabled=True, sandboxPort=7434)
        assert cfg["sandboxPort"] == 7434

    def test_top_level(self) -> None:
        cfg = McpConfig(
            servers={"x": McpServerConfig(command="npx")},
            sessionIdleTtlMs=600_000,
        )
        assert "x" in cfg["servers"]
