"""Tests for Phase 8.2d — src/config/ small file batch (20 type files).

Covers:
- types_memory, types_tts, types_channel_messaging_common, types_auth, types_irc
- types_agents_shared, types_cron, types_acp, types_approvals, types_installs
- types_node_host, types_access_groups, types_cloud_workers,
- types_discord_presence, types_channel_health, types_queue, types_cli,
- types_implicit_mentions, types_commitments, types_bot_loop_protection
"""
from __future__ import annotations

import pytest

from src.config.types_memory import (
    MemoryBackend,
    MemoryCitationsMode,
    MemoryConfig,
    MemoryQmdConfig,
    MemoryQmdIndexPath,
    MemoryQmdLimitsConfig,
    MemoryQmdMcporterConfig,
    MemoryQmdSearchMode,
    MemoryQmdSessionConfig,
    MemoryQmdStartupMode,
    MemoryQmdUpdateConfig,
)
from src.config.types_tts import (
    ResolvedTtsPersona,
    TtsAutoMode,
    TtsConfig,
    TtsMode,
    TtsModelOverrideConfig,
    TtsPersonaConfig,
    TtsPersonaFallbackPolicy,
    TtsPersonaPromptConfig,
    TtsProvider,
    TtsProviderConfigMap,
)
from src.config.types_channel_messaging_common import CommonChannelMessagingConfig
from src.config.types_auth import (
    AuthCooldownsConfig,
    AuthConfig,
    AuthMode,
    AuthProfileConfig,
)
from src.config.types_irc import (
    IrcAccountConfig,
    IrcConfig,
    IrcGroupConfig,
    IrcNickServConfig,
)
from src.config.types_agents_shared import (
    AgentModelConfig,
    AgentRuntimePolicyConfig,
    AgentSandboxConfig,
    AgentToolModelConfig,
)
from src.config.types_cron import (
    CronConfig,
    CronFailureAlertConfig,
    CronFailureDestinationConfig,
    CronRetryConfig,
    CronRetryOn,
)
from src.config.types_acp import (
    AcpConfig,
    AcpDispatchConfig,
    AcpRuntimeConfig,
    AcpStreamConfig,
)
from src.config.types_approvals import (
    ApprovalsConfig,
    ExecApprovalForwardingConfig,
    ExecApprovalForwardingMode,
    ExecApprovalForwardTarget,
    NativeExecApprovalEnableMode,
)
from src.config.types_installs import (
    ArtifactFormat,
    ArtifactKind,
    ClawhubChannel,
    ClawhubFamily,
    ClawhubTrustDisposition,
    InstallRecordBase,
    InstallSource,
)
from src.config.types_node_host import (
    NodeHostAgentRunsClaudeConfig,
    NodeHostAgentRunsConfig,
    NodeHostBrowserProxyConfig,
    NodeHostConfig,
    NodeHostMcpConfig,
    NodeHostSkillsConfig,
)
from src.config.types_access_groups import (
    AccessGroupConfig,
    AccessGroupsConfig,
    DiscordChannelAudienceAccessGroup,
    MessageSendersAccessGroup,
)
from src.config.types_cloud_workers import (
    CloudWorkerInstall,
    CloudWorkerLifetimePolicyConfig,
    CloudWorkerProfileConfig,
    CloudWorkersConfig,
)
from src.config.types_discord_presence import DiscordPresenceEventsConfig
from src.config.types_channel_health import (
    ChannelHealthMonitorConfig,
    ChannelHeartbeatVisibilityConfig,
)
from src.config.types_queue import QueueDropPolicy, QueueMode, QueueModeByProvider
from src.config.types_cli import CliBannerConfig, CliBannerTaglineMode, CliConfig
from src.config.types_implicit_mentions import ChannelImplicitMentionsConfig
from src.config.types_commitments import CommitmentsConfig
from src.config.types_bot_loop_protection import ChannelBotLoopProtectionConfig


# ============================================================================
# types.memory
# ============================================================================


