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


# Backwards compatibility alias
start_openclaw_gateway_server = start_jarvis_gateway_server


def get_running_gateway() -> Any:
    return _running_gateway


__all__ = [
    "get_running_gateway",
    "start_jarvis_gateway_server",
    "start_openclaw_gateway_server",
]

