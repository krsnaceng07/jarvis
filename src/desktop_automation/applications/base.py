"""jarvis.desktop_automation.applications.base — Base application adapter."""

from __future__ import annotations

import asyncio
import ctypes
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from ..core.action_contract import DesktopActionResult
from ..discovery.process_detector import ProcessDetector
from ..discovery.window_detector import WindowDetector, WindowInfo
from ..discovery.window_manager import WindowManager
from ..interaction.keyboard_controller import KeyboardController
from ..interaction.mouse_controller import MouseController
from ..state.active_desktop_context import ActiveDesktopContext

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None


class BaseDesktopApplicationAdapter:
    """Base contract and utility suite for desktop application adapters."""

    app_id: str = "base"
    app_name: str = "Base Application"
    process_names: List[str] = []
    title_patterns: List[str] = []
    launch_command: Optional[str] = None
    uri_protocol: Optional[str] = None

    def __init__(self) -> None:
        self.process_detector = ProcessDetector()
        self.window_detector = WindowDetector()
        self.window_manager = WindowManager()

    def is_running(self) -> bool:
        """Check if any process matching this application is active."""
        for p in self.process_names:
            if self.process_detector.is_process_running(p):
                return True
        return False

    def find_window(self) -> Optional[WindowInfo]:
        """Find the main application window, prioritizing title matches and filtering out utility windows."""
        candidates: List[WindowInfo] = []
        for pattern in self.title_patterns:
            candidates.extend(self.window_detector.find_windows_by_title(pattern))
        for p in self.process_names:
            candidates.extend(self.window_detector.find_windows_by_process(p))

        if not candidates:
            return None

        def rank_key(w: WindowInfo) -> int:
            score = 0
            t_lower = w.title.lower()
            for pattern in self.title_patterns:
                pat_lower = pattern.lower()
                if pat_lower in t_lower:
                    score += 50
                if pat_lower == t_lower:
                    score += 30
            if w.is_visible:
                score += 10
            if not w.is_minimized:
                score += 5
            return score

        best_by_hwnd: Dict[int, WindowInfo] = {}
        for c in candidates:
            if c.hwnd not in best_by_hwnd or rank_key(c) > rank_key(best_by_hwnd[c.hwnd]):
                best_by_hwnd[c.hwnd] = c

        ranked = sorted(best_by_hwnd.values(), key=rank_key, reverse=True)
        return ranked[0] if ranked else None

    def is_foreground(self) -> bool:
        """Check if any valid window of this application is currently in the active foreground."""
        fg_hwnd = self.window_manager.get_foreground_window()
        if not fg_hwnd:
            return False
        win = self.find_window()
        if not win:
            return False
        if sys.platform == "win32" and user32 and user32.IsIconic(win.hwnd):
            return False
        if win.hwnd == fg_hwnd:
            return True
        if sys.platform == "win32" and user32:
            pid_fg = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid_fg))
            if win.pid == pid_fg.value:
                return True
            for p in self.process_names:
                p_wins = self.window_detector.find_windows_by_process(p)
                if any(w.hwnd == fg_hwnd or w.pid == pid_fg.value for w in p_wins):
                    return True
        return False

    async def ensure_running_and_focused(self) -> bool:
        """Ensure application is running and brought to foreground without launching duplicate windows."""
        win = self.find_window()
        if win:
            if sys.platform == "win32" and user32 and user32.IsIconic(win.hwnd):
                user32.ShowWindow(win.hwnd, 9)  # SW_RESTORE
                await asyncio.sleep(0.15)
            focused = await self.window_manager.focus_window_async(win.hwnd)
            if focused:
                return True

        # Application not running or failed to foreground (e.g. suspended UWP), activate instance
        if self.uri_protocol and sys.platform == "win32":
            subprocess.Popen(f'start {self.uri_protocol}', shell=True)
        elif self.launch_command:
            subprocess.Popen(self.launch_command, shell=True)
        else:
            return False

        # Wait for window to appear (up to 5 seconds)
        for _ in range(25):
            await asyncio.sleep(0.2)
            win = self.find_window()
            if win:
                if sys.platform == "win32" and user32 and user32.IsIconic(win.hwnd):
                    user32.ShowWindow(win.hwnd, 9)  # SW_RESTORE
                return await self.window_manager.focus_window_async(win.hwnd)

        return False

    async def execute_action(
        self,
        action: str,
        params: Dict[str, Any],
        context: ActiveDesktopContext,
    ) -> DesktopActionResult:
        """Override in subclasses to handle application-specific actions."""
        return DesktopActionResult(
            ok=False,
            action=action,
            application=self.app_id,
            error=f"Action '{action}' not supported by adapter '{self.app_id}'",
        )

    # Input helpers
    @staticmethod
    def type_text(text: str, delay: float = 0.01) -> bool:
        return KeyboardController.type_text(text, delay)

    @staticmethod
    def press_key(key: str) -> bool:
        return KeyboardController.press_key(key)

    @staticmethod
    def hotkey(*keys: str) -> bool:
        return KeyboardController.hotkey(*keys)

    @staticmethod
    def click(x: int, y: int, button: str = "left") -> bool:
        return MouseController.click(x, y, button)

    @staticmethod
    def get_clipboard_text() -> str:
        """Read Unicode text from Windows clipboard via Win32 API with retry."""
        if not user32 or not kernel32:
            return ""
        CF_UNICODETEXT = 13
        try:
            opened = False
            for _ in range(10):
                if user32.OpenClipboard(0):
                    opened = True
                    break
                time.sleep(0.05)
            if not opened:
                return ""
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                user32.CloseClipboard()
                return ""
            p = kernel32.GlobalLock(handle)
            if not p:
                user32.CloseClipboard()
                return ""
            text = ctypes.wstring_at(p)
            kernel32.GlobalUnlock(handle)
            user32.CloseClipboard()
            return text
        except Exception:
            return ""

    @staticmethod
    def set_clipboard_text(text: str) -> bool:
        """Write Unicode text to Windows clipboard via Win32 API with retry."""
        if not user32 or not kernel32:
            return False
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        try:
            opened = False
            for _ in range(10):
                if user32.OpenClipboard(0):
                    opened = True
                    break
                time.sleep(0.05)
            if not opened:
                return False
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_mem:
                user32.CloseClipboard()
                return False
            p_mem = kernel32.GlobalLock(h_mem)
            ctypes.memmove(p_mem, data, len(data))
            kernel32.GlobalUnlock(h_mem)
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            user32.CloseClipboard()
            return True
        except Exception:
            return False
