"""Tests for Phase 8.2m — Layer 4 src/config/ small files.

Covers:
- src/config/types_secrets.py (SecretRef, SecretInput, coercion helpers, error types)
- src/config/types_models.py (MODEL_APIS, ModelApi, ModelDefinitionConfig, etc.)
- src/config/types_slack.py (SlackConfig family, streaming/exec/types)
- src/config/types_telegram.py (TelegramConfig family, streaming/error modes)
- src/config/types_base.py (ReplyMode, SessionConfig, LoggingConfig, etc.)
- src/config/types_discord.py (DiscordConfig family, voice/stream/types)
- src/config/types_openclaw.py (OpenClawConfig, security, wizard, etc.)
- src/config/read_best_effort_config_runtime.py (facade re-exports)
"""
from __future__ import annotations

import pytest

from src.config import (
    read_best_effort_config_runtime,
    types_base,
    types_discord,
    types_models,
    types_openclaw,
    types_secrets,
    types_slack,
    types_telegram,
)


# ---------------------------------------------------------------------------
# types_secrets
# ---------------------------------------------------------------------------


class TestTypesSecrets:
    def test_imports(self):
        assert types_secrets is not None
        for name in (
            "SecretRefSource", "SecretRef", "SecretInput",
            "DEFAULT_SECRET_PROVIDER_ALIAS", "ENV_SECRET_REF_ID_RE",
            "is_valid_env_secret_ref_id", "is_secret_ref",
            "coerce_secret_ref", "has_configured_secret_input",
            "normalize_secret_input_string",
            "UnresolvedSecretInputError",
            "is_unresolved_secret_input_error",
            "assert_secret_input_resolved",
            "resolve_secret_input_string",
            "normalize_resolved_secret_input_string",
            "resolve_secret_input_ref",
            "SecretsConfig",
        ):
            assert name in types_secrets.__all__, f"missing: {name}"

    def test_secret_ref_source_values(self):
        import typing
        assert typing.get_args(types_secrets.SecretRefSource) == ("env", "file", "exec")

    def test_default_secret_provider_alias(self):
        assert types_secrets.DEFAULT_SECRET_PROVIDER_ALIAS == "default"

    def test_env_secret_ref_id_re_valid(self):
        import re
        assert re.match(types_secrets.ENV_SECRET_REF_ID_RE, "OPENAI_API_KEY")
        assert re.match(types_secrets.ENV_SECRET_REF_ID_RE, "A")
        assert re.match(types_secrets.ENV_SECRET_REF_ID_RE, "A1_B2_C3")
        # Should NOT match lowercase
        assert not re.match(types_secrets.ENV_SECRET_REF_ID_RE, "openai_api_key")
        # Should NOT match starting with digit
        assert not re.match(types_secrets.ENV_SECRET_REF_ID_RE, "1FOO")

    def test_is_valid_env_secret_ref_id(self):
        assert types_secrets.is_valid_env_secret_ref_id("OPENAI_API_KEY") is True
        assert types_secrets.is_valid_env_secret_ref_id("lowercase") is False
        assert types_secrets.is_valid_env_secret_ref_id("") is False

    def test_is_secret_ref_canonical(self):
        ref = {"source": "env", "provider": "default", "id": "FOO"}
        assert types_secrets.is_secret_ref(ref) is True
        # Wrong source
        assert types_secrets.is_secret_ref({"source": "x", "provider": "p", "id": "i"}) is False
        # Missing provider
        assert types_secrets.is_secret_ref({"source": "env", "id": "FOO"}) is False
        # Wrong number of keys
        assert types_secrets.is_secret_ref({"source": "env", "provider": "p"}) is False
        # Non-record
        assert types_secrets.is_secret_ref("string") is False
        assert types_secrets.is_secret_ref(None) is False
        assert types_secrets.is_secret_ref([1, 2, 3]) is False

    def test_parse_env_template_secret_ref(self):
        # ${NAME} form
        ref = types_secrets.parse_env_template_secret_ref("${OPENAI_API_KEY}")
        assert ref == {"source": "env", "provider": "default", "id": "OPENAI_API_KEY"}
        # $NAME form
        ref = types_secrets.parse_env_template_secret_ref("$FOO_BAR")
        assert ref == {"source": "env", "provider": "default", "id": "FOO_BAR"}
        # Non-string
        assert types_secrets.parse_env_template_secret_ref(123) is None
        # Invalid (lowercase)
        assert types_secrets.parse_env_template_secret_ref("$foo") is None
        # With custom provider
        ref = types_secrets.parse_env_template_secret_ref("$FOO", provider="vault")
        assert ref["provider"] == "vault"

    def test_parse_legacy_secret_ref_env_marker(self):
        ref = types_secrets.parse_legacy_secret_ref_env_marker("secretref-env:FOO")
        assert ref == {"source": "env", "provider": "default", "id": "FOO"}
        ref = types_secrets.parse_legacy_secret_ref_env_marker("__env__:BAR")
        assert ref == {"source": "env", "provider": "default", "id": "BAR"}
        # Invalid prefix
        assert types_secrets.parse_legacy_secret_ref_env_marker("foo:BAR") is None
        # Invalid id (lowercase)
        assert types_secrets.parse_legacy_secret_ref_env_marker("secretref-env:bar") is None
        # Non-string
        assert types_secrets.parse_legacy_secret_ref_env_marker(None) is None

    def test_coerce_secret_ref_canonical(self):
        ref = {"source": "env", "provider": "p", "id": "FOO"}
        assert types_secrets.coerce_secret_ref(ref) == ref

    def test_coerce_secret_ref_legacy(self):
        ref = types_secrets.coerce_secret_ref("secretref-env:FOO")
        assert ref is not None
        assert ref == {"source": "env", "provider": "default", "id": "FOO"}

    def test_coerce_secret_ref_template(self):
        ref = types_secrets.coerce_secret_ref("$FOO")
        assert ref is not None
        assert ref == {"source": "env", "provider": "default", "id": "FOO"}

    def test_coerce_secret_ref_legacy_without_provider(self):
        ref = types_secrets.coerce_secret_ref({"source": "env", "id": "FOO"})
        assert ref == {"source": "env", "provider": "default", "id": "FOO"}
        # With defaults
        ref = types_secrets.coerce_secret_ref(
            {"source": "file", "id": "FOO"}, defaults={"file": "vault"}
        )
        assert ref == {"source": "file", "provider": "vault", "id": "FOO"}
        # Exec source with defaults
        ref = types_secrets.coerce_secret_ref(
            {"source": "exec", "id": "FOO"}, defaults={"exec": "1password"}
        )
        assert ref == {"source": "exec", "provider": "1password", "id": "FOO"}

    def test_coerce_secret_ref_returns_none(self):
        assert types_secrets.coerce_secret_ref("just a string") is None
        assert types_secrets.coerce_secret_ref(123) is None
        assert types_secrets.coerce_secret_ref(None) is None

    def test_has_configured_secret_input(self):
        assert types_secrets.has_configured_secret_input("my-literal-secret") is True
        # Empty trimmed
        assert types_secrets.has_configured_secret_input("   ") is False
        # SecretRef shape
        assert types_secrets.has_configured_secret_input(
            {"source": "env", "provider": "p", "id": "FOO"}
        ) is True
        # Not a secret
        assert types_secrets.has_configured_secret_input(123) is False

    def test_normalize_secret_input_string(self):
        assert types_secrets.normalize_secret_input_string("  hello  ") == "hello"
        assert types_secrets.normalize_secret_input_string("hello") == "hello"
        assert types_secrets.normalize_secret_input_string("   ") is None
        assert types_secrets.normalize_secret_input_string("") is None
        assert types_secrets.normalize_secret_input_string(None) is None
        assert types_secrets.normalize_secret_input_string(123) is None

    def test_unresolved_secret_input_error(self):
        ref = {"source": "env", "provider": "p", "id": "FOO"}
        err = types_secrets.UnresolvedSecretInputError(path="cfg.key", ref=ref)
        assert err.path == "cfg.key"
        assert err.ref is ref
        assert "cfg.key" in str(err)
        assert "env:p:FOO" in str(err)
        assert err.name == "UnresolvedSecretInputError"

    def test_is_unresolved_secret_input_error(self):
        err = types_secrets.UnresolvedSecretInputError(path="x", ref={"source": "env", "provider": "p", "id": "i"})
        assert types_secrets.is_unresolved_secret_input_error(err) is True
        assert types_secrets.is_unresolved_secret_input_error(ValueError("x")) is False
        assert types_secrets.is_unresolved_secret_input_error("string") is False

    def test_assert_secret_input_resolved_passes(self):
        # Plain string passes
        types_secrets.assert_secret_input_resolved(value="hello", path="x")
        # None passes
        types_secrets.assert_secret_input_resolved(value=None, path="x")

    def test_assert_secret_input_resolved_raises(self):
        # A ref value should raise
        ref = {"source": "env", "provider": "p", "id": "FOO"}
        with pytest.raises(types_secrets.UnresolvedSecretInputError):
            types_secrets.assert_secret_input_resolved(value=ref, path="cfg.x")

    def test_resolve_secret_input_string_available(self):
        result = types_secrets.resolve_secret_input_string(value="hello", path="x")
        assert result["status"] == "available"
        assert result["value"] == "hello"
        assert result["ref"] is None

    def test_resolve_secret_input_string_missing(self):
        result = types_secrets.resolve_secret_input_string(value=None, path="x")
        assert result["status"] == "missing"

    def test_resolve_secret_input_string_strict_raises(self):
        ref = {"source": "env", "provider": "p", "id": "FOO"}
        with pytest.raises(types_secrets.UnresolvedSecretInputError):
            types_secrets.resolve_secret_input_string(value=ref, path="cfg.x", mode="strict")

    def test_resolve_secret_input_string_inspect(self):
        ref = {"source": "env", "provider": "p", "id": "FOO"}
        result = types_secrets.resolve_secret_input_string(value=ref, path="cfg.x", mode="inspect")
        assert result["status"] == "configured_unavailable"
        assert result["ref"] == ref

    def test_normalize_resolved_secret_input_string(self):
        assert types_secrets.normalize_resolved_secret_input_string(value="hello", path="x") == "hello"
        assert types_secrets.normalize_resolved_secret_input_string(value=None, path="x") is None

    def test_resolve_secret_input_ref_explicit(self):
        ref = {"source": "env", "provider": "p", "id": "FOO"}
        result = types_secrets.resolve_secret_input_ref(value="plain", ref_value=ref)
        # explicitRef matches the input by value
        assert result["explicitRef"] == ref
        # Inline not used when explicit is present
        assert result["inlineRef"] is None
        assert result["ref"] == ref

    def test_resolve_secret_input_ref_inline(self):
        result = types_secrets.resolve_secret_input_ref(value="$FOO")
        assert result["explicitRef"] is None
        assert result["inlineRef"] is not None
        assert result["ref"] is not None

    def test_resolve_secret_input_ref_neither(self):
        result = types_secrets.resolve_secret_input_ref(value="plain")
        assert result["explicitRef"] is None
        assert result["inlineRef"] is None
        assert result["ref"] is None

    def test_secrets_config_typed_dict(self):
        assert hasattr(types_secrets.SecretsConfig, "__total__")


