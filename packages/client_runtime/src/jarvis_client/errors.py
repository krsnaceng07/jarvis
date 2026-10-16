"""Client error taxonomy and exception definitions for Track 3.5.

Maps Gateway protocol error codes (-32700 .. -32014) to client-side typed exceptions.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ClientErrorCode(IntEnum):
    """Standardized JSON-RPC 2.0 and Gateway typed error codes."""

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

    # Track 3.5 Client Runtime Errors (-31001 .. -31010)
    CONNECTION_LOST = -31001
    RESUME_FAILED = -31002
    STALE_APPROVAL = -31003
    UNKNOWN_REQUEST_STATE = -31004
    UNKNOWN_SCHEMA_VERSION = -31005
    CLIENT_OFFLINE = -31006
    CORRUPTED_VIEW_STATE = -31007


class JarvisClientException(Exception):
    """Base exception for all JARVIS client runtime errors."""

    def __init__(self, code: int | ClientErrorCode, message: str, data: Any = None) -> None:
        super().__init__(f"[{int(code)}] {message}")
        self.code = int(code)
        self.message = message
        self.data = data


class AuthenticationError(JarvisClientException):
    """Raised when authentication fails or credential expires."""


class StaleActionError(JarvisClientException):
    """Raised when attempting an approval or action on a stale plan/node."""


class AmbiguousRequestError(JarvisClientException):
    """Raised when a mutating request's outcome is unknown and requires reconciliation."""


class OfflineError(JarvisClientException):
    """Raised when a mutating action is attempted while the client is offline."""


class ProtocolViolationError(JarvisClientException):
    """Raised when server or frame violates gateway protocol."""


class SequenceGapError(JarvisClientException):
    """Raised when an unrecoverable gap is detected in the event stream."""


__all__ = [
    "ClientErrorCode",
    "JarvisClientException",
    "AuthenticationError",
    "StaleActionError",
    "AmbiguousRequestError",
    "OfflineError",
    "ProtocolViolationError",
    "SequenceGapError",
]
