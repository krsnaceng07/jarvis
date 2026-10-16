"""Backward-compatibility re-exports for jarvis_session_core.session_lifecycle_identity."""
from __future__ import annotations

from jarvis_session_core.session_lifecycle_identity import (
    decode_session_identity,
    normalize_session_identities,
)

__all__ = [
    "decode_session_identity",
    "normalize_session_identities",
]
