"""jarvis.config.io — stable public facade for config loading/snapshots/writes.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.ts``.

Focused minimal port: re-exports the public config-IO surface. Heavy
runtime/snapshot work is delegated to caller-provided callables until
the corresponding subsystems land.
"""
from __future__ import annotations

# Re-export selected surface items from the underlying config modules.
from src.config.env_substitution import MissingEnvVarError  # noqa: F401

# CircularIncludeError + ConfigIncludeError live in src.config.includes
# (a future port). For now we provide lightweight placeholders so the
# ``io`` facade can be imported without breaking.
class CircularIncludeError(Exception):
    """Raised when a config include cycle is detected (placeholder)."""


class ConfigIncludeError(Exception):
    """Raised when a config include fails to load (placeholder)."""

# Facade placeholders. The full set of exports lands incrementally as the
# corresponding io.* modules are ported.
def create_config_io(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("createConfigIO facade — install via runtime hooks")


def parse_config_json5(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("parseConfigJson5 facade — install via runtime hooks")


def resolve_config_snapshot_hash(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resolveConfigSnapshotHash facade — install via runtime hooks")


def restore_env_changes_if_unchanged(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("restoreEnvChangesIfUnchanged facade — install via runtime hooks")


def clear_config_cache(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("clearConfigCache facade — install via runtime hooks")


def get_runtime_config(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("getRuntimeConfig facade — install via runtime hooks")


def load_config(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("loadConfig facade — install via runtime hooks")


def preserve_config_snapshot_as_clobbered(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("preserveConfigSnapshotAsClobbered facade — install via runtime hooks")


def promote_config_snapshot_to_last_known_good(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("promoteConfigSnapshotToLastKnownGood facade — install via runtime hooks")


def read_best_effort_config(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readBestEffortConfig facade — install via runtime hooks")


def read_best_effort_config_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readBestEffortConfigSnapshot facade — install via runtime hooks")


def read_config_file_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readConfigFileSnapshot facade — install via runtime hooks")


def read_config_file_snapshot_for_runtime_transaction(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readConfigFileSnapshotForRuntimeTransaction facade")


def read_config_file_snapshot_for_write(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readConfigFileSnapshotForWrite facade — install via runtime hooks")


def read_config_file_snapshot_with_plugin_metadata(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readConfigFileSnapshotWithPluginMetadata facade")


def read_source_config_best_effort(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readSourceConfigBestEffort facade — install via runtime hooks")


def read_source_config_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readSourceConfigSnapshot facade — install via runtime hooks")


def read_source_config_snapshot_for_write(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("readSourceConfigSnapshotForWrite facade")


def recover_config_from_json_root_suffix(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("recoverConfigFromJsonRootSuffix facade")


def recover_config_from_last_known_good(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("recoverConfigFromLastKnownGood facade")


def register_config_write_listener(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("registerConfigWriteListener facade")


def write_config_file(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("writeConfigFile facade — install via runtime hooks")


def project_config_onto_runtime_source_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("projectConfigOntoRuntimeSourceSnapshot facade")


def clear_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("clearRuntimeConfigSnapshot facade")


def get_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("getRuntimeConfigSnapshot facade")


def get_runtime_config_snapshot_metadata(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("getRuntimeConfigSnapshotMetadata facade")


def get_runtime_config_source_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("getRuntimeConfigSourceSnapshot facade")


def register_managed_runtime_config_write_owner(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("registerManagedRuntimeConfigWriteOwner facade")


def reset_config_runtime_state(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resetConfigRuntimeState facade")


def resolve_runtime_config_cache_key(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resolveRuntimeConfigCacheKey facade")


def select_applicable_runtime_config(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("selectApplicableRuntimeConfig facade")


def set_applied_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("setAppliedRuntimeConfigSnapshot facade")


def set_runtime_config_snapshot(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("setRuntimeConfigSnapshot facade")


def set_runtime_config_snapshot_refresh_handler(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("setRuntimeConfigSnapshotRefreshHandler facade")


def resolve_shell_env_expected_keys(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("resolveShellEnvExpectedKeys facade")


__all__ = [
    "MissingEnvVarError",
    "CircularIncludeError",
    "ConfigIncludeError",
    "create_config_io",
    "parse_config_json5",
    "resolve_config_snapshot_hash",
    "restore_env_changes_if_unchanged",
    "clear_config_cache",
    "get_runtime_config",
    "load_config",
    "preserve_config_snapshot_as_clobbered",
    "promote_config_snapshot_to_last_known_good",
    "read_best_effort_config",
    "read_best_effort_config_snapshot",
    "read_config_file_snapshot",
    "read_config_file_snapshot_for_runtime_transaction",
    "read_config_file_snapshot_for_write",
    "read_config_file_snapshot_with_plugin_metadata",
    "read_source_config_best_effort",
    "read_source_config_snapshot",
    "read_source_config_snapshot_for_write",
    "recover_config_from_json_root_suffix",
    "recover_config_from_last_known_good",
    "register_config_write_listener",
    "write_config_file",
    "project_config_onto_runtime_source_snapshot",
    "clear_runtime_config_snapshot",
    "get_runtime_config_snapshot",
    "get_runtime_config_snapshot_metadata",
    "get_runtime_config_source_snapshot",
    "register_managed_runtime_config_write_owner",
    "reset_config_runtime_state",
    "resolve_runtime_config_cache_key",
    "select_applicable_runtime_config",
    "set_applied_runtime_config_snapshot",
    "set_runtime_config_snapshot",
    "set_runtime_config_snapshot_refresh_handler",
    "resolve_shell_env_expected_keys",
]
