"""jarvis.plugins.codex_plugins — Native Codex plugin configuration and management.

OpenClaw parity: mirrors
``openclaw-main/extensions/codex/src/command-plugins-management.ts`` and
``openclaw-main/src/config/codex-plugin-diagnostics.ts``.

Features:
- `POLICY_REFRESH_HINT`: ``"New Codex conversations pick this up automatically. Use /new or /reset to refresh the current one."``
- `CodexNativePluginEntry`: `enabled`, `marketplace_name`, `plugin_name`, `allow_destructive_actions`.
- `CodexPluginsConfigBlock`: `enabled`, `allow_all_plugins`, `allow_destructive_actions`, `plugins`.
- `parse_codex_plugins_config()`: Resolves `codexPlugins` section from plugin options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

POLICY_REFRESH_HINT: str = (
    "New Codex conversations pick this up automatically. Use /new or /reset to refresh the current one."
)

DestructiveActionPolicy = Literal[True, False, "auto", "ask"]


@dataclass
class CodexNativePluginEntry:
    enabled: bool = True
    marketplace_name: str = "openai-curated"
    plugin_name: str = ""
    allow_destructive_actions: DestructiveActionPolicy = "auto"


@dataclass
class CodexPluginsConfigBlock:
    enabled: bool = False
    allow_all_plugins: bool = False
    allow_destructive_actions: DestructiveActionPolicy = True
    plugins: dict[str, CodexNativePluginEntry] = field(default_factory=dict)


def parse_codex_plugins_config(
    plugin_cfg: dict[str, Any] | None,
) -> CodexPluginsConfigBlock:
    """Parse `codexPlugins` block from Codex plugin configuration."""
    if not plugin_cfg or not isinstance(plugin_cfg, dict):
        return CodexPluginsConfigBlock()

    c_block = plugin_cfg.get("codexPlugins")
    if not isinstance(c_block, dict):
        return CodexPluginsConfigBlock()

    enabled = bool(c_block.get("enabled", False))
    allow_all = bool(c_block.get("allow_all_plugins", False))

    raw_dest = c_block.get("allow_destructive_actions", True)
    dest_policy: DestructiveActionPolicy = True
    if isinstance(raw_dest, bool):
        dest_policy = raw_dest
    elif isinstance(raw_dest, str) and raw_dest.lower() in ("auto", "ask"):
        dest_policy = raw_dest.lower()  # type: ignore[assignment]

    plugins: dict[str, CodexNativePluginEntry] = {}
    raw_plugins = c_block.get("plugins")
    if isinstance(raw_plugins, dict):
        for k, val in raw_plugins.items():
            norm_k = str(k).strip()
            if isinstance(val, dict):
                p_enabled = bool(val.get("enabled", True))
                m_name = str(val.get("marketplaceName") or "openai-curated")
                p_name = str(val.get("pluginName") or norm_k)
                raw_p_dest = val.get("allow_destructive_actions", dest_policy)
                p_dest: DestructiveActionPolicy = dest_policy
                if isinstance(raw_p_dest, bool):
                    p_dest = raw_p_dest
                elif isinstance(raw_p_dest, str) and raw_p_dest.lower() in ("auto", "ask"):
                    p_dest = raw_p_dest.lower()  # type: ignore[assignment]

                plugins[norm_k] = CodexNativePluginEntry(
                    enabled=p_enabled,
                    marketplace_name=m_name,
                    plugin_name=p_name,
                    allow_destructive_actions=p_dest,
                )

    return CodexPluginsConfigBlock(
        enabled=enabled,
        allow_all_plugins=allow_all,
        allow_destructive_actions=dest_policy,
        plugins=plugins,
    )


__all__ = [
    "POLICY_REFRESH_HINT",
    "CodexNativePluginEntry",
    "CodexPluginsConfigBlock",
    "DestructiveActionPolicy",
    "parse_codex_plugins_config",
]
