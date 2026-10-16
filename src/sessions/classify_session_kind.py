"""Backward-compatibility re-exports for jarvis_session_core.classify_session_kind."""
from __future__ import annotations

from jarvis_session_core.classify_session_kind import (
    classify_session_kind,
    is_valid_session_kind,
)

__all__ = ["classify_session_kind", "is_valid_session_kind"]
