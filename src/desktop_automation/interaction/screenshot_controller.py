"""jarvis.desktop_automation.interaction.screenshot_controller — Desktop capture and deduplication."""

from __future__ import annotations

import hashlib
from typing import Any, Optional, Tuple

from ..discovery.window_detector import WindowDetector

try:
    import pyautogui
except ImportError:
    pyautogui = None


class ScreenshotController:
    """Captures screenshots with WinSta0 attachment and frame hash deduplication."""

    _last_hash: Optional[str] = None

    @classmethod
    def capture(cls) -> Optional[Any]:
        """Capture Pillow screenshot of interactive display."""
        if not pyautogui:
            return None
        WindowDetector.ensure_desktop_access()
        try:
            return pyautogui.screenshot()
        except Exception:
            return None

    @classmethod
    def capture_with_hash(cls) -> Tuple[Optional[Any], str, bool]:
        """Capture screenshot, compute SHA256, and return (image, hash, is_changed)."""
        img = cls.capture()
        if not img:
            return None, "", False
        raw_bytes = img.tobytes()
        h = hashlib.sha256(raw_bytes).hexdigest()
        is_changed = (h != cls._last_hash)
        cls._last_hash = h
        return img, h, is_changed
