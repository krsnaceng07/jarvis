"""Tests for Phase 8.2h — src/config/ small file batch (11 files).

Covers:
- types, types_googlechat, types_imessage, types_whatsapp, types_channels
- runtime_group_policy, model_provider_config, io_types
- codex_plugin_diagnostics, talk
"""
from __future__ import annotations

from src.config.types_googlechat import (
    GoogleChatAccountConfig,
    GoogleChatActionConfig,
    GoogleChatAudienceType,
    GoogleChatConfig,
    GoogleChatDmConfig,
    GoogleChatGroupConfig,
    GoogleChatTypingIndicator,
)
from src.config.types_imessage import (
    IMessageAccountConfig,
    IMessageActionConfig,
    IMessageCatchupConfig,
    IMessageConfig,
    IMessageGroupConfig,
    IMessageReactionNotificationMode,
    IMessageSendTransport,
    IMessageService,
)
from src.config.types_whatsapp import (
    WhatsAppAccountConfig,
    WhatsAppAckGroupMode,
    WhatsAppAckReactionConfig,
    WhatsAppActionConfig,
    WhatsAppConfig,
    WhatsAppDirectConfig,
    WhatsAppGroupConfig,
    WhatsAppPluginHooksConfig,
    WhatsAppReactionLevel,
)
from src.config.types_channels import (
    ChannelDefaultsConfig,
    ChannelModelByChannelConfig,
    ChannelsConfig,
    ContextVisibilityMode,
    ExtensionAccountConfig,
    ExtensionChannelConfig,
    ExtensionNestedPolicyConfig,
    GroupPolicy,
    OpenWorldChannelConfig,
    ThreadBindingsConfig,
)
from src.config.runtime_group_policy import (
    GROUP_POLICY_BLOCKED_LABEL,
    MAX_WARNED_MISSING_PROVIDER_GROUP_POLICY_KEYS,
    resolve_allowlist_provider_runtime_group_policy,
    resolve_default_group_policy,
    resolve_open_provider_runtime_group_policy,
    warn_missing_provider_group_policy_fallback_once,
)
from src.config.model_provider_config import (
    resolve_merged_model_provider_config,
    resolve_merged_model_provider_entry,
    resolve_merged_model_provider_models,
)
from src.config.io_types import (
    BestEffortConfigSnapshot,
    ConfigIoDeps,
    ConfigRuntimeRefreshError,
    ConfigSnapshotReadOptions,
    ConfigWriteAuditOrigin,
    ConfigWriteOptions,
    ConfigWriteResult,
    InternalConfigWriteResult,
    NormalizedConfigIoDeps,
    ParseConfigJson5Result,
    ReadConfigFileSnapshotForWriteResult,
    ShippedPluginInstallConfigReadMigration,
    ShippedPluginInstallConfigWriteMigration,
    config_write_post_commit_rollback,
)
from src.config.codex_plugin_diagnostics import (
    CODEX_PLUGIN_ID,
    OPENAI_PROVIDER_ID,
    should_suppress_missing_codex_plugin_diagnostics,
)
from src.config.talk import (
    normalize_talk_config,
    normalize_talk_section,
    resolve_active_talk_provider_config,
)


# ============================================================================
# types_googlechat
# ============================================================================


class TestTypesGoogleChat:
    def test_aliases(self) -> None:
        assert GoogleChatAudienceType is not None
        assert GoogleChatTypingIndicator is not None

    def test_dm(self) -> None:
        cfg = GoogleChatDmConfig(enabled=True, policy="pairing", allowFrom=["a@b.com"])
        assert cfg["policy"] == "pairing"

    def test_group(self) -> None:
        cfg = GoogleChatGroupConfig(requireMention=True, users=["u1"])
        assert cfg["users"] == ["u1"]

    def test_action(self) -> None:
        cfg = GoogleChatActionConfig(reactions=False)
        assert cfg["reactions"] is False

    def test_account(self) -> None:
        cfg = GoogleChatAccountConfig(
            name="main", serviceAccountFile="/path/sa.json", audienceType="app-url",
        )
        assert cfg["audienceType"] == "app-url"

    def test_config(self) -> None:
        cfg = GoogleChatConfig(accounts={"main": GoogleChatAccountConfig()}, defaultAccount="main")
        assert cfg["defaultAccount"] == "main"


# ============================================================================
# types_imessage
# ============================================================================


