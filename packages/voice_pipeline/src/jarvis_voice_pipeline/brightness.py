"""packages/voice_pipeline/src/jarvis_voice_pipeline/brightness.py

Native Windows Screen Brightness Controller for JARVIS.
Adjusts brightness (0-100), up, down, min, max, dim via WMI WmiMonitorBrightnessMethods.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys

logger = logging.getLogger("jarvis.brightness")


def get_system_brightness() -> int | None:
    """Returns current screen brightness percentage (0-100)."""
    if sys.platform != "win32":
        return None

    cmd = "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).CurrentBrightness"
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode == 0 and proc.stdout.strip().isdigit():
            return int(proc.stdout.strip())
    except Exception as exc:
        logger.debug("Failed to read brightness via WMI: %s", exc)

    return None


def set_system_brightness(level: int) -> bool:
    """Sets screen brightness percentage (0-100) via WmiMonitorBrightnessMethods."""
    if sys.platform != "win32":
        return False

    val = max(0, min(100, int(level)))
    cmd = f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {val})"
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd,
            ],
            capture_output=True,
            timeout=3,
        )
        if proc.returncode == 0:
            return True
    except Exception as exc:
        logger.debug("Failed to set brightness via WMI: %s", exc)

    return False


def control_system_brightness(
    action: str = "status",
    level: int | None = None,
    step: int = 10,
) -> str:
    """Controls Windows screen brightness with WMI."""
    action = str(action or "status").lower().strip()

    # Parse numeric level if embedded in action string (e.g. "60", "60%", "set to 60")
    if level is None:
        num_match = re.search(r"\b(\d{1,3})\b", action)
        if num_match:
            try:
                cand = int(num_match.group(1))
                if 0 <= cand <= 100:
                    level = cand
                    action = "set"
            except Exception:
                pass

    if action in ("get", "status", "check") and level is None:
        cur = get_system_brightness()
        if cur is None:
            return "Unable to read screen brightness from the display."
        return f"Current screen brightness: {cur}%."

    if action in ("max", "full"):
        level = 100
        action = "set"

    if action in ("min", "dim", "lowest"):
        level = 15
        action = "set"

    if action in ("set", "change") or level is not None:
        val = int(level if level is not None else 70)
        val = max(0, min(100, val))
        if not set_system_brightness(val):
            return f"Failed to set screen brightness to {val}%; the display did not confirm the change."
        actual = get_system_brightness()
        if actual is None:
            return f"Screen brightness was requested at {val}%, but the display could not verify the result."
        if actual != val:
            return f"Screen brightness change was not confirmed: requested {val}%, read back {actual}%."
        return f"Screen brightness set to {actual}% (verified)."

    if action in ("up", "increase", "brighter", "raise", "high", "more"):
        cur = get_system_brightness()
        if cur is None:
            return "Unable to adjust screen brightness because the current level could not be read."
        new_val = min(100, cur + step)
        return control_system_brightness("set", new_val)

    if action in ("down", "decrease", "lower", "dimmer", "reduce", "less"):
        cur = get_system_brightness()
        if cur is None:
            return "Unable to adjust screen brightness because the current level could not be read."
        new_val = max(0, cur - step)
        return control_system_brightness("set", new_val)

    cur = get_system_brightness()
    if cur is None:
        return "Unable to read screen brightness from the display."
    return f"Screen brightness is {cur}%."