# ---------------------------------------------------------------------------
# types_models
# ---------------------------------------------------------------------------


class TestTypesModels:
    def test_imports(self):
        assert types_models is not None
        for name in (
            "MODEL_APIS", "ModelApi", "MODEL_THINKING_FORMATS",
            "is_model_thinking_format", "ModelCompatConfig",
            "ModelProviderConfig", "ModelsConfig", "ModelsConfigInput",
        ):
            assert name in types_models.__all__, f"missing: {name}"

    def test_model_apis_constant(self):
        assert "openai-completions" in types_models.MODEL_APIS
        assert "anthropic-messages" in types_models.MODEL_APIS
        assert "google-generative-ai" in types_models.MODEL_APIS
        assert "ollama" in types_models.MODEL_APIS
        assert len(types_models.MODEL_APIS) == 10

    def test_model_api_literal(self):
        import typing
        assert "openai-completions" in typing.get_args(types_models.ModelApi)

    def test_thinking_formats_constant(self):
        assert "openai" in types_models.MODEL_THINKING_FORMATS
        assert "deepseek" in types_models.MODEL_THINKING_FORMATS
        assert "zai" in types_models.MODEL_THINKING_FORMATS

    def test_is_model_thinking_format(self):
        assert types_models.is_model_thinking_format("openai") is True
        assert types_models.is_model_thinking_format("deepseek") is True
        assert types_models.is_model_thinking_format("unknown") is False
        assert types_models.is_model_thinking_format("") is False

    def test_model_provider_config_accepts_partial(self):
        cfg: types_models.ModelProviderConfig = {
            "baseUrl": "https://api.example.com",
            "models": [],
        }
        assert cfg["baseUrl"] == "https://api.example.com"

    def test_model_definition_config(self):
        cfg: types_models.ModelDefinitionConfig = {
            "id": "claude-opus-4-6",
            "name": "Claude Opus",
            "reasoning": True,
            "input": ["text"],
            "cost": {"input": 15, "output": 75, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": 200000,
            "maxTokens": 8192,
        }
        assert cfg["id"] == "claude-opus-4-6"

    def test_model_compat_config(self):
        cfg: types_models.ModelCompatConfig = {
            "thinkingFormat": "openai",
            "supportsTools": True,
            "supportsPromptCacheKey": True,
        }
        assert cfg["thinkingFormat"] == "openai"

    def test_models_config_typed_dict(self):
        assert hasattr(types_models.ModelsConfig, "__total__")


# ---------------------------------------------------------------------------
# types_slack
# ---------------------------------------------------------------------------


class TestTypesSlack:
    def test_imports(self):
        assert types_slack is not None
        for name in (
            "SlackConfig", "SlackAccountConfig", "SlackChannelConfig",
            "SlackDmConfig", "SlackChannelStreamingConfig",
            "SlackExecApprovalConfig", "SlackActionConfig",
        ):
            assert name in types_slack.__all__, f"missing: {name}"

    def test_slack_config_accepts_partial(self):
        cfg: types_slack.SlackConfig = {
            "enabled": True,
            "botToken": "xoxb-secret",
        }
        assert cfg["enabled"] is True

    def test_slack_account_config(self):
        cfg: types_slack.SlackAccountConfig = {
            "name": "main",
            "mode": "socket",
            "enabled": True,
        }
        assert cfg["name"] == "main"

    def test_slack_multi_account(self):
        cfg: types_slack.SlackConfig = {
            "accounts": {"acc1": {"name": "first"}},
            "defaultAccount": "acc1",
        }
        assert cfg["defaultAccount"] == "acc1"

    def test_streaming_config(self):
        cfg: types_slack.SlackChannelStreamingConfig = {
            "mode": "block",
            "chunkMode": "length",
        }
        assert cfg["mode"] == "block"

    def test_exec_approval_config(self):
        cfg: types_slack.SlackExecApprovalConfig = {
            "enabled": "auto",
            "target": "dm",
        }
        assert cfg["enabled"] == "auto"

    def test_slack_typed_dicts(self):
        for td in (
            types_slack.SlackConfig, types_slack.SlackAccountConfig,
            types_slack.SlackChannelConfig, types_slack.SlackDmConfig,
            types_slack.SlackChannelStreamingConfig,
        ):
            assert hasattr(td, "__total__")


# ---------------------------------------------------------------------------
# types_telegram
# ---------------------------------------------------------------------------


class TestTypesTelegram:
    def test_imports(self):
        assert types_telegram is not None
        for name in (
            "TelegramConfig", "TelegramAccountConfig", "TelegramGroupConfig",
            "TelegramDirectConfig", "TelegramTopicConfig", "TelegramActionConfig",
            "TelegramExecApprovalConfig", "TelegramNetworkConfig",
        ):
            assert name in types_telegram.__all__, f"missing: {name}"

    def test_telegram_config_accepts_partial(self):
        cfg: types_telegram.TelegramConfig = {
            "enabled": True,
            "botToken": "123456:ABC",
        }
        assert cfg["enabled"] is True

    def test_telegram_account_config(self):
        cfg: types_telegram.TelegramAccountConfig = {
            "name": "main",
            "dmPolicy": "pairing",
        }
        assert cfg["dmPolicy"] == "pairing"

    def test_telegram_group_config(self):
        cfg: types_telegram.TelegramGroupConfig = {
            "requireMention": True,
            "groupPolicy": "open",
        }
        assert cfg["groupPolicy"] == "open"

    def test_telegram_topic_config(self):
        cfg: types_telegram.TelegramTopicConfig = {
            "requireMention": False,
            "enabled": True,
        }
        assert cfg["enabled"] is True

    def test_telegram_action_config(self):
        cfg: types_telegram.TelegramActionConfig = {
            "reactions": True,
            "poll": False,
        }
        assert cfg["poll"] is False

    def test_telegram_typed_dicts(self):
        for td in (
            types_telegram.TelegramConfig,
            types_telegram.TelegramAccountConfig,
            types_telegram.TelegramGroupConfig,
            types_telegram.TelegramTopicConfig,
        ):
            assert hasattr(td, "__total__")


# ---------------------------------------------------------------------------
# types_base
# ---------------------------------------------------------------------------


class TestTypesBase:
    def test_imports(self):
        assert types_base is not None
        for name in (
            "ReplyMode", "TypingMode", "SessionScope", "DmScope",
            "ReplyToMode", "GroupPolicy", "DmPolicy",
            "ContextVisibilityMode", "TextChunkMode", "StreamingMode",
            "LoggingConfig", "SessionConfig", "IdentityConfig",
        ):
            assert name in types_base.__all__, f"missing: {name}"

    def test_group_policy_values(self):
        import typing
        assert typing.get_args(types_base.GroupPolicy) == ("open", "disabled", "allowlist")

    def test_dm_policy_values(self):
        import typing
        assert "pairing" in typing.get_args(types_base.DmPolicy)

    def test_session_config(self):
        cfg: types_base.SessionConfig = {
            "scope": "per-sender",
            "dmScope": "main",
            "mainKey": "main",
        }
        assert cfg["mainKey"] == "main"

    def test_logging_config(self):
        cfg: types_base.LoggingConfig = {
            "level": "info",
            "consoleStyle": "pretty",
        }
        assert cfg["level"] == "info"

    def test_identity_config(self):
        cfg: types_base.IdentityConfig = {
            "name": "Jarvis",
            "emoji": "🤖",
        }
        assert cfg["name"] == "Jarvis"

    def test_session_reset_config(self):
        cfg: types_base.SessionResetConfig = {
            "mode": "daily",
            "atHour": 4,
        }
        assert cfg["mode"] == "daily"


# ---------------------------------------------------------------------------
# types_discord
# ---------------------------------------------------------------------------


class TestTypesDiscord:
    def test_imports(self):
        assert types_discord is not None
        for name in (
            "DiscordConfig", "DiscordAccountConfig", "DiscordGuildEntry",
            "DiscordGuildChannelConfig", "DiscordVoiceConfig",
            "DiscordActionConfig", "DiscordIntentsConfig",
        ):
            assert name in types_discord.__all__, f"missing: {name}"

    def test_discord_config_minimal(self):
        cfg: types_discord.DiscordConfig = {
            "enabled": True,
            "token": "secret",
        }
        assert cfg["enabled"] is True

    def test_discord_account_config_full(self):
        cfg: types_discord.DiscordAccountConfig = {
            "name": "main",
            "token": "secret",
            "dmPolicy": "allowlist",
        }
        assert cfg["dmPolicy"] == "allowlist"

    def test_discord_voice_modes(self):
        import typing
        for mode in ("stt-tts", "agent-proxy", "bidi"):
            assert mode in typing.get_args(types_discord.DiscordVoiceMode)

    def test_discord_action_config(self):
        cfg: types_discord.DiscordActionConfig = {
            "reactions": True,
            "messages": True,
            "moderation": False,
        }
        assert cfg["moderation"] is False

    def test_discord_intents(self):
        cfg: types_discord.DiscordIntentsConfig = {
            "presence": True,
            "guildMembers": True,
        }
        assert cfg["presence"] is True

    def test_discord_typed_dicts(self):
        for td in (
            types_discord.DiscordConfig,
            types_discord.DiscordAccountConfig,
            types_discord.DiscordGuildEntry,
        ):
            assert hasattr(td, "__total__")


# ---------------------------------------------------------------------------
# types_openclaw
# ---------------------------------------------------------------------------


class TestTypesOpenClaw:
    def test_imports(self):
        assert types_openclaw is not None
        for name in (
            "OpenClawConfig", "OpenClawConfigInput", "OpenClawSecurityConfig",
            "OpenClawWizardConfig", "OpenClawUiConfig", "OpenClawUpdateConfig",
            "ConfigValidationIssue", "LegacyConfigIssue", "ConfigFileSnapshot",
        ):
            assert name in types_openclaw.__all__, f"missing: {name}"

    def test_openclaw_config(self):
        cfg: types_openclaw.OpenClawConfig = {
            "meta": {"lastTouchedVersion": "0.9.0-rc2"},
            "ui": {"seamColor": "#ff00ff"},
        }
        assert cfg["ui"]["seamColor"] == "#ff00ff"  # type: ignore[index]

    def test_openclaw_security_config(self):
        cfg: types_openclaw.OpenClawSecurityConfig = {
            "audit": {"suppressions": []},
            "installPolicy": {"enabled": True},
        }
        assert cfg["installPolicy"]["enabled"] is True  # type: ignore[index]

    def test_openclaw_wizard_config(self):
        cfg: types_openclaw.OpenClawWizardConfig = {
            "accessMode": "guarded",
            "appRecommendations": True,
        }
        assert cfg["accessMode"] == "guarded"

    def test_openclaw_ui_config(self):
        cfg: types_openclaw.OpenClawUiConfig = {
            "seamColor": "#00ff00",
            "prefs": {"theme": "claw", "textScale": 100},
        }
        assert cfg["seamColor"] == "#00ff00"

    def test_openclaw_update_config(self):
        cfg: types_openclaw.OpenClawUpdateConfig = {
            "channel": "stable",
            "checkOnStart": True,
        }
        assert cfg["channel"] == "stable"

    def test_config_validation_issue(self):
        issue: types_openclaw.ConfigValidationIssue = {
            "path": "agents.list[0].model",
            "message": "invalid model",
            "allowedValues": ["a", "b"],
        }
        assert issue["path"] == "agents.list[0].model"

    def test_legacy_config_issue(self):
        issue: types_openclaw.LegacyConfigIssue = {
            "path": "agents.list[0].compaction",
            "message": "legacy key",
        }
        assert "legacy" in issue["message"]

    def test_config_file_snapshot(self):
        snap: types_openclaw.ConfigFileSnapshot = {
            "path": "/tmp/config.json",
            "exists": True,
            "valid": True,
        }
        assert snap["exists"] is True

    def test_openclaw_typed_dicts(self):
        for td in (
            types_openclaw.OpenClawConfig,
            types_openclaw.OpenClawSecurityConfig,
            types_openclaw.OpenClawWizardConfig,
        ):
            assert hasattr(td, "__total__")


# ---------------------------------------------------------------------------
# read_best_effort_config_runtime
# ---------------------------------------------------------------------------


class TestReadBestEffortConfigRuntime:
    def test_imports(self):
        assert read_best_effort_config_runtime is not None
        for name in (
            "read_best_effort_config",
            "read_best_effort_config_snapshot",
            "read_source_config_best_effort",
        ):
            assert name in read_best_effort_config_runtime.__all__, f"missing: {name}"

    def test_facade_re_exports(self):
        # The facade re-exports the io.py stubs.
        assert (
            read_best_effort_config_runtime.read_best_effort_config
            is not None
        )
        assert (
            read_best_effort_config_runtime.read_best_effort_config_snapshot
            is not None
        )

    def test_facade_callable(self):
        # read_source_config_best_effort is a thin facade callable.
        assert callable(read_best_effort_config_runtime.read_source_config_best_effort)
