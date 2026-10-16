"""jarvis.plugins.plugin_config — plugin configuration normalization and activation policy.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/config-state.ts``,
``openclaw-main/src/plugins/config-activation-shared.ts``, and
``openclaw-main/src/plugins/activation-planner.ts``.

Features:
- Global `plugins.enabled` flag (default True).
- `plugins.deny` list (always overrides allow and per-plugin settings).
- `plugins.allow` list (exclusive allowlist when configured).
- `plugins.entries.<id>` per-plugin config (`enabled`, `config`).
- `plugins.slots.<slot>` exclusive category slot selection (`memory`, `contextEngine`).
- `is_plugin_enabled()`: Determines effective plugin enablement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginEntryConfig:
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedPluginsConfig:
    enabled: bool = True
    allow: list[str] | None = None
    deny: list[str] = field(default_factory=list)
    slots: dict[str, str] = field(default_factory=dict)
    load_paths: list[str] = field(default_factory=list)
    entries: dict[str, PluginEntryConfig] = field(default_factory=dict)


def normalize_plugins_config(cfg: dict[str, Any] | None) -> NormalizedPluginsConfig:
    """Normalize the raw `plugins` section of config into NormalizedPluginsConfig."""
    if not cfg or not isinstance(cfg, dict):
        return NormalizedPluginsConfig()

    p_block = cfg.get("plugins")
    if not isinstance(p_block, dict):
        return NormalizedPluginsConfig()

    global_enabled = p_block.get("enabled", True)
    if not isinstance(global_enabled, bool):
        global_enabled = True

    allow_list: list[str] | None = None
    if "allow" in p_block and isinstance(p_block["allow"], list):
        allow_list = [str(x).strip().lower() for x in p_block["allow"] if str(x).strip()]

    deny_list: list[str] = []
    if "deny" in p_block and isinstance(p_block["deny"], list):
        deny_list = [str(x).strip().lower() for x in p_block["deny"] if str(x).strip()]

    slots: dict[str, str] = {}
    if "slots" in p_block and isinstance(p_block["slots"], dict):
        for k, v in p_block["slots"].items():
            if isinstance(v, str) and v.strip():
                slots[str(k).strip()] = str(v).strip().lower()

    load_paths: list[str] = []
    if "load" in p_block and isinstance(p_block["load"], dict):
        paths = p_block["load"].get("paths")
        if isinstance(paths, list):
            load_paths = [str(p) for p in paths if str(p)]

    entries: dict[str, PluginEntryConfig] = {}
    if "entries" in p_block and isinstance(p_block["entries"], dict):
        for plugin_id, val in p_block["entries"].items():
            norm_id = str(plugin_id).strip().lower()
            if isinstance(val, dict):
                ent_enabled = val.get("enabled", True)
                ent_cfg = val.get("config") if isinstance(val.get("config"), dict) else {}
                entries[norm_id] = PluginEntryConfig(
                    enabled=bool(ent_enabled),
                    config=ent_cfg,
                )

    return NormalizedPluginsConfig(
        enabled=global_enabled,
        allow=allow_list,
        deny=deny_list,
        slots=slots,
        load_paths=load_paths,
        entries=entries,
    )


def is_plugin_enabled(
    plugin_id: str,
    norm_cfg: NormalizedPluginsConfig,
    is_bundled: bool = False,
) -> bool:
    """Determine whether a plugin is enabled under OpenClaw policy rules.

    Rules:
    1. If global `plugins.enabled` is False, non-bundled plugins are disabled.
    2. `plugins.deny` list ALWAYS overrides allow and per-plugin settings.
    3. `plugins.entries.<id>.enabled: False` explicitly disables that plugin.
    4. If `plugins.allow` is configured, plugin_id MUST be in allow (unless slot selection force-activates it).
    """
    norm_id = plugin_id.strip().lower()

    # Rule 1: Global disable
    if not norm_cfg.enabled and not is_bundled:
        return False

    # Rule 2: Deny list precedence
    if norm_id in norm_cfg.deny:
        return False

    # Rule 3: Per-plugin entry disable
    if norm_id in norm_cfg.entries:
        if not norm_cfg.entries[norm_id].enabled:
            return False

    # Check slot force-activation
    is_slot_active = any(s_val == norm_id for s_val in norm_cfg.slots.values())
    if is_slot_active:
        return True

    # Rule 4: Allowlist restriction
    if norm_cfg.allow is not None:
        if norm_id not in norm_cfg.allow:
            return False

    return True


__all__ = [
    "NormalizedPluginsConfig",
    "PluginEntryConfig",
    "is_plugin_enabled",
    "normalize_plugins_config",
]
