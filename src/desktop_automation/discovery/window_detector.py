r"""jarvis.desktop_automation.discovery.window_detector — Native Win32 window discovery.

Attaches to WinSta0\Default to enumerate all user desktop windows.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import Any, Dict, List, Optional

user32 = ctypes.windll.user32 if sys.platform == "win32" else None


class WindowInfo:
    def __init__(self, hwnd: int, pid: int, title: str, rect: Dict[str, int], is_visible: bool, is_minimized: bool):
        self.hwnd = hwnd
        self.pid = pid
        self.title = title
        self.rect = rect
        self.is_visible = is_visible
        self.is_minimized = is_minimized

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "pid": self.pid,
            "title": self.title,
            "rect": self.rect,
            "is_visible": self.is_visible,
            "is_minimized": self.is_minimized,
        }


class WindowDetector:
    """Enumerates and inspects native Windows on the active desktop station."""

    @staticmethod
    def ensure_desktop_access() -> bool:
        r"""Attach current thread to WinSta0\Default if on Windows."""
        if not user32:
            return False
        try:
            hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0000037F)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x000001FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
            return True
        except Exception:
            return False

    @classmethod
    def list_windows(cls, title_filter: Optional[str] = None) -> List[WindowInfo]:
        """List all top-level titled windows on the interactive desktop."""
        if not user32:
            return []

        cls.ensure_desktop_access()
        windows: List[WindowInfo] = []

        def enum_windows_callback(hwnd: int, extra: Any) -> bool:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if title:
                    if title_filter and title_filter.lower() not in title.lower():
                        return True
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    is_vis = bool(user32.IsWindowVisible(hwnd))
                    is_min = bool(user32.IsIconic(hwnd))
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    bounds = {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom,
                        "width": max(0, rect.right - rect.left),
                        "height": max(0, rect.bottom - rect.top),
                    }
                    t_lower = title.lower()
                    if any(t_lower.startswith(pfx) for pfx in ("gdi+", "default ime", "msctfime ui", "olechannelwnd")):
                        return True
                    if not is_min and bounds["width"] <= 1 and bounds["height"] <= 1:
                        return True

                    windows.append(WindowInfo(
                        hwnd=hwnd,
                        pid=pid.value,
                        title=title,
                        rect=bounds,
                        is_visible=is_vis,
                        is_minimized=is_min,
                    ))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return windows

    @classmethod
    def find_windows_by_process(cls, process_name: str) -> List[WindowInfo]:
        """Find all windows belonging to processes matching process_name."""
        from .process_detector import ProcessDetector

        matches = ProcessDetector.find_processes_by_name(process_name)
        target_pids = {m["pid"] for m in matches if "pid" in m}
        if not target_pids:
            clean_name = process_name.lower().removesuffix(".exe").removesuffix(".root")
            return [win for win in cls.list_windows() if clean_name in win.title.lower()]

        matched_wins = [win for win in cls.list_windows() if win.pid in target_pids]
        if not matched_wins:
            clean_name = process_name.lower().removesuffix(".exe").removesuffix(".root")
            matched_wins = [win for win in cls.list_windows() if clean_name in win.title.lower()]
        return matched_wins

    @classmethod
    def find_windows_by_title(cls, title_pattern: str) -> List[WindowInfo]:
        """Find all windows whose title contains title_pattern."""
        if not title_pattern:
            return []
        pat = title_pattern.lower()
        return [win for win in cls.list_windows() if pat in win.title.lower()]

    @classmethod
    def find_windows_by_pid(cls, pid: int) -> List[WindowInfo]:
        """Find all windows belonging to a given PID."""
        return [win for win in cls.list_windows() if win.pid == pid]

    @classmethod
    def find_window_by_title_or_pid(cls, title_pattern: Optional[str] = None, pids: Optional[List[int]] = None) -> Optional[WindowInfo]:
        """Find matching window by title substring or process ID."""
        for win in cls.list_windows():
            if pids and win.pid in pids:
                return win
            if title_pattern and title_pattern.lower() in win.title.lower():
                return win
        return None

