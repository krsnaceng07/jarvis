"""jarvis.config.materialize — config materialization pipeline.

OpenClaw parity: mirrors
``openclaw-main/src/config/materialize.ts``.

Focused minimal port: the public surface accepts a config and a
materialization mode, and applies the per-mode profile selection. The
actual default-applier functions are delegated to caller-provided
callables until those subsystems land.
"""
from __future__ import annotations

from typing import Callable, Literal

MaterializationMode = Literal["load", "missing", "snapshot"]


_MATERIALIZATION_PROFILES = {
    "load": {
        "includeCompactionDefaults": True,
        "includeContextPruningDefaults": True,
        "includeLoggingDefaults": True,
        "normalizePaths": True,
    },
    "missing": {
        "includeCompactionDefaults": True,
        "includeContextPruningDefaults": True,
        "includeLoggingDefaults": False,
        "normalizePaths": False,
    },
    "snapshot": {
        "includeCompactionDefaults": False,
        "includeContextPruningDefaults": False,
        "includeLoggingDefaults": True,
        "normalizePaths": True,
    },
}


def as_resolved_source_config(config) -> dict:
    return config


def as_runtime_config(config) -> dict:
    return config


def materialize_runtime_config(
    config: dict,
    mode: MaterializationMode,
    options: Optional[dict] = None,
    *,
    apply_message_defaults: Optional[Callable[[dict], dict]] = None,
    apply_logging_defaults: Optional[Callable[[dict], dict]] = None,
    apply_session_defaults: Optional[Callable[[dict], dict]] = None,
    apply_agent_defaults: Optional[Callable[[dict], dict]] = None,
    apply_cron_defaults: Optional[Callable[[dict], dict]] = None,
    apply_context_pruning_defaults: Optional[Callable[[dict], dict]] = None,
    apply_compaction_defaults: Optional[Callable[[dict], dict]] = None,
    apply_model_defaults: Optional[Callable[[dict, dict], dict]] = None,
    apply_talk_config_normalization: Optional[Callable[[dict], dict]] = None,
    normalize_config_paths_fn: Optional[Callable[[dict], dict]] = None,
    normalize_exec_safe_bin_profiles_in_config: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Materialize a config to runtime-ready settings.

    Mirrors :func:`materializeRuntimeConfig`
    (``shared/config/materialize.ts`).
    """
    options = options or {}
    profile = _MATERIALIZATION_PROFILES.get(mode, _MATERIALIZATION_PROFILES["load"])
    next_config = config
    if callable(apply_message_defaults):
        next_config = apply_message_defaults(next_config)
    if profile.get("includeLoggingDefaults") and callable(apply_logging_defaults):
        next_config = apply_logging_defaults(next_config)
    if callable(apply_session_defaults):
        next_config = apply_session_defaults(next_config)
    if callable(apply_agent_defaults):
        next_config = apply_agent_defaults(next_config)
    if callable(apply_cron_defaults):
        next_config = apply_cron_defaults(next_config)
    if profile.get("includeContextPruningDefaults") and callable(apply_context_pruning_defaults):
        next_config = apply_context_pruning_defaults(
            next_config, {"manifestRegistry": options.get("manifestRegistry")}
        )
    if profile.get("includeCompactionDefaults") and callable(apply_compaction_defaults):
        next_config = apply_compaction_defaults(next_config)
    if callable(apply_model_defaults):
        next_config = apply_model_defaults(
            next_config,
            {
                "manifestRegistry": options.get("manifestRegistry"),
                "loadManifestRegistry": options.get("loadManifestRegistry"),
            },
        )
    if callable(apply_talk_config_normalization):
        next_config = apply_talk_config_normalization(next_config)
    if profile.get("normalizePaths") and callable(normalize_config_paths_fn):
        normalize_config_paths_fn(next_config)
    if callable(normalize_exec_safe_bin_profiles_in_config):
        normalize_exec_safe_bin_profiles_in_config(next_config)
    return as_runtime_config(next_config)


__all__ = [
    "MaterializationMode",
    "as_resolved_source_config",
    "as_runtime_config",
    "materialize_runtime_config",
]
