"""jarvis.config.types_openclaw — top-level OpenClaw / JARVIS configuration type.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.openclaw.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
top-level :class:`OpenClawConfig` plus the security / wizard / ui /
update / media / discovery / env shape entries. Cross-references to
sibling config types are preserved as :data:`dict` aliases since the
Python port already exposes the canonical shapes via sibling modules.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Wizard access mode.
WizardAccessMode = Literal["full", "guarded"]


#: Wizard last-run mode.
WizardLastRunMode = Literal["local", "remote"]


#: Update channel.
UpdateChannel = Literal["stable", "extended-stable", "beta", "dev"]


#: UI theme.
UiTheme = Literal["claw", "knot", "dash", "custom"]


#: UI theme mode.
UiThemeMode = Literal["light", "dark", "system"]


#: Text scale percentage stops.
UiTextScale = Literal[90, 100, 110, 125, 140]


#: Chat send shortcut.
UiChatSendShortcut = Literal["enter", "modifier-enter"]


#: Chat follow-up mode.
UiChatFollowUpMode = Literal["steer", "queue"]


#: Install policy supported targets.
InstallPolicyTarget = Literal["skill", "plugin"]


class OpenClawMetaConfig(TypedDict, total=False):
    """Persisted config file metadata."""
    lastTouchedVersion: str
    lastTouchedAt: str
    migrations: dict  # {modelPolicyAllowlist?: true}


class OpenClawShellEnvConfig(TypedDict, total=False):
    """Login-shell env import config."""
    enabled: bool
    timeoutMs: int


class OpenClawEnvConfig(TypedDict, total=False):
    """Inline env config."""
    shellEnv: OpenClawShellEnvConfig
    vars: dict


class OpenClawUpdateAutoConfig(TypedDict, total=False):
    """Auto-update policy."""
    enabled: bool
    stableDelayHours: int
    stableJitterHours: int
    betaCheckIntervalHours: int


class OpenClawUpdateConfig(TypedDict, total=False):
    """Update channel + auto-update policy."""
    channel: str  # UpdateChannel
    checkOnStart: bool
    auto: OpenClawUpdateAutoConfig


class OpenClawUiAssistantConfig(TypedDict, total=False):
    """Assistant display."""
    name: str
    avatar: str


class OpenClawUiPrefsConfig(TypedDict, total=False):
    """Operator display preferences."""
    theme: str  # UiTheme
    themeMode: str  # UiThemeMode
    textScale: int  # UiTextScale
    locale: str
    chatShowThinking: bool
    chatShowToolCalls: bool
    chatPersistCommentary: bool
    chatSendShortcut: str  # UiChatSendShortcut
    chatFollowUpMode: str  # UiChatFollowUpMode


class OpenClawUiConfig(TypedDict, total=False):
    """UI customization."""
    seamColor: str
    assistant: OpenClawUiAssistantConfig
    prefs: OpenClawUiPrefsConfig


class OpenClawTuiFooterConfig(TypedDict, total=False):
    """TUI footer display settings."""
    showRemoteHost: bool


class OpenClawTuiConfig(TypedDict, total=False):
    """TUI display config."""
    footer: OpenClawTuiFooterConfig


class OpenClawMediaConfig(TypedDict, total=False):
    """Media retention config."""
    preserveFilenames: bool
    ttlHours: int


class OpenClawWizardConfig(TypedDict, total=False):
    """Wizard metadata."""
    accessMode: str  # WizardAccessMode
    appRecommendations: bool
    lastRunAt: str
    lastRunVersion: str
    lastRunCommit: str
    lastRunCommand: str
    lastRunMode: str  # WizardLastRunMode
    localModelLeanAutoModel: str
    securityAcknowledgedAt: str


class SecurityAuditSuppression(TypedDict, total=False):
    """One persisted suppression for a known security audit finding."""
    checkId: str
    titleIncludes: str
    detailIncludes: str
    reason: str


class SecurityAuditConfig(TypedDict, total=False):
    """Security audit policy config."""
    suppressions: list  # SecurityAuditSuppression[]


class SecurityInstallPolicyExecConfig(TypedDict, total=False):
    """Trusted local policy command (transport mirrors exec SecretRef provider)."""
    source: str
    command: str
    args: list
    timeoutMs: int
    noOutputTimeoutMs: int
    maxOutputBytes: int
    env: dict
    passEnv: list
    trustedDirs: list
    allowInsecurePath: bool
    allowSymlinkCommand: bool


class SecurityInstallPolicyConfig(TypedDict, total=False):
    """Operator-owned install policy."""
    enabled: bool
    targets: list  # InstallPolicyTarget[]
    exec: SecurityInstallPolicyExecConfig


class OpenClawSecurityConfig(TypedDict, total=False):
    """Security audit suppressions and install policy."""
    audit: SecurityAuditConfig
    installPolicy: SecurityInstallPolicyConfig


class WorktreesCleanupConfig(TypedDict, total=False):
    """Worktree retention limits."""
    maxCount: int
    maxTotalSizeGb: int


class WorktreesConfig(TypedDict, total=False):
    """Worktree retention config."""
    cleanup: WorktreesCleanupConfig


class SurfaceConfigEntry(TypedDict, total=False):
    """Surface-specific config entry."""
    silentReply: dict  # SilentReplyPolicyShape


class OpenClawConfig(TypedDict, total=False):
    """Top-level OpenClaw / JARVIS config."""
    # NOTE: $schema is the JSON-Schema URL field; Python identifiers can't start
    # with `$` so we expose it via a sibling key name (`schemaUrl`) and accept
    # both spellings at runtime.
    schemaUrl: str
    meta: OpenClawMetaConfig
    auth: dict
    accessGroups: dict
    acp: dict
    env: OpenClawEnvConfig
    wizard: OpenClawWizardConfig
    diagnostics: dict
    logging: dict
    audit: dict
    security: OpenClawSecurityConfig
    cli: dict
    systemAgent: dict
    update: OpenClawUpdateConfig
    browser: dict
    ui: OpenClawUiConfig
    tui: OpenClawTuiConfig
    secrets: dict
    marketplaces: dict
    skills: dict
    plugins: dict
    surfaces: dict
    models: dict
    nodeHost: dict
    agents: dict
    tools: dict
    bindings: list
    broadcast: dict
    media: OpenClawMediaConfig
    messages: dict
    commands: dict
    approvals: dict
    session: dict
    web: dict
    channels: dict
    cron: dict
    worktrees: WorktreesConfig
    transcripts: dict
    commitments: dict
    hooks: dict
    discovery: dict
    talk: dict
    gateway: dict
    cloudWorkers: dict
    memory: dict
    mcp: dict
    proxy: dict


#: Config input shape accepted before model provider defaults are fully materialized.
OpenClawConfigInput = dict  # Omit<OpenClawConfig, "models"> & {models?: ModelsConfigInput}


#: Config state brand.
OpenClawConfigStateBrand = str  # "source" | "resolved-source" | "runtime"


class ConfigValidationIssue(TypedDict, total=False):
    """Structured config validation issue."""
    path: str
    pathSegments: list
    message: str
    allowedValues: list
    allowedValuesHiddenCount: int


class LegacyConfigIssue(TypedDict, total=False):
    """Legacy-config detection issue."""
    path: str
    message: str


class ConfigFileSnapshot(TypedDict, total=False):
    """Persisted config file snapshot."""
    path: str
    exists: bool
    raw: object  # str | None
    parsed: object
    sourceConfig: dict  # ResolvedSourceConfig
    resolved: dict  # ResolvedSourceConfig
    valid: bool
    runtimeConfig: dict  # RuntimeConfig
    config: dict  # deprecated alias
    hash: str
    readError: dict
    issues: list  # ConfigValidationIssue[]
    warnings: list  # ConfigValidationIssue[]
    legacyIssues: list  # LegacyConfigIssue[]


__all__ = [
    "WizardAccessMode",
    "WizardLastRunMode",
    "UpdateChannel",
    "UiTheme",
    "UiThemeMode",
    "UiTextScale",
    "UiChatSendShortcut",
    "UiChatFollowUpMode",
    "InstallPolicyTarget",
    "OpenClawMetaConfig",
    "OpenClawShellEnvConfig",
    "OpenClawEnvConfig",
    "OpenClawUpdateAutoConfig",
    "OpenClawUpdateConfig",
    "OpenClawUiAssistantConfig",
    "OpenClawUiPrefsConfig",
    "OpenClawUiConfig",
    "OpenClawTuiFooterConfig",
    "OpenClawTuiConfig",
    "OpenClawMediaConfig",
    "OpenClawWizardConfig",
    "SecurityAuditSuppression",
    "SecurityAuditConfig",
    "SecurityInstallPolicyExecConfig",
    "SecurityInstallPolicyConfig",
    "OpenClawSecurityConfig",
    "WorktreesCleanupConfig",
    "WorktreesConfig",
    "SurfaceConfigEntry",
    "OpenClawConfig",
    "OpenClawConfigInput",
    "OpenClawConfigStateBrand",
    "ConfigValidationIssue",
    "LegacyConfigIssue",
    "ConfigFileSnapshot",
]
