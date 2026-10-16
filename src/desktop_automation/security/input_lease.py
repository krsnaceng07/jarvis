"""Short-lived exclusive input lease for AI-driven desktop actions."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator


_MUTATING_INPUT_ACTIONS = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "type",
        "press_key",
        "hotkey",
        "scroll",
        "drag",
    }
)


def is_input_mutation(action: str) -> bool:
    return action.lower() in _MUTATING_INPUT_ACTIONS


@contextmanager
def ai_input_lease(action: str) -> Iterator[None]:
    """Optionally block competing manual input during one short AI input action."""

    if not is_input_mutation(action) or not _input_block_enabled():
        yield
        return

    blocked = False
    timer: threading.Timer | None = None
    started = time.monotonic()
    try:
        blocked = _set_block_input(True)
        if blocked:
            timer = threading.Timer(_max_block_seconds(), _set_block_input, args=(False,))
            timer.daemon = True
            timer.start()
        yield
    finally:
        if timer is not None:
            timer.cancel()
        if blocked:
            _set_block_input(False)
        if time.monotonic() - started > _max_block_seconds():
            _set_block_input(False)


def _input_block_enabled() -> bool:
    return os.environ.get("JARVIS_BLOCK_USER_INPUT_DURING_AI_CONTROL", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _max_block_seconds() -> float:
    try:
        return max(0.25, min(float(os.environ.get("JARVIS_INPUT_BLOCK_MAX_SECONDS", "3")), 5.0))
    except ValueError:
        return 3.0


def _set_block_input(value: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.BlockInput(bool(value)))
    except Exception:
        return False
