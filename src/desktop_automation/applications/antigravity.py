"""jarvis.desktop_automation.applications.antigravity — Antigravity IDE application adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class AntigravityDesktopAdapter(BaseDesktopApplicationAdapter):
    """Antigravity IDE desktop application adapter."""

    app_id = "antigravity"
    app_name = "Antigravity IDE"
    process_names = ["Antigravity IDE.exe", "Antigravity.exe"]
    title_patterns = ["Antigravity"]

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "focus_prompt":
            self.hotkey("ctrl", "l")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        if action == "submit_prompt":
            text = str(params.get("text") or params.get("prompt") or "")
            self.hotkey("ctrl", "l")
            await asyncio.sleep(0.2)
            prev = self.get_clipboard_text()
            self.set_clipboard_text(text)
            self.hotkey("ctrl", "v")
            await asyncio.sleep(0.1)
            self.press_key("enter")
            if prev:
                self.set_clipboard_text(prev)
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"length": len(text)},
            )

        if action == "open_file":
            path = str(params.get("path") or "")
            self.hotkey("ctrl", "p")
            await asyncio.sleep(0.2)
            self.type_text(path)
            self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"path": path},
            )

        return DesktopActionResult(
            ok=False, action=action, application=self.app_id,
            error=f"Antigravity action '{action}' is not supported",
        )
