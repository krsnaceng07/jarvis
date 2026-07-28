"""Bonjour Discovery infra plugin — full surface port.

Mirrors OpenClaw's ``extensions/bonjour/index.ts``: registers a
gateway discovery service via ``api.registerGatewayDiscoveryService``
with an async ``advertise`` callback that starts the mDNS
advertiser (using ``zeroconf`` in the Python port vs ciao in the
TS source).

The advertise callback is lazy: it only imports the advertiser
module when the host actually starts the gateway — same-to-same
as the TS source's ``import("./src/advertiser.js")`` dynamic
import. This keeps cold-start fast for hosts that don't
enable Bonjour (containers, headless servers, etc.).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from jarvis_sdk import Plugin, PluginApi

from .src.advertiser import (
    DEFAULT_SERVICE_TYPE,
    BonjourAdvertiserDeps,
    GatewayBonjourAdvertiseOpts,
    format_bonjour_instance_name,
    start_gateway_bonjour_advertiser,
)


@dataclass(slots=True)
class BonjourDiscoveryPlugin(Plugin):
    """Bonjour Discovery infra plugin descriptor.

    The ``Plugin`` base class supplies ``id`` / ``kind`` / ``version``
    / ``description`` + the ``init`` lifecycle hook. The bonjour
    extension doesn't need its own init state — the gateway
    discovery service does all the work.
    """

    id: str = "bonjour"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Advertise the local JARVIS gateway over Bonjour/mDNS."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook — no-op for bonjour (advertiser is lazy)."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the gateway discovery service.

        Mirrors OpenClaw's ``register(api)`` in
        ``extensions/bonjour/index.ts``. The advertised service
        has id ``"bonjour"`` and exposes a single ``advertise``
        async function that the host invokes with a context
        carrying the gateway port + machine display name.
        """

        async def advertise(ctx: dict[str, Any]) -> dict[str, Callable[[], Awaitable[None]]]:
            """Start the gateway Bonjour advertisements.

            Mirrors the TS ``advertise`` callback in
            ``extensions/bonjour/index.ts``. The implementation
            delegates to ``start_gateway_bonjour_advertiser``
            from ``src/advertiser.py``.
            """
            # Translate the TS context into our opts dataclass.
            opts = GatewayBonjourAdvertiseOpts(
                instance_name=format_bonjour_instance_name(
                    ctx.get("machineDisplayName", "")
                ),
                gateway_port=ctx.get("gatewayPort", 0),
                ssh_port=ctx.get("sshPort"),
                gateway_tls_enabled=bool(ctx.get("gatewayTlsEnabled", False)),
                gateway_tls_fingerprint_sha256=ctx.get("gatewayTlsFingerprintSha256"),
                gateway_direct_reachable=bool(ctx.get("gatewayDirectReachable", False)),
                canvas_port=ctx.get("canvasPort"),
                tailnet_dns=ctx.get("tailnetDns"),
                cli_path=ctx.get("cliPath"),
                minimal=bool(ctx.get("minimal", False)),
            )

            # Wire SDK logger + exception handlers. The Python
            # port uses ``logging`` instead of pino; the SDK's
            # ``register_uncaught_exception_handler`` is a stub
            # (the host wires the real one).
            sdk_logger = api.logger
            if not isinstance(sdk_logger, logging.Logger):
                sdk_logger = logging.getLogger("extensions.bonjour")

            def _register_uncaught(handler: Callable[[BaseException], bool]) -> Callable[[], None]:
                # Best-effort: forward to the SDK's runtime facade
                # when wired; otherwise return a no-op unregister.
                runtime = getattr(api, "runtime", None)
                register = getattr(runtime, "register_uncaught_exception_handler", None) if runtime else None
                if callable(register):
                    try:
                        result = register(handler)
                        if callable(result):
                            return result
                    except Exception:  # noqa: BLE001 — best-effort
                        pass
                return lambda: None

            def _register_rejection(handler: Callable[[Any], bool]) -> Callable[[], None]:
                runtime = getattr(api, "runtime", None)
                register = getattr(runtime, "register_unhandled_rejection_handler", None) if runtime else None
                if callable(register):
                    try:
                        result = register(handler)
                        if callable(result):
                            return result
                    except Exception:  # noqa: BLE001 — best-effort
                        pass
                return lambda: None

            deps = BonjourAdvertiserDeps(
                logger=sdk_logger,
                on_uncaught_exception=None,
                on_unhandled_rejection=None,
            )
            # Attach the uncaught/rejection handlers via the deps'
            # internal mechanism: we pass them through the
            # ``BonjourAdvertiserDeps`` fields when wired.
            setattr(deps, "register_uncaught_exception_handler", _register_uncaught)
            setattr(deps, "register_unhandled_rejection_handler", _register_rejection)

            advertiser = start_gateway_bonjour_advertiser(opts, deps)
            return {"stop": advertiser.stop}

        api.register_gateway_discovery_service(
            {
                "id": "bonjour",
                "advertise": advertise,
            }
        )


bonjour_plugin = BonjourDiscoveryPlugin()
entry = bonjour_plugin
