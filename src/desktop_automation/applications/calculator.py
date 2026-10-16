"""jarvis.desktop_automation.applications.calculator — Windows Calculator application adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..state.active_desktop_context import ActiveDesktopContext


class CalculatorDesktopAdapter(BaseDesktopApplicationAdapter):
    """Windows Calculator application adapter with result extraction."""

    app_id = "calculator"
    app_name = "Windows Calculator"
    process_names = ["CalculatorApp.exe", "calc.exe"]
    title_patterns = ["Calculator"]
    launch_command = "calc"

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action == "calculate":
            expr = str(params.get("expression") or "").strip()
            if not expr:
                return DesktopActionResult(
                    ok=False, action=action, application=self.app_id,
                    error="Expression is required",
                )

            # Clear calculator
            self.press_key("escape")
            await asyncio.sleep(0.1)

            # Type expression and equals
            # Ensure proper symbols
            clean_expr = expr.replace("x", "*").replace("X", "*")
            if not clean_expr.endswith("="):
                clean_expr += "="

            self.type_text(clean_expr)
            await asyncio.sleep(0.2)

            # Copy result to clipboard
            self.hotkey("ctrl", "c")
            await asyncio.sleep(0.1)
            result_val = self.get_clipboard_text().strip()

            context.last_verified_action = f"calculated_{expr}_{result_val}"

            return DesktopActionResult(
                ok=True,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"expression": expr, "result": result_val},
                output_text=result_val,
            )

        if action == "clear":
            self.press_key("escape")
            return DesktopActionResult(
                ok=True, action=action, application=self.app_id,
                effect=ActionEffect.CONFIRMED, verified=True,
            )

        return DesktopActionResult(
            ok=False, action=action, application=self.app_id,
            error=f"Calculator action '{action}' is not supported",
        )