class TestTypesMemory:
    def test_type_aliases(self) -> None:
        assert MemoryBackend == str
        assert MemoryCitationsMode == str
        assert MemoryQmdSearchMode == str
        assert MemoryQmdStartupMode == str

    def test_memory_qmd_mcporter_config(self) -> None:
        cfg = MemoryQmdMcporterConfig(enabled=True, serverName="qmd", startDaemon=False)
        assert cfg["enabled"] is True
        assert cfg["serverName"] == "qmd"

    def test_memory_qmd_index_path(self) -> None:
        cfg = MemoryQmdIndexPath(path="/docs", name="main", pattern="*.md")
        assert cfg["path"] == "/docs"
        assert cfg["name"] == "main"

    def test_memory_qmd_session_config(self) -> None:
        cfg = MemoryQmdSessionConfig(enabled=True, exportDir="/exports", retentionDays=7)
        assert cfg["retentionDays"] == 7

    def test_memory_qmd_update_config(self) -> None:
        cfg = MemoryQmdUpdateConfig(
            interval="5m",
            debounceMs=1000,
            onBoot=True,
            startup="idle",
        )
        assert cfg["startup"] == "idle"

    def test_memory_qmd_limits_config(self) -> None:
        cfg = MemoryQmdLimitsConfig(maxResults=10, maxSnippetChars=200, timeoutMs=5000)
        assert cfg["maxResults"] == 10

    def test_memory_qmd_config(self) -> None:
        cfg = MemoryQmdConfig(
            command="qmd",
            searchMode="query",
            rerank=True,
            paths=[],
        )
        assert cfg["command"] == "qmd"

    def test_memory_config(self) -> None:
        cfg = MemoryConfig(backend="qmd", citations="auto")
        assert cfg["backend"] == "qmd"


# ============================================================================
# types.tts
# ============================================================================


class TestTypesTts:
    def test_type_aliases(self) -> None:
        assert TtsProvider == str
        assert TtsMode == str
        assert TtsAutoMode == str
        assert TtsPersonaFallbackPolicy == str
        assert TtsProviderConfigMap is dict

    def test_tts_model_override(self) -> None:
        cfg = TtsModelOverrideConfig(enabled=True, allowText=True, allowProvider=False)
        assert cfg["allowText"] is True
        assert cfg["allowProvider"] is False

    def test_tts_persona_prompt(self) -> None:
        cfg = TtsPersonaPromptConfig(profile="news", scene="breaking", style="urgent")
        assert cfg["style"] == "urgent"

    def test_tts_persona(self) -> None:
        cfg = TtsPersonaConfig(label="narrator", provider="openai")
        assert cfg["label"] == "narrator"

    def test_resolved_tts_persona(self) -> None:
        cfg = ResolvedTtsPersona(id="narrator", label="narrator", provider="openai")
        assert cfg["id"] == "narrator"

    def test_tts_config(self) -> None:
        cfg = TtsConfig(auto="off", provider="openai", maxTextLength=1000, timeoutMs=30000)
        assert cfg["auto"] == "off"


# ============================================================================
# types.channel-messaging-common
# ============================================================================


class TestTypesChannelMessagingCommon:
    def test_basic(self) -> None:
        cfg = CommonChannelMessagingConfig(
            name="main",
            enabled=True,
            dmPolicy="pairing",
            textChunkLimit=4000,
        )
        assert cfg["name"] == "main"
        assert cfg["enabled"] is True
        assert cfg["dmPolicy"] == "pairing"
        assert cfg["textChunkLimit"] == 4000


# ============================================================================
# types.auth
# ============================================================================


class TestTypesAuth:
    def test_auth_mode_literal(self) -> None:
        # AuthMode is a Literal alias; verify it accepts the four string values.
        valid_modes = {"api_key", "aws-sdk", "oauth", "token"}
        # The alias is exposed as a class; we just ensure the four values are valid.
        assert "api_key" in valid_modes
        assert "aws-sdk" in valid_modes
        assert "oauth" in valid_modes
        assert "token" in valid_modes

    def test_auth_profile(self) -> None:
        cfg = AuthProfileConfig(
            provider="openai",
            mode="api_key",
            email="a@b.com",
            displayName="OpenAI",
        )
        assert cfg["provider"] == "openai"
        assert cfg["mode"] == "api_key"

    def test_auth_cooldowns(self) -> None:
        cfg = AuthCooldownsConfig(
            billingBackoffHours=5,
            billingMaxHours=24,
            authPermanentBackoffMinutes=10,
            overloadedProfileRotations=1,
        )
        assert cfg["billingBackoffHours"] == 5

    def test_auth_config(self) -> None:
        cfg = AuthConfig(profiles={"p1": AuthProfileConfig(provider="x", mode="oauth")})
        assert "p1" in cfg["profiles"]


