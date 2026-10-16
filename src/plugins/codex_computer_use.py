"""jarvis.plugins.codex_computer_use — Codex Computer Use plugin & status resolution.

OpenClaw parity: mirrors
``openclaw-main/extensions/codex/src/app-server/computer-use.ts`` and
``openclaw-main/extensions/codex/src/app-server/config.ts``.

Features:
- `DEFAULT_COMPUTER_USE_PLUGIN_NAME`: `"computer-use"`
- `DEFAULT_COMPUTER_USE_MCP_SERVER_NAME`: `"computer-use"`
- `CodexComputerUseConfig`: Dataclass containing `enabled`, `autoInstall`, timeouts, `pluginName`, `mcpServerName`, `pluginCacheMode`, etc.
- `ComputerUseStatusReason`: Enum of setup status codes (`disabled`, `marketplace_missing`, `plugin_not_installed`, `plugin_disabled`, `mcp_missing`, `ready`, `check_failed`, `auto_install_blocked`).
- `resolve_codex_computer_use_config()`: Resolves Computer Use options from plugin configuration or environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_COMPUTER_USE_PLUGIN_NAME: str = "computer-use"
DEFAULT_COMPUTER_USE_MCP_SERVER_NAME: str = "computer-use"

ComputerUseStatusReason = Literal[
    "disabled",
    "marketplace_missing",
    "plugin_not_installed",
    "plugin_disabled",
    "remote_install_unsupported",
    "mcp_missing",
    "live_test_failed",
    "ready",
    "check_failed",
    "auto_install_blocked",
]

PluginCacheMode = Literal["independent", "shared"]


@dataclass
class CodexComputerUseConfig:
    enabled: bool = False
    autoInstall: bool = False
    marketplaceDiscoveryTimeoutMs: int = 60_000
    liveTestTimeoutMs: int = 60_000
    toolCallTimeoutMs: int = 60_000
    healthCheckEnabled: bool = False
    healthCheckIntervalMinutes: int = 60
    pluginCacheMode: PluginCacheMode = "independent"
    strictReadiness: bool = False
    autoRepair: bool = False
    marketplaceSource: str | None = None
    marketplacePath: str | None = None
    marketplaceName: str | None = None
    pluginName: str = DEFAULT_COMPUTER_USE_PLUGIN_NAME
    mcpServerName: str = DEFAULT_COMPUTER_USE_MCP_SERVER_NAME


def resolve_codex_computer_use_config(
    plugin_cfg: dict[str, Any] | None,
) -> CodexComputerUseConfig:
    """Resolve Codex Computer Use configuration with environment variable fallbacks."""
    cu_block: dict[str, Any] = {}
    if plugin_cfg and isinstance(plugin_cfg, dict):
        raw_cu = plugin_cfg.get("computerUse")
        if isinstance(raw_cu, dict):
            cu_block = raw_cu

    # 1. enabled
    env_enabled = os.getenv("OPENCLAW_CODEX_COMPUTER_USE") or os.getenv("JARVIS_CODEX_COMPUTER_USE")
    if env_enabled is not None:
        enabled = env_enabled.strip().lower() in ("1", "true", "yes")
    elif "enabled" in cu_block:
        enabled = bool(cu_block["enabled"])
    else:
        # Inferred: enabled if any other computerUse field is set
        enabled = len(cu_block) > 0

    # 2. autoInstall
    env_auto = os.getenv("OPENCLAW_CODEX_COMPUTER_USE_AUTO_INSTALL") or os.getenv("JARVIS_CODEX_COMPUTER_USE_AUTO_INSTALL")
    if env_auto is not None:
        auto_install = env_auto.strip().lower() in ("1", "true", "yes")
    else:
        auto_install = bool(cu_block.get("autoInstall", False))

    # 3. pluginName / mcpServerName
    plugin_name = str(
        os.getenv("OPENCLAW_CODEX_COMPUTER_USE_PLUGIN_NAME")
        or cu_block.get("pluginName")
        or DEFAULT_COMPUTER_USE_PLUGIN_NAME
    )
    mcp_server_name = str(
        os.getenv("OPENCLAW_CODEX_COMPUTER_USE_MCP_SERVER_NAME")
        or cu_block.get("mcpServerName")
        or DEFAULT_COMPUTER_USE_MCP_SERVER_NAME
    )

    # 4. cacheMode
    raw_cache = str(
        os.getenv("OPENCLAW_CODEX_COMPUTER_USE_PLUGIN_CACHE_MODE")
        or cu_block.get("pluginCacheMode")
        or "independent"
    ).lower()
    cache_mode: PluginCacheMode = "shared" if raw_cache == "shared" else "independent"

    return CodexComputerUseConfig(
        enabled=enabled,
        autoInstall=auto_install,
        marketplaceDiscoveryTimeoutMs=int(cu_block.get("marketplaceDiscoveryTimeoutMs", 60_000)),
        liveTestTimeoutMs=int(cu_block.get("liveTestTimeoutMs", 60_000)),
        toolCallTimeoutMs=int(cu_block.get("toolCallTimeoutMs", 60_000)),
        healthCheckEnabled=bool(cu_block.get("healthCheckEnabled", False)),
        healthCheckIntervalMinutes=int(cu_block.get("healthCheckIntervalMinutes", 60)),
        pluginCacheMode=cache_mode,
        strictReadiness=bool(cu_block.get("strictReadiness", False)),
        autoRepair=bool(cu_block.get("autoRepair", False)),
        marketplaceSource=cu_block.get("marketplaceSource"),
        marketplacePath=cu_block.get("marketplacePath"),
        marketplaceName=cu_block.get("marketplaceName"),
        pluginName=plugin_name,
        mcpServerName=mcp_server_name,
    )


__all__ = [
    "DEFAULT_COMPUTER_USE_MCP_SERVER_NAME",
    "DEFAULT_COMPUTER_USE_PLUGIN_NAME",
    "CodexComputerUseConfig",
    "ComputerUseStatusReason",
    "PluginCacheMode",
    "resolve_codex_computer_use_config",
]
