"""Backward-compatibility re-exports for jarvis_session_core.session_label."""
from __future__ import annotations

from jarvis_session_core.session_label import (
    ParsedSessionLabel,
    SESSION_LABEL_MAX_LENGTH,
    parse_session_label,
)

__all__ = [
    "ParsedSessionLabel",
    "SESSION_LABEL_MAX_LENGTH",
    "parse_session_label",
]
