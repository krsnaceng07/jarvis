"""Backward-compatibility re-exports for jarvis_session_core.session_id_resolution."""
from __future__ import annotations

from jarvis_session_core.session_id_resolution import (
    SessionEntry,
    SessionIdMatchSelection,
    resolve_preferred_session_key_for_session_id_matches,
    resolve_session_id_match_selection,
)

__all__ = [
    "SessionEntry",
    "SessionIdMatchSelection",
    "resolve_preferred_session_key_for_session_id_matches",
    "resolve_session_id_match_selection",
]
