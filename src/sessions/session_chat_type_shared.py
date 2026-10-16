"""Backward-compatibility re-exports for jarvis_session_core.session_chat_type_shared."""
from __future__ import annotations

from jarvis_session_core.session_chat_type_shared import (
    CanonicalSessionPeerShape,
    SessionKeyChatType,
    derive_session_chat_type_from_key,
    has_ambiguous_canonical_session_peer_shape,
    parse_canonical_session_peer_shape,
)

__all__ = [
    "CanonicalSessionPeerShape",
    "SessionKeyChatType",
    "derive_session_chat_type_from_key",
    "has_ambiguous_canonical_session_peer_shape",
    "parse_canonical_session_peer_shape",
]
