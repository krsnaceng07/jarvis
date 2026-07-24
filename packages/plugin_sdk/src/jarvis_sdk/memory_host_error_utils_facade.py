"""jarvis_sdk.memory_host_error_utils_facade — public SDK re-export.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/memory-host-sdk/error-utils.ts``
(the SDK root facade that re-exports the public surface from
``host/error-utils.ts``).

The Python port re-exports the same public surface from
``jarvis_sdk.memory_host_error_utils``:
- ``format_error_message`` — format + redact secrets.
- ``redact_sensitive_text`` — apply the SECRET_PATTERNS list.
"""
from __future__ import annotations

from .memory_host_error_utils import (
    format_error_message,
    redact_sensitive_text,
)

__all__ = [
    "format_error_message",
    "redact_sensitive_text",
]
