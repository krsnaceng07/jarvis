"""jarvis_sdk.plugin_config — live plugin config resolution.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/plugin-config-runtime``'s
``resolveLivePluginConfigObject``,
``resolvePluginConfigObject``, and ``normalizePluginsConfig``.

Used by extensions that want their config to follow the
host's live config (the user can edit ``config/jarvis.json``
and the change should be visible on the next turn without a
restart). ``active-memory`` is the canonical consumer.

Architecture
============
The OpenClaw pattern is: a "live config" supplier is a
zero-arg callable that returns the most recent config.
The plugin's effective config is ``merge(plugin_static,
live_plugin_config)`` — static defaults + live overrides.

The Python port mirrors this with:
- ``resolve_live_plugin_config_object(live_config_supplier,
  plugin_id, plugin_static_config)`` — merged dict.
- ``resolve_plugin_config_object(config, plugin_id)`` —
  read-only view of a single plugin's entry from a config
  dict (no merging).
- ``normalize_plugins_config(plugins)`` — defends against
  the malformed-config cases OpenClaw documents (missing
  entries dict, missing enabled flag, unknown shape) and
  returns a fully-shaped ``PluginsConfig`` with ``enabled``,
  ``allow``, ``deny``, ``entries``, and ``slots``.

Parity
======
- ``resolve_live_plugin_config_object(supplier, plugin_id, static)``
  → ``dict | None``.
- ``resolve_plugin_config_object(config, plugin_id)`` →
  ``dict | None`` (the raw ``plugins.entries.<id>`` entry, or
  ``None``).
- ``normalize_plugins_config(plugins)`` → ``PluginsConfig``
  with ``enabled`` (bool), ``allow`` (list[str]),
  ``deny`` (list[str]), ``entries`` (dict[str, dict]),
  ``slots`` (dict[str, str]).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

PluginConfigMap = dict[str, Any]

if TYPE_CHECKING:
    from collections.abc import Callable


# ruff: noqa: PLR0911
# Each early return handles a specific failure mode (no
# supplier, supplier raises, config malformed, plugin id
# missing, plugin config malformed). The returns make the
# failure surface explicit in the test suite.


def resolve_live_plugin_config_object(
    get_config: Callable[[], dict[str, Any] | None] | None,
    plugin_id: str,
    static_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the live plugin config, merged with static defaults.

    Mirrors ``openclaw/plugin-sdk/plugin-config-runtime``'s
    ``resolveLivePluginConfigObject``. Used by extensions
    that want to follow the host's live config (so a user
    editing ``config/jarvis.json`` sees the change without a
    restart).

    Returns ``None`` if no live config is available (caller
    should fall back to static). Otherwise returns a merged
    dict: live overrides win over static.
    """
    if get_config is None:
        return None
    try:
        live = get_config()
    except Exception:
        return None
    if not isinstance(live, dict):
        return None
    live_config = cast(PluginConfigMap, live)
    plugins_raw = live_config.get("plugins")
    plugins = cast(PluginConfigMap | None, plugins_raw if isinstance(plugins_raw, dict) else None)
    if not plugins:
        return None
    plugins_config = cast(PluginConfigMap, plugins)
    entries_raw = plugins_config.get("entries")
    entries = cast(PluginConfigMap | None, entries_raw if isinstance(entries_raw, dict) else None)
    if not isinstance(entries, dict):
        return None
    entries_config = cast(PluginConfigMap, entries)
    live_plugin = entries_config.get(plugin_id)
    if not isinstance(live_plugin, dict):
        return None
    live_plugin = cast(PluginConfigMap, live_plugin)

    # Merge: static first, then live overrides. Live wins.
    merged: dict[str, Any] = {}
    if isinstance(static_config, dict):
        merged.update(static_config)
    merged.update(live_plugin)
    return merged


def resolve_plugin_config_object(
    config: Any,
    plugin_id: str,
) -> dict[str, Any] | None:
    """Return the plugin's effective config (or the entry itself).

    Mirrors ``openclaw/plugin-sdk/plugin-config-runtime``'s
    ``resolvePluginConfigObject``. Returns the ``entry.config``
    sub-key when present (the modern shape); otherwise
    returns the entry itself (the legacy shape). Returns
    ``None`` if the config is malformed or the plugin has
    no entry.
    """
    if not isinstance(config, dict):
        return None
    config_map = cast(PluginConfigMap, config)
    plugins = config_map.get("plugins")
    if not isinstance(plugins, dict):
        return None
    plugins_map = cast(PluginConfigMap, plugins)
    entries = plugins_map.get("entries")
    if not isinstance(entries, dict):
        return None
    entries_map = cast(PluginConfigMap, entries)
    entry = entries_map.get(plugin_id)
    if not isinstance(entry, dict):
        return None
    entry_map = cast(PluginConfigMap, entry)
    inner = entry_map.get("config")
    return (
        cast(dict[str, Any], inner) if isinstance(inner, dict) else cast(dict[str, Any], entry_map)
    )


@dataclass(frozen=True, slots=True)
class PluginsConfig:
    """Normalized shape of ``config.plugins``.

    Mirrors OpenClaw's normalized plugins config. Always safe
    to read fields on, even when the source config was
    malformed.
    """

    enabled: bool = True
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    slots: dict[str, str] = field(default_factory=dict)


def normalize_plugins_config(plugins: Any) -> PluginsConfig:
    """Defensively normalize ``config.plugins`` into a typed shape.

    Mirrors ``openclaw/plugin-sdk/plugin-config-runtime``'s
    ``normalizePluginsConfig``. Returns a ``PluginsConfig``
    with safe defaults; never raises on bad input.
    """
    if not isinstance(plugins, dict):
        return PluginsConfig()
    plugins_config = cast(dict[str, object], plugins)
    raw_enabled = plugins_config.get("enabled")
    enabled = True if raw_enabled is None else bool(raw_enabled) is True
    raw_allow = plugins_config.get("allow")
    allow = (
        tuple(sorted({str(x).strip() for x in raw_allow if isinstance(x, str) and x.strip()}))
        if isinstance(raw_allow, list | tuple)
        else ()
    )
    raw_deny = plugins_config.get("deny")
    deny = (
        tuple(sorted({str(x).strip() for x in raw_deny if isinstance(x, str) and x.strip()}))
        if isinstance(raw_deny, list | tuple)
        else ()
    )
    raw_entries = plugins_config.get("entries")
    entries: dict[str, dict[str, Any]] = {}
    if isinstance(raw_entries, dict):
        raw_entries_map = cast(PluginConfigMap, raw_entries)
        for key, value in raw_entries_map.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            entries[key] = cast(dict[str, Any], dict(value))
    raw_slots = plugins_config.get("slots")
    slots: dict[str, str] = {}
    if isinstance(raw_slots, dict):
        raw_slots_map = cast(PluginConfigMap, raw_slots)
        for key, value in raw_slots_map.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            slots[key] = value
    return PluginsConfig(
        enabled=enabled,
        allow=allow,
        deny=deny,
        entries=entries,
        slots=slots,
    )


__all__ = [
    "PluginsConfig",
    "normalize_plugins_config",
    "resolve_live_plugin_config_object",
    "resolve_plugin_config_object",
]