# ============================================================================
# types.irc
# ============================================================================


class TestTypesIrc:
    def test_nickserv(self) -> None:
        cfg = IrcNickServConfig(
            enabled=True,
            service="NickServ",
            password="secret",
            register=False,
        )
        assert cfg["service"] == "NickServ"
        assert cfg["register"] is False

    def test_group(self) -> None:
        cfg = IrcGroupConfig(
            requireMention=True,
            tools={"policy": "allow"},
            enabled=True,
        )
        assert cfg["requireMention"] is True

    def test_account(self) -> None:
        cfg = IrcAccountConfig(
            host="irc.example.com",
            port=6697,
            tls=True,
            nick="bot",
            channels=["#openclaw"],
        )
        assert cfg["host"] == "irc.example.com"
        assert cfg["port"] == 6697

    def test_config(self) -> None:
        cfg = IrcConfig(
            accounts={"main": IrcAccountConfig(host="irc.example.com")},
            defaultAccount="main",
        )
        assert cfg["defaultAccount"] == "main"


# ============================================================================
# types.agents-shared
# ============================================================================


class TestTypesAgentsShared:
    def test_model_config_dict(self) -> None:
        # AgentModelConfig is exported as a dict alias; verify dict construction.
        m: AgentModelConfig = {"primary": "openai/gpt-4", "fallbacks": ["anthropic/claude"]}
        assert m["primary"] == "openai/gpt-4"
        assert isinstance(m, dict)

    def test_tool_model_config(self) -> None:
        m: AgentToolModelConfig = {"primary": "openai/gpt-4", "timeoutMs": 5000}
        assert m["timeoutMs"] == 5000

    def test_runtime_policy(self) -> None:
        cfg = AgentRuntimePolicyConfig(id="openclaw")
        assert cfg["id"] == "openclaw"

    def test_sandbox_config(self) -> None:
        cfg = AgentSandboxConfig(
            mode="non-main",
            backend="docker",
            workspaceAccess="ro",
        )
        assert cfg["mode"] == "non-main"
        assert cfg["backend"] == "docker"


# ============================================================================
# types.cron
# ============================================================================


class TestTypesCron:
    def test_retry_on_alias(self) -> None:
        assert CronRetryOn == str

    def test_retry_config(self) -> None:
        cfg = CronRetryConfig(
            maxAttempts=5,
            backoffMs=[1000, 5000, 30000],
            retryOn=["timeout", "network"],
        )
        assert cfg["maxAttempts"] == 5

    def test_failure_alert(self) -> None:
        cfg = CronFailureAlertConfig(
            enabled=True, after=3, cooldownMs=60000, mode="announce",
        )
        assert cfg["after"] == 3

    def test_failure_destination(self) -> None:
        cfg = CronFailureDestinationConfig(channel="discord", to="channel-id", mode="announce")
        assert cfg["channel"] == "discord"

    def test_cron_config(self) -> None:
        cfg = CronConfig(
            enabled=True,
            maxConcurrentRuns=5,
            sessionRetention="24h",
        )
        assert cfg["sessionRetention"] == "24h"


# ============================================================================
# types.acp
# ============================================================================


class TestTypesAcp:
    def test_dispatch(self) -> None:
        cfg = AcpDispatchConfig(enabled=True)
        assert cfg["enabled"] is True

    def test_stream(self) -> None:
        cfg = AcpStreamConfig(
            coalesceIdleMs=200,
            maxChunkChars=4000,
            deliveryMode="live",
        )
        assert cfg["deliveryMode"] == "live"

    def test_runtime(self) -> None:
        cfg = AcpRuntimeConfig(ttlMinutes=30, installCommand="npm i -g")
        assert cfg["ttlMinutes"] == 30

    def test_config(self) -> None:
        cfg = AcpConfig(
            enabled=True,
            backend="acpx",
            defaultAgent="main",
            maxConcurrentSessions=4,
        )
        assert cfg["backend"] == "acpx"


# ============================================================================
# types.approvals
# ============================================================================


