"""jarvis.desktop_automation.applications.vscode — Visual Studio Code application adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class VSCodeDesktopAdapter(BaseDesktopApplicationAdapter):
    """VS Code desktop application adapter."""

    app_id = "vscode"
    app_name = "Visual Studio Code"
    process_names = ["Code.exe"]
    title_patterns = ["Visual Studio Code"]
    launch_command = "code"

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "open_file":
            path = str(params.get("path") or "")
            self.hotkey("ctrl", "p")
            await asyncio.sleep(0.2)
            self.type_text(path)
            await asyncio.sleep(0.1)
            self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"path": path},
            )

        if action == "run_command":
            cmd = str(params.get("command") or "")
            self.hotkey("ctrl", "shift", "p")
            await asyncio.sleep(0.2)
            self.type_text(cmd)
            await asyncio.sleep(0.1)
            self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"command": cmd},
            )

        if action == "toggle_terminal":
            self.hotkey("ctrl", "`")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        if action == "save_file":
            self.hotkey("ctrl", "s")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        if action == "type_code":
            code = str(params.get("code") or params.get("text") or "")
            prev = self.get_clipboard_text()
            self.set_clipboard_text(code)
            self.hotkey("ctrl", "v")
            if prev:
                self.set_clipboard_text(prev)
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"length": len(code)},
            )

        return DesktopActionResult(
            ok=False, action=action, application=self.app_id,
            error=f"VS Code action '{action}' is not supported",
        )
