"""jarvis.desktop_automation.core.task_continuity — Natural language task continuity resolver."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..state.active_desktop_context import ActiveDesktopContext


class TaskContinuityResolver:
    """Resolves multi-turn pronouns and continuation actions into concrete application commands."""

    def __init__(self, context: Optional[ActiveDesktopContext] = None) -> None:
        self.context = context or ActiveDesktopContext()

    def resolve_utterance(self, text: str) -> Optional[Dict[str, Any]]:
        """Resolve continuation intent from user utterance."""
        clean = text.strip().lower()

        # Send it / Send the message
        if re.search(r"\b(?:send\s+it|send\s+the\s+message|pathaideu|pathau|send\s+gare)\b", clean):
            return {
                "application": self.context.active_application or "whatsapp",
                "action": "send_message",
                "recipient": self.context.active_recipient,
                "message": self.context.pending_message,
                "is_continuation": True,
            }

        # Open his/her chat
        match_chat = re.search(r"\b(?:open\s+(?:his|her|their|the)\s+chat|chat\s+khol|chat\s+open\s+gara)\b", clean)
        if match_chat and self.context.active_recipient:
            return {
                "application": self.context.active_application or "whatsapp",
                "action": "open_chat",
                "recipient": self.context.active_recipient,
                "is_continuation": True,
            }

        # Save it / Save document
        if re.search(r"\b(?:save\s+it|save\s+the\s+file|save\s+gara)\b", clean):
            return {
                "application": self.context.active_application or "editor",
                "action": "save",
                "document": self.context.active_document,
                "is_continuation": True,
            }

        return None


# Alias for backward compatibility / facade naming
TaskContinuity = TaskContinuityResolver
