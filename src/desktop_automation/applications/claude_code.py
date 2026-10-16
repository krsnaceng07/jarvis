"""jarvis.desktop_automation.applications.claude_code — Claude Code CLI / terminal adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class ClaudeCodeDesktopAdapter(BaseDesktopApplicationAdapter):
    """Claude Code CLI automation adapter."""

    app_id = "claude_code"
    app_name = "Claude Code"
    process_names = ["node.exe", "cmd.exe", "powershell.exe", "wt.exe", "conhost.exe"]
    title_patterns = ["Claude", "claude"]

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "submit_prompt":
            prompt = str(params.get("prompt") or params.get("text") or "")
            prev = self.get_clipboard_text()
            self.set_clipboard_text(prompt)
            self.hotkey("ctrl", "v")
            await asyncio.sleep(0.1)
            self.press_key("enter")
            if prev:
                self.set_clipboard_text(prev)
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"prompt_length": len(prompt)},
            )

        if action == "cancel":
            self.hotkey("ctrl", "c")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        return DesktopActionResult(
            ok=False, action=action, application=self.app_id,
            error=f"Claude Code action '{action}' is not supported",
        )
