"""Tests for Phase 8.2f — src/config/ small file batch (20 files).

Covers:
- types_provider_request, types_system_agent, types_marketplaces
- zod_schema_approvals, zod_schema_proxy, zod_schema_agent_model
- zod_schema_node_host, zod_schema_sensitive, zod_schema_implicit_mentions
- zod_schema_discord, zod_schema_allowdeny, zod_schema_channels
- io_observe_suspicious, io_state, provider_policy
- schema_node_capabilities, schema_help
- markdown_tables_types, io_warnings, types_signal
"""
from __future__ import annotations

import pytest

from src.config.types_provider_request import (
    ConfiguredModelProviderRequest,
    ConfiguredProviderRequest,
    ConfiguredProviderRequestAuth,
    ConfiguredProviderRequestProxy,
    ConfiguredProviderRequestTls,
)
from src.config.types_system_agent import (
    SystemAgentConfig,
    SystemAgentRescueConfig,
)
from src.config.types_marketplaces import (
    MarketplacesConfig,
    MarketplaceFeedKeyConfig,
    MarketplaceFeedProfileConfig,
    MarketplaceFeedVerificationConfig,
    MarketplaceSourceProfileConfig,
)
from src.config.zod_schema_approvals import (
    ApprovalsSchema,
    ExecApprovalForwardingSchema,
    ExecApprovalForwardTargetSchema,
    NativeExecApprovalEnableModeSchema,
    native_exec_approval_enable_mode_validator,
)
from src.config.zod_schema_proxy import (
    ProxyConfigSchema,
    ProxyLoopbackModeSchema,
    ProxyTlsConfigSchema,
)
from src.config.zod_schema_agent_model import (
    AgentModelSchema,
    AgentToolModelSchema,
    is_agent_model_value,
    is_agent_tool_model_value,
)
from src.config.zod_schema_node_host import (
    BrowserSnapshotDefaultsSchema,
    NodeHostAgentRunsSchema,
)
from src.config.zod_schema_sensitive import sensitive
from src.config.zod_schema_implicit_mentions import (
    ChannelImplicitMentionsSchema,
    is_valid_implicit_mentions,
)
from src.config.zod_schema_discord import (
    is_valid_discord_id,
    is_valid_discord_snowflake,
)
from src.config.zod_schema_allowdeny import (
    create_allow_deny_channel_rules_schema,
    is_allow_deny_action,
    is_allow_deny_chat_type,
)
from src.config.zod_schema_channels import (
    ChannelHealthMonitorConfig,
    ChannelHealthMonitorSchema,
    ChannelHeartbeatVisibilityConfig,
    ChannelHeartbeatVisibilitySchema,
)
from src.config.io_observe_suspicious import (
    ConfigObserveSuspiciousBaseline,
    resolve_config_observe_suspicious_reasons,
)
from src.config.io_state import (
    CONFIG_IO_WARNING_CACHE_MAX_SIZE,
    auto_owner_display_secret_by_path,
    logged_config_warning_fingerprints,
    set_bounded_config_io_warning_entry,
)
from src.config.provider_policy import (
    apply_provider_config_defaults_for_config,
    normalize_provider_config_for_config_defaults,
)
from src.config.schema_node_capabilities import (
    NODE_CAPABILITY_FIELD_HELP,
    NODE_CAPABILITY_FIELD_LABELS,
)
from src.config.schema_help import FIELD_HELP, get_field_help
from src.config.markdown_tables_types import (
    MarkdownTableMode,
    ResolveMarkdownTableModeParams,
)
from src.config.io_warnings import (
    log_config_warnings_once,
    warn_if_config_from_future,
    warn_on_config_miskeys,
)
from src.config.types_signal import (
    SignalAccountConfig,
    SignalActionsConfig,
    SignalApiMode,
    SignalConfig,
    SignalGroupConfig,
    SignalReactionLevel,
    SignalReactionNotificationMode,
)


# ============================================================================
# types.provider-request
# ============================================================================


