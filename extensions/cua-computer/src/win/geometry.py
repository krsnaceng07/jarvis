"""extensions/cua-computer/src/win/geometry.py

Screen geometry and coordinate conversion for multi-monitor Windows virtual desktops.
Follows OpenClaw CUA specifications:
- Coordinates in 0..1000 normalized space (CUA API standard)
- Pixel space mapped to virtual desktop bounds (SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, etc.)
- Win32 SendInput absolute normalization space (0..65535) with MOUSEEVENTF_VIRTUALDESK
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import sys
from typing import Tuple

# Windows Virtual Screen Metric Constants
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


@dataclass(frozen=True, slots=True)
class VirtualDesktopBounds:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


class ScreenGeometry:
    """Provides coordinate transformations between normalized (0..1000),

    pixel coordinates, and Win32 SendInput 0..65535 absolute coordinates.
    """

    def __init__(self, override_bounds: VirtualDesktopBounds | None = None) -> None:
        self._override_bounds = override_bounds

    def get_bounds(self) -> VirtualDesktopBounds:
        if self._override_bounds is not None:
            return self._override_bounds

        if sys.platform != "win32":
            # Headless or non-Windows test fallback
            return VirtualDesktopBounds(left=0, top=0, width=1920, height=1080)

        try:
            user32 = ctypes.windll.user32
            # Set process DPI aware before reading metrics if possible
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
            except Exception:
                try:
                    user32.SetProcessDPIAware()
                except Exception:
                    pass

            left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
            top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
            width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
            height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

            if width <= 0 or height <= 0:
                width = int(user32.GetSystemMetrics(SM_CXSCREEN)) or 1920
                height = int(user32.GetSystemMetrics(SM_CYSCREEN)) or 1080
                left = 0
                top = 0

            return VirtualDesktopBounds(left=left, top=top, width=width, height=height)
        except Exception:
            return VirtualDesktopBounds(left=0, top=0, width=1920, height=1080)

    def norm_to_px(self, nx: float, ny: float) -> Tuple[int, int]:
        """Convert normalized 0..1000 coordinates to absolute virtual desktop pixel coordinates."""
        bounds = self.get_bounds()
        # Clamp normalized inputs to [0.0, 1000.0]
        clamped_x = max(0.0, min(1000.0, float(nx)))
        clamped_y = max(0.0, min(1000.0, float(ny)))

        px = int(bounds.left + (clamped_x / 1000.0) * bounds.width)
        py = int(bounds.top + (clamped_y / 1000.0) * bounds.height)

        # Clamp pixels within desktop bounds
        max_x = bounds.right - 1 if bounds.width > 0 else bounds.left
        max_y = bounds.bottom - 1 if bounds.height > 0 else bounds.top
        px = max(bounds.left, min(max_x, px))
        py = max(bounds.top, min(max_y, py))

        return px, py

    def px_to_norm(self, px: int, py: int) -> Tuple[int, int]:
        """Convert absolute virtual desktop pixels to normalized 0..1000 coordinates."""
        bounds = self.get_bounds()
        if bounds.width <= 0 or bounds.height <= 0:
            return 0, 0

        nx = int(((px - bounds.left) / bounds.width) * 1000.0)
        ny = int(((py - bounds.top) / bounds.height) * 1000.0)

        return max(0, min(1000, nx)), max(0, min(1000, ny))

    def px_to_abs65535(self, px: int, py: int) -> Tuple[int, int]:
        """Convert virtual desktop pixel coordinates to SendInput 0..65535 normalized absolute units.

        Used with MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK.
        Formula: abs = ((coord - origin) * 65536) // span.
        """
        bounds = self.get_bounds()
        if bounds.width <= 0 or bounds.height <= 0:
            return 0, 0

        # Win32 SendInput absolute coordinate mapping across virtual desktop
        abs_x = int(((px - bounds.left) * 65536) / bounds.width)
        abs_y = int(((py - bounds.top) * 65536) / bounds.height)

        return max(0, min(65535, abs_x)), max(0, min(65535, abs_y))

    def clamp_px(self, px: int, py: int) -> Tuple[int, int]:
        bounds = self.get_bounds()
        max_x = bounds.right - 1 if bounds.width > 0 else bounds.left
        max_y = bounds.bottom - 1 if bounds.height > 0 else bounds.top
        return max(bounds.left, min(max_x, px)), max(bounds.top, min(max_y, py))


__all__ = ["SM_CXSCREEN", "SM_CXVIRTUALSCREEN", "SM_CYSCREEN", "SM_CYVIRTUALSCREEN", "SM_XVIRTUALSCREEN", "SM_YVIRTUALSCREEN", "ScreenGeometry", "VirtualDesktopBounds"]