class TestTypesIMessage:
    def test_aliases(self) -> None:
        assert IMessageService is not None
        assert IMessageSendTransport is not None
        assert IMessageReactionNotificationMode is not None

    def test_action(self) -> None:
        cfg = IMessageActionConfig(reactions=True, polls=True)
        assert cfg["polls"] is True

    def test_group(self) -> None:
        cfg = IMessageGroupConfig(requireMention=True, systemPrompt="hi")
        assert cfg["systemPrompt"] == "hi"

    def test_catchup(self) -> None:
        cfg = IMessageCatchupConfig(enabled=True, maxAgeMinutes=120, perRunLimit=50)
        assert cfg["maxAgeMinutes"] == 120

    def test_account(self) -> None:
        cfg = IMessageAccountConfig(
            enabled=True, service="imessage", sendTransport="bridge",
            coalesceSameSenderDms=True, reactionNotifications="own",
        )
        assert cfg["coalesceSameSenderDms"] is True

    def test_config(self) -> None:
        cfg = IMessageConfig(accounts={"u": IMessageAccountConfig()}, defaultAccount="u")
        assert cfg["defaultAccount"] == "u"


# ============================================================================
# types_whatsapp
# ============================================================================


class TestTypesWhatsApp:
    def test_aliases(self) -> None:
        assert WhatsAppReactionLevel is not None
        assert WhatsAppAckGroupMode is not None

    def test_action(self) -> None:
        cfg = WhatsAppActionConfig(reactions=True, calls=False)
        assert cfg["calls"] is False

    def test_group(self) -> None:
        cfg = WhatsAppGroupConfig(requireMention=True, systemPrompt="hi")
        assert cfg["systemPrompt"] == "hi"

    def test_direct(self) -> None:
        cfg = WhatsAppDirectConfig(systemPrompt="hi")
        assert cfg["systemPrompt"] == "hi"

    def test_ack_reaction(self) -> None:
        cfg = WhatsAppAckReactionConfig(emoji="👀", direct=True, group="always")
        assert cfg["group"] == "always"

    def test_plugin_hooks(self) -> None:
        cfg = WhatsAppPluginHooksConfig(messageReceived=True)
        assert cfg["messageReceived"] is True

    def test_account(self) -> None:
        cfg = WhatsAppAccountConfig(
            enabled=True, authDir="/path", selfChatMode=False,
        )
        assert cfg["authDir"] == "/path"

    def test_config(self) -> None:
        cfg = WhatsAppConfig(accounts={"u": WhatsAppAccountConfig()}, defaultAccount="u")
        assert cfg["defaultAccount"] == "u"


# ============================================================================
# types_channels
# ============================================================================


class TestTypesChannels:
    def test_aliases(self) -> None:
        assert GroupPolicy is not None
        assert ContextVisibilityMode is not None

    def test_defaults(self) -> None:
        cfg = ChannelDefaultsConfig(groupPolicy="allowlist", contextVisibility="all")
        assert cfg["groupPolicy"] == "allowlist"

    def test_model_by_channel(self) -> None:
        cfg: ChannelModelByChannelConfig = {
            "discord": {"channel-id": "openai/gpt-4"},
        }
        assert cfg["discord"]["channel-id"] == "openai/gpt-4"

    def test_nested_policy(self) -> None:
        cfg = ExtensionNestedPolicyConfig(policy="allowlist", allowFrom=["a"])
        assert cfg["allowFrom"] == ["a"]

    def test_account(self) -> None:
        cfg = ExtensionAccountConfig(defaultTo="u1", dmPolicy="pairing")
        assert cfg["defaultTo"] == "u1"

    def test_thread_bindings(self) -> None:
        cfg = ThreadBindingsConfig(enabled=True, spawnSessions=True, defaultSpawnContext="fork")
        assert cfg["defaultSpawnContext"] == "fork"

    def test_channel(self) -> None:
        cfg = ExtensionChannelConfig(
            enabled=True,
            threadBindings=ThreadBindingsConfig(enabled=True),
        )
        assert cfg["threadBindings"]["enabled"] is True

    def test_open_world(self) -> None:
        cfg: OpenWorldChannelConfig = {"custom": "x"}
        assert cfg["custom"] == "x"

    def test_top_level(self) -> None:
        cfg = ChannelsConfig(
            defaults=ChannelDefaultsConfig(),
            discord={"enabled": True},
        )
        assert cfg["discord"]["enabled"] is True


# ============================================================================
# runtime_group_policy
# ============================================================================


