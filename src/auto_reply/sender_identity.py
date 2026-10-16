"""jarvis.auto_reply.sender_identity - Shared sender identity helpers for authorization checks.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/sender-identity.ts``.
"""

from __future__ import annotations

import re
from typing import Optional

from jarvis.utils import _lower


def is_conversation_like_identity(value: Optional[str]) -> bool:
    """Check if the identity value represents a conversation (group, channel, etc) rather than a person."""
    if not value:
        return False
    normalized = _lower(value)
    if not normalized:
        return False
    if normalized.startswith("chat_id:"):
        return True
    
    # Mirror RegExp: /(^|:)(channel|group|thread|topic|room|space|spaces):/
    return bool(re.search(r"(^|:)(channel|group|thread|topic|room|space|spaces):", normalized))


def should_use_from_as_sender_fallback(from_val: Optional[str] = None, chat_type: Optional[str] = None) -> bool:
    """Determine if 'From' field should be used as fallback when 'SenderId' is not present."""
    normalized_from = (from_val or "").strip()
    if not normalized_from:
        return False
    
    normalized_chat_type = _lower(chat_type)
    if normalized_chat_type and normalized_chat_type != "direct":
        return False
        
    return not is_conversation_like_identity(normalized_from)