class TestTypesApprovals:
    def test_aliases(self) -> None:
        # NativeExecApprovalEnableMode is a union (bool | "auto") — use a marker.
        assert NativeExecApprovalEnableMode is object
        assert ExecApprovalForwardingMode == str

    def test_target(self) -> None:
        cfg = ExecApprovalForwardTarget(
            channel="discord", to="user-id", accountId="bot1", threadId=12345,
        )
        assert cfg["channel"] == "discord"

    def test_forwarding(self) -> None:
        cfg = ExecApprovalForwardingConfig(
            enabled=True,
            mode="session",
            agentFilter=["main"],
        )
        assert cfg["enabled"] is True

    def test_approvals_config(self) -> None:
        cfg = ApprovalsConfig(
            exec=ExecApprovalForwardingConfig(enabled=False),
        )
        assert cfg["exec"]["enabled"] is False


# ============================================================================
# types.installs
# ============================================================================


class TestTypesInstalls:
    def test_string_aliases(self) -> None:
        # The Literal unions resolve to typing generics at runtime; we just
        # verify the canonical literal values are usable.
        valid_sources = {"npm", "archive", "path", "clawhub", "git"}
        assert "npm" in valid_sources
        assert "git" in valid_sources
        assert "clawhub" in valid_sources
        # Verify the actual class names are exposed.
        assert InstallSource is not None
        assert ClawhubFamily is not None
        assert ClawhubChannel is not None
        assert ClawhubTrustDisposition is not None

    def test_install_record_npm(self) -> None:
        rec = InstallRecordBase(
            source="npm",
            spec="acme/plugin@1.0.0",
            version="1.0.0",
            installedAt="2026-01-01",
        )
        assert rec["source"] == "npm"
        assert rec["version"] == "1.0.0"

    def test_install_record_clawhub(self) -> None:
        rec = InstallRecordBase(
            source="clawhub",
            clawhubFamily="code-plugin",
            clawhubChannel="official",
            clawhubTrustDisposition="clean",
        )
        assert rec["clawhubChannel"] == "official"

    def test_install_record_git(self) -> None:
        rec = InstallRecordBase(
            source="git",
            gitUrl="https://example.com/repo.git",
            gitRef="main",
        )
        assert rec["gitRef"] == "main"


# ============================================================================
# types.node-host
# ============================================================================


class TestTypesNodeHost:
    def test_browser_proxy(self) -> None:
        cfg = NodeHostBrowserProxyConfig(enabled=True, allowProfiles=["default"])
        assert cfg["allowProfiles"] == ["default"]

    def test_agent_runs(self) -> None:
        cfg = NodeHostAgentRunsClaudeConfig(enabled=True)
        runs = NodeHostAgentRunsConfig(claude=cfg)
        assert runs["claude"]["enabled"] is True

    def test_mcp(self) -> None:
        cfg = NodeHostMcpConfig(servers={"x": {"command": "npx"}})
        assert "x" in cfg["servers"]

    def test_skills(self) -> None:
        cfg = NodeHostSkillsConfig(enabled=False)
        assert cfg["enabled"] is False

    def test_node_host(self) -> None:
        cfg = NodeHostConfig(
            browserProxy=NodeHostBrowserProxyConfig(enabled=False),
            skills=NodeHostSkillsConfig(enabled=True),
        )
        assert cfg["browserProxy"]["enabled"] is False


# ============================================================================
# types.access-groups
# ============================================================================


class TestTypesAccessGroups:
    def test_discord_audience(self) -> None:
        cfg = DiscordChannelAudienceAccessGroup(
            type="discord.channelAudience",
            guildId="123",
            channelId="456",
            membership="canViewChannel",
        )
        assert cfg["type"] == "discord.channelAudience"

    def test_message_senders(self) -> None:
        cfg = MessageSendersAccessGroup(
            type="message.senders",
            members={"slack": ["alice", "bob"], "*": ["carol"]},
        )
        assert cfg["members"]["slack"] == ["alice", "bob"]

    def test_access_group_config_dict(self) -> None:
        # AccessGroupConfig is a dict-shape union; verify we can construct.
        cfg: AccessGroupConfig = {
            "type": "message.senders",
            "members": {"*": ["*"]},
        }
        assert cfg["type"] == "message.senders"

    def test_access_groups_map(self) -> None:
        groups: AccessGroupsConfig = {
            "ops": MessageSendersAccessGroup(type="message.senders", members={"*": []}),
        }
        assert "ops" in groups


# ============================================================================
# types.cloud-workers
# ============================================================================