class TestRuntimeGroupPolicy:
    def test_constants(self) -> None:
        assert MAX_WARNED_MISSING_PROVIDER_GROUP_POLICY_KEYS == 4096
        assert "group" in GROUP_POLICY_BLOCKED_LABEL
        assert "channel" in GROUP_POLICY_BLOCKED_LABEL

    def test_resolve_default_group_policy(self) -> None:
        cfg = {"channels": {"defaults": {"groupPolicy": "allowlist"}}}
        assert resolve_default_group_policy(cfg) == "allowlist"

    def test_resolve_default_group_policy_no_value(self) -> None:
        assert resolve_default_group_policy({}) is None
        assert resolve_default_group_policy({"channels": {}}) is None
        assert resolve_default_group_policy({"channels": {"defaults": {}}}) is None
        assert resolve_default_group_policy(None) is None  # type: ignore[arg-type]

    def test_resolve_open_provider_present_uses_explicit(self) -> None:
        out = resolve_open_provider_runtime_group_policy({
            "providerConfigPresent": True,
            "groupPolicy": "open",
        })
        assert out["groupPolicy"] == "open"
        assert out["providerMissingFallbackApplied"] is False

    def test_resolve_open_provider_present_no_explicit(self) -> None:
        out = resolve_open_provider_runtime_group_policy({
            "providerConfigPresent": True,
            "defaultGroupPolicy": "open",
        })
        assert out["groupPolicy"] == "open"
        assert out["providerMissingFallbackApplied"] is False

    def test_resolve_open_provider_missing_uses_allowlist(self) -> None:
        out = resolve_open_provider_runtime_group_policy({
            "providerConfigPresent": False,
        })
        assert out["groupPolicy"] == "allowlist"
        assert out["providerMissingFallbackApplied"] is True

    def test_resolve_allowlist_provider_with_explicit_uses_explicit(self) -> None:
        # The OpenClaw source only applies configuredFallbackPolicy when no
        # explicit groupPolicy is provided. With groupPolicy="open", the
        # explicit value wins even under the allowlist provider preset.
        out = resolve_allowlist_provider_runtime_group_policy({
            "providerConfigPresent": True,
            "groupPolicy": "open",
        })
        assert out["groupPolicy"] == "open"
        assert out["providerMissingFallbackApplied"] is False

    def test_resolve_allowlist_provider_no_explicit(self) -> None:
        out = resolve_allowlist_provider_runtime_group_policy({
            "providerConfigPresent": True,
        })
        # No explicit, no default, configuredFallbackPolicy = "allowlist".
        assert out["groupPolicy"] == "allowlist"
        assert out["providerMissingFallbackApplied"] is False

    def test_warn_emits_when_applied(self) -> None:
        calls = []
        out = warn_missing_provider_group_policy_fallback_once({
            "providerMissingFallbackApplied": True,
            "providerKey": "telegram",
            "accountId": "u1",
            "log": lambda m: calls.append(m),
        })
        assert out is True
        assert calls and "telegram" in calls[0]
        assert "allowlist" in calls[0]

    def test_warn_no_op_when_not_applied(self) -> None:
        calls = []
        out = warn_missing_provider_group_policy_fallback_once({
            "providerMissingFallbackApplied": False,
            "providerKey": "telegram",
            "log": lambda m: calls.append(m),
        })
        assert out is False
        assert calls == []


# ============================================================================
# model_provider_config
# ============================================================================


