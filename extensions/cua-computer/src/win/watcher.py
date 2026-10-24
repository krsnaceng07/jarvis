"""extensions/cua-computer/src/win/watcher.py

Low-level Windows Input Watcher using WH_MOUSE_LL and WH_KEYBOARD_LL.
Distinguishes synthetic agent input (tagged with JARVIS_INPUT_MAGIC = 0x4A415256)
from physical human user input.

Features:
- Sub-millisecond takeover detection for user mouse and keyboard activity
- Grace window (120ms) and deadband (6px) to avoid resting hand jitter aborts
- Dedicated background thread with Win32 message loop
- Global Panic Hotkey detection (Pause / Break or Ctrl+Alt+Esc)
- Thread watchdog heartbeat for health reporting
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import math
import sys
import threading
import time
from typing import Any, Callable

from .backend import JARVIS_INPUT_MAGIC, ensure_desktop_access

logger = logging.getLogger(__name__)

# Hook Constants
WH_KEYBOARD_LL: int = 13
WH_MOUSE_LL: int = 14

# Mouse Hook Messages
WM_MOUSEMOVE: int = 0x0200
WM_LBUTTONDOWN: int = 0x0201
WM_LBUTTONUP: int = 0x0202
WM_RBUTTONDOWN: int = 0x0204
WM_RBUTTONUP: int = 0x0205
WM_MBUTTONDOWN: int = 0x0207
WM_MBUTTONUP: int = 0x0208
WM_MOUSEWHEEL: int = 0x020A

# Keyboard Hook Messages
WM_KEYDOWN: int = 0x0100
WM_KEYUP: int = 0x0101
WM_SYSKEYDOWN: int = 0x0104
WM_SYSKEYUP: int = 0x0105

# Injected Event Flag (LLMHF_INJECTED = 0x01, LLKHF_INJECTED = 0x10)
LLMHF_INJECTED: int = 0x00000001
LLKHF_INJECTED: int = 0x00000010

# Panic Virtual Keys
VK_ESCAPE: int = 0x1B
VK_PAUSE: int = 0x13
VK_CONTROL: int = 0x11
VK_MENU: int = 0x12  # Alt


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, ctypes.c_size_t
)


class LowLevelInputWatcher:
    """Monitors raw mouse and keyboard events at the Windows kernel message level.

    Instantly dispatches human takeover and panic callbacks when the user interacts.
    """

    def __init__(
        self,
        on_human_input: Callable[[str, dict[str, Any]], None] | None = None,
        on_panic: Callable[[], None] | None = None,
        grace_period_ms: float = 120.0,
        deadband_px: float = 6.0,
    ) -> None:
        self.on_human_input = on_human_input
        self.on_panic = on_panic
        self.grace_period_ms = grace_period_ms
        self.deadband_px = deadband_px

        self._arm_time: float = 0.0
        self._is_active_or_arming: bool = False
        self._last_human_pos: tuple[int, int] | None = None

        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hhook_mouse: wintypes.HHOOK | None = None
        self._hhook_keyboard: wintypes.HHOOK | None = None
        self._mouse_proc: Any = None
        self._kbd_proc: Any = None
        self._running: bool = False
        self._ready_event = threading.Event()
        self._last_heartbeat: float = time.time()

        # Key state tracking for chord panic (Ctrl+Alt+Esc)
        self._ctrl_down: bool = False
        self._alt_down: bool = False

    def arm(self) -> None:
        """Mark lease as ARMING/ACTIVE with a grace timestamp to filter hand-rest jitter."""
        self._arm_time = time.time()
        self._is_active_or_arming = True

    def disarm(self) -> None:
        """Mark lease as IDLE/RELEASED."""
        self._is_active_or_arming = False

    @property
    def is_healthy(self) -> bool:
        """Return True if background hook thread is running and updating heartbeat."""
        if not self._running or self._thread is None or not self._thread.is_alive():
            return False
        return (time.time() - self._last_heartbeat) < 5.0

    def start(self) -> bool:
        """Start low-level input hook thread."""
        if sys.platform != "win32":
            self._running = True
            return True

        if self._running:
            return True

        self._running = True
        self._ready_event.clear()
        self._thread = threading.Thread(
            target=self._run_hook_loop, name="JarvisInputWatcherThread", daemon=True
        )
        self._thread.start()
        # Wait up to 1.5 seconds for hooks to attach
        success = self._ready_event.wait(timeout=1.5)
        return success and (self._hhook_mouse is not None or self._hhook_keyboard is not None)

    def stop(self) -> None:
        """Unhook and terminate background thread."""
        if not self._running:
            return

        self._running = False
        if sys.platform == "win32" and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None

    def _run_hook_loop(self) -> None:
        if sys.platform != "win32":
            return

        ensure_desktop_access()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        # Fix 64-bit CallNextHookEx signature
        user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            ctypes.c_size_t,
        ]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t

        self._mouse_proc = HOOKPROC(self._low_level_mouse_proc)
        self._kbd_proc = HOOKPROC(self._low_level_keyboard_proc)

        h_mod = kernel32.GetModuleHandleW(None)

        self._hhook_mouse = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, h_mod, 0
        )
        self._hhook_keyboard = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._kbd_proc, h_mod, 0
        )

        if not self._hhook_mouse and not self._hhook_keyboard:
            logger.error("Failed to install low-level mouse and keyboard hooks.")
            self._ready_event.set()
            return

        self._ready_event.set()

        msg = wintypes.MSG()
        # Message loop
        while self._running:
            self._last_heartbeat = time.time()
            # Non-blocking or timed peek to update heartbeat
            b_ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if b_ret <= 0:  # WM_QUIT or error
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup hooks on exit
        if self._hhook_mouse:
            user32.UnhookWindowsHookEx(self._hhook_mouse)
            self._hhook_mouse = None
        if self._hhook_keyboard:
            user32.UnhookWindowsHookEx(self._hhook_keyboard)
            self._hhook_keyboard = None

    def _low_level_mouse_proc(
        self, n_code: int, w_param: wintypes.WPARAM, l_param: int
    ) -> int:
        if n_code < 0:
            return ctypes.windll.user32.CallNextHookEx(
                self._hhook_mouse, n_code, w_param, l_param
            )

        try:
            info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            is_injected = bool(info.flags & LLMHF_INJECTED)
            is_ours = is_injected and (info.dwExtraInfo == JARVIS_INPUT_MAGIC)

            if not is_ours and self._is_active_or_arming:
                now = time.time()
                elapsed_ms = (now - self._arm_time) * 1000.0

                # Check if it's a click or scroll
                is_click = w_param in (
                    WM_LBUTTONDOWN,
                    WM_RBUTTONDOWN,
                    WM_MBUTTONDOWN,
                    WM_MOUSEWHEEL,
                )

                # Check deadband for mouse movement
                pos = (int(info.pt.x), int(info.pt.y))
                dist = 0.0
                if self._last_human_pos is not None:
                    dist = math.hypot(
                        pos[0] - self._last_human_pos[0], pos[1] - self._last_human_pos[1]
                    )

                self._last_human_pos = pos

                # Trigger takeover if click, OR if past grace period and outside deadband
                if is_click or (elapsed_ms > self.grace_period_ms and dist >= self.deadband_px):
                    if self.on_human_input:
                        self.on_human_input(
                            "mouse",
                            {
                                "x": pos[0],
                                "y": pos[1],
                                "msg": int(w_param),
                                "is_click": is_click,
                                "elapsed_ms": elapsed_ms,
                            },
                        )
        except Exception:
            pass

        return ctypes.windll.user32.CallNextHookEx(
            self._hhook_mouse, n_code, w_param, l_param
        )

    def _low_level_keyboard_proc(
        self, n_code: int, w_param: wintypes.WPARAM, l_param: int
    ) -> int:
        if n_code < 0:
            return ctypes.windll.user32.CallNextHookEx(
                self._hhook_keyboard, n_code, w_param, l_param
            )

        try:
            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            is_injected = bool(info.flags & LLKHF_INJECTED)
            is_ours = is_injected and (info.dwExtraInfo == JARVIS_INPUT_MAGIC)

            is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)

            if not is_ours:
                vk = int(info.vkCode)
                if vk in (VK_CONTROL, 0xA2, 0xA3):
                    self._ctrl_down = is_down
                elif vk in (VK_MENU, 0xA4, 0xA5):
                    self._alt_down = is_down

                # 1. Global Panic Hotkey Check: Pause/Break OR Ctrl+Alt+Escape
                is_panic = (vk == VK_PAUSE and is_down) or (
                    vk == VK_ESCAPE and is_down and self._ctrl_down and self._alt_down
                )
                if is_panic:
                    if self.on_panic:
                        self.on_panic()
                    elif self.on_human_input:
                        self.on_human_input("panic", {"vk": vk})

                # 2. General Human Takeover via Keyboard
                elif self._is_active_or_arming and is_down:
                    now = time.time()
                    elapsed_ms = (now - self._arm_time) * 1000.0
                    if elapsed_ms > self.grace_period_ms:
                        if self.on_human_input:
                            self.on_human_input(
                                "keyboard",
                                {"vk": vk, "msg": int(w_param), "elapsed_ms": elapsed_ms},
                            )
        except Exception:
            pass

        return ctypes.windll.user32.CallNextHookEx(
            self._hhook_keyboard, n_code, w_param, l_param
        )


__all__ = ["LowLevelInputWatcher"]
