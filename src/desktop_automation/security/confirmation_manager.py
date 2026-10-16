"""jarvis.desktop_automation.security.confirmation_manager — Human-in-the-loop action gating."""

from __future__ import annotations

from typing import Any, Dict


class ConfirmationManager:
    """Manages explicit confirmations for external side-effects and destructive actions."""

    _CONFIRMATION_REQUIRED_ACTIONS = {
        "send_message",
        "call_contact",
        "make_call",
        "video_call",
        "voice_call",
        "delete_file",
        "delete_chat",
        "clear_chat",
        "modify_security_setting",
        "kill_process",
    }

    @classmethod
    def requires_confirmation(cls, action_type: str, arguments: Dict[str, Any]) -> bool:
        if action_type.lower() in cls._CONFIRMATION_REQUIRED_ACTIONS:
            return True
        return False

    @classmethod
    def build_confirmation_prompt(cls, action_type: str, arguments: Dict[str, Any]) -> str:
        if action_type in ("call_contact", "make_call", "video_call", "voice_call"):
            recipient = arguments.get("recipient", "contact")
            call_type = arguments.get("call_type", "call")
            return f"Sir, please confirm if you want to make a {call_type} call to {recipient}."
        if action_type == "send_message":
            recipient = arguments.get("recipient", "contact")
            msg = arguments.get("message", "")
            return f"Sir, I have prepared the message to {recipient}: {repr(msg)}. Shall I send it now?"
        if action_type == "delete_file":
            path = arguments.get("path", "file")
            return f"Sir, are you sure you want to delete {path}?"
        return f"Sir, please confirm if you want to proceed with {action_type}."
