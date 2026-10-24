"""extensions/cua-computer/src/win/backend.py

Windows Input Backend implementing the InputBackend protocol.
Uses Win32 SendInput with private magic signature (0x4A415256 = 'JARV')
in dwExtraInfo to distinguish synthetic agent actions from human hardware input.

Features:
- Thread desktop access attachment (OpenInputDesktop + SetThreadDesktop)
- ScreenGeometry conversion for multi-monitor setups
- Natural Bézier curve trajectory with quintic easing and micro-jitter
- Emits real-time cursor/click events for PyQt6 overlay animation
- Unicode text synthesis without clipboard interference
- Key combos and modifier chord synthesis
- Absolute pixel drag & drop
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import math
import random
import sys
from typing import Callable, Sequence, Tuple

from jarvis_sdk.input_backend import InputBackend

from .geometry import ScreenGeometry

# Private MAGIC identifier for JARVIS synthetic events ('JARV' = 0x4A415256)
JARVIS_INPUT_MAGIC: int = 0x4A415256

# Win32 Constants
INPUT_MOUSE: int = 0
INPUT_KEYBOARD: int = 1

# Mouse Event Flags
MOUSEEVENTF_MOVE: int = 0x0001
MOUSEEVENTF_LEFTDOWN: int = 0x0002
MOUSEEVENTF_LEFTUP: int = 0x0004
MOUSEEVENTF_RIGHTDOWN: int = 0x0008
MOUSEEVENTF_RIGHTUP: int = 0x0010
MOUSEEVENTF_MIDDLEDOWN: int = 0x0020
MOUSEEVENTF_MIDDLEUP: int = 0x0040
MOUSEEVENTF_WHEEL: int = 0x0800
MOUSEEVENTF_HWHEEL: int = 0x1000
MOUSEEVENTF_VIRTUALDESK: int = 0x4000
MOUSEEVENTF_ABSOLUTE: int = 0x8000

# Keyboard Event Flags
KEYEVENTF_EXTENDEDKEY: int = 0x0001
KEYEVENTF_KEYUP: int = 0x0002
KEYEVENTF_UNICODE: int = 0x0004
KEYEVENTF_SCANCODE: int = 0x0008

# Virtual Key (VK) Table
VK_MAP: dict[str, int] = {
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "meta": 0x5B,
    "win": 0x5B,
    "windows": 0x5B,
    "capslock": 0x14,
    "numlock": 0x90,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "scrolllock": 0x91,
    "pause": 0x13,
}

for i in range(1, 13):
    VK_MAP[f"f{i}"] = 0x70 + (i - 1)


# Ctypes Win32 Structures
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


def ensure_desktop_access() -> bool:
    """Attach current thread to active input desktop to guarantee SendInput permissions.

    Prevents Win32 ERROR_ACCESS_DENIED (5) in service or background contexts.
    """
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            user32.CloseDesktop(hdesk)
            return True
    except Exception:
        pass
    return False


def _send_inputs(inputs: Sequence[INPUT]) -> int:
    """Send an array of INPUT structures via user32.SendInput."""
    if sys.platform != "win32" or not inputs:
        return len(inputs)

    ensure_desktop_access()
    user32 = ctypes.windll.user32
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    cb_size = ctypes.sizeof(INPUT)
    res = user32.SendInput(n, arr, cb_size)
    return int(res)


class WindowsInputBackend(InputBackend):
    """Windows implementation of the InputBackend protocol.

    Tags all synthetic events with JARVIS_INPUT_MAGIC in dwExtraInfo.
    """

    def __init__(
        self,
        geometry: ScreenGeometry | None = None,
        on_cursor_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.geometry = geometry or ScreenGeometry()
        self.on_cursor_event = on_cursor_event
        self._saved_cursor_pos: Tuple[int, int] | None = None
        self._current_pos: Tuple[int, int] = (0, 0)
        self._init_current_pos()

    def _init_current_pos(self) -> None:
        if sys.platform == "win32":
            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                self._current_pos = (int(pt.x), int(pt.y))

    def _emit(self, event_type: str, data: dict) -> None:
        if self.on_cursor_event:
            try:
                self.on_cursor_event(event_type, data)
            except Exception:
                pass

    def get_cursor_pos(self) -> Tuple[int, int]:
        """Query current physical cursor position."""
        if sys.platform == "win32":
            ensure_desktop_access()
            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                self._current_pos = (int(pt.x), int(pt.y))
        return self._current_pos

    def save_cursor_pos(self) -> Tuple[int, int]:
        pos = self.get_cursor_pos()
        self._saved_cursor_pos = pos
        return pos

    def restore_cursor_pos(self) -> None:
        if self._saved_cursor_pos is not None:
            sx, sy = self._saved_cursor_pos
            self.move_instant(sx, sy)
            self._saved_cursor_pos = None

    def move_instant(self, px: int, py: int) -> None:
        """Instantly warp cursor to virtual desktop pixel coordinates."""
        cx, cy = self.geometry.clamp_px(px, py)
        abs_x, abs_y = self.geometry.px_to_abs65535(cx, cy)

        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.u.mi.dx = abs_x
        inp.u.mi.dy = abs_y
        inp.u.mi.mouseData = 0
        inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        inp.u.mi.time = 0
        inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC

        _send_inputs([inp])
        self._current_pos = (cx, cy)
        self._emit("event.computer.cursor.move", {"x": cx, "y": cy, "instant": True})

    async def move(self, x: int, y: int, smooth: bool = True) -> None:
        """Move cursor to target pixel coordinates with natural Bézier trajectory."""
        tx, ty = self.geometry.clamp_px(x, y)
        if not smooth:
            self.move_instant(tx, ty)
            return

        sx, sy = self.get_cursor_pos()
        dx = tx - sx
        dy = ty - sy
        dist = math.hypot(dx, dy)

        if dist < 4:
            self.move_instant(tx, ty)
            return

        # Adaptive step count: 12 to 36 steps based on distance
        steps = max(10, min(36, int(dist / 25)))
        # Total trajectory duration 120ms to 350ms
        total_time = max(0.12, min(0.35, dist / 1800.0))
        dt = total_time / steps

        # Quadratic/Cubic Bézier control point with subtle orthogonal deviation
        norm_dx = -dy / dist if dist > 0 else 0
        norm_dy = dx / dist if dist > 0 else 0
        deviation = random.uniform(-0.12, 0.12) * dist
        ctrl_x = sx + dx * 0.5 + norm_dx * deviation
        ctrl_y = sy + dy * 0.5 + norm_dy * deviation

        for i in range(1, steps + 1):
            t = i / steps
            # Quintic ease in-out: 6t^5 - 15t^4 + 10t^3
            eased_t = t * t * t * (t * (t * 6 - 15) + 10)

            # Quadratic Bézier: B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
            omt = 1.0 - eased_t
            cur_x = int(omt * omt * sx + 2.0 * omt * eased_t * ctrl_x + eased_t * eased_t * tx)
            cur_y = int(omt * omt * sy + 2.0 * omt * eased_t * ctrl_y + eased_t * eased_t * ty)

            self.move_instant(cur_x, cur_y)
            await asyncio.sleep(dt)

        self.move_instant(tx, ty)

    async def click(self, button: str = "left", count: int = 1) -> None:
        """Synthesize mouse click with realistic down/up timing and overlay ripple."""
        btn = button.lower()
        if btn == "right":
            down_flag = MOUSEEVENTF_RIGHTDOWN
            up_flag = MOUSEEVENTF_RIGHTUP
        elif btn == "middle":
            down_flag = MOUSEEVENTF_MIDDLEDOWN
            up_flag = MOUSEEVENTF_MIDDLEUP
        else:
            down_flag = MOUSEEVENTF_LEFTDOWN
            up_flag = MOUSEEVENTF_LEFTUP

        cx, cy = self.get_cursor_pos()
        abs_x, abs_y = self.geometry.px_to_abs65535(cx, cy)

        for c in range(count):
            self._emit("event.computer.cursor.click", {
                "x": cx,
                "y": cy,
                "button": btn,
                "count": count,
                "index": c + 1,
            })

            # Mouse down
            down_inp = INPUT()
            down_inp.type = INPUT_MOUSE
            down_inp.u.mi.dx = abs_x
            down_inp.u.mi.dy = abs_y
            down_inp.u.mi.dwFlags = down_flag | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            down_inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC
            _send_inputs([down_inp])

            # Realistic click duration (35ms - 65ms)
            await asyncio.sleep(random.uniform(0.035, 0.065))

            # Mouse up
            up_inp = INPUT()
            up_inp.type = INPUT_MOUSE
            up_inp.u.mi.dx = abs_x
            up_inp.u.mi.dy = abs_y
            up_inp.u.mi.dwFlags = up_flag | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            up_inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC
            _send_inputs([up_inp])

            if c < count - 1:
                # Inter-click delay for double/triple clicks (50ms - 90ms)
                await asyncio.sleep(random.uniform(0.050, 0.090))

    async def type_text(self, text: str) -> None:
        """Synthesize Unicode text keystrokes without clipboard interference."""
        if not text:
            return

        for ch in text:
            code = ord(ch)

            # Key Down (Unicode)
            down = INPUT()
            down.type = INPUT_KEYBOARD
            down.u.ki.wVk = 0
            down.u.ki.wScan = code
            down.u.ki.dwFlags = KEYEVENTF_UNICODE
            down.u.ki.time = 0
            down.u.ki.dwExtraInfo = JARVIS_INPUT_MAGIC

            # Key Up (Unicode)
            up = INPUT()
            up.type = INPUT_KEYBOARD
            up.u.ki.wVk = 0
            up.u.ki.wScan = code
            up.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            up.u.ki.time = 0
            up.u.ki.dwExtraInfo = JARVIS_INPUT_MAGIC

            _send_inputs([down, up])

            # Natural inter-keystroke variance (15ms - 40ms)
            await asyncio.sleep(random.uniform(0.015, 0.040))

    async def key(self, key_code: str, modifiers: list[str] | None = None) -> None:
        """Synthesize a single key press or hotkey chord."""
        norm_key = key_code.lower().strip()
        vk_key = VK_MAP.get(norm_key)

        if vk_key is None:
            if len(norm_key) == 1 and norm_key.isalnum():
                vk_key = ord(norm_key.upper())
            else:
                # Unknown key name: fallback to unicode type
                await self.type_text(key_code)
                return

        # Prepare modifier VKs
        mod_vks: list[int] = []
        if modifiers:
            for m in modifiers:
                m_vk = VK_MAP.get(m.lower().strip())
                if m_vk and m_vk not in mod_vks:
                    mod_vks.append(m_vk)

        inputs_down: list[INPUT] = []
        # Press modifiers down
        for m_vk in mod_vks:
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.u.ki.wVk = m_vk
            inp.u.ki.wScan = 0
            inp.u.ki.dwFlags = 0
            inp.u.ki.dwExtraInfo = JARVIS_INPUT_MAGIC
            inputs_down.append(inp)

        # Press main key down
        main_down = INPUT()
        main_down.type = INPUT_KEYBOARD
        main_down.u.ki.wVk = vk_key
        main_down.u.ki.wScan = 0
        main_down.u.ki.dwFlags = 0
        main_down.u.ki.dwExtraInfo = JARVIS_INPUT_MAGIC
        inputs_down.append(main_down)

        _send_inputs(inputs_down)
        await asyncio.sleep(random.uniform(0.035, 0.060))

        inputs_up: list[INPUT] = []
        # Release main key up
        main_up = INPUT()
        main_up.type = INPUT_KEYBOARD
        main_up.u.ki.wVk = vk_key
        main_up.u.ki.wScan = 0
        main_up.u.ki.dwFlags = KEYEVENTF_KEYUP
        main_up.u.ki.dwExtraInfo = JARVIS_INPUT_MAGIC
        inputs_up.append(main_up)

        # Release modifiers up in reverse order
        for m_vk in reversed(mod_vks):
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.u.ki.wVk = m_vk
            inp.u.ki.wScan = 0
            inp.u.ki.dwFlags = KEYEVENTF_KEYUP
            inp.u.ki.dwExtraInfo = JARVIS_INPUT_MAGIC
            inputs_up.append(inp)

        _send_inputs(inputs_up)

    async def scroll(self, dx: int, dy: int) -> None:
        """Synthesize vertical and/or horizontal mouse wheel scroll."""
        cx, cy = self.get_cursor_pos()
        abs_x, abs_y = self.geometry.px_to_abs65535(cx, cy)
        inputs: list[INPUT] = []

        if dy != 0:
            v_inp = INPUT()
            v_inp.type = INPUT_MOUSE
            v_inp.u.mi.dx = abs_x
            v_inp.u.mi.dy = abs_y
            v_inp.u.mi.mouseData = int(dy)
            v_inp.u.mi.dwFlags = MOUSEEVENTF_WHEEL | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            v_inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC
            inputs.append(v_inp)

        if dx != 0:
            h_inp = INPUT()
            h_inp.type = INPUT_MOUSE
            h_inp.u.mi.dx = abs_x
            h_inp.u.mi.dy = abs_y
            h_inp.u.mi.mouseData = int(dx)
            h_inp.u.mi.dwFlags = MOUSEEVENTF_HWHEEL | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            h_inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC
            inputs.append(h_inp)

        if inputs:
            _send_inputs(inputs)

    async def drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        """Synthesize drag operation from start to end pixel coordinates."""
        # 1. Move to start position
        await self.move(start_x, start_y, smooth=True)
        await asyncio.sleep(0.05)

        # 2. Left mouse down
        abs_x, abs_y = self.geometry.px_to_abs65535(start_x, start_y)
        down_inp = INPUT()
        down_inp.type = INPUT_MOUSE
        down_inp.u.mi.dx = abs_x
        down_inp.u.mi.dy = abs_y
        down_inp.u.mi.dwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        down_inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC
        _send_inputs([down_inp])
        await asyncio.sleep(0.06)

        # 3. Smooth drag move to end position
        await self.move(end_x, end_y, smooth=True)
        await asyncio.sleep(0.05)

        # 4. Left mouse up
        abs_ex, abs_ey = self.geometry.px_to_abs65535(end_x, end_y)
        up_inp = INPUT()
        up_inp.type = INPUT_MOUSE
        up_inp.u.mi.dx = abs_ex
        up_inp.u.mi.dy = abs_ey
        up_inp.u.mi.dwFlags = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        up_inp.u.mi.dwExtraInfo = JARVIS_INPUT_MAGIC
        _send_inputs([up_inp])


__all__ = [
    "JARVIS_INPUT_MAGIC",
    "WindowsInputBackend",
    "ensure_desktop_access",
]
