"""JARVIS Gateway WebSocket Client — JSON-RPC 2.0 client for Port 7433.

Provides full duplex JSON-RPC 2.0 communication over WebSocket between
clients (Desktop HUD, CLI, TUI, Web Control UI) and the Gateway micro-kernel.
"""

from __future__ import annotations

from jarvis_gateway_protocol.client import GatewayWSClient

__all__ = ["GatewayWSClient"]
