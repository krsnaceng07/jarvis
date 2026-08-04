"""jarvis.config.plugin_install_config_migration — legacy plugin install migration.

OpenClaw parity: mirrors
``openclaw-main/src/config/plugin-install-config-migration.ts``.

Focused minimal port: the zod parser is replaced with a permissive
shape check; the migration helpers operate on plain dicts.
"""
from __future__ import annotations

import copy
from typing import Any, Dict


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def _looks_like_install_record(value) -> bool:
    """Permissive check for a plugin install record shape."""
    if not _is_record(value):
        return False
    # The OpenClaw source uses zod for validation; we accept any object that
    # has a ``source`` field that's one of the canonical install sources.
    source = value.get("source")
    if not isinstance(source, str):
        return False
    return source in {"npm", "archive", "path", "clawhub", "git", "marketplace"}


def extract_shipped_plugin_install_config_records(config: Any) -> Dict[str, dict]:
    """Read legacy shipped ``plugins.installs`` records for migration.

    Mirrors :func:`extractShippedPluginInstallConfigRecords`
    (``shared/config/plugin-install-config-migration.ts`).
    """
    if not _is_record(config):
        return {}
    plugins = config.get("plugins")
    if not _is_record(plugins):
        return {}
    installs = plugins.get("installs")
    if not _is_record(installs):
        return {}
    out: Dict[str, dict] = {}
    for name, rec in installs.items():
        if not isinstance(name, str) or not _looks_like_install_record(rec):
            continue
        out[name] = copy.deepcopy(rec)
    return out


def _prune_empty_plugins_object(plugins: Dict[str, Any]) -> Any:
    """Return the plugins dict without ``installs``; ``None`` if it becomes empty."""
    rest = {k: v for k, v in plugins.items() if k != "installs"}
    return rest or None


def strip_shipped_plugin_install_config_records(config: Any) -> Any:
    """Remove legacy shipped ``plugins.installs`` without mutating the input.

    Mirrors :func:`stripShippedPluginInstallConfigRecords`
    (``shared/config/plugin-install-config-migration.ts`).
    """
    if not _is_record(config):
        return config
    plugins = config.get("plugins")
    if not _is_record(plugins) or "installs" not in plugins:
        return config
    new_plugins = _prune_empty_plugins_object(plugins)
    if new_plugins is None:
        return {k: v for k, v in config.items() if k != "plugins"}
    return {**config, "plugins": new_plugins}


__all__ = [
    "extract_shipped_plugin_install_config_records",
    "strip_shipped_plugin_install_config_records",
]
