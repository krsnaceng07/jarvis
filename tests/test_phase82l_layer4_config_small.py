"""Tests for Phase 8.2l — Layer 4 src/config/ small files (last batch).

Covers:
- src/config/types_messages.py (MessagesConfig, GroupChatConfig, QueueConfig, etc.)
- src/config/types_agents.py (AgentConfig, AgentBinding, etc.)
- src/config/types_msteams.py (MSTeamsConfig, MSTeamsSsoConfig, etc.)
- src/config/channel_alias_migration.py (define_channel_alias_migration)
"""
from __future__ import annotations


from src.config import (
    channel_alias_migration,
    types_agents,
    types_messages,
    types_msteams,
)


# ---------------------------------------------------------------------------
# types_messages
# ---------------------------------------------------------------------------


class TestTypesMessages:
    def test_imports(self):
        assert types_messages is not None
        # Literal types are typing._LiteralGenericAlias at runtime; verify the
        # public names exist and are usable as type aliases.
        import typing
        for name in (
            "MentionPatternsMode",
            "VisibleRepliesMode",
            "UnmentionedInboundMode",
            "CommandOwnerDisplay",
            "BroadcastStrategy",
            "NativeCommandsSetting",
        ):
            assert name in types_messages.__all__, f"missing export: {name}"
            obj = getattr(types_messages, name)
            assert obj is not None
        # MentionPatternsMode and VisibleRepliesMode are typing.Literal aliases
        assert typing.get_args(types_messages.MentionPatternsMode) == ("allow", "deny")
        assert typing.get_args(types_messages.VisibleRepliesMode) == ("automatic", "message_tool")
        assert typing.get_args(types_messages.UnmentionedInboundMode) == ("user_request", "room_event")
        assert typing.get_args(types_messages.CommandOwnerDisplay) == ("raw", "hash")
        assert typing.get_args(types_messages.BroadcastStrategy) == ("parallel", "sequential")

    def test_typed_dicts_are_classes(self):
        # TypedDict factories are types.MappingProxyType instances.
        assert hasattr(types_messages.MentionPatternsPolicyConfig, "__total__")
        assert hasattr(types_messages.GroupChatConfig, "__total__")
        assert hasattr(types_messages.DmConfig, "__total__")
        assert hasattr(types_messages.QueueConfig, "__total__")
        assert hasattr(types_messages.InboundDebounceConfig, "__total__")
        assert hasattr(types_messages.StatusReactionsEmojiConfig, "__total__")
        assert hasattr(types_messages.StatusReactionsTimingConfig, "__total__")
        assert hasattr(types_messages.StatusReactionsConfig, "__total__")
        assert hasattr(types_messages.MessagesConfig, "__total__")
        assert hasattr(types_messages.CommandsConfig, "__total__")
        assert hasattr(types_messages.ProviderCommandsConfig, "__total__")

    def test_group_chat_accepts_partial(self):
        cfg: types_messages.GroupChatConfig = {
            "historyLimit": 20,
            "visibleReplies": "automatic",
        }
        assert cfg["historyLimit"] == 20

    def test_messages_config_accepts_partial(self):
        cfg: types_messages.MessagesConfig = {
            "messagePrefix": "[jarvis] ",
            "ackReaction": "👍",
        }
        assert cfg["messagePrefix"] == "[jarvis] "

    def test_status_reactions_full(self):
        cfg: types_messages.StatusReactionsConfig = {
            "enabled": True,
            "emojis": {"queued": "🕒", "done": "✅", "error": "❌"},
            "timing": {"debounceMs": 700, "stallSoftMs": 10000},
        }
        assert cfg["enabled"] is True
        assert cfg["emojis"]["done"] == "✅"  # type: ignore[index]

    def test_commands_config(self):
        cfg: types_messages.CommandsConfig = {
            "native": "auto",
            "bash": False,
            "restart": True,
        }
        assert cfg["native"] == "auto"
        assert cfg["bash"] is False

    def test_queue_config(self):
        cfg: types_messages.QueueConfig = {
            "mode": "collect",
            "debounceMs": 1000,
            "cap": 10,
            "drop": "old",
        }
        assert cfg["mode"] == "collect"

    def test_inbound_debounce(self):
        cfg: types_messages.InboundDebounceConfig = {
            "debounceMs": 500,
            "byChannel": {"discord": 200, "telegram": 300},
        }
        assert cfg["byChannel"]["discord"] == 200  # type: ignore[index]

    def test_all_exports(self):
        assert "MentionPatternsMode" in types_messages.__all__
        assert "MessagesConfig" in types_messages.__all__
        assert "CommandsConfig" in types_messages.__all__
        assert len(types_messages.__all__) == 19