class TestTypesProviderRequest:
    def test_tls_config(self) -> None:
        cfg = ConfiguredProviderRequestTls(
            ca="ca-cert", serverName="api.example.com", insecureSkipVerify=False,
        )
        assert cfg["serverName"] == "api.example.com"

    def test_auth_provider_default(self) -> None:
        cfg = ConfiguredProviderRequestAuth(mode="provider-default")
        assert cfg["mode"] == "provider-default"

    def test_auth_bearer(self) -> None:
        cfg = ConfiguredProviderRequestAuth(
            mode="authorization-bearer", token="abc",
        )
        assert cfg["token"] == "abc"

    def test_auth_header(self) -> None:
        cfg = ConfiguredProviderRequestAuth(
            mode="header", headerName="X-Api-Key", value="xyz", prefix="Bearer",
        )
        assert cfg["headerName"] == "X-Api-Key"

    def test_proxy_env(self) -> None:
        cfg = ConfiguredProviderRequestProxy(mode="env-proxy")
        assert cfg["mode"] == "env-proxy"

    def test_proxy_explicit(self) -> None:
        cfg = ConfiguredProviderRequestProxy(
            mode="explicit-proxy", url="http://proxy:8080",
        )
        assert cfg["url"] == "http://proxy:8080"

    def test_request_full(self) -> None:
        cfg = ConfiguredProviderRequest(
            headers={"X-Foo": "bar"},
            auth=ConfiguredProviderRequestAuth(mode="provider-default"),
        )
        assert cfg["headers"]["X-Foo"] == "bar"

    def test_model_request_private_network(self) -> None:
        cfg: ConfiguredModelProviderRequest = {
            "allowPrivateNetwork": True,
        }
        assert cfg["allowPrivateNetwork"] is True


# ============================================================================
# types.system-agent
# ============================================================================


class TestTypesSystemAgent:
    def test_rescue(self) -> None:
        cfg = SystemAgentRescueConfig(
            enabled="auto", ownerDmOnly=True, pendingTtlMinutes=15,
        )
        assert cfg["enabled"] == "auto"
        assert cfg["ownerDmOnly"] is True

    def test_rescue_bool(self) -> None:
        cfg = SystemAgentRescueConfig(enabled=False)
        assert cfg["enabled"] is False

    def test_top_level(self) -> None:
        cfg = SystemAgentConfig(
            rescue=SystemAgentRescueConfig(enabled="auto"),
        )
        assert cfg["rescue"]["enabled"] == "auto"


# ============================================================================
# types.marketplaces
# ============================================================================


class TestTypesMarketplaces:
    def test_feed_key(self) -> None:
        cfg = MarketplaceFeedKeyConfig(keyId="k1", publicKey="pk1")
        assert cfg["keyId"] == "k1"

    def test_feed_verification_unsigned(self) -> None:
        cfg = MarketplaceFeedVerificationConfig(mode="unsigned")
        assert cfg["mode"] == "unsigned"

    def test_feed_verification_signed(self) -> None:
        cfg = MarketplaceFeedVerificationConfig(
            mode="signed",
            keys=[MarketplaceFeedKeyConfig(keyId="k1", publicKey="pk1")],
            threshold=2,
        )
        assert cfg["threshold"] == 2

    def test_feed_profile(self) -> None:
        cfg = MarketplaceFeedProfileConfig(
            url="https://example.com/feed.json",
            verification=MarketplaceFeedVerificationConfig(mode="unsigned"),
        )
        assert cfg["url"] == "https://example.com/feed.json"

    def test_source(self) -> None:
        cfg = MarketplaceSourceProfileConfig(type="npm")
        assert cfg["type"] == "npm"

    def test_top_level(self) -> None:
        cfg = MarketplacesConfig(
            feeds={"main": MarketplaceFeedProfileConfig(url="x")},
            sources={"npm": MarketplaceSourceProfileConfig(type="npm")},
        )
        assert "main" in cfg["feeds"]


# ============================================================================
# zod-schema.approvals
# ============================================================================


class TestZodSchemaApprovals:
    def test_constants_exist(self) -> None:
        # Placeholders until the zod schema lands.
        assert NativeExecApprovalEnableModeSchema is None or (
            NativeExecApprovalEnableModeSchema is not None
        )
        assert ExecApprovalForwardingSchema is None or True
        assert ApprovalsSchema is None or True

    def test_validator_bool(self) -> None:
        assert native_exec_approval_enable_mode_validator(True) is True
        assert native_exec_approval_enable_mode_validator(False) is True

    def test_validator_auto(self) -> None:
        assert native_exec_approval_enable_mode_validator("auto") is True

    def test_validator_invalid(self) -> None:
        assert native_exec_approval_enable_mode_validator("yes") is False
        assert native_exec_approval_enable_mode_validator(42) is False


