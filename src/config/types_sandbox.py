"""jarvis.config.types_sandbox — sandbox execution config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.sandbox.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class SandboxUlimitEntry(TypedDict, total=False):
    soft: int
    hard: int


#: ulimit value can be a string "soft:hard", a number, or a structured entry.
SandboxUlimitValue = object  # str | int | SandboxUlimitEntry


class SandboxDockerSettings(TypedDict, total=False):
    image: str
    containerPrefix: str
    workdir: str
    readOnlyRoot: bool
    tmpfs: list
    network: str
    user: str
    capDrop: list
    env: dict
    setupCommand: str
    pidsLimit: int
    memory: object
    memorySwap: object
    cpus: int
    gpus: str
    ulimits: dict
    seccompProfile: str
    apparmorProfile: str
    dns: list
    extraHosts: list
    binds: list
    dangerouslyAllowReservedContainerTargets: bool
    dangerouslyAllowExternalBindSources: bool
    dangerouslyAllowContainerNamespaceJoin: bool


class SandboxBrowserSettings(TypedDict, total=False):
    enabled: bool
    image: str
    containerPrefix: str
    network: str
    cdpPort: int
    cdpSourceRange: str
    vncPort: int
    noVncPort: int
    headless: bool
    enableNoVnc: bool
    allowHostControl: bool
    autoStart: bool
    autoStartTimeoutMs: int
    binds: list


class SandboxPruneSettings(TypedDict, total=False):
    idleHours: int
    maxAgeDays: int


class SandboxSshSettings(TypedDict, total=False):
    target: str
    command: str
    workspaceRoot: str
    strictHostKeyChecking: bool
    updateHostKeys: bool
    identityFile: str
    certificateFile: str
    knownHostsFile: str
    identityData: object
    certificateData: object
    knownHostsData: object


__all__ = [
    "SandboxUlimitEntry",
    "SandboxUlimitValue",
    "SandboxDockerSettings",
    "SandboxBrowserSettings",
    "SandboxPruneSettings",
    "SandboxSshSettings",
]
