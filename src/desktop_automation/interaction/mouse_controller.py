"""jarvis.desktop_automation.interaction.mouse_controller — Pointer actions."""

from __future__ import annotations

from typing import Optional

try:
    import pyautogui
except ImportError:
    pyautogui = None


class MouseController:
    """Executes clicks, double-clicks, drags, and scrolling."""

    @staticmethod
    def click(x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> bool:
        if not pyautogui:
            return False
        try:
            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
            return True
        except Exception:
            return False

    @staticmethod
    def scroll(amount: int) -> bool:
        if not pyautogui:
            return False
        try:
            pyautogui.scroll(amount)
            return True
        except Exception:
            return False

    @staticmethod
    def drag_to(x: int, y: int, duration: float = 0.25, button: str = "left") -> bool:
        if not pyautogui:
            return False
        try:
            pyautogui.dragTo(x=x, y=y, duration=duration, button=button)
            return True
        except Exception:
            return False