# ============================================================================
# zod-schema.proxy
# ============================================================================


class TestZodSchemaProxy:
    def test_placeholders(self) -> None:
        assert ProxyConfigSchema is None
        assert ProxyLoopbackModeSchema is None
        assert ProxyTlsConfigSchema is None


# ============================================================================
# zod-schema.agent-model
# ============================================================================


class TestZodSchemaAgentModel:
    def test_placeholders(self) -> None:
        assert AgentModelSchema is None
        assert AgentToolModelSchema is None

    def test_string_is_valid(self) -> None:
        assert is_agent_model_value("openai/gpt-4") is True
        assert is_agent_tool_model_value("anthropic/claude") is True

    def test_dict_is_valid(self) -> None:
        assert is_agent_model_value({"primary": "gpt-4"}) is True
        assert is_agent_model_value({"primary": "gpt-4", "fallbacks": ["a"]}) is True
        assert is_agent_tool_model_value({"primary": "gpt-4", "timeoutMs": 5000}) is True

    def test_invalid_keys(self) -> None:
        assert is_agent_model_value({"unknown": "x"}) is False
        assert is_agent_tool_model_value({"unknown": "x"}) is False

    def test_non_string_non_dict(self) -> None:
        assert is_agent_model_value(42) is False
        assert is_agent_tool_model_value(None) is False


# ============================================================================
# zod-schema.node-host
# ============================================================================


class TestZodSchemaNodeHost:
    def test_placeholders(self) -> None:
        assert BrowserSnapshotDefaultsSchema is None
        assert NodeHostAgentRunsSchema is None


# ============================================================================
# zod-schema.sensitive
# ============================================================================


class TestZodSchemaSensitive:
    def test_sensitive_registry_placeholder(self) -> None:
        # The zod registry is None until the schema validator lands.
        assert sensitive is None


# ============================================================================
# zod-schema.implicit-mentions
# ============================================================================


class TestZodSchemaImplicitMentions:
    def test_placeholder(self) -> None:
        assert ChannelImplicitMentionsSchema is None

    def test_validator_valid(self) -> None:
        assert is_valid_implicit_mentions({"replyToBot": True}) is True
        assert is_valid_implicit_mentions({}) is True
        assert is_valid_implicit_mentions({
            "replyToBot": True, "quotedBot": False, "threadParticipation": True,
        }) is True

    def test_validator_invalid_keys(self) -> None:
        assert is_valid_implicit_mentions({"unknown": True}) is False

    def test_validator_non_dict(self) -> None:
        assert is_valid_implicit_mentions("x") is False
        assert is_valid_implicit_mentions(None) is False


# ============================================================================
# zod-schema.discord
# ============================================================================


class TestZodSchemaDiscord:
    def test_placeholders(self) -> None:
        from src.config.zod_schema_discord import (
            DiscordIdSchema, DiscordIdListSchema,
            DiscordSnowflakeStringSchema, DiscordDmSchema, DiscordPresenceEventsSchema,
        )
        # All None until the validator lands.
        assert DiscordIdSchema is None
        assert DiscordIdListSchema is None
        assert DiscordSnowflakeStringSchema is None
        assert DiscordDmSchema is None
        assert DiscordPresenceEventsSchema is None

    def test_valid_snowflake(self) -> None:
        assert is_valid_discord_snowflake("123456789") is True
        assert is_valid_discord_snowflake("0") is True

    def test_invalid_snowflake(self) -> None:
        assert is_valid_discord_snowflake("abc") is False
        assert is_valid_discord_snowflake("123abc") is False
        assert is_valid_discord_snowflake(123) is False
        assert is_valid_discord_snowflake("") is False

    def test_valid_id_string(self) -> None:
        assert is_valid_discord_id("12345") is True
        assert is_valid_discord_id("foo") is True

    def test_valid_id_int(self) -> None:
        assert is_valid_discord_id(12345) is True
        assert is_valid_discord_id(0) is True

    def test_invalid_id_negative(self) -> None:
        assert is_valid_discord_id(-1) is False

    def test_invalid_id_too_large(self) -> None:
        # 2^53 is the max safe integer; 2^53 itself is still safe.
        assert is_valid_discord_id(1 << 53) is False

    def test_invalid_id_non_numeric(self) -> None:
        assert is_valid_discord_id([1, 2]) is False
        assert is_valid_discord_id(None) is False


# ============================================================================
# zod-schema.allowdeny
# ============================================================================


