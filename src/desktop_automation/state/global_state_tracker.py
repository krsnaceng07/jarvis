"""jarvis.desktop_automation.state.global_state_tracker — Global task and runtime state tracker.

Mirrors OpenClaw's internal runtime context engine (internal-runtime-context.ts).
Provides a single canonical state tracker for active applications, workflow stages,
completed steps, and conversational self-healing flags.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .active_desktop_context import ActiveDesktopContext


class GlobalStateTracker:
    """Singleton state tracker coordinating desktop and session context."""

    _instance: Optional[GlobalStateTracker] = None

    def __init__(self) -> None:
        self.context = ActiveDesktopContext()

    @classmethod
    def get_instance(cls) -> GlobalStateTracker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def get_context(cls) -> ActiveDesktopContext:
        return cls.get_instance().context

    def reset(self) -> None:
        """Reset the global active desktop context."""
        self.context.reset()

    def record_action_start(self, tool_name: str, args: Dict[str, Any]) -> None:
        """Record the start of a tool action and update timing."""
        self.context.last_action_timestamp = time.time()
        # Derive task if not set
        if not self.context.current_task:
            if tool_name == "desktop":
                action = args.get("action", "")
                recipient = args.get("recipient", "")
                self.context.current_task = f"{action} (recipient: {recipient})" if recipient else action
            elif tool_name == "open_path":
                self.context.current_task = f"Open {args.get('target', '')}"
            elif tool_name == "browser":
                self.context.current_task = f"Browser {args.get('action', '')}"

    def record_action_outcome(
        self,
        tool_name: str,
        args: Dict[str, Any],
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record completed tool action, advance workflow stage, and update step ledger."""
        step_desc = f"{tool_name}({args.get('action') or args.get('target') or ''})"
        self.context.record_step(step_desc, status=status, details=details)

        # Update active application heuristic
        if tool_name == "desktop":
            action = str(args.get("action", ""))
            app = str(args.get("application", "")).lower()
            if "whatsapp" in action or app == "whatsapp" or self.context.active_application == "WhatsApp":
                self.context.active_application = "WhatsApp"
                if "send" in action:
                    self.context.workflow_stage = "message_sent"
                elif "chat" in action or "search" in action:
                    self.context.workflow_stage = "chat_opened"
            elif "calc" in action:
                self.context.active_application = "Calculator"
                self.context.workflow_stage = "calculated"
            elif "vscode" in action:
                self.context.active_application = "VS Code"
            recipient = args.get("recipient") or args.get("contact")
            if recipient:
                self.context.active_recipient = str(recipient)

        elif tool_name == "open_path":
            target = str(args.get("target", "")).lower()
            if "whatsapp" in target:
                self.context.active_application = "WhatsApp"
                self.context.workflow_stage = "app_opened"
            elif "explorer" in target:
                self.context.active_application = "File Explorer"
            elif "notepad" in target:
                self.context.active_application = "Notepad"
            elif "terminal" in target or "wt" in target:
                self.context.active_application = "Terminal"

        elif tool_name == "browser":
            self.context.active_application = "Browser"
            url = args.get("url") or args.get("targetUrl") or ""
            if "youtube.com" in str(url):
                self.context.workflow_stage = "youtube_browsing"

        # If user reported failure was being tracked and this action succeeded, clear it
        if status == "success" and self.context.user_reported_failure:
            self.context.user_reported_failure = False
            self.context.needs_remedy_for = None

    def record_user_negation_feedback(self, raw_utterance: str) -> None:
        """Mark that user observed failure ('chaina', 'bhayena', 'khulena')."""
        self.context.user_reported_failure = True
        self.context.needs_remedy_for = self.context.last_verified_action or "last requested action"

    def format_runtime_context_trailer(self) -> str:
        """Return formatted OpenClaw-grade runtime context block."""
        return self.context.format_runtime_state_trailer()
