"""Admin HTTP RPC infra plugin definition.

Mirrors OpenClaw's ``extensions/admin-http-rpc/src/index.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin

from .src.handler import AdminHttpRpcHandler
from .src.methods import ADMIN_HTTP_RPC_ROUTE_PATH


@dataclass(frozen=True, slots=True)
class AdminHTTPRPCPlugin(Plugin):
    """Admin HTTP RPC infra descriptor."""

    id: str = "admin-http-rpc"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = (
        "Exposes an allowlisted set of Gateway control-plane methods over HTTP "
        "for trusted host automation."
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Register the Admin HTTP RPC route on plugin startup."""
        dispatch_fn = getattr(ctx, "dispatch_gateway_method", None)
        handler = AdminHttpRpcHandler(dispatch_method=dispatch_fn)

        # Register route with Gateway HTTP server
        if hasattr(ctx, "register_http_route"):
            ctx.register_http_route(
                path=ADMIN_HTTP_RPC_ROUTE_PATH,
                method="POST",
                handler=handler.handle_request,
            )
        elif hasattr(ctx, "register_http_handler"):
            ctx.register_http_handler(
                path=ADMIN_HTTP_RPC_ROUTE_PATH,
                handler=handler.handle_request,
            )


admin_http_rpc_plugin = AdminHTTPRPCPlugin()
entry = admin_http_rpc_plugin

__all__ = ["AdminHTTPRPCPlugin", "admin_http_rpc_plugin", "entry"]
