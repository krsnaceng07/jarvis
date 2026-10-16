"""Codex Computer Use config types and resolver.

OpenClaw parity: ``config-contracts.ts`` (CodexComputerUseConfig /
ResolvedCodexComputerUseConfig) + ``config-parsing.ts`` (defaults) +
``config-options.ts`` (resolveCodexComputerUseConfig).

All defaults are verbatim copies of the TypeScript constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# ── OpenClaw verbatim defaults ────────────────────────────────────────────────
DEFAULT_PLUGIN_NAME: str = "computer-use"
DEFAULT_MCP_SERVER_NAME: str = "computer-use"
DEFAULT_MARKETPLACE_DISCOVERY_TIMEOUT_MS: int = 60_000
DEFAULT_LIVE_TEST_TIMEOUT_MS: int = 60_000
DEFAULT_TOOL_CALL_TIMEOUT_MS: int = 60_000
DEFAULT_HEALTH_CHECK_INTERVAL_MINUTES: int = 60

HealthCheckInterval = Literal[30, 60, 120, 240]
PluginCacheMode = Literal["shared", "independent"]


@dataclass(frozen=True, slots=True)
class CodexComputerUseConfig:
    """Raw config shape — mirrors OpenClaw's ``CodexComputerUseConfig`` type.

    All fields are optional so callers can pass a sparse dict and rely on
    ``resolve_computer_use_config`` to fill the defaults.
    """

    enabled: Optional[bool] = None
    auto_install: Optional[bool] = None
    marketplace_discovery_timeout_ms: Optional[int] = None
    live_test_timeout_ms: Optional[int] = None
    tool_call_timeout_ms: Optional[int] = None
    health_check_enabled: Optional[bool] = None
    health_check_interval_minutes: Optional[HealthCheckInterval] = None
    plugin_cache_mode: Optional[PluginCacheMode] = None
    strict_readiness: Optional[bool] = None
    auto_repair: Optional[bool] = None
    marketplace_source: Optional[str] = None
    marketplace_path: Optional[str] = None
    marketplace_name: Optional[str] = None
    plugin_name: Optional[str] = None
    mcp_server_name: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ResolvedCodexComputerUseConfig:
    """Fully-resolved config — every field is non-optional.

    OpenClaw parity: ``ResolvedCodexComputerUseConfig`` in
    ``config-contracts.ts``.
    """

    enabled: bool
    auto_install: bool
    marketplace_discovery_timeout_ms: int
    live_test_timeout_ms: int
    tool_call_timeout_ms: int
    health_check_enabled: bool
    health_check_interval_minutes: HealthCheckInterval
    plugin_cache_mode: PluginCacheMode
    strict_readiness: bool
    auto_repair: bool
    plugin_name: str
    mcp_server_name: str
    marketplace_source: Optional[str] = None
    marketplace_path: Optional[str] = None
    marketplace_name: Optional[str] = None


def resolve_computer_use_config(
    raw: Optional[CodexComputerUseConfig] = None,
    overrides: Optional[CodexComputerUseConfig] = None,
    *,
    force_enable: bool = False,
) -> ResolvedCodexComputerUseConfig:
    """Merge raw plugin config → overrides → defaults into a resolved config.

    OpenClaw parity: ``resolveCodexComputerUseConfig`` in ``config-options.ts``.
    """
    r: CodexComputerUseConfig = raw or CodexComputerUseConfig()
    o: CodexComputerUseConfig = overrides or CodexComputerUseConfig()

    def pick(raw_val, override_val, default):  # type: ignore[no-untyped-def]
        if override_val is not None:
            return override_val
        if raw_val is not None:
            return raw_val
        return default

    enabled: bool = pick(r.enabled, o.enabled, False)
    if force_enable:
        enabled = True

    interval_raw = pick(
        r.health_check_interval_minutes,
        o.health_check_interval_minutes,
        DEFAULT_HEALTH_CHECK_INTERVAL_MINUTES,
    )
    # Clamp to the allowed set, matching OpenClaw's zod union literal schema.
    allowed_intervals: list[HealthCheckInterval] = [30, 60, 120, 240]
    health_check_interval: HealthCheckInterval = (
        interval_raw if interval_raw in allowed_intervals else DEFAULT_HEALTH_CHECK_INTERVAL_MINUTES  # type: ignore[assignment]
    )

    return ResolvedCodexComputerUseConfig(
        enabled=enabled,
        auto_install=pick(r.auto_install, o.auto_install, False),
        marketplace_discovery_timeout_ms=pick(
            r.marketplace_discovery_timeout_ms,
            o.marketplace_discovery_timeout_ms,
            DEFAULT_MARKETPLACE_DISCOVERY_TIMEOUT_MS,
        ),
        live_test_timeout_ms=pick(
            r.live_test_timeout_ms, o.live_test_timeout_ms, DEFAULT_LIVE_TEST_TIMEOUT_MS
        ),
        tool_call_timeout_ms=pick(
            r.tool_call_timeout_ms, o.tool_call_timeout_ms, DEFAULT_TOOL_CALL_TIMEOUT_MS
        ),
        health_check_enabled=pick(r.health_check_enabled, o.health_check_enabled, True),
        health_check_interval_minutes=health_check_interval,
        plugin_cache_mode=pick(r.plugin_cache_mode, o.plugin_cache_mode, "shared"),
        strict_readiness=pick(r.strict_readiness, o.strict_readiness, False),
        auto_repair=pick(r.auto_repair, o.auto_repair, True),
        plugin_name=pick(r.plugin_name, o.plugin_name, DEFAULT_PLUGIN_NAME),
        mcp_server_name=pick(r.mcp_server_name, o.mcp_server_name, DEFAULT_MCP_SERVER_NAME),
        marketplace_source=pick(r.marketplace_source, o.marketplace_source, None),
        marketplace_path=pick(r.marketplace_path, o.marketplace_path, None),
        marketplace_name=pick(r.marketplace_name, o.marketplace_name, None),
    )


resolve_codex_computer_use_config = resolve_computer_use_config

__all__ = [
    "DEFAULT_HEALTH_CHECK_INTERVAL_MINUTES",
    "DEFAULT_LIVE_TEST_TIMEOUT_MS",
    "DEFAULT_MARKETPLACE_DISCOVERY_TIMEOUT_MS",
    "DEFAULT_MCP_SERVER_NAME",
    "DEFAULT_PLUGIN_NAME",
    "DEFAULT_TOOL_CALL_TIMEOUT_MS",
    "CodexComputerUseConfig",
    "ResolvedCodexComputerUseConfig",
    "resolve_codex_computer_use_config",
    "resolve_computer_use_config",
]