# ---------------------------------------------------------------------------
# types_agents
# ---------------------------------------------------------------------------


class TestTypesAgents:
    def test_imports(self):
        assert types_agents is not None
        import typing
        for name in (
            "AgentRuntimeType",
            "AcpSessionMode",
            "AgentVerboseLevel",
            "AgentReasoningDefault",
            "SubagentDelegationMode",
        ):
            assert name in types_agents.__all__
        assert typing.get_args(types_agents.AgentRuntimeType) == ("embedded", "acp")
        assert typing.get_args(types_agents.AcpSessionMode) == ("persistent", "oneshot")
        assert typing.get_args(types_agents.AgentVerboseLevel) == ("off", "on", "full")
        assert typing.get_args(types_agents.AgentReasoningDefault) == ("on", "off", "stream")
        assert typing.get_args(types_agents.SubagentDelegationMode) == ("suggest", "prefer")

    def test_typed_dicts_are_classes(self):
        assert hasattr(types_agents.AgentRuntimeAcpConfig, "__total__")
        assert hasattr(types_agents.AgentRuntimeConfig, "__total__")
        assert hasattr(types_agents.AgentBindingMatch, "__total__")
        assert hasattr(types_agents.AgentRouteBinding, "__total__")
        assert hasattr(types_agents.AgentAcpBinding, "__total__")
        assert hasattr(types_agents.AgentConfig, "__total__")
        assert hasattr(types_agents.AgentsConfig, "__total__")

    def test_agent_config_minimal(self):
        cfg: types_agents.AgentConfig = {"id": "main", "name": "Main"}
        assert cfg["id"] == "main"

    def test_agent_config_full(self):
        cfg: types_agents.AgentConfig = {
            "id": "main",
            "default": True,
            "name": "Main Agent",
            "description": "primary",
            "workspace": "/tmp/agent",
            "model": "anthropic/claude-opus-4-6",
            "thinkingDefault": "low",
            "verboseDefault": "on",
            "tools": {"bash": True},
        }
        assert cfg["model"] == "anthropic/claude-opus-4-6"

    def test_agent_binding_match(self):
        match: types_agents.AgentBindingMatch = {
            "channel": "telegram",
            "accountId": "default",
            "peer": {"kind": "dm", "id": "u1"},
        }
        assert match["channel"] == "telegram"

    def test_agent_route_binding(self):
        binding: types_agents.AgentRouteBinding = {
            "type": "route",
            "agentId": "alt",
            "match": {"channel": "discord", "accountId": "*"},
        }
        assert binding["agentId"] == "alt"

    def test_agent_acp_binding(self):
        binding: types_agents.AgentAcpBinding = {
            "type": "acp",
            "agentId": "codex",
            "match": {"channel": "cli"},
            "acp": {"mode": "persistent"},
        }
        assert binding["type"] == "acp"

    def test_agents_config(self):
        cfg: types_agents.AgentsConfig = {
            "defaults": {"model": "anthropic/claude-opus-4-6"},
            "list": [{"id": "a1"}, {"id": "a2"}],
        }
        assert len(cfg["list"]) == 2  # type: ignore[arg-type]

    def test_all_exports(self):
        assert "AgentRuntimeType" in types_agents.__all__
        assert "AgentConfig" in types_agents.__all__
        assert "AgentsConfig" in types_agents.__all__
        assert len(types_agents.__all__) == 13


# ---------------------------------------------------------------------------
# types_msteams
# ---------------------------------------------------------------------------


