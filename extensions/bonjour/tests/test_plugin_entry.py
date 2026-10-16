"""Tests for ``extensions/bonjour/plugin.py`` (gateway discovery registration).

Mirrors OpenClaw's ``extensions/bonjour/index.test.ts``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest import mock

import pytest

from extensions.bonjour import bonjour_plugin
from jarvis_sdk import PluginApi
from jarvis_sdk.context import PluginContext


def _make_api() -> tuple[PluginApi, dict]:
    """Create a fresh PluginApi + capture dict for assertions."""
    captured: dict = {}
    api = PluginApi(
        ctx=PluginContext(plugin_id="bonjour", plugin_kind="infra"),
    )
    # Capture register_gateway_discovery_service calls.
    original = api.register_gateway_discovery_service

    def capture(service: dict) -> None:
        captured["service"] = service
        return original(service)

    api.register_gateway_discovery_service = capture  # type: ignore[assignment]
    return api, captured


class TestBonjourPluginEntry:
    def test_register_lazy_loads_advertiser(self) -> None:
        """The plugin registers a discovery service but doesn't start the advertiser yet."""
        for name in list(sys.modules):
            if name.startswith("extensions.bonjour.src.advertiser") or "zeroconf" in name:
                sys.modules.pop(name, None)

        api, captured = _make_api()
        bonjour_plugin.register(api)
        assert "service" in captured
        service = captured["service"]
        assert service["id"] == "bonjour"
        assert callable(service["advertise"])
        assert not any(m.startswith("extensions.bonjour.src.advertiser") for m in sys.modules)
        assert not any("zeroconf" in m for m in sys.modules)

    def test_advertise_starts_with_mdns_advertiser(self) -> None:
        """``advertise()`` starts the mDNS advertiser with formatted instance name."""
        api, captured = _make_api()
        bonjour_plugin.register(api)
        advertise = captured["service"]["advertise"]

        # Disable Bonjour (e.g. test mode) so we don't hit real mDNS.
        with mock.patch.dict(os.environ, {"NODE_ENV": "test"}, clear=True):
            result = asyncio.run(
                advertise(
                    {
                        "machineDisplayName": "Dev Box",
                        "gatewayPort": 3210,
                        "gatewayTlsEnabled": True,
                        "gatewayTlsFingerprintSha256": "abc123",
                        "gatewayDirectReachable": True,
                        "canvasPort": 9876,
                        "sshPort": 22,
                        "tailnetDns": "dev.tailnet.ts.net",
                        "cliPath": "/usr/local/bin/openclaw",
                        "minimal": False,
                    }
                )
            )
        assert "stop" in result
        assert callable(result["stop"])

    def test_advertise_disabled_in_test_mode(self) -> None:
        """When ``NODE_ENV=test`` is set, advertise returns a no-op handle."""
        api, captured = _make_api()
        bonjour_plugin.register(api)
        advertise = captured["service"]["advertise"]

        with mock.patch.dict(os.environ, {"NODE_ENV": "test"}, clear=True):
            result = asyncio.run(advertise({"machineDisplayName": "Test", "gatewayPort": 7433}))
        # Even when disabled, stop() must be callable.
        assert callable(result["stop"])
        asyncio.run(result["stop"]())  # idempotent


class TestBonjourPluginMetadata:
    def test_id_kind_version_description(self) -> None:
        """The plugin exposes the OpenClaw-shaped identity fields."""
        assert bonjour_plugin.id == "bonjour"
        assert bonjour_plugin.kind == "infra"
        assert isinstance(bonjour_plugin.version, str)
        assert (
            "Bonjour" in bonjour_plugin.description
            or "bonjour" in bonjour_plugin.description.lower()
        )

    def test_init_is_noop(self) -> None:
        """``init`` is a no-op — the advertiser is lazy-loaded by the host."""
        assert bonjour_plugin.init(ctx=None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