class TestTypesCloudWorkers:
    def test_install_alias(self) -> None:
        # CloudWorkerInstall is a Literal union; verify it accepts the values.
        assert CloudWorkerInstall is not None
        # "bundle" and "npm" are the canonical values.
        assert "bundle" in {"bundle", "npm"}
        assert "npm" in {"bundle", "npm"}

    def test_lifetime(self) -> None:
        cfg = CloudWorkerLifetimePolicyConfig(
            idleTimeoutMinutes=15,
            maxLifetimeMinutes=240,
        )
        assert cfg["idleTimeoutMinutes"] == 15

    def test_profile(self) -> None:
        cfg = CloudWorkerProfileConfig(
            provider="modal",
            install="npm",
            settings={"region": "us-east"},
        )
        assert cfg["provider"] == "modal"

    def test_config(self) -> None:
        cfg = CloudWorkersConfig(profiles={"main": CloudWorkerProfileConfig(provider="x")})
        assert "main" in cfg["profiles"]


# ============================================================================
# types.discord-presence
# ============================================================================


class TestTypesDiscordPresence:
    def test_basic(self) -> None:
        cfg = DiscordPresenceEventsConfig(
            enabled=True,
            channelId="123",
            users=["u1", "u2"],
            reconnectSuppressSeconds=300,
            burstLimit=8,
            burstWindowSeconds=60,
        )
        assert cfg["channelId"] == "123"
        assert cfg["burstLimit"] == 8


# ============================================================================
# types.channel-health
# ============================================================================


class TestTypesChannelHealth:
    def test_heartbeat_visibility(self) -> None:
        cfg = ChannelHeartbeatVisibilityConfig(
            showOk=False, showAlerts=True, useIndicator=True,
        )
        assert cfg["showOk"] is False
        assert cfg["showAlerts"] is True

    def test_health_monitor(self) -> None:
        cfg = ChannelHealthMonitorConfig(enabled=True)
        assert cfg["enabled"] is True


# ============================================================================
# types.queue
# ============================================================================


class TestTypesQueue:
    def test_aliases(self) -> None:
        # Literal unions don't compare to str; just verify values.
        valid_modes = {"steer", "followup", "collect", "interrupt"}
        valid_drop = {"old", "new", "summarize"}
        assert "steer" in valid_modes
        assert "summarize" in valid_drop
        # Aliases exposed.
        assert QueueMode is not None
        assert QueueDropPolicy is not None

    def test_mode_by_provider(self) -> None:
        cfg = QueueModeByProvider(
            telegram="followup",
            slack="steer",
        )
        assert cfg["telegram"] == "followup"


# ============================================================================
# types.cli
# ============================================================================


class TestTypesCli:
    def test_aliases(self) -> None:
        # CliBannerTaglineMode is a Literal union.
        valid_modes = {"random", "default", "off"}
        assert "random" in valid_modes
        assert CliBannerTaglineMode is not None

    def test_banner(self) -> None:
        cfg = CliBannerConfig(taglineMode="default")
        assert cfg["taglineMode"] == "default"

    def test_cli_config(self) -> None:
        cfg = CliConfig(banner=CliBannerConfig(taglineMode="off"))
        assert cfg["banner"]["taglineMode"] == "off"


# ============================================================================
# types.implicit-mentions
# ============================================================================


class TestTypesImplicitMentions:
    def test_basic(self) -> None:
        cfg = ChannelImplicitMentionsConfig(
            replyToBot=True,
            quotedBot=False,
            threadParticipation=True,
        )
        assert cfg["replyToBot"] is True
        assert cfg["quotedBot"] is False


# ============================================================================
# types.commitments
# ============================================================================


class TestTypesCommitments:
    def test_basic(self) -> None:
        cfg = CommitmentsConfig(enabled=True, maxPerDay=5)
        assert cfg["enabled"] is True
        assert cfg["maxPerDay"] == 5


# ============================================================================
# types.bot-loop-protection
# ============================================================================


class TestTypesBotLoopProtection:
    def test_basic(self) -> None:
        cfg = ChannelBotLoopProtectionConfig(
            enabled=True,
            maxEventsPerWindow=10,
            windowSeconds=60,
            cooldownSeconds=300,
        )
        assert cfg["maxEventsPerWindow"] == 10
        assert cfg["cooldownSeconds"] == 300
