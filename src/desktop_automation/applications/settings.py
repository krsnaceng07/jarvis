"""jarvis.desktop_automation.applications.settings — Windows Settings application adapter."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class SettingsDesktopAdapter(BaseDesktopApplicationAdapter):
    """Windows Settings application adapter."""

    app_id = "settings"
    app_name = "Windows Settings"
    process_names = ["SystemSettings.exe"]
    title_patterns = ["Settings"]
    uri_protocol = "ms-settings:"

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "open_page":
            page = str(params.get("page") or "").strip()
            uri = f"ms-settings:{page}" if page else "ms-settings:"
            subprocess.Popen(f"start {uri}", shell=True)
            await asyncio.sleep(0.5)
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"page": page, "uri": uri},
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
            error=f"Settings action '{action}' is not supported",
        )