class TestModelProviderConfig:
    def test_resolve_models(self) -> None:
        def normalize(mid):
            return mid.lower().strip() or None

        out = resolve_merged_model_provider_models(
            {"models": [{"id": "openai/gpt-4", "v": 1}]},
            normalize_model_id=normalize,
        )
        assert "openai/gpt-4" in out
        assert out["openai/gpt-4"]["v"] == 1

    def test_resolve_models_empty(self) -> None:
        assert resolve_merged_model_provider_models({}) == {}
        assert resolve_merged_model_provider_models({"models": []}) == {}

    def test_resolve_models_no_normalize(self) -> None:
        # Without normalize fn, returns empty.
        out = resolve_merged_model_provider_models({"models": [{"id": "x"}]})
        assert out == {}

    def test_resolve_entry_basic(self) -> None:
        cfg = {
            "models": {
                "providers": {
                    "openai": {"apiKey": "x", "models": [{"id": "gpt-4"}]},
                },
            },
        }
        out = resolve_merged_model_provider_entry(cfg, "openai")
        assert out is not None
        assert out["providerKey"] == "openai"
        assert out["providerConfig"]["apiKey"] == "x"

    def test_resolve_entry_case_insensitive(self) -> None:
        cfg = {"models": {"providers": {"OpenAI": {"x": 1}}}}
        out = resolve_merged_model_provider_entry(cfg, "openai")
        assert out is not None
        assert out["providerKey"] == "OpenAI"

    def test_resolve_entry_not_found(self) -> None:
        cfg = {"models": {"providers": {"openai": {}}}}
        assert resolve_merged_model_provider_entry(cfg, "anthropic") is None

    def test_resolve_entry_invalid(self) -> None:
        assert resolve_merged_model_provider_entry(None, "openai") is None  # type: ignore[arg-type]
        assert resolve_merged_model_provider_entry({}, "") is None
        assert resolve_merged_model_provider_entry({}, 123) is None  # type: ignore[arg-type]

    def test_resolve_merged_config_merges_later(self) -> None:
        # Duplicate provider entries are folded at JSON parse time, so the
        # canonical shape is a single merged object.
        cfg = {
            "models": {
                "providers": {
                    "openai": {"apiKey": "second", "models": [{"id": "gpt-4"}]},
                },
            },
        }
        out = resolve_merged_model_provider_config(cfg, "openai")
        assert out is not None
        assert out["apiKey"] == "second"
        assert out["models"] == [{"id": "gpt-4"}]

    def test_resolve_merged_config_not_found(self) -> None:
        cfg = {"models": {"providers": {"openai": {}}}}
        assert resolve_merged_model_provider_config(cfg, "anthropic") is None


# ============================================================================
# io_types
# ============================================================================


class TestIoTypes:
    def test_parse_result_alias(self) -> None:
        assert ParseConfigJson5Result is dict

    def test_write_result(self) -> None:
        r: ConfigWriteResult = {"persistedHash": "abc", "persistedConfig": {}}
        assert r["persistedHash"] == "abc"

    def test_internal_write_result(self) -> None:
        r: InternalConfigWriteResult = {
            "persistedHash": "abc",
            "persistedConfig": {},
            "configWritePostCommitRollback": lambda: None,
        }
        assert callable(r["configWritePostCommitRollback"])

    def test_audit_origin_alias(self) -> None:
        assert ConfigWriteAuditOrigin is not None

    def test_write_options(self) -> None:
        opts: ConfigWriteOptions = {
            "auditOrigin": "cli",
            "allowDestructiveWrite": True,
        }
        assert opts["auditOrigin"] == "cli"

    def test_read_for_write_result(self) -> None:
        r: ReadConfigFileSnapshotForWriteResult = {
            "snapshot": {"valid": True},
            "writeOptions": {"auditOrigin": "doctor"},
        }
        assert r["snapshot"]["valid"] is True

    def test_runtime_refresh_error(self) -> None:
        err = ConfigRuntimeRefreshError("boom")
        assert err.name == "ConfigRuntimeRefreshError"
        assert "boom" in str(err)

    def test_runtime_refresh_error_with_cause(self) -> None:
        cause = ValueError("inner")
        err = ConfigRuntimeRefreshError("outer", cause=cause)
        assert err.__cause__ is cause

    def test_io_deps(self) -> None:
        deps: ConfigIoDeps = {"configPath": "/x", "env": {}}
        assert deps["configPath"] == "/x"

    def test_normalized_io_deps(self) -> None:
        deps: NormalizedConfigIoDeps = {"configPath": "/x", "logger": None}
        assert deps["configPath"] == "/x"

    def test_snapshot_read_options(self) -> None:
        opts: ConfigSnapshotReadOptions = {
            "observe": True,
            "isolateEnv": True,
        }
        assert opts["isolateEnv"] is True

    def test_best_effort_snapshot(self) -> None:
        s: BestEffortConfigSnapshot = {"config": {"x": 1}, "sourceConfig": {"x": 1}}
        assert s["config"]["x"] == 1

    def test_shipped_migrations_aliases(self) -> None:
        assert ShippedPluginInstallConfigWriteMigration is dict
        assert ShippedPluginInstallConfigReadMigration is dict

    def test_post_commit_symbol(self) -> None:
        # The symbol is exposed as a string sentinel for dict-keyed use.
        assert config_write_post_commit_rollback == "configWritePostCommitRollback"


# ============================================================================
# codex_plugin_diagnostics
# ============================================================================


