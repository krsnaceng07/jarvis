"""Gateway error taxonomy and error definitions for Track 3.4.

Defines standardized JSON-RPC 2.0 and Track 3.4 domain error codes and exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class GatewayErrorCode(IntEnum):
    """Standardized JSON-RPC 2.0 and Track 3.4 typed error codes."""

    # Standard JSON-RPC 2.0 errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Track 3.4 Domain Errors (-32001 .. -32014)
    AUTH_FAILED = -32001
    SESSION_FORBIDDEN = -32002
    REQUEST_DUPLICATE = -32003
    REQUEST_CONFLICT = -32004
    APPROVAL_EXPIRED = -32005
    APPROVAL_ALREADY_RESOLVED = -32006
    APPROVAL_BINDING_MISMATCH = -32007
    INVALID_CURSOR = -32008
    CURSOR_TOO_OLD = -32009
    EVENT_HISTORY_UNAVAILABLE = -32010
    RATE_LIMITED = -32011
    FRAME_TOO_LARGE = -32012
    SLOW_DRAIN_TIMEOUT = -32013
    PROTOCOL_VERSION_UNSUPPORTED = -32014


from jarvis_gateway_protocol.schema import GatewayError


class GatewayException(Exception):
    """Base exception for Gateway protocol and transport errors."""

    def __init__(
        self,
        code: GatewayErrorCode | int,
        message: str,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = int(code)
        self.message = message
        self.data = data

    def to_gateway_error(self) -> GatewayError:
        return GatewayError(code=self.code, message=self.message, data=self.data)


__all__ = ["GatewayErrorCode", "GatewayError", "GatewayException"]
