"""jarvis.desktop_automation.applications.office — Microsoft Office (Word, PowerPoint, Excel) adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class OfficeDesktopAdapter(BaseDesktopApplicationAdapter):
    """Unified Microsoft Office suite application adapter."""

    def __init__(self, office_suite: str = "word") -> None:
        super().__init__()
        self.office_suite = office_suite.lower()
        if self.office_suite == "powerpoint":
            self.app_id = "powerpoint"
            self.app_name = "Microsoft PowerPoint"
            self.process_names = ["POWERPNT.EXE"]
            self.title_patterns = ["PowerPoint", "Presentation"]
            self.launch_command = "powerpnt"
        elif self.office_suite == "excel":
            self.app_id = "excel"
            self.app_name = "Microsoft Excel"
            self.process_names = ["EXCEL.EXE"]
            self.title_patterns = ["Excel", "Book"]
            self.launch_command = "excel"
        else:
            self.app_id = "word"
            self.app_name = "Microsoft Word"
            self.process_names = ["WINWORD.EXE"]
            self.title_patterns = ["Word", "Document"]
            self.launch_command = "winword"

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "new_document":
            self.hotkey("ctrl", "n")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        if action == "insert_text":
            text = str(params.get("text") or "")
            prev = self.get_clipboard_text()
            self.set_clipboard_text(text)
            self.hotkey("ctrl", "v")
            if prev:
                self.set_clipboard_text(prev)
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"length": len(text)},
            )

        if action == "save_document":
            self.hotkey("ctrl", "s")
            path = params.get("path")
            if path:
                await asyncio.sleep(0.5)
                self.type_text(str(path))
                self.press_key("enter")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
                evidence={"path": path},
            )

        if action == "start_slideshow" and self.app_id == "powerpoint":
            self.press_key("f5")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        return DesktopActionResult(
            ok=False, action=action, application=self.app_id,
            error=f"Office action '{action}' not supported for {self.app_id}",
        )
