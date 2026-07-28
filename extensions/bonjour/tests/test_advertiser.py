"""Tests for ``extensions/bonjour/src/advertiser.py``.

Mirrors the key cases from OpenClaw's
``extensions/bonjour/src/advertiser.test.ts`` but adapted
to the Python ``zeroconf`` API (no ciao mocks).
"""
from __future__ import annotations

import asyncio
import os
from unittest import mock

import pytest

from extensions.bonjour.src.advertiser import (
    DEFAULT_SERVICE_TYPE,
    BonjourAdvertiserDeps,
    GatewayBonjourAdvertiseOpts,
    format_bonjour_instance_name,
    start_gateway_bonjour_advertiser,
)
from extensions.bonjour.src.env_helpers import (
    is_disabled_by_env,
    prettify_instance_name,
    safe_service_name,
    truncate_to_dns_label,
)


def _txt(info) -> dict[str, str]:
    """Decode a ``ServiceInfo.properties`` dict to str keys/values."""
    return {k.decode("utf-8"): v.decode("utf-8") for k, v in (info.properties or {}).items()}


class TestFormatBonjourInstanceName:
    def test_empty_returns_openclaw(self) -> None:
        assert format_bonjour_instance_name("") == "openclaw"
        assert format_bonjour_instance_name("   ") == "openclaw"

    def test_already_contains_openclaw_unchanged(self) -> None:
        assert format_bonjour_instance_name("openclaw") == "openclaw"
        assert format_bonjour_instance_name("OpenClaw Gateway") == "OpenClaw Gateway"
        assert format_bonjour_instance_name("my-OPENCLAW-host") == "my-OPENCLAW-host"

    def test_appends_openclaw_suffix(self) -> None:
        assert format_bonjour_instance_name("MyHost") == "MyHost (openclaw)"
        assert format_bonjour_instance_name("  MyHost  ") == "MyHost (openclaw)"


class TestGatewayBonjourAdvertiseOpts:
    def test_defaults(self) -> None:
        opts = GatewayBonjourAdvertiseOpts(gateway_port=7433)
        assert opts.gateway_port == 7433
        assert opts.ssh_port is None
        assert opts.gateway_tls_enabled is False
        assert opts.canvas_port is None
        assert opts.minimal is False
        assert opts.service_type == DEFAULT_SERVICE_TYPE
        assert opts.domain == "local."


class TestStartGatewayBonjourAdvertiserDisabled:
    def test_disabled_via_node_env(self) -> None:
        with mock.patch.dict(os.environ, {"NODE_ENV": "test"}, clear=True):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(gateway_port=7433),
            )
        # No services registered.
        assert handle._services == []
        # Stop is a no-op.
        asyncio.run(handle.stop())

    def test_disabled_via_vitest(self) -> None:
        with mock.patch.dict(os.environ, {"VITEST": "1"}, clear=True):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(gateway_port=7433),
            )
        assert handle._services == []
        asyncio.run(handle.stop())

    def test_disabled_via_env_override(self) -> None:
        with mock.patch.dict(
            os.environ, {"OPENCLAW_DISABLE_BONJOUR": "true"}, clear=True
        ):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(gateway_port=7433),
            )
        assert handle._services == []
        asyncio.run(handle.stop())


class TestStartGatewayBonjourAdvertiserHostname:
    def test_uses_openclaw_mdns_hostname_override(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "NODE_ENV": "development",
                "OPENCLAW_MDNS_HOSTNAME": "k8s-pod-abc123",
                "VITEST": "",
            },
            clear=True,
        ):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(
                    gateway_port=7433,
                    ssh_port=22,
                ),
                deps=BonjourAdvertiserDeps(),
            )
        try:
            assert len(handle._services) == 1
            info = handle._services[0]
            # The hostname is the first label of the override
            # (the dot-trimming keeps only the first label).
            assert "k8s-pod-abc123" in info.server
        finally:
            asyncio.run(handle.stop())

    def test_truncates_long_hostname_to_dns_label(self) -> None:
        long_name = "a" * 100
        with mock.patch.dict(
            os.environ,
            {
                "NODE_ENV": "development",
                "OPENCLAW_MDNS_HOSTNAME": long_name,
                "VITEST": "",
            },
            clear=True,
        ):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(gateway_port=7433),
                deps=BonjourAdvertiserDeps(),
            )
        try:
            info = handle._services[0]
            # Server name is "{hostname}.local"; the hostname is
            # the first label, truncated to 63 bytes.
            server = info.server.removesuffix(".local")
            assert len(server.encode("utf-8")) <= 63
        finally:
            asyncio.run(handle.stop())


