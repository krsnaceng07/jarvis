"""plugins.memory_runtime — runtime bridge for plugin-owned memory hooks.

OpenClaw parity: 1:1 port of ``src/plugins/memory-runtime.ts``.

Runtime bridge for plugin-owned memory hooks and state.

Port seams (documented, ImportError-guarded):

- ``getLoadedRuntimePluginRegistry`` (``active-runtime-registry.ts``) and
  ``ensureStandaloneRuntimePluginRegistryLoaded``
  (``runtime/standalone-runtime-registry-loader.ts``) are not ported yet.
  ``_ensure_memory_runtime`` routes through seams that no-op when the
  loaders are absent — matching the source behavior when no plugin loads
  a memory runtime (``getMemoryRuntime()`` stays ``None`` and callers get
  the "memory plugin unavailable" result).
- ``resolveUserPath`` (``infra/home-dir.ts``) — home-relative expansion +
  absolutization via ``os.path`` (the source resolves against the
  effective home dir and returns an absolute path).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from jarvis_sdk.agent_runtime import resolve_agent_workspace_dir
from jarvis_sdk.plugin_config import normalize_plugins_config

from src.routing.agent_scope import resolve_default_agent_id

from .memory_state import get_memory_runtime
from .slots import default_slot_id_for_key

__all__ = [
    "get_active_memory_search_manager",
    "resolve_active_memory_backend_config",
    "close_active_memory_search_managers",
    "close_active_memory_search_manager",
]


def _resolve_user_path(value: str) -> str:
    """Mirrors ``resolveUserPath`` (``infra/home-dir.ts:147-156``):
    empty → "", else expand ``~`` and absolutize."""
    if not value:
        return ""
    return os.path.abspath(os.path.expanduser(value))


def _get_loaded_runtime_plugin_registry(params: dict) -> Any:
    """Seam for ``getLoadedRuntimePluginRegistry``
    (``active-runtime-registry.ts``, unported)."""
    try:  # pragma: no cover - exercised once the loader lands
        from .active_runtime_registry import (  # type: ignore[attr-defined]
            get_loaded_runtime_plugin_registry,
        )
    except ImportError:
        return None
    return get_loaded_runtime_plugin_registry(params)


def _ensure_standalone_runtime_plugin_registry_loaded(params: dict) -> Any:
    """Seam for ``ensureStandaloneRuntimePluginRegistryLoaded``
    (``runtime/standalone-runtime-registry-loader.ts``, unported)."""
    try:  # pragma: no cover - exercised once the loader lands
        from .standalone_runtime_registry_loader import (  # type: ignore[attr-defined]
            ensure_standalone_runtime_plugin_registry_loaded,
        )
    except ImportError:
        return None
    return ensure_standalone_runtime_plugin_registry_loaded(params)


def _normalize_memory_slot_value(value: Any) -> Any:
    """Mirrors ``normalizeSlotValue`` (config-normalization-shared.ts:62-71):
    empty/non-string → ``_UNSET``, "none" (case-insensitive) → ``None``
    (disabled), else the trimmed string."""
    trimmed = value.strip() if isinstance(value, str) else ""
    if not trimmed:
        return _UNSET
    if trimmed.lower() == "none":
        return None
    return trimmed


_UNSET = object()


def _resolve_memory_runtime_plugin_ids(config: dict) -> list[str]:
    """Resolves the configured memory slot to the single runtime plugin
    that may load memory.

    Mirrors ``resolveMemoryRuntimePluginIds`` (memory-runtime.ts:11-22).

    Port note: the source calls ``normalizePluginsConfig`` from
    ``config-state.ts``, whose slot normalization defaults an unset
    memory slot to ``defaultSlotIdForKey("memory")`` ("memory-core")
    and maps "none" → ``null`` (config-normalization-shared.ts:232-241).
    ``jarvis_sdk.plugin_config.normalize_plugins_config`` copies slots
    verbatim, so that slot normalization is applied here.
    """
    plugins = normalize_plugins_config((config or {}).get("plugins"))
    memory_slot = _normalize_memory_slot_value(plugins.slots.get("memory"))
    if memory_slot is _UNSET:
        memory_slot = default_slot_id_for_key("memory")
    if (
        not plugins.enabled
        or not isinstance(memory_slot, str)
        or not memory_slot.strip()
    ):
        return []
    plugin_id = memory_slot.strip()
    if plugin_id in plugins.deny or (
        (plugins.entries.get(plugin_id) or {}).get("enabled") is False
    ):
        return []
    return [plugin_id]


def _resolve_memory_runtime_workspace_dir(cfg: dict) -> Optional[str]:
    """Mirrors ``resolveMemoryRuntimeWorkspaceDir`` (memory-runtime.ts:24-31)."""
    agent_id = resolve_default_agent_id(cfg)
    dir_ = resolve_agent_workspace_dir(cfg, agent_id)
    if not isinstance(dir_, str) or not dir_.strip():
        return None
    return _resolve_user_path(dir_)


def _ensure_memory_runtime(cfg: dict | None = None) -> Any:
    """Mirrors ``ensureMemoryRuntime`` (memory-runtime.ts:33-56)."""
    current = get_memory_runtime()
    if current or not cfg:
        return current
    only_plugin_ids = _resolve_memory_runtime_plugin_ids(cfg)
    if not only_plugin_ids:
        return get_memory_runtime()
    _get_loaded_runtime_plugin_registry({"requiredPluginIds": only_plugin_ids})
    if get_memory_runtime():
        return get_memory_runtime()
    workspace_dir = _resolve_memory_runtime_workspace_dir(cfg)
    _ensure_standalone_runtime_plugin_registry_loaded(
        {
            "requiredPluginIds": only_plugin_ids,
            "loadOptions": {
                "config": cfg,
                "onlyPluginIds": only_plugin_ids,
                "workspaceDir": workspace_dir,
            },
        }
    )
    return get_memory_runtime()


async def get_active_memory_search_manager(params: dict) -> dict:
    """Returns the active plugin-backed memory search manager for an agent.

    Mirrors ``getActiveMemorySearchManager`` (memory-runtime.ts:59-69).
    ``params`` keys: ``cfg``, ``agentId``, ``purpose``?
    ("default" | "status" | "cli").
    """
    runtime = _ensure_memory_runtime(params.get("cfg"))
    if not runtime:
        return {"manager": None, "error": "memory plugin unavailable"}
    return await runtime.get_memory_search_manager(params)


def resolve_active_memory_backend_config(params: dict) -> Any:
    """Resolves current memory backend config without constructing a manager.

    Mirrors ``resolveActiveMemoryBackendConfig`` (memory-runtime.ts:72-74).
    ``params`` keys: ``cfg``, ``agentId``.
    """
    runtime = _ensure_memory_runtime(params.get("cfg"))
    if runtime is None:
        return None
    result = runtime.resolve_memory_backend_config(params)
    return result if result is not None else None


async def close_active_memory_search_managers(
    cfg: dict | None = None,
) -> None:
    """Closes all active plugin-backed memory search managers.

    Mirrors ``closeActiveMemorySearchManagers`` (memory-runtime.ts:77-81).
    """
    _ = cfg
    runtime = get_memory_runtime()
    if runtime is None:
        return
    close_all = getattr(runtime, "close_all_memory_search_managers", None)
    if close_all is None:
        return
    await close_all()


async def close_active_memory_search_manager(params: dict) -> None:
    """Closes the plugin-backed memory search manager for one agent.

    Mirrors ``closeActiveMemorySearchManager`` (memory-runtime.ts:84-90).
    ``params`` keys: ``cfg``, ``agentId``.
    """
    runtime = get_memory_runtime()
    if runtime is None:
        return
    close_one = getattr(runtime, "close_memory_search_manager", None)
    if close_one is None:
        return
    await close_one(params)
