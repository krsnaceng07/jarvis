"""jarvis.gateway.presence_events — presence snapshot broadcaster.

OpenClaw parity: mirrors ``src/gateway/server/presence-events.ts``.

Provides the ``broadcast_presence_snapshot`` helper that the gateway uses to
push a fresh presence list to all connected clients with synchronized state
version numbers.
"""

from __future__ import annotations

from typing import Any, Callable

from src.infra.system_presence import list_system_presence

# ---------------------------------------------------------------------------
# Type alias for the broadcast callable
# ---------------------------------------------------------------------------
# Mirrors GatewayBroadcastFn from server-broadcast-types.ts.
# Signature: broadcast(event, payload, opts) -> None
GatewayBroadcastFn = Callable[[str, dict[str, Any], dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def broadcast_presence_snapshot(
    *,
    broadcast: GatewayBroadcastFn,
    increment_presence_version: Callable[[], int],
    get_health_version: Callable[[], int],
) -> int:
    """Broadcast a fresh presence snapshot to all gateway clients.

    Mirrors ``broadcastPresenceSnapshot`` (``gateway/server/presence-events.ts``).

    Increments the presence version counter, then pushes the full presence list
    via *broadcast* with synchronized ``stateVersion`` metadata so clients can
    detect missed updates.

    Returns the new presence version number.
    """
    presence_version = increment_presence_version()
    payload = {
        "presence": [entry.to_dict() for entry in list_system_presence()],
    }
    opts = {
        "dropIfSlow": True,
        "stateVersion": {
            "presence": presence_version,
            "health": get_health_version(),
        },
    }
    broadcast("presence", payload, opts)
    return presence_version


__all__ = [
    "GatewayBroadcastFn",
    "broadcast_presence_snapshot",
]
