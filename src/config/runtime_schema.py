"""jarvis.config.runtime_schema — runtime config schema defaults builder.

OpenClaw parity: mirrors ``openclaw-main/src/config/runtime-schema.ts``.

Focused minimal port: thin facade with NotImplementedError placeholders.
The schema builder and metadata collectors live in modules that land
separately.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def load_gateway_runtime_config_schema(
    *,
    get_runtime_config_fn: Optional[Callable] = None,
    load_manifest_registry_fn: Optional[Callable] = None,
    build_config_schema_fn: Optional[Callable] = None,
    collect_plugin_schema_metadata_fn: Optional[Callable] = None,
    collect_channel_schema_metadata_fn: Optional[Callable] = None,
) -> Any:
    """Build the config schema from the active runtime config and plugin metadata.

    Mirrors :func:`loadGatewayRuntimeConfigSchema`
    (``shared/config/runtime-schema.ts`).
    """
    if not callable(get_runtime_config_fn) or not callable(build_config_schema_fn):
        raise NotImplementedError("loadGatewayRuntimeConfigSchema requires runtime hooks")
    config = get_runtime_config_fn()
    registry = load_manifest_registry_fn(config) if callable(load_manifest_registry_fn) else None
    return build_config_schema_fn({
        "plugins": collect_plugin_schema_metadata_fn(registry) if callable(collect_plugin_schema_metadata_fn) else [],
        "channels": collect_channel_schema_metadata_fn(registry) if callable(collect_channel_schema_metadata_fn) else [],
    })


async def read_best_effort_runtime_config_schema(
    *,
    read_config_file_snapshot_fn: Optional[Callable] = None,
    load_manifest_registry_fn: Optional[Callable] = None,
    build_config_schema_fn: Optional[Callable] = None,
    collect_plugin_schema_metadata_fn: Optional[Callable] = None,
    collect_channel_schema_metadata_fn: Optional[Callable] = None,
) -> Any:
    """Best-effort async variant for setup/onboarding flows.

    Mirrors :func:`readBestEffortRuntimeConfigSchema`
    (``shared/config/runtime-schema.ts`).
    """
    if not callable(read_config_file_snapshot_fn) or not callable(build_config_schema_fn):
        raise NotImplementedError("readBestEffortRuntimeConfigSchema requires runtime hooks")
    snapshot = await read_config_file_snapshot_fn()
    config = snapshot.get("config") if (isinstance(snapshot, dict) and snapshot.get("valid")) else {"plugins": {"enabled": True}}
    registry = load_manifest_registry_fn(config) if callable(load_manifest_registry_fn) else None
    return build_config_schema_fn({
        "plugins": (
            collect_plugin_schema_metadata_fn(registry)
            if isinstance(snapshot, dict) and snapshot.get("valid") and callable(collect_plugin_schema_metadata_fn)
            else []
        ),
        "channels": (
            collect_channel_schema_metadata_fn(registry)
            if callable(collect_channel_schema_metadata_fn)
            else []
        ),
    })


__all__ = [
    "load_gateway_runtime_config_schema",
    "read_best_effort_runtime_config_schema",
]