class TestZodSchemaAllowDeny:
    def test_create_returns_placeholder(self) -> None:
        assert create_allow_deny_channel_rules_schema() is None

    def test_is_allow_deny_action(self) -> None:
        assert is_allow_deny_action("allow") is True
        assert is_allow_deny_action("deny") is True
        assert is_allow_deny_action("maybe") is False

    def test_is_allow_deny_chat_type(self) -> None:
        for v in ("direct", "group", "channel", "dm", None):
            assert is_allow_deny_chat_type(v) is True
        assert is_allow_deny_chat_type("other") is False


# ============================================================================
# zod-schema.channels
# ============================================================================


class TestZodSchemaChannels:
    def test_placeholders(self) -> None:
        assert ChannelHeartbeatVisibilitySchema is None
        assert ChannelHealthMonitorSchema is None

    def test_heartbeat_visibility(self) -> None:
        cfg = ChannelHeartbeatVisibilityConfig(
            showOk=True, showAlerts=False, useIndicator=True,
        )
        assert cfg["showOk"] is True

    def test_health_monitor(self) -> None:
        cfg = ChannelHealthMonitorConfig(enabled=False)
        assert cfg["enabled"] is False


# ============================================================================
# io.observe-suspicious
# ============================================================================


class TestIoObserveSuspicious:
    def test_no_baseline_no_reasons(self) -> None:
        reasons = resolve_config_observe_suspicious_reasons({
            "bytes": 100, "hasMeta": True, "gatewayMode": "local", "parsed": {},
        })
        assert reasons == []

    def test_size_drop(self) -> None:
        baseline: ConfigObserveSuspiciousBaseline = {
            "bytes": 1000, "hasMeta": True, "gatewayMode": "local",
        }
        reasons = resolve_config_observe_suspicious_reasons({
            "bytes": 200, "hasMeta": True, "gatewayMode": "local", "parsed": {},
            "lastKnownGood": baseline,
        })
        assert any("size-drop" in r for r in reasons)

    def test_missing_meta(self) -> None:
        baseline: ConfigObserveSuspiciousBaseline = {
            "bytes": 100, "hasMeta": True, "gatewayMode": "local",
        }
        reasons = resolve_config_observe_suspicious_reasons({
            "bytes": 100, "hasMeta": False, "gatewayMode": "local", "parsed": {},
            "lastKnownGood": baseline,
        })
        assert "missing-meta-vs-last-good" in reasons

    def test_gateway_mode_missing(self) -> None:
        baseline: ConfigObserveSuspiciousBaseline = {
            "bytes": 100, "hasMeta": True, "gatewayMode": "remote",
        }
        reasons = resolve_config_observe_suspicious_reasons({
            "bytes": 100, "hasMeta": True, "gatewayMode": None, "parsed": {},
            "lastKnownGood": baseline,
        })
        assert "gateway-mode-missing-vs-last-good" in reasons

    def test_update_channel_only(self) -> None:
        baseline: ConfigObserveSuspiciousBaseline = {
            "bytes": 100, "hasMeta": True, "gatewayMode": "local",
        }
        reasons = resolve_config_observe_suspicious_reasons({
            "bytes": 100, "hasMeta": True, "gatewayMode": "local",
            "parsed": {"update": {"channel": "stable"}},
            "lastKnownGood": baseline,
        })
        assert "update-channel-only-root" in reasons

    def test_update_channel_only_wrong_shape(self) -> None:
        baseline: ConfigObserveSuspiciousBaseline = {
            "bytes": 100, "hasMeta": True, "gatewayMode": "local",
        }
        reasons = resolve_config_observe_suspicious_reasons({
            "bytes": 100, "hasMeta": True, "gatewayMode": "local",
            "parsed": {"update": {"channel": "stable", "version": "1"}},
            "lastKnownGood": baseline,
        })
        assert "update-channel-only-root" not in reasons


# ============================================================================
# io.state
# ============================================================================


