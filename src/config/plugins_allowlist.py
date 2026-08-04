"""jarvis.config.plugins_allowlist — plugin allowlist helpers.

OpenClaw parity: mirrors ``openclaw-main/src/config/plugins-allowlist.ts``.
"""
from __future__ import annotations

from typing import Any


def ensure_plugin_allowlisted(cfg: Any, plugin_id: str) -> Any:
    """Append ``pluginId`` to a restrictive plugin allowlist; pass-through otherwise.

    Mirrors :func:`ensurePluginAllowlisted`
    (``shared/config/plugins-allowlist.ts`).
    """
    if not isinstance(cfg, dict):
        return cfg
    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        return cfg
    allow = plugins.get("allow")
    if not isinstance(allow, list) or plugin_id in allow:
        # Missing allowlist means unrestricted plugin loading; avoid creating a new restrictive list.
        return cfg
    return {
        **cfg,
        "plugins": {
            **plugins,
            "allow": [*allow, plugin_id],
        },
    }


__all__ = ["ensure_plugin_allowlisted"]
