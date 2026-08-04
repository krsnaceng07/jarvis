"""jarvis.config.plugin_web_search_config — plugin web-search config resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/plugin-web-search-config.ts``.
"""
from __future__ import annotations

from typing import Any, Optional


def _is_record(value) -> bool:
    return isinstance(value, dict) and not isinstance(value, (list, tuple, str, bytes, set))


def resolve_plugin_web_search_config(
    config: Optional[Any],
    plugin_id: str,
) -> Optional[dict]:
    """Resolve a plugin-owned ``config.webSearch`` object without interpreting provider fields.

    Mirrors :func:`resolvePluginWebSearchConfig`
    (``shared/config/plugin-web-search-config.ts`).
    """
    if not _is_record(config):
        return None
    entries = ((config.get("plugins") or {}).get("entries") or {}) if _is_record(config.get("plugins")) else {}
    plugin_entry = entries.get(plugin_id) if _is_record(entries) else None
    if not _is_record(plugin_entry):
        return None
    plugin_config = plugin_entry.get("config")
    if not _is_record(plugin_config):
        return None
    return plugin_config.get("webSearch") if _is_record(plugin_config.get("webSearch")) else None


__all__ = ["resolve_plugin_web_search_config"]
