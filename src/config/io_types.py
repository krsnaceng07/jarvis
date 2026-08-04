"""jarvis.config.io_types — config-IO runtime type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.types.ts``.

Focused minimal port: exposes the public config-IO type surface. The
error class is a small Python class; everything else is a TypedDict or
type alias.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal, TypedDict


#: JSON5 parse outcome.
ParseConfigJson5Result = dict  # {ok: True, parsed} | {ok: False, error}


class ConfigWriteResult(TypedDict, total=False):
    persistedHash: str
    persistedConfig: dict


#: Symbol used to attach a post-commit rollback hook to a write result.
config_write_post_commit_rollback = "configWritePostCommitRollback"


class InternalConfigWriteResult(ConfigWriteResult, total=False):
    configWritePostCommitRollback: Callable[[], None]


#: Audit origin label for config writes.
ConfigWriteAuditOrigin = Literal["doctor", "system-agent", "config-rpc", "plugin-install", "cli"]


class ConfigWriteOptions(TypedDict, total=False):
    auditOrigin: str
    envSnapshotForRestore: dict
    expectedConfigPath: str
    ownedConfigPathForWrite: str
    assertConfigPathForWrite: Callable[[], None]
    unsetPaths: list
    explicitSetPaths: list
    explicitSetValueSource: dict
    baseSnapshot: dict
    basePluginMetadataSnapshot: dict
    skipRuntimeSnapshotRefresh: bool
    runtimeRefresh: dict
    allowDestructiveWrite: bool
    allowConfigSizeDrop: bool
    skipOutputLogs: bool
    afterWrite: dict
    preservedLegacyRootKeys: list
    skipPluginValidation: bool
    lastTouchedVersionOverride: str
    preCommitRuntimePreflight: Callable[[dict], Awaitable[Any]]
    includeFileHashesForWrite: dict
    includeFileTargetsForWrite: dict


class ReadConfigFileSnapshotForWriteResult(TypedDict, total=False):
    snapshot: dict
    writeOptions: ConfigWriteOptions


#: Type alias for config-write notifications.
ConfigWriteNotification = dict
#: Async measure wrapper around a named run.
ConfigSnapshotReadMeasure = Callable[[str, Callable[[], Any]], Awaitable[Any]]


class ConfigRuntimeRefreshError(Exception):
    """Raised when a config runtime refresh fails.

    Mirrors :class:`ConfigRuntimeRefreshError`
    (``shared/config/io.types.ts`).
    """

    def __init__(self, message: str, *, cause: Any = None) -> None:
        super().__init__(message)
        self.name = "ConfigRuntimeRefreshError"
        if cause is not None:
            self.__cause__ = cause


class ConfigIoDeps(TypedDict, total=False):
    """Injectable dependencies for config-IO operations."""

    fs: Any
    json5: Any
    env: dict
    lowerPrecedenceEnv: dict
    homedir: Callable[[], str]
    configPath: str
    logger: Any
    measure: ConfigSnapshotReadMeasure
    suppressFutureVersionWarning: bool
    observe: bool


class NormalizedConfigIoDeps(TypedDict, total=False):
    fs: Any
    json5: Any
    env: dict
    lowerPrecedenceEnv: dict
    homedir: Callable[[], str]
    configPath: str
    logger: Any
    measure: ConfigSnapshotReadMeasure
    suppressFutureVersionWarning: bool
    observe: bool


class ConfigIoFactoryOptions(ConfigIoDeps, total=False):
    pluginValidation: str
    preservedLegacyRootKeys: list
    shellEnvFallback: str


class ConfigSnapshotReadOptions(TypedDict, total=False):
    measure: ConfigSnapshotReadMeasure
    observe: bool
    isolateEnv: bool
    lowerPrecedenceEnv: dict
    recoverSuspicious: bool
    allowSuspiciousRecovery: Callable[[dict, dict], Any]
    skipPluginValidation: bool
    preservedLegacyRootKeys: list
    suppressFutureVersionWarning: bool


class ReadConfigFileSnapshotInternalResult(TypedDict, total=False):
    snapshot: dict
    envSnapshotForRestore: dict
    includeFileHashesForWrite: dict
    includeFileTargetsForWrite: dict
    pluginMetadataSnapshot: dict


class ReadConfigFileSnapshotWithPluginMetadataResult(TypedDict, total=False):
    snapshot: dict
    pluginMetadataSnapshot: dict


class BestEffortConfigSnapshot(TypedDict, total=False):
    config: dict
    sourceConfig: dict


ShippedPluginInstallConfigWriteMigration = dict
ShippedPluginInstallConfigReadMigration = dict


__all__ = [
    "ParseConfigJson5Result",
    "ConfigWriteResult",
    "config_write_post_commit_rollback",
    "InternalConfigWriteResult",
    "ConfigWriteAuditOrigin",
    "ConfigWriteOptions",
    "ReadConfigFileSnapshotForWriteResult",
    "ConfigWriteNotification",
    "ConfigSnapshotReadMeasure",
    "ConfigRuntimeRefreshError",
    "ConfigIoDeps",
    "NormalizedConfigIoDeps",
    "ConfigIoFactoryOptions",
    "ConfigSnapshotReadOptions",
    "ReadConfigFileSnapshotInternalResult",
    "ReadConfigFileSnapshotWithPluginMetadataResult",
    "BestEffortConfigSnapshot",
    "ShippedPluginInstallConfigWriteMigration",
    "ShippedPluginInstallConfigReadMigration",
]