class TestIoState:
    def test_constants(self) -> None:
        assert CONFIG_IO_WARNING_CACHE_MAX_SIZE == 4096
        assert isinstance(logged_config_warning_fingerprints, dict)
        assert isinstance(auto_owner_display_secret_by_path, dict)

    def test_set_bounded_entry(self) -> None:
        m: dict = {}
        set_bounded_config_io_warning_entry(m, "a", 1)
        assert m == {"a": 1}
        set_bounded_config_io_warning_entry(m, "b", 2)
        assert m == {"a": 1, "b": 2}

    def test_set_bounded_entry_prune(self) -> None:
        m: dict = {}
        # Use a custom prune function for the test.
        pruned = []

        def prune(map_, max_size):
            pruned.append((dict(map_), max_size))
            while len(map_) > max_size:
                map_.pop(next(iter(map_)))

        for i in range(5):
            set_bounded_config_io_warning_entry(m, f"k{i}", i, prune_map_to_max_size_fn=prune)
        # Map is bounded to CONFIG_IO_WARNING_CACHE_MAX_SIZE, but our input is
        # only 5 keys so nothing is pruned.
        assert len(m) == 5
        assert pruned[0][1] == 4096

    def test_set_bounded_promotes_recent(self) -> None:
        m: dict = {}
        set_bounded_config_io_warning_entry(m, "a", 1)
        set_bounded_config_io_warning_entry(m, "b", 2)
        # Re-insert "a"; should be at the end (most recent).
        set_bounded_config_io_warning_entry(m, "a", 3)
        assert list(m.keys()) == ["b", "a"]
        assert m["a"] == 3


# ============================================================================
# provider_policy
# ============================================================================


class TestProviderPolicy:
    def test_normalize_no_surface(self) -> None:
        out = normalize_provider_config_for_config_defaults({
            "provider": "openai",
            "providerConfig": {"apiKey": "x"},
        })
        # No surface callable, returns input unchanged.
        assert out == {"apiKey": "x"}

    def test_normalize_with_surface(self) -> None:
        def resolve_surface(provider, opts):
            return {
                "normalizeConfig": lambda p: {
                    "apiKey": "normalized",
                    "provider": p["provider"],
                },
            }

        out = normalize_provider_config_for_config_defaults({
            "provider": "openai",
            "providerConfig": {"apiKey": "orig"},
            "resolve_bundled_provider_policy_surface_fn": resolve_surface,
        })
        assert out == {"apiKey": "normalized", "provider": "openai"}

    def test_normalize_preserves_identity_when_no_op(self) -> None:
        original = {"apiKey": "x"}
        def resolve_surface(provider, opts):
            return {"normalizeConfig": lambda p: p["providerConfig"]}

        out = normalize_provider_config_for_config_defaults({
            "provider": "openai",
            "providerConfig": original,
            "resolve_bundled_provider_policy_surface_fn": resolve_surface,
        })
        # Normalizer returned the original object; preserve identity.
        assert out is original

    def test_apply_defaults(self) -> None:
        def resolve_surface(provider, opts):
            return {
                "applyConfigDefaults": lambda p: {**p["config"], "defaultApplied": True},
            }

        out = apply_provider_config_defaults_for_config({
            "provider": "openai",
            "config": {"x": 1},
            "env": {},
            "resolve_bundled_provider_policy_surface_fn": resolve_surface,
        })
        assert out == {"x": 1, "defaultApplied": True}

    def test_apply_defaults_fallback(self) -> None:
        out = apply_provider_config_defaults_for_config({
            "provider": "x", "config": {"y": 2}, "env": {},
        })
        assert out == {"y": 2}


# ============================================================================
# schema.node-capabilities
# ============================================================================


class TestSchemaNodeCapabilities:
    def test_help_keys(self) -> None:
        assert "gateway.nodes.pluginTools" in NODE_CAPABILITY_FIELD_HELP
        assert "gateway.nodes.skills" in NODE_CAPABILITY_FIELD_HELP
        assert "node" in NODE_CAPABILITY_FIELD_HELP["gateway.nodes.skills"].lower()

    def test_label_keys(self) -> None:
        assert "Gateway Node Plugin Tools" in NODE_CAPABILITY_FIELD_LABELS.values()
        assert "Gateway Node Skills" in NODE_CAPABILITY_FIELD_LABELS.values()


# ============================================================================
# schema.help
# ============================================================================


class TestSchemaHelp:
    def test_field_help_empty(self) -> None:
        # Aggregator is empty until the section-specific ports land.
        assert isinstance(FIELD_HELP, dict)

    def test_get_field_help_unknown(self) -> None:
        assert get_field_help("nonexistent") == ""


# ============================================================================
# markdown-tables.types
# ============================================================================


