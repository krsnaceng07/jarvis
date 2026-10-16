"""plugins.active_runtime_registry — active runtime registry state seam.

OpenClaw parity: mirrors the active runtime registry loader used by
provider/channel runtime discovery. The Python port keeps the same
process-global state slot under :mod:`src.plugins.runtime_state_key` and
reuses the live state if it is already populated.
"""
from __future__ import annotations

from typing import Any

from .runtime_state_key import get_plugin_registry_state, set_plugin_registry_state

__all__ = ["get_loaded_runtime_plugin_registry"]


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


def get_loaded_runtime_plugin_registry(
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the active runtime registry state for the required plugin ids.

    The loader is intentionally lightweight: when the process-global state is
    absent, it creates the same ``{"activeRegistry": {"providers": ...}}
    structure that the provider-thinking active lookup expects.
    """
    base = get_plugin_registry_state() or {}
    if not isinstance(base, dict):
        base = {}

    active_registry = base.get("activeRegistry")
    if not isinstance(active_registry, dict):
        active_registry = {}
        base["activeRegistry"] = active_registry

    if not isinstance(active_registry.get("providers"), list):
        active_registry["providers"] = []

    required = _normalize_required_plugin_ids(params)
    if required:
        existing_ids = [
            plugin_id
            for plugin_id in active_registry.get("pluginIds", [])
            if isinstance(plugin_id, str) and plugin_id
        ]
        merged_ids: list[str] = []
        seen: set[str] = set()
        for plugin_id in [*existing_ids, *required]:
            if plugin_id and plugin_id not in seen:
                seen.add(plugin_id)
                merged_ids.append(plugin_id)
        active_registry["pluginIds"] = merged_ids

    set_plugin_registry_state(base)
    return base
