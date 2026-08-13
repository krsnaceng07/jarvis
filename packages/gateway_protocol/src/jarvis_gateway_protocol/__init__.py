"""jarvis_gateway_protocol — JARVIS gateway WebSocket schema.

Mirrors OpenClaw's ``packages/gateway-protocol/`` (60+ schema files).
Phase W0.4 starts with the minimal contract:

- ``version.py``  — protocol version constant
- ``schema.py``   — Gateway request/response/error dataclasses
- ``validators.py`` — validate_request() / validate_response()

The gateway uses these shapes on every inbound and outbound frame
(HTTP and WebSocket). Clients deserialize gateway responses using
the same shapes.
"""

from __future__ import annotations

from .schema import (
    GatewayError,
    RPCMethod,
    GatewayRequest,
    GatewayResponse,
    GatewayEvent,
    RPCRequest,
    RPCResponse,
)
from .validators import validate_request, validate_response
from .version import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "GatewayError",
    "RPCMethod",
    "GatewayRequest",
    "GatewayResponse",
    "GatewayEvent",
    "validate_request",
    "validate_response",
]

# Export JSON-RPC shapes and keep GatewayError as RPCError alias for compatibility.
RPCError = GatewayError
__all__ += ["RPCError", "RPCRequest", "RPCResponse"]
