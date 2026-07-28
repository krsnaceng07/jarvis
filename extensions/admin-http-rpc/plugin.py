"""Admin HTTP RPC infra plugin definition.

OpenClaw parity: mirrors the OpenClaw ``admin-http-rpc`` infra
extension (8 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin


@dataclass(frozen=True, slots=True)
class AdminHTTPRPCPlugin(Plugin):
    """Admin HTTP RPC infra descriptor."""

    id: str = "admin-http-rpc"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Admin HTTP RPC for gateway admin."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub in Phase 5.15."""
        return None


admin_http_rpc_plugin = AdminHTTPRPCPlugin()
entry = admin_http_rpc_plugin
