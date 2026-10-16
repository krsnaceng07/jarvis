"""Tests for Codex Computer Use — config resolver and service state machine.

Covers:
- Config resolution: defaults, overrides, force_enable.
- Status builders: disabled, unavailable, plugin detail variants.
- Service state machine: read_status (disabled, check_failed, mcp_missing,
  ready), ensure_ready (auto_install), install.
- Live-test: pass, fail, retry + repair.
- Marketplace resolution helpers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from extensions.codex.src.computer_use.config import (
    DEFAULT_LIVE_TEST_TIMEOUT_MS,
    DEFAULT_MCP_SERVER_NAME,
    DEFAULT_PLUGIN_NAME,
    CodexComputerUseConfig,
    ResolvedCodexComputerUseConfig,
    resolve_computer_use_config,
)
from extensions.codex.src.computer_use.service import (
    CodexComputerUseSetupError,
    _find_computer_use_marketplaces,
    ensure_ready,
    install,
    read_status,
    run_live_test,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_config(**kwargs: Any) -> ResolvedCodexComputerUseConfig:
    raw = CodexComputerUseConfig(**kwargs)
    return resolve_computer_use_config(raw)


def _resolved(**kwargs: Any) -> ResolvedCodexComputerUseConfig:
    """Build a resolved config, filling in required fields."""
    base: dict[str, Any] = {
        "enabled": True,
        "auto_install": False,
        "marketplace_discovery_timeout_ms": 100,
        "live_test_timeout_ms": 100,
        "tool_call_timeout_ms": 100,
        "health_check_enabled": True,
        "health_check_interval_minutes": 60,
        "plugin_cache_mode": "shared",
        "strict_readiness": False,
        "auto_repair": False,
        "plugin_name": "computer-use",
        "mcp_server_name": "computer-use",
    }
    base.update(kwargs)
    return ResolvedCodexComputerUseConfig(**base)


def _make_listed(
    marketplace_name: str = "openai-bundled",
    plugin_name: str = "computer-use",
    path: str = "/fake/market",
    *,
    remote: bool = False,
    remote_id: str = "cu-remote-id",
) -> dict[str, Any]:
    plugin_entry: dict[str, Any] = {"name": plugin_name, "id": plugin_name}
    if remote:
        plugin_entry["remotePluginId"] = remote_id
    marketplace: dict[str, Any] = {
        "name": marketplace_name,
        "plugins": [plugin_entry],
    }
    if not remote:
        marketplace["path"] = path
    return {"marketplaces": [marketplace]}


def _plugin_detail(*, installed: bool = True, enabled: bool = True) -> dict[str, Any]:
    return {
        "summary": {"installed": installed, "enabled": enabled},
        "marketplaceName": "openai-bundled",
    }


def _mcp_server(tools: list[str]) -> dict[str, Any]:
    return {"name": "computer-use", "tools": {t: {} for t in tools}}


# ── config resolution ────────────────────────────────────────────────────────


class TestResolveComputerUseConfig:
    def test_defaults(self) -> None:
        cfg = resolve_computer_use_config()
        assert cfg.enabled is False
        assert cfg.plugin_name == DEFAULT_PLUGIN_NAME
        assert cfg.mcp_server_name == DEFAULT_MCP_SERVER_NAME
        assert cfg.live_test_timeout_ms == DEFAULT_LIVE_TEST_TIMEOUT_MS
        assert cfg.auto_install is False
        assert cfg.strict_readiness is False
        assert cfg.auto_repair is True

    def test_override_wins(self) -> None:
        raw = CodexComputerUseConfig(enabled=True, plugin_name="custom-cu")
        override = CodexComputerUseConfig(plugin_name="override-cu")
        cfg = resolve_computer_use_config(raw, override)
        assert cfg.plugin_name == "override-cu"
        assert cfg.enabled is True  # raw value preserved when override is None

    def test_marketplace_name_is_preserved(self) -> None:
        cfg = resolve_computer_use_config(
            CodexComputerUseConfig(
                enabled=True,
                marketplace_name="openai-curated",
            )
        )
        assert cfg.marketplace_name == "openai-curated"

    def test_force_enable(self) -> None:
        cfg = resolve_computer_use_config(force_enable=True)
        assert cfg.enabled is True

    def test_health_interval_clamped(self) -> None:
        raw = CodexComputerUseConfig(health_check_interval_minutes=999)  # type: ignore[arg-type]
        cfg = resolve_computer_use_config(raw)
        # invalid value → falls back to default (60)
        assert cfg.health_check_interval_minutes == 60

    @pytest.mark.parametrize("interval", [30, 60, 120, 240])
    def test_valid_health_intervals(self, interval: int) -> None:
        raw = CodexComputerUseConfig(health_check_interval_minutes=interval)  # type: ignore[arg-type]
        cfg = resolve_computer_use_config(raw)
        assert cfg.health_check_interval_minutes == interval


# ── marketplace resolution helpers ───────────────────────────────────────────


class TestFindComputerUseMarketplaces:
    def test_local_marketplace_found(self) -> None:
        listed = _make_listed("openai-bundled", "computer-use", "/path/to/market")
        results = _find_computer_use_marketplaces(listed, "computer-use")
        assert len(results) == 1
        assert results[0]["kind"] == "local"
        assert results[0]["path"] == "/path/to/market"
        assert results[0]["name"] == "openai-bundled"

    def test_remote_marketplace_found(self) -> None:
        listed = _make_listed(remote=True, remote_id="cu-abc")
        results = _find_computer_use_marketplaces(listed, "computer-use")
        assert len(results) == 1
        assert results[0]["kind"] == "remote"
        assert results[0]["remotePluginId"] == "cu-abc"

    def test_no_match_returns_empty(self) -> None:
        listed = _make_listed(plugin_name="other-plugin")
        results = _find_computer_use_marketplaces(listed, "computer-use")
        assert results == []

    def test_remote_with_empty_id_excluded(self) -> None:
        listed = _make_listed(remote=True, remote_id="  ")
        results = _find_computer_use_marketplaces(listed, "computer-use")
        assert results == []

    def test_matches_by_id(self) -> None:
        listed = {
            "marketplaces": [
                {"name": "m1", "path": "/m1", "plugins": [{"name": "other", "id": "computer-use"}]}
            ]
        }
        results = _find_computer_use_marketplaces(listed, "computer-use")
        assert len(results) == 1


# ── read_status ───────────────────────────────────────────────────────────────


class TestReadStatus:
    def test_disabled_when_not_enabled(self) -> None:
        status = asyncio.run(read_status(CodexComputerUseConfig(enabled=False)))
        assert status.enabled is False
        assert status.reason == "disabled"
        assert not status.ready

    def test_check_failed_on_request_error(self) -> None:
        async def bad_req(method: str, params: Any = None, **kw: Any) -> Any:
            raise RuntimeError("connection refused")

        status = asyncio.run(read_status(CodexComputerUseConfig(enabled=True), request=bad_req))
        assert status.reason == "check_failed"
        assert "connection refused" in status.message

    def test_marketplace_missing(self) -> None:
        calls: list[str] = []

        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            calls.append(method)
            if method == "plugin/list":
                return {"marketplaces": []}
            return {}

        status = asyncio.run(
            read_status(
                CodexComputerUseConfig(enabled=True, marketplace_discovery_timeout_ms=0),
                request=req,
            )
        )
        assert status.reason == "marketplace_missing"
        assert not status.ready

    def test_plugin_not_installed(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail(installed=False)}
            return {}

        status = asyncio.run(read_status(CodexComputerUseConfig(enabled=True), request=req))
        assert status.reason == "plugin_not_installed"
        assert not status.installed

    def test_plugin_disabled(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail(enabled=False)}
            return {}

        status = asyncio.run(read_status(CodexComputerUseConfig(enabled=True), request=req))
        assert status.reason == "plugin_disabled"

    def test_mcp_server_missing(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail()}
            if method == "mcpServerStatus/list":
                return {"data": [], "nextCursor": None}
            return {}

        status = asyncio.run(read_status(CodexComputerUseConfig(enabled=True), request=req))
        assert status.reason == "mcp_missing"
        assert not status.mcp_server_available

    def test_ready_when_all_ok(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail()}
            if method == "mcpServerStatus/list":
                return {"data": [_mcp_server(["screenshot", "left_click"])], "nextCursor": None}
            if method == "thread/start":
                return {"thread": {"id": "t1"}}
            if method == "mcpServer/tool/call":
                return {"result": "ok"}
            return {}

        status = asyncio.run(read_status(CodexComputerUseConfig(enabled=True), request=req))
        assert status.ready
        assert status.reason == "ready"
        assert "screenshot" in status.tools
        assert "left_click" in status.tools


# ── ensure_ready ─────────────────────────────────────────────────────────────


class TestEnsureReady:
    def test_returns_ready_status(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail()}
            if method == "mcpServerStatus/list":
                return {"data": [_mcp_server(["screenshot"])], "nextCursor": None}
            if method == "thread/start":
                return {"thread": {"id": "t1"}}
            if method == "mcpServer/tool/call":
                return {}
            return {}

        status = asyncio.run(ensure_ready(CodexComputerUseConfig(enabled=True), request=req))
        assert status.ready

    def test_raises_when_not_ready_no_auto_install(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail(installed=False)}
            return {}

        with pytest.raises(CodexComputerUseSetupError) as exc_info:
            asyncio.run(
                ensure_ready(
                    CodexComputerUseConfig(enabled=True, auto_install=False),
                    request=req,
                )
            )
        assert exc_info.value.status.reason == "plugin_not_installed"

    def test_auto_install_blocked_with_marketplace_source(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "plugin/list":
                return {"marketplaces": []}
            return {}

        with pytest.raises(CodexComputerUseSetupError) as exc_info:
            asyncio.run(
                ensure_ready(
                    CodexComputerUseConfig(
                        enabled=True,
                        auto_install=True,
                        marketplace_source="https://example.com/market",
                        marketplace_discovery_timeout_ms=0,
                    ),
                    request=req,
                )
            )
        assert exc_info.value.status.reason == "auto_install_blocked"


# ── install ───────────────────────────────────────────────────────────────────


class TestInstall:
    def test_install_raises_on_failure(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method in ("experimentalFeature/enablement/set", "config/mcpServer/reload"):
                return {}
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                return {"plugin": _plugin_detail(installed=False)}
            if method == "plugin/install":
                return {}
            return {}

        with pytest.raises(CodexComputerUseSetupError):
            asyncio.run(install(request=req))

    def test_install_succeeds(self) -> None:
        install_called: list[bool] = []

        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method in ("experimentalFeature/enablement/set", "config/mcpServer/reload"):
                return {}
            if method == "plugin/list":
                return _make_listed()
            if method == "plugin/read":
                if install_called:
                    return {"plugin": _plugin_detail(installed=True, enabled=True)}
                return {"plugin": _plugin_detail(installed=False)}
            if method == "plugin/install":
                install_called.append(True)
                return {}
            if method == "mcpServerStatus/list":
                return {"data": [_mcp_server(["screenshot"])], "nextCursor": None}
            if method == "thread/start":
                return {"thread": {"id": "t1"}}
            if method == "mcpServer/tool/call":
                return {}
            return {}

        status = asyncio.run(install(request=req))
        assert status.ready
        assert install_called


# ── live test ─────────────────────────────────────────────────────────────────


class TestRunLiveTest:
    def test_passes_on_success(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "thread/start":
                return {"thread": {"id": "t1"}}
            return {}

        cfg = _resolved(auto_repair=False)
        live_test, repair = asyncio.run(run_live_test(req, cfg))
        assert live_test.ok
        assert live_test.status == "passed"
        assert live_test.attempts == 1
        assert repair is None

    def test_fails_after_retries(self) -> None:
        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "thread/start":
                return {"thread": {"id": "t1"}}
            if method == "mcpServer/tool/call":
                raise RuntimeError("tool unavailable")
            return {}

        cfg = _resolved(auto_repair=False)
        live_test, repair = asyncio.run(run_live_test(req, cfg))
        assert not live_test.ok
        assert live_test.status == "failed"
        assert live_test.attempts == 2  # 1 initial + 1 retry
        assert live_test.error is not None and "tool unavailable" in live_test.error

    def test_repair_attempted_on_first_failure(self) -> None:
        call_count: dict[str, int] = {"tool": 0, "reload": 0}

        async def req(method: str, params: Any = None, **kw: Any) -> Any:
            if method == "thread/start":
                return {"thread": {"id": "t1"}}
            if method == "mcpServer/tool/call":
                call_count["tool"] += 1
                if call_count["tool"] == 1:
                    raise RuntimeError("transient")
                return {}
            if method == "config/mcpServer/reload":
                call_count["reload"] += 1
                return {}
            return {}

        cfg = _resolved(auto_repair=True)
        live_test, repair = asyncio.run(run_live_test(req, cfg))
        assert live_test.ok  # passes on second attempt after repair
        assert live_test.retried is True
        assert repair is not None
        assert repair.attempted
        assert call_count["reload"] == 1
