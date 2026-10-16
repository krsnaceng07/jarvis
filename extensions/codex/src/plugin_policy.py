"""Native Codex plugin policy and restrictive thread app configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DestructiveMode = bool | str


@dataclass(frozen=True, slots=True)
class CodexPluginPolicyEntry:
    config_key: str
    plugin_name: str
    marketplace_name: str | None
    enabled: bool
    allow_destructive_actions: DestructiveMode


@dataclass(frozen=True, slots=True)
class CodexPluginsPolicy:
    configured: bool
    enabled: bool
    allow_all_plugins: bool
    allow_destructive_actions: DestructiveMode
    plugins: tuple[CodexPluginPolicyEntry, ...]


def resolve_codex_plugins_policy(config: Any) -> CodexPluginsPolicy:
    """Normalize the OpenClaw ``codexPlugins`` policy shape."""
    raw = config if isinstance(config, dict) else {}
    configured = "codexPlugins" in raw or "codex_plugins" in raw
    value = raw.get("codexPlugins", raw.get("codex_plugins"))
    block = value if isinstance(value, dict) else {}
    global_mode = _normalize_destructive_mode(block.get("allow_destructive_actions"))
    raw_plugins = block.get("plugins")
    entries: list[CodexPluginPolicyEntry] = []
    if isinstance(raw_plugins, dict):
        for config_key, raw_entry in raw_plugins.items():
            if (
                not isinstance(config_key, str)
                or not config_key.strip()
                or not isinstance(raw_entry, dict)
            ):
                continue
            plugin_name = _string(raw_entry.get("pluginName")) or _qualified_name(config_key)[0]
            marketplace = (
                _string(raw_entry.get("marketplaceName")) or _qualified_name(config_key)[1]
            )
            if not plugin_name:
                continue
            entries.append(
                CodexPluginPolicyEntry(
                    config_key=config_key.strip(),
                    plugin_name=plugin_name,
                    marketplace_name=marketplace,
                    enabled=raw_entry.get("enabled") is not False,
                    allow_destructive_actions=_normalize_destructive_mode(
                        raw_entry.get("allow_destructive_actions", global_mode)
                    ),
                )
            )
    return CodexPluginsPolicy(
        configured=configured,
        enabled=block.get("enabled") is True,
        allow_all_plugins=block.get("allow_all_plugins") is True,
        allow_destructive_actions=global_mode,
        plugins=tuple(entries),
    )


def build_codex_plugin_apps_config(
    policy: CodexPluginsPolicy,
    *,
    inventory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deny-by-default ``config.apps`` patch for a native thread.

    Inventory records must contain stable ``appId`` ownership. Display names
    and unverified plugin metadata are intentionally never admitted.
    """
    apps: dict[str, Any] = {"_default": {"enabled": False, "open_world_enabled": False}}
    if not policy.enabled:
        return {"apps": apps}
    allowed = {entry.config_key: entry for entry in policy.plugins if entry.enabled}
    for record in inventory or []:
        if not isinstance(record, dict) or record.get("owned") is not True:
            continue
        app_id = _string(record.get("appId"))
        config_key = _string(record.get("configKey"))
        if not app_id or (config_key not in allowed and not policy.allow_all_plugins):
            continue
        entry = allowed.get(config_key)
        mode = (
            entry.allow_destructive_actions
            if entry is not None
            else policy.allow_destructive_actions
        )
        apps[app_id] = {
            "enabled": True,
            "open_world_enabled": True,
            "destructive_enabled": mode is not False,
        }
    return {"apps": apps}


def _normalize_destructive_mode(value: Any) -> DestructiveMode:
    return value if value in (True, False, "auto", "ask") else True


def _qualified_name(value: str) -> tuple[str, str | None]:
    name, separator, marketplace = value.rpartition("@")
    return (name.strip(), marketplace.strip() if separator and marketplace.strip() else None)


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = [
    "CodexPluginPolicyEntry",
    "CodexPluginsPolicy",
    "build_codex_plugin_apps_config",
    "resolve_codex_plugins_policy",
]