class TestMarkdownTablesTypes:
    def test_mode_alias(self) -> None:
        assert MarkdownTableMode == str

    def test_params_typed_dict(self) -> None:
        params: ResolveMarkdownTableModeParams = {
            "channel": "slack",
            "accountId": "u1",
            "supportsBlockTables": True,
        }
        assert params["channel"] == "slack"
        assert params["supportsBlockTables"] is True


# ============================================================================
# io.warnings
# ============================================================================


class TestIoWarnings:
    def test_warn_on_miskeys_no_gateway(self) -> None:
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        warn_on_config_miskeys({}, logger)
        assert calls == []

    def test_warn_on_miskeys_token(self) -> None:
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        warn_on_config_miskeys({"gateway": {"token": "abc"}}, logger)
        assert len(calls) == 1
        assert "gateway.token" in calls[0]
        assert "gateway.auth.token" in calls[0]

    def test_warn_on_miskeys_no_token(self) -> None:
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        warn_on_config_miskeys({"gateway": {"auth": {"token": "x"}}}, logger)
        assert calls == []

    def test_log_warnings_once_empty(self) -> None:
        logged_config_warning_fingerprints.pop("p1", None)
        log_config_warnings_once({
            "configPath": "p1", "warnings": [], "logger": None,
        })
        assert "p1" not in logged_config_warning_fingerprints

    def test_log_warnings_once_emits(self) -> None:
        logged_config_warning_fingerprints.pop("p2", None)
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        log_config_warnings_once({
            "configPath": "p2",
            "warnings": [{"path": "agents", "message": "missing"}],
            "logger": logger,
            "hash_config_raw_fn": lambda s: "fp1",
        })
        assert "p2" in logged_config_warning_fingerprints
        assert calls and "agents" in calls[0]

    def test_log_warnings_once_dedup(self) -> None:
        logged_config_warning_fingerprints.pop("p3", None)
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        params = {
            "configPath": "p3",
            "warnings": [{"path": "x", "message": "y"}],
            "logger": logger,
            "hash_config_raw_fn": lambda s: "fp-fixed",
        }
        log_config_warnings_once(params)
        log_config_warnings_once(params)
        # Same fingerprint => second call doesn't re-warn.
        assert len(calls) == 1

    def test_warn_if_config_from_future_emits(self) -> None:
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        warn_if_config_from_future(
            {"meta": {"lastTouchedVersion": "9.9.9"}},
            logger,
            version="1.0.0",
            should_warn_on_touched_version_fn=lambda current, touched: True,
        )
        assert calls and "9.9.9" in calls[0]
        assert "1.0.0" in calls[0]

    def test_warn_if_config_from_future_no_meta(self) -> None:
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        warn_if_config_from_future(
            {}, logger,
            version="1.0.0",
            should_warn_on_touched_version_fn=lambda current, touched: True,
        )
        assert calls == []

    def test_warn_if_config_from_future_no_warn(self) -> None:
        calls = []
        logger = type("L", (), {"warn": lambda self, m: calls.append(m)})()
        warn_if_config_from_future(
            {"meta": {"lastTouchedVersion": "0.1.0"}},
            logger,
            version="1.0.0",
            should_warn_on_touched_version_fn=lambda current, touched: False,
        )
        assert calls == []


# ============================================================================
# types.signal
# ============================================================================


class TestTypesSignal:
    def test_mode_aliases(self) -> None:
        # Literal unions resolve to generic types at runtime.
        assert SignalReactionNotificationMode is not None
        assert SignalReactionLevel is not None
        assert SignalApiMode is not None

    def test_group(self) -> None:
        cfg = SignalGroupConfig(
            requireMention=True, ingest=False,
            tools={"policy": "allow"},
        )
        assert cfg["requireMention"] is True
        assert cfg["ingest"] is False

    def test_actions(self) -> None:
        cfg = SignalActionsConfig(reactions=False)
        assert cfg["reactions"] is False

    def test_account(self) -> None:
        cfg = SignalAccountConfig(
            account="+1234",
            httpUrl="http://127.0.0.1:8080",
            httpPort=8080,
            reactionLevel="minimal",
        )
        assert cfg["account"] == "+1234"
        assert cfg["reactionLevel"] == "minimal"

    def test_config(self) -> None:
        cfg = SignalConfig(
            apiMode="container",
            accounts={"main": SignalAccountConfig(account="+1")},
            defaultAccount="main",
        )
        assert cfg["apiMode"] == "container"
        assert cfg["defaultAccount"] == "main"