class TestCodexPluginDiagnostics:
    def test_constants(self) -> None:
        assert CODEX_PLUGIN_ID == "codex"
        assert OPENAI_PROVIDER_ID == "openai"

    def test_no_cfg_returns_true(self) -> None:
        assert should_suppress_missing_codex_plugin_diagnostics(None) is True
        # Empty config: the implicit default OpenAI route has no facts, so
        # route resolution is indeterminate with a Codex default
        # (provider-policy-api.ts indeterminate branch). The missing-codex
        # diagnostic is therefore NOT suppressed.
        assert should_suppress_missing_codex_plugin_diagnostics({}) is False

    def test_disabled_entry(self) -> None:
        cfg = {"plugins": {"entries": {"codex": {"enabled": False}}}}
        # Disabled entry is an explicit opt-out — the missing-plugin
        # diagnostic stays suppressed; the doctor reports selected-route
        # conflicts separately (shouldSuppressMissingCodexPluginDiagnostics
        # returns entryEnabled === false).
        assert should_suppress_missing_codex_plugin_diagnostics(cfg) is True

    def test_enabled_entry_short_circuits(self) -> None:
        cfg = {"plugins": {"entries": {"codex": {"enabled": True}}}}
        # Entry explicitly enabled => don't suppress.
        assert should_suppress_missing_codex_plugin_diagnostics(cfg) is False


# ============================================================================
# talk
# ============================================================================


class TestTalk:
    def test_normalize_section_non_dict(self) -> None:
        assert normalize_talk_section(None) is None
        assert normalize_talk_section("x") is None
        assert normalize_talk_section([]) is None

    def test_normalize_section_basic(self) -> None:
        out = normalize_talk_section({
            "speechLocale": "en-US",
            "interruptOnSpeech": True,
        })
        assert out is not None
        assert out["speechLocale"] == "en-US"
        assert out["interruptOnSpeech"] is True

    def test_normalize_section_consult_thinking(self) -> None:
        out = normalize_talk_section({
            "consultThinkingLevel": "low",
        })
        assert out is not None
        assert out["consultThinkingLevel"] == "low"

    def test_normalize_section_fast_mode(self) -> None:
        out = normalize_talk_section({"consultFastMode": True})
        assert out is not None
        assert out["consultFastMode"] is True

    def test_normalize_section_silence_timeout(self) -> None:
        out = normalize_talk_section({"silenceTimeoutMs": 700})
        assert out is not None
        assert out["silenceTimeoutMs"] == 700

    def test_normalize_section_rejects_invalid_silence(self) -> None:
        out = normalize_talk_section({"silenceTimeoutMs": -1})
        # -1 not positive => entire section is empty (no recognized fields).
        assert out is None

    def test_normalize_section_preserves_providers(self) -> None:
        out = normalize_talk_section({
            "providers": {"openai": {"apiKey": "x"}},
        })
        assert out is not None
        assert "providers" in out

    def test_normalize_config_no_talk(self) -> None:
        cfg = {"agents": {}}
        out = normalize_talk_config(cfg)
        assert out is cfg

    def test_normalize_config_with_talk(self) -> None:
        cfg = {"talk": {"speechLocale": "en"}}
        out = normalize_talk_config(cfg)
        assert out["talk"]["speechLocale"] == "en"

    def test_resolve_active_no_talk(self) -> None:
        assert resolve_active_talk_provider_config(None) is None
        assert resolve_active_talk_provider_config({}) is None

    def test_resolve_active_explicit_provider(self) -> None:
        out = resolve_active_talk_provider_config({
            "provider": "openai",
            "providers": {"openai": {"apiKey": "x"}},
        })
        assert out is not None
        assert out["provider"] == "openai"
        assert out["config"]["apiKey"] == "x"

    def test_resolve_active_single_provider(self) -> None:
        out = resolve_active_talk_provider_config({
            "providers": {"openai": {"apiKey": "x"}},
        })
        assert out is not None
        assert out["provider"] == "openai"

    def test_resolve_active_ambiguous_providers(self) -> None:
        out = resolve_active_talk_provider_config({
            "providers": {"a": {}, "b": {}},
        })
        assert out is None

    def test_resolve_active_provider_not_in_list(self) -> None:
        # Provider named but not in providers list.
        out = resolve_active_talk_provider_config({
            "provider": "openai",
            "providers": {"elevenlabs": {}},
        })
        assert out is None