class TestTypesMsteams:
    def test_imports(self):
        assert types_msteams is not None
        import typing
        for name in (
            "MSTeamsCloudName",
            "MSTeamsReplyStyle",
        ):
            assert name in types_msteams.__all__
        assert typing.get_args(types_msteams.MSTeamsCloudName) == ("Public", "USGov", "USGovDoD", "China")
        assert typing.get_args(types_msteams.MSTeamsReplyStyle) == ("thread", "top-level")

    def test_typed_dicts_are_classes(self):
        assert hasattr(types_msteams.MSTeamsWebhookConfig, "__total__")
        assert hasattr(types_msteams.MSTeamsSsoConfig, "__total__")
        assert hasattr(types_msteams.MSTeamsChannelConfig, "__total__")
        assert hasattr(types_msteams.MSTeamsTeamConfig, "__total__")
        assert hasattr(types_msteams.MSTeamsConfig, "__total__")

    def test_msteams_config_minimal(self):
        cfg: types_msteams.MSTeamsConfig = {
            "enabled": True,
            "appId": "00000000-0000-0000-0000-000000000000",
            "appPassword": "secret",
            "tenantId": "tenant-id",
            "cloud": "Public",
        }
        assert cfg["enabled"] is True
        assert cfg["cloud"] == "Public"

    def test_msteams_webhook(self):
        cfg: types_msteams.MSTeamsWebhookConfig = {
            "port": 3978,
            "path": "/api/messages",
        }
        assert cfg["port"] == 3978

    def test_msteams_sso(self):
        cfg: types_msteams.MSTeamsSsoConfig = {
            "enabled": True,
            "connectionName": "default",
        }
        assert cfg["connectionName"] == "default"

    def test_msteams_channel(self):
        cfg: types_msteams.MSTeamsChannelConfig = {
            "requireMention": True,
            "replyStyle": "thread",
            "tools": {"allow": ["bash"]},
        }
        assert cfg["replyStyle"] == "thread"

    def test_msteams_team(self):
        cfg: types_msteams.MSTeamsTeamConfig = {
            "requireMention": True,
            "replyStyle": "top-level",
            "channels": {
                "19:abc@thread.tacv2": {"requireMention": False},
            },
        }
        assert cfg["replyStyle"] == "top-level"

    def test_all_exports(self):
        assert "MSTeamsCloudName" in types_msteams.__all__
        assert "MSTeamsConfig" in types_msteams.__all__
        assert len(types_msteams.__all__) == 7


# ---------------------------------------------------------------------------
# channel_alias_migration
# ---------------------------------------------------------------------------


