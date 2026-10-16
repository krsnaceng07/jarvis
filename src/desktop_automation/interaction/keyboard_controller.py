"""jarvis.desktop_automation.interaction.keyboard_controller — Keystrokes, typing, and shortcuts."""

from __future__ import annotations

import asyncio

from ..discovery.window_manager import WindowManager

try:
    import pyautogui
except ImportError:
    pyautogui = None


class KeyboardController:
    """Simulates keyboard inputs, key chords, and text typing."""

    @staticmethod
    def type_text(text: str, delay: float = 0.01, *, expected_hwnd: int | None = None) -> bool:
        """Stop typing as soon as the bound foreground window changes."""
        if not pyautogui:
            return False
        target = expected_hwnd or WindowManager.get_foreground_window()
        if not target:
            return False
        try:
            # A single bulk write keeps sending to whichever app gains focus.
            # Check between characters so closing the editor stops the remaining text.
            for character in text:
                if WindowManager.get_foreground_window() != target:
                    return False
                pyautogui.write(character, interval=delay, _pause=False)
            return True
        except Exception:
            return False

    @staticmethod
    def press_key(key: str) -> bool:
        """Press a single key (e.g. 'enter', 'tab', 'escape')."""
        if not pyautogui:
            return False
        try:
            pyautogui.press(key.lower())
            return True
        except Exception:
            return False

    @staticmethod
    def hotkey(*keys: str) -> bool:
        """Execute key combination e.g. ('ctrl', 'shift', 'p') or ('ctrl', 'f')."""
        if not pyautogui:
            return False
        try:
            pyautogui.hotkey(*[k.lower() for k in keys])
            return True
        except Exception:
            return False

    @classmethod
    async def type_text_async(cls, text: str, delay: float = 0.01) -> bool:
        res = cls.type_text(text, delay)
        await asyncio.sleep(0.05)
        return res
