"""jarvis.desktop_automation.applications.explorer — File Explorer application adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class ExplorerDesktopAdapter(BaseDesktopApplicationAdapter):
    """Windows File Explorer application adapter."""

    app_id = "explorer"
    app_name = "File Explorer"
    process_names = ["explorer.exe"]
    title_patterns = ["File Explorer", "This PC"]
    launch_command = "explorer"

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "navigate":
            path = str(params.get("path") or "").strip()
            self.hotkey("ctrl", "l")
            await asyncio.sleep(0.2)
            self.type_text(path)
            self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"path": path},
            )

        if action == "create_folder":
            name = str(params.get("name") or "").strip()
            self.hotkey("ctrl", "shift", "n")
            await asyncio.sleep(0.2)
            if name:
                self.type_text(name)
                self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"folder_name": name},
            )

        if action == "search":
            query = str(params.get("query") or "").strip()
            self.hotkey("ctrl", "e")
            await asyncio.sleep(0.2)
            self.type_text(query)
            self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"query": query},
            )

        return DesktopActionResult(
            ok=False, action=action, application=self.app_id,
            error=f"Explorer action '{action}' is not supported",
        )