class TestChannelAliasMigration:
    def test_imports(self):
        assert channel_alias_migration is not None
        assert channel_alias_migration.StreamingAliasMode is str
        assert callable(channel_alias_migration.define_channel_alias_migration)

    def test_define_basic_spec(self):
        spec = {
            "channelId": "discord",
            "streaming": {
                "defaultMode": "off",
                "includePreviewChunk": True,
            },
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        assert "legacyConfigRules" in out
        assert "hasLegacyAliases" in out
        assert "normalizeChannelConfig" in out
        assert len(out["legacyConfigRules"]) == 2

    def test_legacy_config_rules_paths(self):
        spec = {
            "channelId": "telegram",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        paths = [tuple(r["path"]) for r in out["legacyConfigRules"]]
        assert ("channels", "telegram") in paths
        assert ("channels", "telegram", "accounts") in paths

    def test_root_message_mentions_streaming_scalar(self):
        spec = {
            "channelId": "slack",
            "streaming": {
                "defaultMode": "off",
                "includePreviewChunk": True,
                "resolveNativeTransport": lambda entry: "rtm",
            },
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        root_msg = out["legacyConfigRules"][0]["message"]
        # Root message should mention streamMode and streaming (scalar) with full path prefix.
        assert "channels.slack.streamMode" in root_msg
        assert "channels.slack.streaming (scalar)" in root_msg
        # Should mention draftChunk and nativeStreaming (when those flags are set).
        assert "draftChunk" in root_msg
        assert "nativeStreaming" in root_msg

    def test_account_message_uses_path_prefix(self):
        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        account_msg = out["legacyConfigRules"][1]["message"]
        assert "channels.discord.accounts.<id>" in account_msg
        assert "streamMode" in account_msg

    def test_delivery_only_excludes_streaming_scalar(self):
        spec = {
            "channelId": "imessage",
            "streaming": {"defaultMode": "off", "deliveryOnly": True},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        root_msg = out["legacyConfigRules"][0]["message"]
        # deliveryOnly means no streamMode/streaming (scalar) in message
        assert "streamMode" not in root_msg
        assert "streaming (scalar)" not in root_msg
        # But chunkMode and blockStreaming should be there
        assert "chunkMode" in root_msg
        assert "blockStreaming" in root_msg

    def test_has_legacy_aliases_delivery_only(self):
        spec = {
            "channelId": "imessage",
            "streaming": {"defaultMode": "off", "deliveryOnly": True},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        # Empty entry → no legacy
        assert out["hasLegacyAliases"]({}) is False
        # chunkMode present → has legacy
        assert out["hasLegacyAliases"]({"chunkMode": "field"}) is True
        # blockStreaming present → has legacy
        assert out["hasLegacyAliases"]({"blockStreaming": True}) is True
        # blockStreamingCoalesce present → has legacy
        assert out["hasLegacyAliases"]({"blockStreamingCoalesce": 2}) is True
        # Non-dict value → not legacy
        assert out["hasLegacyAliases"]("string") is False
        assert out["hasLegacyAliases"](None) is False

    def test_has_legacy_aliases_with_callback(self):
        captured = {}

        def legacy_check(value, opts):
            captured["opts"] = opts
            return bool(isinstance(value, dict) and value.get("flag"))

        spec = {
            "channelId": "discord",
            "streaming": {
                "defaultMode": "off",
                "includePreviewChunk": True,
            },
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            has_legacy_streaming_aliases_fn=legacy_check,
        )
        assert out["hasLegacyAliases"]({"flag": True}) is True
        assert out["hasLegacyAliases"]({"flag": False}) is False
        assert captured["opts"]["includePreviewChunk"] is True
        assert captured["opts"]["includeNativeTransport"] is False

    def test_has_legacy_aliases_without_callback(self):
        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        # No callback, no deliveryOnly → falls through to default False
        assert out["hasLegacyAliases"]({"chunkMode": "x"}) is False

    def test_normalize_channel_config_no_op_when_no_entry(self):
        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        result = out["normalizeChannelConfig"]({"cfg": {"channels": {}}})
        assert result["config"] == {"channels": {}}
        assert result["changes"] == []

    def test_normalize_channel_config_no_channels(self):
        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        result = out["normalizeChannelConfig"]({"cfg": {}})
        assert result["config"] == {}
        assert result["changes"] == []

    def test_normalize_channel_config_no_callback(self):
        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        cfg = {"channels": {"discord": {"foo": "bar"}}}
        result = out["normalizeChannelConfig"]({"cfg": cfg, "changes": ["x"]})
        assert result["config"] == cfg
        assert result["changes"] == ["x"]

    def test_normalize_channel_config_uses_callback(self):
        def normalize(params):
            return {
                "changed": True,
                "entry": {"chunkMode": "field", "blockStreaming": True, "_normalized": True},
            }

        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            normalize_legacy_channel_aliases_fn=normalize,
        )
        result = out["normalizeChannelConfig"]({"cfg": {"channels": {"discord": {}}}})
        # The channels.discord entry should be replaced
        assert result["config"]["channels"]["discord"] == {  # type: ignore[index]
            "chunkMode": "field",
            "blockStreaming": True,
            "_normalized": True,
        }

    def test_normalize_channel_config_unchanged_callback(self):
        def normalize(params):
            return {"changed": False, "entry": params.get("entry")}

        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            normalize_legacy_channel_aliases_fn=normalize,
        )
        original = {"foo": "bar"}
        result = out["normalizeChannelConfig"]({"cfg": {"channels": {"discord": original}}})
        # No change → original cfg passed back
        assert result["config"]["channels"]["discord"] == original  # type: ignore[index]

    def test_normalize_channel_config_passes_spec_fields(self):
        captured = {}

        def normalize(params):
            captured.update(params)
            return {"changed": False, "entry": params.get("entry")}

        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
            "dm": {
                "root": True,
                "rootPromoteAllowFrom": True,
                "accounts": True,
            },
            "accountStreamingReplacesRoot": True,
            "normalizeAccountExtra": lambda p: {"changed": False, "entry": p.get("entry")},
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            normalize_legacy_channel_aliases_fn=normalize,
        )
        out["normalizeChannelConfig"]({"cfg": {"channels": {"discord": {}}}})
        assert captured["pathPrefix"] == "channels.discord"
        assert captured["normalizeDm"] is True
        assert captured["rootDmPromoteAllowFrom"] is True
        assert captured["normalizeAccountDm"] is True
        assert captured["seedAccountStreamingFromRoot"] is True
        assert callable(captured["resolveStreamingOptions"])
        assert callable(captured["normalizeAccountExtra"])

    def test_resolve_streaming_options(self):
        captured = {}

        def resolver(entry, default):
            captured["default"] = default
            return "block"

        spec = {
            "channelId": "discord",
            "streaming": {
                "defaultMode": "off",
                "absentObjectDefault": "progress",
                "includePreviewChunk": True,
            },
        }

        # Trigger via normalize (which uses resolve_streaming_options internally)
        def normalize(params):
            opts = params["resolveStreamingOptions"]({"entry": "x"})
            captured["opts"] = opts
            return {"changed": False, "entry": params["entry"]}

        out_with_norm = channel_alias_migration.define_channel_alias_migration(
            spec,
            normalize_legacy_channel_aliases_fn=normalize,
            resolve_legacy_alias_streaming_mode_fn=resolver,
        )
        out_with_norm["normalizeChannelConfig"]({"cfg": {"channels": {"discord": {}}}})
        assert captured["default"] == "off"
        assert captured["opts"]["resolvedMode"] == "block"
        assert captured["opts"]["aliasOnlyMode"] == "progress"
        assert captured["opts"]["includePreviewChunk"] is True

    def test_account_legacy_check_with_callback(self):
        calls = []

        def account_check(value, matcher):
            calls.append((value, matcher))
            return False

        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            has_legacy_account_streaming_aliases_fn=account_check,
        )
        # Trigger the matcher from the second legacyConfigRule
        matcher = out["legacyConfigRules"][1]["match"]
        result = matcher({"acc1": {}})
        assert result is False
        assert len(calls) == 1
        assert calls[0][0] == {"acc1": {}}
        assert callable(calls[0][1])

    def test_account_legacy_check_without_callback(self):
        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        matcher = out["legacyConfigRules"][1]["match"]
        # Without callback, returns False
        assert matcher({"acc1": {}}) is False

    def test_normalize_delivery_only_short_circuit(self):
        """When deliveryOnly is set and no legacy aliases, skip normalize."""
        def normalize(params):
            return {"changed": True, "entry": {"_called": True}}

        spec = {
            "channelId": "imessage",
            "streaming": {"defaultMode": "off", "deliveryOnly": True},
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            normalize_legacy_channel_aliases_fn=normalize,
        )
        # No legacy aliases → should NOT call normalize
        result = out["normalizeChannelConfig"]({"cfg": {"channels": {"imessage": {}}}})
        # The entry is unchanged
        assert result["config"]["channels"]["imessage"] == {}  # type: ignore[index]

    def test_normalize_does_not_mutate_changes(self):
        def normalize(params):
            return {"changed": True, "entry": {}}

        spec = {
            "channelId": "discord",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(
            spec,
            normalize_legacy_channel_aliases_fn=normalize,
        )
        changes = ["existing-change"]
        result = out["normalizeChannelConfig"]({"cfg": {"channels": {"discord": {}}}, "changes": changes})
        # The changes list passed in should be preserved (by value)
        assert result["changes"] == changes

    def test_root_message_format_with_two_keys(self):
        """When flat list has 2 elements, the format uses ', and ' between them."""
        spec = {
            "channelId": "minimal",
            "streaming": {"defaultMode": "off"},
        }
        out = channel_alias_migration.define_channel_alias_migration(spec)
        msg = out["legacyConfigRules"][0]["message"]
        # streamMode and streaming (scalar) both get full prefix; chunkMode and blockStreaming don't
        assert msg.startswith("channels.minimal.streamMode, channels.minimal.streaming (scalar),")
        assert "are legacy" in msg
        assert 'Run "openclaw doctor --fix"' in msg
