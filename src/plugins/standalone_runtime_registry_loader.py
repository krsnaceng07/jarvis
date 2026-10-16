"""plugins.standalone_runtime_registry_loader — standalone registry loader seam.

OpenClaw parity: mirrors the startup-time loader that ensures the active
registry exists before provider/channel runtime hooks read from it.
"""
from __future__ import annotations

from typing import Any

from .active_runtime_registry import get_loaded_runtime_plugin_registry
from .runtime_state_key import set_plugin_registry_state

__all__ = ["ensure_standalone_runtime_plugin_registry_loaded"]


def _normalize_required_plugin_ids(params: dict[str, Any] | None) -> list[str]:
    if not isinstance(params, dict):
        return []
    required = params.get("requiredPluginIds")
    if isinstance(required, str):
        required = [required]
    if not isinstance(required, (list, tuple, set)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in required:
        if not isinstance(item, str):
            continue
        plugin_id = item.strip()
        if not plugin_id or plugin_id in seen:
            continue
        seen.add(plugin_id)
        out.append(plugin_id)
    return out


def ensure_standalone_runtime_plugin_registry_loaded(
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Ensure the active registry state is present and populated.

    This is intentionally a compatibility seam: the port does not load a full
    plugin runtime from disk yet, but it does keep the runtime state in the same
    shape that the rest of the provider/channel runtime code expects.
    """
    state = get_loaded_runtime_plugin_registry(params)
    if not isinstance(state, dict):
        return None

    active_registry = state.get("activeRegistry")
    if not isinstance(active_registry, dict):
        active_registry = {}
        state["activeRegistry"] = active_registry

    if not isinstance(active_registry.get("providers"), list):
        active_registry["providers"] = []

    required = _normalize_required_plugin_ids(params)
    for plugin_id in required:
        provider_entries = active_registry["providers"]
        if any(
            isinstance(entry, dict)
            and isinstance(entry.get("provider"), dict)
            and entry["provider"].get("id") == plugin_id
            for entry in provider_entries
        ):
            continue
        provider_entries.append({"provider": {"id": plugin_id}})

    active_registry["pluginIds"] = list(
        dict.fromkeys(
            [
                plugin_id
                for plugin_id in active_registry.get("pluginIds", [])
                if isinstance(plugin_id, str) and plugin_id
            ]
            + required
        )
    )

    set_plugin_registry_state(state)
    return state
