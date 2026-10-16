"""jarvis.config.plugin_auto_enable_apply — apply plugin auto-enable pass.

OpenClaw parity: mirrors
``openclaw-main/src/config/plugin-auto-enable.apply.ts``.

Focused minimal port: thin facade. The real pass walks the candidate
list returned by ``detect_plugin_auto_enable_candidates`` and writes
the new ``config.plugins.entries[id].enabled = true`` only when
onboarding is allowed. Heavy logic is delegated to caller-provided
callables.
"""
from __future__ import annotations

from typing import Callable, Optional

from src.config.plugin_auto_enable_detect import detect_plugin_auto_enable_candidates
from src.config.plugin_auto_enable_types import PluginAutoEnableResult


def apply_plugin_auto_enable(params: dict) -> dict:
    """Run an auto-enable pass and return the new config + change log.

    Mirrors :func:`applyPluginAutoEnable`
    (``shared/config/plugin-auto-enable.apply.ts`).
    """
    config = params.get("config")
    if not isinstance(config, dict):
        return {"config": config, "changes": [], "autoEnabledReasons": {}}
    env = params.get("env")
    manifest_registry = params.get("manifestRegistry")
    discovery = params.get("discovery")
    resolve_reasons_fn: Optional[Callable] = params.get("resolve_plugin_auto_enable_candidate_reason_fn")
    candidates = detect_plugin_auto_enable_candidates(
        config=config, env=env, manifest_registry=manifest_registry, discovery=discovery,
    )
    changes: list = []
    auto_enabled: dict = {}
    next_config: dict = dict(config)
    plugins = dict(next_config.get("plugins") or {})
    entries = dict(plugins.get("entries") or {})
    for c in candidates or []:
        if not isinstance(c, dict):
            continue
        plugin_id = c.get("pluginId")
        if not isinstance(plugin_id, str) or not plugin_id:
            continue
        entry = dict(entries.get(plugin_id) or {})
        if entry.get("enabled") is True:
            continue
        entry["enabled"] = True
        entries[plugin_id] = entry
        if callable(resolve_reasons_fn):
            reason = resolve_reasons_fn(c)
        else:
            reason = c.get("kind") or "auto-enabled"
        changes.append(f"enabled {plugin_id}")
        auto_enabled[plugin_id] = list(auto_enabled.get(plugin_id, [])) + [reason]
    if changes:
        plugins["entries"] = entries
        next_config["plugins"] = plugins
    return PluginAutoEnableResult(
        config=next_config,
        changes=changes,
        autoEnabledReasons=auto_enabled,
    )


__all__ = ["apply_plugin_auto_enable"]
