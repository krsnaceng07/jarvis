"""jarvis.desktop_automation.discovery.window_manager — Window focus, restore, and state management."""

from __future__ import annotations

import asyncio
import ctypes
import sys
import time
from typing import Optional

from .window_detector import WindowDetector

user32 = ctypes.windll.user32 if sys.platform == "win32" else None

SW_RESTORE = 9
SW_SHOW = 5
SW_MAXIMIZE = 3


class WindowManager:
    """Manages window focusing, restoration, minimization, and responsiveness checks."""

    @staticmethod
    def is_responsive(hwnd: int) -> bool:
        """Check if target window is responsive (not hung/frozen)."""
        if not user32:
            return True
        try:
            return not bool(user32.IsHungAppWindow(hwnd))
        except Exception:
            return True

    @staticmethod
    def is_window_minimized(hwnd: int) -> bool:
        """Check if target window is currently minimized/iconic."""
        if not user32 or not hwnd:
            return False
        try:
            return bool(user32.IsIconic(hwnd))
        except Exception:
            return False

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        """Restore and bring window to the foreground with Win32 lock bypass and verification."""
        if not user32 or not hwnd:
            return False

        WindowDetector.ensure_desktop_access()
        kernel32 = ctypes.windll.kernel32 if sys.platform == "win32" else None

        try:
            # 1. Unminimize / restore if minimized
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
                time.sleep(0.15)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)

            # 2. Check if already in foreground
            fg = user32.GetForegroundWindow()
            if fg == hwnd:
                return True

            # 3. AttachThreadInput bypass for Windows foreground activation lock
            cur_thread = kernel32.GetCurrentThreadId() if kernel32 else 0
            fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)

            attached = False
            if cur_thread and fg_thread and cur_thread != fg_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, True)
                user32.AttachThreadInput(cur_thread, target_thread, True)
                attached = True

            # 4. Simulate Ctrl key down/up to unlock Windows foreground lock (avoids system menu activation)
            user32.keybd_event(0x11, 0, 0, 0)  # VK_CONTROL down
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.keybd_event(0x11, 0, 2, 0)  # VK_CONTROL up

            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)

            if attached:
                user32.AttachThreadInput(cur_thread, target_thread, False)
                user32.AttachThreadInput(cur_thread, fg_thread, False)

            time.sleep(0.15)

            # 5. Verification: ensure target window or same process has foreground
            new_fg = user32.GetForegroundWindow()
            if new_fg == hwnd:
                return True

            if new_fg and kernel32:
                pid_target = ctypes.c_ulong()
                pid_new_fg = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_target))
                user32.GetWindowThreadProcessId(new_fg, ctypes.byref(pid_new_fg))
                if pid_target.value and pid_target.value == pid_new_fg.value:
                    return True

            return False
        except Exception:
            return False

    @classmethod
    async def focus_window_async(cls, hwnd: int) -> bool:
        """Asynchronously focus window, restore from minimized, and verify foreground."""
        for _ in range(3):
            if cls.focus_window(hwnd):
                return True
            await asyncio.sleep(0.15)
        return False

    @staticmethod
    def get_foreground_window() -> Optional[int]:
        """Retrieve HWND of current foreground window."""
        if not user32:
            return None
        WindowDetector.ensure_desktop_access()
        hwnd = user32.GetForegroundWindow()
        return hwnd if hwnd != 0 else None
