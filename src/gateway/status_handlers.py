"""Gateway health and status RPC handlers — mirrors OpenClaw's:
- src/gateway/server-methods/health.ts
- src/gateway/server-methods/system.ts
"""

from __future__ import annotations

import time
from typing import Any

from src.system.system_metrics import SystemMetrics

_START_TIME = time.time()


def make_system_handlers() -> dict[str, Any]:
    """Build and return gateway RPC handlers for health, status, and host system info."""

    def status_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        uptime_sec = round(time.time() - _START_TIME, 2)
        telemetry = SystemMetrics.get_full_system_telemetry()
        return {
            "ok": True,
            "status": "healthy",
            "uptime_seconds": uptime_sec,
            "system": telemetry,
        }

    def health_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "healthy": True,
            "timestamp": time.time(),
        }

    def system_info_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        return SystemMetrics.get_full_system_telemetry()

    def last_heartbeat_handler(params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "timestamp": time.time(),
            "status": "alive",
        }

    return {
        "status": status_handler,
        "status.get": status_handler,
        "health": health_handler,
        "health.get": health_handler,
        "system.info": system_info_handler,
        "system_info": system_info_handler,
        "last-heartbeat": last_heartbeat_handler,
    }


__all__ = ["make_system_handlers"]
