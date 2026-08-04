"""jarvis.config.types_browser — browser profile config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.browser.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Profile driver kind.
BrowserProfileDriver = Literal["openclaw", "clawd", "existing-session", "extension"]


class BrowserProfileConfig(TypedDict, total=False):
    cdpPort: int
    cdpUrl: str
    userDataDir: str
    mcpCommand: str
    mcpArgs: list
    driver: str
    headless: bool
    executablePath: str
    attachOnly: bool
    color: str


class BrowserSnapshotDefaults(TypedDict, total=False):
    mode: str  # "efficient"


class BrowserTabCleanupConfig(TypedDict, total=False):
    enabled: bool
    idleMinutes: int
    maxTabsPerSession: int
    sweepMinutes: int


class BrowserSsrfPolicyConfig(TypedDict, total=False):
    dangerouslyAllowPrivateNetwork: bool
    allowedHostnames: list
    hostnameAllowlist: list


class BrowserConfig(TypedDict, total=False):
    enabled: bool
    allowSystemProfileImport: bool
    evaluateEnabled: bool
    cdpUrl: str
    remoteCdpTimeoutMs: int
    remoteCdpHandshakeTimeoutMs: int
    localLaunchTimeoutMs: int
    localCdpReadyTimeoutMs: int
    actionTimeoutMs: int
    color: str
    executablePath: str
    headless: bool
    noSandbox: bool
    attachOnly: bool
    cdpPortRangeStart: int
    defaultProfile: str
    profiles: dict
    snapshotDefaults: BrowserSnapshotDefaults
    tabCleanup: BrowserTabCleanupConfig
    ssrfPolicy: BrowserSsrfPolicyConfig
    extraArgs: list


__all__ = [
    "BrowserProfileDriver",
    "BrowserProfileConfig",
    "BrowserSnapshotDefaults",
    "BrowserTabCleanupConfig",
    "BrowserSsrfPolicyConfig",
    "BrowserConfig",
]
