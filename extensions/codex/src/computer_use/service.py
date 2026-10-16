"""Codex Computer Use service layer.

OpenClaw parity: the three public functions in
``extensions/codex/src/app-server/computer-use.ts``:

  - ``read_status``   → ``readCodexComputerUseStatus``
  - ``ensure_ready``  → ``ensureCodexComputerUse``
  - ``install``       → ``installCodexComputerUse``

The Codex app-server is a separate process (Codex CLI / Desktop) reachable
via JSON-RPC (stdio / WebSocket / Unix socket).  JARVIS does not vendor the
binary; it finds or awaits one through the pluggable ``CodexRequest`` seam.

This module owns the readiness state machine: disabled → marketplace_missing
→ plugin_not_installed → plugin_disabled → mcp_missing → live_test_failed
→ ready.  It mirrors the TypeScript state machine exactly, including the
live-test + auto-repair loop.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from typing import Any, Callable, Coroutine, Optional

from .config import (
    CodexComputerUseConfig,
    ResolvedCodexComputerUseConfig,
    resolve_computer_use_config,
)
from .status import (
    CodexComputerUseStatus,
    ExposureStatus,
    InstallationStatus,
    LiveTestStatus,
    RepairStatus,
    StatusReason,
)

# Live-test is attempted once and retried once on failure (matching OpenClaw).
_LIVE_TEST_RETRY_COUNT = 1
_LIVE_TEST_THREAD_NAME = "JARVIS Computer Use readiness probe"

# Marketplace poll cadence (matching OpenClaw: 2 s).
_MARKETPLACE_POLL_INTERVAL_MS = 2_000

# Marketplace priority order (verbatim from OpenClaw).
_MARKETPLACE_NAME_PRIORITY = [
    "openai-bundled",
    "openai-curated",
    "openai-api-curated",
    "openai-curated-remote",
    "local",
]

# ── request seam ─────────────────────────────────────────────────────────────

#: Callable that mirrors OpenClaw's ``CodexComputerUseRequest`` type.
#: Signature: (method, params?, timeout_ms?) → Any
CodexRequest = Callable[..., Coroutine[Any, Any, Any]]


class CodexComputerUseSetupError(Exception):
    """Raised when Computer Use cannot be made ready.

    OpenClaw parity: ``CodexComputerUseSetupError``.
    """

    def __init__(self, status: CodexComputerUseStatus) -> None:
        super().__init__(status.message)
        self.status = status


# ── public entry points ───────────────────────────────────────────────────────


async def read_status(
    raw_config: Optional[CodexComputerUseConfig] = None,
    *,
    overrides: Optional[CodexComputerUseConfig] = None,
    request: Optional[CodexRequest] = None,
) -> CodexComputerUseStatus:
    """Probe Computer Use readiness without mutating Codex state.

    OpenClaw parity: ``readCodexComputerUseStatus``.
    """
    config = resolve_computer_use_config(raw_config, overrides)
    if not config.enabled:
        return _disabled_status(config)
    try:
        return await _inspect(config, install_plugin=False, request=request)
    except Exception as exc:
        return _unavailable_status(config, "check_failed", f"Computer Use check failed: {exc}")


async def ensure_ready(
    raw_config: Optional[CodexComputerUseConfig] = None,
    *,
    overrides: Optional[CodexComputerUseConfig] = None,
    request: Optional[CodexRequest] = None,
) -> CodexComputerUseStatus:
    """Ensure Computer Use is ready, auto-installing when config allows.

    OpenClaw parity: ``ensureCodexComputerUse``.
    Raises ``CodexComputerUseSetupError`` when not ready and cannot recover.
    """
    config = resolve_computer_use_config(raw_config, overrides)
    if not config.enabled:
        return _disabled_status(config)

    status = await _inspect(config, install_plugin=False, request=request)
    if status.ready:
        return status
    if _non_strict_live_test_startup_allowed(status, config):
        return status
    if config.auto_install:
        blocked = _block_unsafe_auto_install_status(config)
        if blocked:
            raise CodexComputerUseSetupError(blocked)
        installed_status = await _inspect(config, install_plugin=True, request=request)
        if _non_strict_live_test_startup_allowed(installed_status, config):
            return installed_status
        if not installed_status.ready:
            raise CodexComputerUseSetupError(installed_status)
        return installed_status
    if not status.ready:
        raise CodexComputerUseSetupError(status)
    return status


async def install(
    raw_config: Optional[CodexComputerUseConfig] = None,
    *,
    overrides: Optional[CodexComputerUseConfig] = None,
    request: Optional[CodexRequest] = None,
) -> CodexComputerUseStatus:
    """Force-install Computer Use and return the ready status.

    OpenClaw parity: ``installCodexComputerUse``.
    Raises ``CodexComputerUseSetupError`` when installation fails.
    """
    merged_overrides = CodexComputerUseConfig(
        enabled=True,
        auto_install=True,
        **({k: v for k, v in vars(overrides).items() if v is not None} if overrides else {}),
    )
    config = resolve_computer_use_config(raw_config, merged_overrides, force_enable=True)
    status = await _inspect(config, install_plugin=True, request=request)
    if not status.ready:
        raise CodexComputerUseSetupError(status)
    return status


# ── internal state machine ────────────────────────────────────────────────────


async def _inspect(
    config: ResolvedCodexComputerUseConfig,
    *,
    install_plugin: bool,
    request: Optional[CodexRequest],
) -> CodexComputerUseStatus:
    """Core readiness probe — mirrors ``inspectCodexComputerUseWithoutFence``.

    Performs in order:
    1. Optionally enable plugin support in Codex app-server.
    2. Resolve marketplace reference.
    3. Ensure plugin is installed + enabled (optionally auto-installing).
    4. Enumerate MCP tools.
    5. Run live test with optional auto-repair retry.
    """
    req = _make_request(config, request)

    if install_plugin:
        await req("experimentalFeature/enablement/set", {"enablement": {"plugins": True}})

    marketplace = await _resolve_marketplace(req, config, allow_add=install_plugin)
    if marketplace is None:
        return _unavailable_status(
            config,
            "marketplace_missing",
            (
                f"No Codex marketplace containing {config.plugin_name} is registered. "
                "Configure computerUse.marketplaceSource or computerUse.marketplacePath, "
                "then run /codex computer-use install."
            ),
        )

    plugin = await _ensure_plugin(req, config, marketplace, install_plugin=install_plugin)
    if isinstance(plugin, CodexComputerUseStatus):
        return plugin  # not_installed / plugin_disabled early return

    return await _read_tools_and_live_test(req, config, plugin, install_plugin=install_plugin)


async def _resolve_marketplace(
    req: CodexRequest,
    config: ResolvedCodexComputerUseConfig,
    *,
    allow_add: bool,
) -> Optional[dict[str, Any]]:
    """Find the best marketplace containing the computer-use plugin.

    OpenClaw parity: ``resolveMarketplaceRef``.
    Returns a marketplace reference dict or None.
    """
    preferred_name: Optional[str] = config.marketplace_name

    if config.marketplace_source and allow_add:
        added = await req("marketplace/add", {"source": config.marketplace_source})
        preferred_name = preferred_name or (added or {}).get("marketplaceName")

    if config.marketplace_path:
        ref: dict[str, Any] = {"kind": "local", "path": config.marketplace_path}
        if preferred_name:
            ref["name"] = preferred_name
        return ref

    candidates = await _list_computer_use_marketplace_candidates(req, config)

    wait_until_ms = _marketplace_wait_until_ms(config, allow_add)
    while not candidates:
        if _now_ms() >= wait_until_ms:
            break
        sleep_ms = min(_MARKETPLACE_POLL_INTERVAL_MS, max(0, wait_until_ms - _now_ms()))
        await asyncio.sleep(sleep_ms / 1000)
        candidates = await _list_computer_use_marketplace_candidates(req, config)

    if preferred_name:
        preferred = next((c for c in candidates if c.get("name") == preferred_name), None)
        if preferred:
            return preferred
        return None  # configured name not found → marketplace_missing

    if len(candidates) > 1:
        return _choose_known_marketplace(candidates)

    return candidates[0] if candidates else None


async def _list_computer_use_marketplace_candidates(
    req: CodexRequest,
    config: ResolvedCodexComputerUseConfig,
) -> list[dict[str, Any]]:
    """Query Codex plugin list and extract marketplaces that carry the plugin."""
    listed = await req("plugin/list", {"cwds": []})
    return _find_computer_use_marketplaces(listed or {}, config.plugin_name)


def _find_computer_use_marketplaces(
    listed: dict[str, Any],
    plugin_name: str,
) -> list[dict[str, Any]]:
    """Extract marketplace refs that contain the plugin.

    OpenClaw parity: ``findComputerUseMarketplaces``.
    """
    results: list[dict[str, Any]] = []
    for marketplace in listed.get("marketplaces", []):
        plugins = marketplace.get("plugins", [])
        m_name = marketplace.get("name", "")
        plugin = next(
            (
                p
                for p in plugins
                if p.get("name") == plugin_name
                or p.get("id") == plugin_name
                or p.get("id") == f"{plugin_name}@{m_name}"
            ),
            None,
        )
        if not plugin:
            continue
        m_path = marketplace.get("path")
        if m_path:
            results.append({"kind": "local", "name": m_name, "path": m_path})
        else:
            remote_id = (plugin.get("remotePluginId") or "").strip()
            if remote_id:
                results.append(
                    {
                        "kind": "remote",
                        "name": m_name,
                        "remoteMarketplaceName": m_name,
                        "remotePluginId": remote_id,
                    }
                )
    return results


def _choose_known_marketplace(
    candidates: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    for priority_name in _MARKETPLACE_NAME_PRIORITY:
        found = next((c for c in candidates if c.get("name") == priority_name), None)
        if found:
            return found
    return None


async def _ensure_plugin(
    req: CodexRequest,
    config: ResolvedCodexComputerUseConfig,
    marketplace: dict[str, Any],
    *,
    install_plugin: bool,
) -> "CodexComputerUseStatus | dict[str, Any]":
    """Install + enable the plugin, returning plugin detail or a failed status.

    OpenClaw parity: ``ensureComputerUsePlugin``.
    Returns the raw plugin detail dict on success, or a terminal
    ``CodexComputerUseStatus`` on failure.
    """
    plugin = await _read_plugin(req, marketplace, config.plugin_name)
    summary = plugin.get("summary", {})
    if not summary.get("installed") or not summary.get("enabled"):
        if not install_plugin:
            reason = _plugin_setup_reason(plugin)
            return _status_from_plugin(
                config=config,
                plugin=plugin,
                tools=[],
                reason=reason,
                message=_plugin_setup_message(config, plugin),
            )
        await req("plugin/install", _plugin_request_params(marketplace, config.plugin_name))
        await req("config/mcpServer/reload", None)
        plugin = await _read_plugin(req, marketplace, config.plugin_name)
        summary = plugin.get("summary", {})

    if not summary.get("installed") or not summary.get("enabled"):
        return _status_from_plugin(
            config=config,
            plugin=plugin,
            tools=[],
            reason=_plugin_setup_reason(plugin),
            message=_plugin_setup_message(config, plugin),
        )

    return plugin


async def _read_tools_and_live_test(
    req: CodexRequest,
    config: ResolvedCodexComputerUseConfig,
    plugin: dict[str, Any],
    *,
    install_plugin: bool,
) -> CodexComputerUseStatus:
    """Read exposed MCP tools and run the live test.

    OpenClaw parity: ``readComputerUseTools``.
    """
    server = await _read_mcp_server_status(req, config.mcp_server_name)
    tools = sorted((server or {}).get("tools", {}).keys())
    if (server is None or not tools) and install_plugin:
        await req("config/mcpServer/reload", None)
        server = await _read_mcp_server_status(req, config.mcp_server_name)
        tools = sorted((server or {}).get("tools", {}).keys())

    if server is None:
        return _status_from_plugin(
            config=config,
            plugin=plugin,
            tools=[],
            reason="mcp_missing",
            message=(
                f"Computer Use is installed, but the {config.mcp_server_name} "
                "MCP server is not available."
            ),
        )
    if not tools:
        return _status_from_plugin(
            config=config,
            plugin=plugin,
            tools=[],
            reason="mcp_missing",
            message=(
                f"Computer Use is installed, but the {config.mcp_server_name} "
                "MCP server exposes no tools."
            ),
        )

    pre_status = _status_from_plugin(
        config=config,
        plugin=plugin,
        tools=tools,
        reason="ready",
        message="Computer Use is ready.",
    )
    live_test, repair = await run_live_test(req, config)
    compat_allowed = not live_test.ok and not config.strict_readiness
    warnings = [
        *pre_status.warnings,
        *(repair.warnings if repair else []),
        *(
            [
                "Computer Use live test failed, but compatibility startup remains enabled; "
                "set computerUse.strictReadiness to true to fail closed."
            ]
            if compat_allowed
            else []
        ),
    ]
    return dataclasses.replace(
        pre_status,
        ready=live_test.ok,
        reason="ready" if live_test.ok else "live_test_failed",
        live_test=live_test,
        repair=repair,
        warnings=warnings,
        message=(
            "Computer Use is ready."
            if live_test.ok
            else (
                f"{live_test.message} Startup is allowed because "
                "computerUse.strictReadiness is false."
                if compat_allowed
                else live_test.message
            )
        ),
    )


async def run_live_test(
    req: CodexRequest,
    config: ResolvedCodexComputerUseConfig,
) -> tuple[LiveTestStatus, Optional[RepairStatus]]:
    """Run the live MCP tool call test.

    OpenClaw parity: ``runCodexComputerUseLiveTest``.
    Retries once, with optional auto-repair between attempts.
    """
    started_at = _now_ms()
    last_error: Optional[Exception] = None
    repair: Optional[RepairStatus] = None

    for attempt in range(_LIVE_TEST_RETRY_COUNT + 1):
        thread_id: Optional[str] = None
        try:
            thread_resp = await req(
                "thread/start",
                {
                    "input": [],
                    "developerInstructions": _LIVE_TEST_THREAD_NAME,
                    "ephemeral": True,
                },
                timeout_ms=config.live_test_timeout_ms,
            )
            thread_id = (thread_resp or {}).get("thread", {}).get("id")
            await req(
                "mcpServer/tool/call",
                {
                    "threadId": thread_id,
                    "server": config.mcp_server_name,
                    "tool": "list_apps",
                    "arguments": {},
                },
                timeout_ms=config.tool_call_timeout_ms,
            )
            return (
                LiveTestStatus(
                    status="passed",
                    ok=True,
                    attempted=True,
                    attempts=attempt + 1,
                    timeout_ms=config.live_test_timeout_ms,
                    retried=attempt > 0,
                    repaired=bool(repair and repair.attempted and not repair.warnings),
                    duration_ms=max(0, _now_ms() - started_at),
                    message="Computer Use live test passed.",
                ),
                repair,
            )
        except Exception as exc:
            last_error = exc
        finally:
            if thread_id:
                await _cleanup_probe_thread(req, thread_id, config)

        if attempt < _LIVE_TEST_RETRY_COUNT and config.auto_repair:
            repair = await _repair_mcp_runtime(req, config)

    error_msg = str(last_error) if last_error else "unknown error"
    return (
        LiveTestStatus(
            status="failed",
            ok=False,
            attempted=True,
            attempts=_LIVE_TEST_RETRY_COUNT + 1,
            timeout_ms=config.live_test_timeout_ms,
            retried=_LIVE_TEST_RETRY_COUNT > 0,
            repaired=bool(repair and repair.attempted and not repair.warnings),
            duration_ms=max(0, _now_ms() - started_at),
            message=(
                f"Computer Use live test failed after "
                f"{_LIVE_TEST_RETRY_COUNT + 1} attempts: {error_msg}"
            ),
            error=error_msg,
        ),
        repair,
    )


async def _repair_mcp_runtime(
    req: CodexRequest,
    config: ResolvedCodexComputerUseConfig,
) -> RepairStatus:
    """Ask Codex to reload MCP servers between live-test retry attempts."""
    try:
        await req(
            "config/mcpServer/reload",
            None,
            timeout_ms=config.live_test_timeout_ms,
        )
        return RepairStatus(
            attempted=True,
            killed_pids=[],
            warnings=[],
            message="Reloaded Computer Use MCP servers through Codex app-server.",
        )
    except Exception as exc:
        msg = f"Could not reload Computer Use MCP servers: {exc}"
        return RepairStatus(attempted=True, killed_pids=[], warnings=[msg], message=msg)


async def _cleanup_probe_thread(
    req: CodexRequest,
    thread_id: str,
    config: ResolvedCodexComputerUseConfig,
) -> None:
    timeout = config.live_test_timeout_ms
    await asyncio.gather(
        _safe_request(req, "thread/unsubscribe", {"threadId": thread_id}, timeout_ms=timeout),
        _safe_request(req, "thread/archive", {"threadId": thread_id}, timeout_ms=timeout),
    )


async def _safe_request(req: CodexRequest, method: str, params: Any, *, timeout_ms: int) -> None:
    try:
        await req(method, params, timeout_ms=timeout_ms)
    except Exception:
        pass


async def _read_plugin(
    req: CodexRequest,
    marketplace: dict[str, Any],
    plugin_name: str,
) -> dict[str, Any]:
    resp = await req("plugin/read", _plugin_request_params(marketplace, plugin_name))
    return (resp or {}).get("plugin", {})


async def _read_mcp_server_status(
    req: CodexRequest,
    server_name: str,
) -> Optional[dict[str, Any]]:
    """Page through ``mcpServerStatus/list`` looking for ``server_name``."""
    cursor: Optional[str] = None
    while True:
        resp = await req(
            "mcpServerStatus/list",
            {"cursor": cursor, "limit": 100, "detail": "toolsAndAuthOnly"},
        )
        data = (resp or {}).get("data", [])
        found = next((s for s in data if s.get("name") == server_name), None)
        if found:
            return found
        cursor = (resp or {}).get("nextCursor")
        if not cursor:
            return None


# ── status helpers (OpenClaw parity: statusFromPlugin, disabledStatus, …) ───


def _status_from_plugin(
    *,
    config: ResolvedCodexComputerUseConfig,
    plugin: dict[str, Any],
    tools: list[str],
    reason: StatusReason,
    message: str,
) -> CodexComputerUseStatus:
    summary = plugin.get("summary", {})
    installed: bool = bool(summary.get("installed"))
    enabled: bool = bool(summary.get("enabled"))
    source = summary.get("source")
    warnings: list[str] = []
    if isinstance(source, dict) and source.get("type") == "remote":
        warnings.append(
            "Computer Use plugin is resolved from a remote marketplace; "
            "live local bundles are preferred."
        )
    return CodexComputerUseStatus(
        enabled=True,
        ready=installed and enabled and bool(tools),
        reason=reason,
        installed=installed,
        plugin_enabled=enabled,
        mcp_server_available=bool(tools),
        plugin_name=config.plugin_name,
        mcp_server_name=config.mcp_server_name,
        marketplace_name=plugin.get("marketplaceName"),
        marketplace_path=plugin.get("marketplacePath"),
        tools=tools,
        installation=_installation_status_from_plugin(plugin, message),
        exposure=_exposure_status_from_tools(config, tools),
        live_test=_skipped_live_test_status(config, "Computer Use live test was not run."),
        warnings=warnings,
        message=message,
    )


def _disabled_status(config: ResolvedCodexComputerUseConfig) -> CodexComputerUseStatus:
    return CodexComputerUseStatus(
        enabled=False,
        ready=False,
        reason="disabled",
        installed=False,
        plugin_enabled=False,
        mcp_server_available=False,
        plugin_name=config.plugin_name,
        mcp_server_name=config.mcp_server_name,
        tools=[],
        installation=InstallationStatus(
            status="disabled", ok=False, message="Computer Use is disabled."
        ),
        exposure=ExposureStatus(
            status="skipped",
            ok=False,
            message="MCP exposure was not checked because Computer Use is disabled.",
        ),
        live_test=_skipped_live_test_status(
            config, "Computer Use live test was not run because Computer Use is disabled."
        ),
        warnings=[],
        message="Computer Use is disabled.",
    )


def _unavailable_status(
    config: ResolvedCodexComputerUseConfig,
    reason: StatusReason,
    message: str,
) -> CodexComputerUseStatus:
    installation_status_code = (
        "marketplace_missing" if reason == "marketplace_missing" else "not_installed"
    )
    return CodexComputerUseStatus(
        enabled=True,
        ready=False,
        reason=reason,
        installed=False,
        plugin_enabled=False,
        mcp_server_available=False,
        plugin_name=config.plugin_name,
        mcp_server_name=config.mcp_server_name,
        marketplace_name=config.marketplace_name,
        marketplace_path=config.marketplace_path,
        tools=[],
        installation=InstallationStatus(
            status=installation_status_code,  # type: ignore[arg-type]
            ok=False,
            message=message,
        ),
        exposure=ExposureStatus(
            status="skipped",
            ok=False,
            message="MCP exposure was not checked because Computer Use installation is not ready.",
        ),
        live_test=_skipped_live_test_status(
            config,
            "Computer Use live test was not run because installation is not ready.",
        ),
        warnings=[],
        message=message,
    )


def _installation_status_from_plugin(plugin: dict[str, Any], message: str) -> InstallationStatus:
    summary = plugin.get("summary", {})
    if not summary.get("installed"):
        return InstallationStatus(status="not_installed", ok=False, message=message)
    if not summary.get("enabled"):
        return InstallationStatus(status="installed_disabled", ok=False, message=message)
    return InstallationStatus(
        status="installed",
        ok=True,
        message="Computer Use plugin is installed and enabled.",
    )


def _exposure_status_from_tools(
    config: ResolvedCodexComputerUseConfig, tools: list[str]
) -> ExposureStatus:
    if not tools:
        return ExposureStatus(
            status="missing",
            ok=False,
            message=f"Computer Use MCP server {config.mcp_server_name} is not exposed.",
        )
    return ExposureStatus(
        status="available",
        ok=True,
        message=(f"Computer Use MCP server {config.mcp_server_name} exposes {len(tools)} tools."),
    )


def _skipped_live_test_status(
    config: ResolvedCodexComputerUseConfig, message: str
) -> LiveTestStatus:
    return LiveTestStatus(
        status="skipped",
        ok=False,
        attempted=False,
        attempts=0,
        timeout_ms=config.live_test_timeout_ms,
        retried=False,
        repaired=False,
        message=message,
    )


def _plugin_setup_reason(plugin: dict[str, Any]) -> StatusReason:
    return (
        "plugin_disabled" if plugin.get("summary", {}).get("installed") else "plugin_not_installed"
    )


def _plugin_setup_message(config: ResolvedCodexComputerUseConfig, plugin: dict[str, Any]) -> str:
    if not plugin.get("summary", {}).get("installed"):
        return (
            "Computer Use is available but not installed. "
            "Run /codex computer-use install or enable computerUse.autoInstall."
        )
    return (
        f"Computer Use is installed, but the {config.plugin_name} plugin is disabled. "
        "Run /codex computer-use install or enable computerUse.autoInstall to re-enable it."
    )


def _block_unsafe_auto_install_status(
    config: ResolvedCodexComputerUseConfig,
) -> Optional[CodexComputerUseStatus]:
    if not config.marketplace_source:
        return None
    return _unavailable_status(
        config,
        "auto_install_blocked",
        (
            "Computer Use auto-install only uses marketplaces Codex app-server has already "
            "discovered. Run /codex computer-use install to install from a configured "
            "marketplace source."
        ),
    )


def _non_strict_live_test_startup_allowed(
    status: CodexComputerUseStatus,
    config: ResolvedCodexComputerUseConfig,
) -> bool:
    return (
        not config.strict_readiness
        and status.reason == "live_test_failed"
        and status.installed
        and status.plugin_enabled
        and status.mcp_server_available
        and status.installation.ok
        and status.exposure.ok
    )


def _plugin_request_params(marketplace: dict[str, Any], plugin_name: str) -> dict[str, Any]:
    if marketplace.get("kind") == "local":
        return {"marketplacePath": marketplace["path"], "pluginName": plugin_name}
    return {
        "remoteMarketplaceName": marketplace["remoteMarketplaceName"],
        "pluginName": marketplace["remotePluginId"],
    }


def _marketplace_wait_until_ms(
    config: ResolvedCodexComputerUseConfig,
    allow_add: bool,
) -> int:
    if (
        allow_add
        and not config.marketplace_source
        and not config.marketplace_path
        and not config.marketplace_name
    ):
        return _now_ms() + config.marketplace_discovery_timeout_ms
    return 0


def _make_request(
    config: ResolvedCodexComputerUseConfig,
    request: Optional[CodexRequest],
) -> CodexRequest:
    """Return the caller-supplied request seam or a stub that raises.

    In production JARVIS, the Codex app-server client is injected through
    the ``request`` seam (matching OpenClaw's ``createComputerUseRequest``).
    The stub raises so that callers that forget to inject get a clear error.
    """
    if request is not None:
        return request

    async def _no_client(method: str, params: Any = None, *, timeout_ms: int = 0) -> Any:
        raise RuntimeError(
            f"Computer Use: no Codex app-server client configured "
            f"(attempted: {method!r}). "
            "Inject a CodexRequest via the `request` parameter or "
            "configure the Codex harness before calling this function."
        )

    return _no_client  # type: ignore[return-value]


def _now_ms() -> int:
    return int(time.monotonic() * 1000)
