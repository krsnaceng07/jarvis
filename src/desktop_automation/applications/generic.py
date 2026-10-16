"""jarvis.desktop_automation.applications.generic — Generic fallback desktop adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseDesktopApplicationAdapter
from ..core.action_contract import ActionEffect, DesktopActionResult
from ..interaction.screenshot_controller import ScreenshotController
from ..interaction.keyboard_controller import KeyboardController
from ..state.active_desktop_context import ActiveDesktopContext


class GenericDesktopAdapter(BaseDesktopApplicationAdapter):
    """Generic fallback adapter for any unspecialized desktop application or window."""

    app_id = "generic"
    app_name = "Generic Application"

    async def ensure_running_and_focused(self) -> bool:
        """Generic actions operate on the currently active foreground desktop window."""
        return True

    def find_window(self) -> Any:
        """Generic actions target the active desktop rather than a named window."""
        return True

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        if action in {
            "type",
            "press_key",
            "hotkey",
            "click",
            "double_click",
            "right_click",
            "scroll",
            "drag",
        }:
            # The observed target belongs to the task. Never adopt whatever window
            # gained focus after the user closed or switched away from that target.
            if (
                not context.active_hwnd
                or self.window_manager.get_foreground_window() != context.active_hwnd
            ):
                return DesktopActionResult(
                    ok=False,
                    action=action,
                    application=self.app_id,
                    error="Target window is missing or no longer focused. Re-observe the intended target before resuming.",
                )
        if action == "click":
            x = int(params.get("x", 0))
            y = int(params.get("y", 0))
            button = str(params.get("button", "left"))
            self.click(x, y, button)
            return DesktopActionResult(
                ok=True,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"x": x, "y": y, "button": button},
            )

        if action in ("double_click", "right_click"):
            x = int(params.get("x", 0))
            y = int(params.get("y", 0))
            button = "right" if action == "right_click" else str(params.get("button", "left"))
            clicks = 2 if action == "double_click" else 1
            self.click(x, y, button)
            if clicks == 2:
                self.click(x, y, button)
            return DesktopActionResult(
                ok=True,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"x": x, "y": y, "button": button, "clicks": clicks},
            )

        if action == "scroll":
            amount = int(params.get("amount") or params.get("delta") or 0)
            if not amount:
                direction = str(params.get("direction") or "down").lower()
                ticks = int(params.get("ticks") or 5)
                amount = ticks if direction in ("up", "left") else -ticks
            ok = self.mouse_scroll(amount)
            return DesktopActionResult(
                ok=ok,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED if ok else ActionEffect.SUSPECTED_NOOP,
                verified=ok,
                evidence={"amount": amount},
                error=None if ok else "Mouse scroll failed",
            )

        if action == "drag":
            x = int(params.get("x", 0))
            y = int(params.get("y", 0))
            duration = float(params.get("duration") or 0.25)
            ok = self.mouse_drag_to(x, y, duration=duration)
            return DesktopActionResult(
                ok=ok,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED if ok else ActionEffect.SUSPECTED_NOOP,
                verified=ok,
                evidence={"x": x, "y": y, "duration": duration},
                error=None if ok else "Mouse drag failed",
            )

        if action == "type":
            text = str(params.get("text") or "")
            target = context.active_hwnd
            if not target or self.window_manager.get_foreground_window() != target:
                return DesktopActionResult(
                    ok=False,
                    action=action,
                    application=self.app_id,
                    error="Target window is missing or no longer focused. Re-observe the intended document before resuming.",
                )
            ok = KeyboardController.type_text(text, expected_hwnd=target)
            return DesktopActionResult(
                ok=ok,
                action=action,
                application=self.app_id,
                effect=ActionEffect.UNVERIFIABLE,
                verified=False,
                evidence={"target_hwnd": target},
                error=None
                if ok
                else "Typing interrupted: target focus changed or input failed. Re-observe before resuming; some text may already have been entered.",
            )

        if action == "press_key":
            key = str(params.get("key") or "")
            self.press_key(key)
            return DesktopActionResult(
                ok=True,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"key": key},
            )

        if action == "hotkey":
            keys = params.get("keys", [])
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            self.hotkey(*keys)
            return DesktopActionResult(
                ok=True,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"keys": keys},
            )

        if action == "wait":
            duration = float(params.get("duration") or params.get("seconds") or 1.0)
            await asyncio.sleep(max(0.1, min(duration, 10.0)))
            return DesktopActionResult(
                ok=True,
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"duration": duration},
            )

        if action == "screenshot":
            img, h, changed = ScreenshotController.capture_with_hash()
            return DesktopActionResult(
                ok=bool(img),
                action=action,
                application=self.app_id,
                effect=ActionEffect.CONFIRMED,
                verified=True,
                evidence={"hash": h, "changed": changed},
            )

        return DesktopActionResult(
            ok=False,
            action=action,
            application=self.app_id,
            error=f"Generic action '{action}' is not supported",
        )

    @staticmethod
    def mouse_scroll(amount: int) -> bool:
        from ..interaction.mouse_controller import MouseController

        return MouseController.scroll(amount)

    @staticmethod
    def mouse_drag_to(x: int, y: int, duration: float = 0.25) -> bool:
        from ..interaction.mouse_controller import MouseController

        return MouseController.drag_to(x, y, duration=duration)
