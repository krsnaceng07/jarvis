"""jarvis.config.types_memory — memory config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.memory.ts``.
"""
from __future__ import annotations

from typing import TypedDict


#: Memory backend family selected for retrieval and session memory features.
MemoryBackend = str  # "builtin" | "qmd"
#: Citation rendering mode for memory-injected context.
MemoryCitationsMode = str  # "auto" | "on" | "off"
#: QMD search command flavor used for retrieval.
MemoryQmdSearchMode = str  # "query" | "search" | "vsearch"
#: QMD startup/update scheduling mode.
MemoryQmdStartupMode = str  # "off" | "idle" | "immediate"


class MemoryQmdMcporterConfig(TypedDict, total=False):
    """mcporter daemon integration for long-lived QMD MCP access."""

    enabled: bool
    serverName: str
    startDaemon: bool


class MemoryQmdIndexPath(TypedDict, total=False):
    """Additional QMD index path entry."""

    path: str
    name: str
    pattern: str


class MemoryQmdSessionConfig(TypedDict, total=False):
    """Session export settings for QMD memory indexing."""

    enabled: bool
    exportDir: str
    retentionDays: int


class MemoryQmdUpdateConfig(TypedDict, total=False):
    """Background update and embedding schedule for QMD memory."""

    interval: str
    debounceMs: int
    onBoot: bool
    startup: str
    startupDelayMs: int
    waitForBootSync: bool
    embedInterval: str
    commandTimeoutMs: int
    updateTimeoutMs: int
    embedTimeoutMs: int


class MemoryQmdLimitsConfig(TypedDict, total=False):
    """Retrieval and injection limits for QMD memory results."""

    maxResults: int
    maxSnippetChars: int
    maxInjectedChars: int
    timeoutMs: int


class MemoryQmdConfig(TypedDict, total=False):
    """QMD-specific memory backend config."""

    command: str
    mcporter: MemoryQmdMcporterConfig
    searchMode: str
    rerank: bool
    searchTool: str
    includeDefaultMemory: bool
    paths: list
    sessions: MemoryQmdSessionConfig
    update: MemoryQmdUpdateConfig
    limits: MemoryQmdLimitsConfig
    scope: dict


class MemoryConfig(TypedDict, total=False):
    """Top-level memory config block."""

    backend: str
    citations: str
    qmd: MemoryQmdConfig


__all__ = [
    "MemoryBackend",
    "MemoryCitationsMode",
    "MemoryQmdSearchMode",
    "MemoryQmdStartupMode",
    "MemoryQmdConfig",
    "MemoryQmdMcporterConfig",
    "MemoryQmdIndexPath",
    "MemoryQmdSessionConfig",
    "MemoryQmdUpdateConfig",
    "MemoryQmdLimitsConfig",
    "MemoryConfig",
]
