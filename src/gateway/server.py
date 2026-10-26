"""jarvis.gateway.server — JARVIS JSON-RPC Gateway Server bootstrap."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("jarvis.gateway.server")

_running_gateway: Any = None


async def start_jarvis_gateway_server(host: str = "127.0.0.1", port: int = 7433) -> Any:
    """Start the JARVIS JSON-RPC Gateway server non-blockingly."""
    global _running_gateway
    if _running_gateway is not None:
        return _running_gateway

    # Check if port is already bound by an existing gateway process
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        if s.connect_ex((host, port)) == 0:
            logger.debug("Gateway port %s:%d already bound by another instance", host, port)
            return None

    try:
        from src.gateway import Gateway

        gw = Gateway(host=host, port=port)
        await asyncio.to_thread(gw.start)
        _running_gateway = gw
        logger.info("JARVIS Gateway server running on %s:%d", host, port)
        return gw
    except Exception as exc:
        logger.debug("Gateway server start skipped or already running: %s", exc)
        return None


def get_running_gateway() -> Any:
    return _running_gateway


__all__ = [
    "get_running_gateway",
    "start_jarvis_gateway_server",
]

