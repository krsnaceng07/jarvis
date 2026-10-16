"""jarvis.commands.gateway_presence — gateway self-presence command helpers.

OpenClaw parity: mirrors ``src/commands/gateway-presence.ts``.

Provides ``pick_gateway_self_presence``, a thin re-export of the same function
from :mod:`src.infra.system_presence` that the command layer uses to extract
the gateway host/ip/version from a presence payload.
"""

from __future__ import annotations

from src.infra.system_presence import pick_gateway_self_presence

__all__ = [
    "pick_gateway_self_presence",
]
