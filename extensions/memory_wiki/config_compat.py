"""config_compat — legacy config compatibility shims.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/config-compat.ts``.

The memory-wiki plugin used to expose
``plugins.entries.memory-wiki.config.bridge.readMemoryCore``
(an older name for ``bridge.readMemoryArtifacts``).
The compat layer detects the legacy key, migrates it
to the canonical key, and returns a list of human-
readable change descriptions. The migration is
idempotent: running it twice on the same config is a
no-op.
"""

from __future__ import annotations

from typing import Any


def _as_record(value: Any) -> dict[str, Any] | None:
    """Return ``value`` if it is a plain dict, else ``None``.

    Mirrors OpenClaw's ``asRecord`` helper. Mirrors
    the OpenClaw behavior of treating arrays and
    ``null`` as "not a record".
    """
    if value is None or isinstance(value, list | str | int | float | bool):
        return None
    if not isinstance(value, dict):
        return None
    return value


def has_legacy_bridge_artifact_toggle(value: Any) -> bool:
    """Return True iff ``value`` is a record with the legacy key.

    Mirrors OpenClaw's ``hasLegacyBridgeArtifactToggle``.
    """
    record = _as_record(value)
    if record is None:
        return False
    return "readMemoryCore" in record


LEGACY_CONFIG_RULES: list[dict[str, Any]] = [
    {
        "path": ["plugins", "entries", "memory-wiki", "config", "bridge"],
        "message": (
            "plugins.entries.memory-wiki.config.bridge.readMemoryCore is "
            "legacy; use plugins.entries.memory-wiki.config.bridge."
            'readMemoryArtifacts. Run "openclaw doctor --fix".'
        ),
        "match": has_legacy_bridge_artifact_toggle,
    },
]


def migrate_memory_wiki_legacy_config(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Migrate the legacy ``bridge.readMemoryCore`` key to canonical.

    Mirrors OpenClaw's ``migrateMemoryWikiLegacyConfig``.
    Returns ``None`` when no migration is needed,
    otherwise ``{"config": nextConfig, "changes":
    [human-readable strings]}``.

    The migration is best-effort: any malformed segment
    in the path is silently ignored so a partially-
    shaped config still returns a useful result.
    """
    plugins = _as_record(config.get("plugins") if isinstance(config, dict) else None)
    if plugins is None:
        return None
    entries = _as_record(plugins.get("entries"))
    if entries is None:
        return None
    entry = _as_record(entries.get("memory-wiki") or entries.get("memory_wiki"))
    if entry is None:
        return None
    plugin_config = _as_record(entry.get("config"))
    if plugin_config is None:
        return None
    bridge = _as_record(plugin_config.get("bridge"))
    if bridge is None or not has_legacy_bridge_artifact_toggle(bridge):
        return None

    # Build a deep-clone-style next config. The
    # Python equivalent of OpenClaw's ``structuredClone``
    # is ``copy.deepcopy`` for plain JSON-compatible
    # objects.
    import copy

    next_config = copy.deepcopy(config)
    next_plugins = _as_record(next_config.get("plugins")) or {}
    next_config["plugins"] = next_plugins
    next_entries = _as_record(next_plugins.get("entries")) or {}
    next_plugins["entries"] = next_entries
    next_entry = (
        _as_record(next_entries.get("memory-wiki"))
        or _as_record(next_entries.get("memory_wiki"))
        or {}
    )
    if "memory-wiki" in next_entries:
        next_entries["memory-wiki"] = next_entry
    else:
        next_entries["memory_wiki"] = next_entry
    next_plugin_config = _as_record(next_entry.get("config")) or {}
    next_entry["config"] = next_plugin_config
    next_bridge = _as_record(next_plugin_config.get("bridge")) or {}
    next_plugin_config["bridge"] = next_bridge

    legacy_value = next_bridge.get("readMemoryCore")
    has_canonical = "readMemoryArtifacts" in next_bridge
    if not has_canonical:
        next_bridge["readMemoryArtifacts"] = legacy_value
    del next_bridge["readMemoryCore"]

    return {
        "config": next_config,
        "changes": [
            (
                "Removed legacy plugins.entries.memory-wiki.config.bridge."
                "readMemoryCore; kept explicit plugins.entries.memory-wiki."
                "config.bridge.readMemoryArtifacts."
                if has_canonical
                else "Moved plugins.entries.memory-wiki.config.bridge."
                "readMemoryCore -> plugins.entries.memory-wiki.config."
                "bridge.readMemoryArtifacts."
            )
        ],
    }


def normalize_compatibility_config(
    *,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Run the migration suite and return the (config, changes) pair.

    Mirrors OpenClaw's ``normalizeCompatibilityConfig``.
    Returns ``{"config": cfg, "changes": []}`` when
    no migration is needed.
    """
    result = migrate_memory_wiki_legacy_config(cfg)
    if result is None:
        return {"config": cfg, "changes": []}
    return result


__all__ = [
    "LEGACY_CONFIG_RULES",
    "has_legacy_bridge_artifact_toggle",
    "migrate_memory_wiki_legacy_config",
    "normalize_compatibility_config",
]
