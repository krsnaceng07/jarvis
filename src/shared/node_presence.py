"""jarvis.shared.node_presence — node presence normalization.

OpenClaw parity: mirrors ``openclaw-main/src/shared/node-presence.ts``.
"""
from __future__ import annotations

from typing import Any, Literal, Set

#: Gateway event name used by node hosts to refresh last-seen presence.
NODE_PRESENCE_ALIVE_EVENT = "node.presence.alive"

#: Gateway event name used by interactive nodes to report local input.
NODE_PRESENCE_ACTIVITY_EVENT = "node.presence.activity"

#: Reasons accepted from native/background node presence events.
_NODE_PRESENCE_ALIVE_REASONS = (
    "background",
    "silent_push",
    "bg_app_refresh",
    "significant_location",
    "manual",
    "connect",
)

NodePresenceAliveReason = Literal[
    "background",
    "silent_push",
    "bg_app_refresh",
    "significant_location",
    "manual",
    "connect",
]

_NODE_PRESENCE_ALIVE_REASON_SET: Set[str] = set(_NODE_PRESENCE_ALIVE_REASONS)


def normalize_node_presence_alive_reason(value: Any) -> str:
    """Normalize a presence trigger reason, defaulting unknown to ``"background"``.

    Mirrors :func:`normalizeNodePresenceAliveReason`
    (``shared/node-presence.ts``).
    """
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized and normalized in _NODE_PRESENCE_ALIVE_REASON_SET:
            return normalized
    return "background"


__all__ = [
    "NODE_PRESENCE_ALIVE_EVENT",
    "NODE_PRESENCE_ACTIVITY_EVENT",
    "normalize_node_presence_alive_reason",
    "NodePresenceAliveReason",
]
