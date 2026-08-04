"""jarvis.config.zod_schema_session — session/messages Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.session.ts``.

Focused minimal port: thin facade with placeholder Zod schemas plus
the maintenance size/duration validators that don't require the full
zod runtime.
"""
from __future__ import annotations

import re
from typing import Any, Optional


_BYTE_SIZE_RE = re.compile(r"^\s*\d+(\.\d+)?\s*(b|kb|mb|gb|tb)\s*$", re.IGNORECASE)
_DURATION_RE = re.compile(r"^\s*\d+(\.\d+)?\s*(ms|s|m|h|d)\s*$", re.IGNORECASE)


def is_valid_byte_size(value: Any) -> bool:
    """Return whether ``value`` parses as a byte-size string or number > 0."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return bool(_BYTE_SIZE_RE.match(value))
    return False


def is_valid_duration(value: Any) -> bool:
    """Return whether ``value`` parses as a positive duration string or number."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return bool(_DURATION_RE.match(value))
    return False


def validate_session_maintenance_size_bytes(value: Any) -> Optional[list]:
    """Validate the maintenance block's size fields, returning a list of issues."""
    if not isinstance(value, dict):
        return None
    issues: list = []
    raw = value.get("maxDiskBytes")
    if raw is not None and raw is not False and not is_valid_byte_size(raw):
        issues.append({
            "path": ["maxDiskBytes"],
            "message": "invalid size (use b, kb, mb, gb, tb)",
        })
    high = value.get("highWaterBytes")
    if high is not None and not is_valid_byte_size(high):
        issues.append({
            "path": ["highWaterBytes"],
            "message": "invalid size (use b, kb, mb, gb, tb)",
        })
    return issues or None


#: Session config schema (zod facade).
SessionSchema: Any = None

#: Messages config schema (zod facade).
MessagesSchema: Any = None

#: Commands config schema (zod facade).
CommandsSchema: Any = None

#: Session send policy schema (zod facade).
SessionSendPolicySchema: Any = None


__all__ = [
    "is_valid_byte_size",
    "is_valid_duration",
    "validate_session_maintenance_size_bytes",
    "SessionSchema",
    "MessagesSchema",
    "CommandsSchema",
    "SessionSendPolicySchema",
]