class TestStartGatewayBonjourAdvertiserTxt:
    def _make_handle(self, **kwargs) -> tuple[Any, Any]:
        env = {
            "NODE_ENV": "development",
            "VITEST": "",
            "OPENCLAW_MDNS_HOSTNAME": "test-host",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(gateway_port=7433, **kwargs),
                deps=BonjourAdvertiserDeps(),
            )
        return handle, handle._services[0]

    def test_publishes_expected_txt_keys_full_mode(self) -> None:
        handle, info = self._make_handle(
            ssh_port=2222,
            gateway_direct_reachable=True,
            tailnet_dns="host.tailnet.ts.net",
            cli_path="/opt/homebrew/bin/openclaw",
        )
        try:
            txt = _txt(info)
            assert txt["role"] == "gateway"
            assert txt["gatewayPort"] == "7433"
            assert txt["lanHost"] == "test-host.local"
            assert txt["transport"] == "gateway"
            assert txt["sshPort"] == "2222"
            assert txt["gatewayDirectReachable"] == "1"
            assert txt["tailnetDns"] == "host.tailnet.ts.net"
            assert txt["cliPath"] == "/opt/homebrew/bin/openclaw"
        finally:
            asyncio.run(handle.stop())

    def test_omits_ssh_cli_tailnet_in_minimal_mode(self) -> None:
        handle, info = self._make_handle(
            ssh_port=2222,
            cli_path="/opt/homebrew/bin/openclaw",
            tailnet_dns="host.tailnet.ts.net",
            minimal=True,
        )
        try:
            txt = _txt(info)
            assert "sshPort" not in txt
            assert "cliPath" not in txt
            assert "tailnetDns" not in txt
            # Other keys still present
            assert txt["role"] == "gateway"
            assert txt["transport"] == "gateway"
        finally:
            asyncio.run(handle.stop())

    def test_tls_keys_omitted_when_disabled(self) -> None:
        handle, info = self._make_handle()
        try:
            txt = _txt(info)
            assert "gatewayTls" not in txt
            assert "gatewayTlsSha256" not in txt
        finally:
            asyncio.run(handle.stop())

    def test_tls_keys_present_when_enabled(self) -> None:
        handle, info = self._make_handle(
            gateway_tls_enabled=True,
            gateway_tls_fingerprint_sha256="abc123",
        )
        try:
            txt = _txt(info)
            assert txt["gatewayTls"] == "1"
            assert txt["gatewayTlsSha256"] == "abc123"
        finally:
            asyncio.run(handle.stop())

    def test_canvas_port_omitted_when_zero(self) -> None:
        handle, info = self._make_handle(canvas_port=0)
        try:
            txt = _txt(info)
            assert "canvasPort" not in txt
        finally:
            asyncio.run(handle.stop())

    def test_canvas_port_present_when_positive(self) -> None:
        handle, info = self._make_handle(canvas_port=9876)
        try:
            txt = _txt(info)
            assert txt["canvasPort"] == "9876"
        finally:
            asyncio.run(handle.stop())

    def test_instance_name_in_display_name(self) -> None:
        handle, info = self._make_handle(instance_name="My Custom Host")
        try:
            txt = _txt(info)
            # The display name is prettified — the (openclaw) suffix
            # is stripped for display purposes.
            assert txt["displayName"] == "My Custom Host"
        finally:
            asyncio.run(handle.stop())


class TestStartGatewayBonjourAdvertiserStop:
    def test_stop_is_idempotent(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "NODE_ENV": "development",
                "VITEST": "",
                "OPENCLAW_MDNS_HOSTNAME": "test-host",
            },
            clear=True,
        ):
            handle = start_gateway_bonjour_advertiser(
                GatewayBonjourAdvertiseOpts(gateway_port=7433),
            )
        # Multiple stop calls should not raise.
        asyncio.run(handle.stop())
        asyncio.run(handle.stop())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
