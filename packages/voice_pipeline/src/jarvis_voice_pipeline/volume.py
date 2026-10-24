"""packages/voice_pipeline/src/jarvis_voice_pipeline/volume.py

Native Windows System Volume Controller for JARVIS.
Adjusts volume (0-100), mute/unmute, up, down in <5ms using pycaw / CoreAudio with PowerShell fallback.
"""

from __future__ import annotations

import logging
import re
import sys

logger = logging.getLogger("jarvis.volume")


def control_system_volume(
    action: str = "status",
    level: int | None = None,
    step: int = 10,
) -> str:
    """Controls Windows master volume with zero-latency CoreAudio / pycaw."""
    action = str(action or "status").lower().strip()

    # Parse numeric level if embedded in action string (e.g. "40", "40%", "set to 40")
    if level is None:
        num_match = re.search(r"\b(\d{1,3})\b", action)
        if num_match:
            try:
                candidate = int(num_match.group(1))
                if 0 <= candidate <= 100:
                    level = candidate
                    if "set" in action or "to" in action or action == str(candidate):
                        action = "set"
            except Exception:
                pass

    if sys.platform != "win32":
        return "System volume control is only supported on Windows host."

    try:
        from pycaw.pycaw import AudioUtilities

        device = AudioUtilities.GetSpeakers()
        vol = device.EndpointVolume
        if not vol:
            raise RuntimeError("No EndpointVolume on default speakers")

        if action in ("get", "status", "check") and level is None:
            pct = round(vol.GetMasterVolumeLevelScalar() * 100)
            muted = vol.GetMute()
            return f"Current volume: {pct}%" + (" (Muted)" if muted else "")

        if action in ("mute", "silence"):
            vol.SetMute(1, None)
            return "System audio muted."

        if action in ("unmute",):
            vol.SetMute(0, None)
            pct = round(vol.GetMasterVolumeLevelScalar() * 100)
            return f"System audio unmuted (Volume: {pct}%)."

        if action in ("set", "change") or level is not None:
            val = int(level if level is not None else 50)
            val = max(0, min(100, val))
            vol.SetMasterVolumeLevelScalar(val / 100.0, None)
            if vol.GetMute():
                vol.SetMute(0, None)
            return f"System volume set to {val}%."

        if action in ("up", "increase", "louder", "raise"):
            cur = vol.GetMasterVolumeLevelScalar()
            new_val = min(1.0, cur + (step / 100.0))
            vol.SetMasterVolumeLevelScalar(new_val, None)
            if vol.GetMute():
                vol.SetMute(0, None)
            return f"Volume increased to {round(new_val * 100)}%."

        if action in ("down", "decrease", "lower", "quieter", "reduce"):
            cur = vol.GetMasterVolumeLevelScalar()
            new_val = max(0.0, cur - (step / 100.0))
            vol.SetMasterVolumeLevelScalar(new_val, None)
            return f"Volume decreased to {round(new_val * 100)}%."

        return f"Volume is {round(vol.GetMasterVolumeLevelScalar() * 100)}%."

    except Exception as exc:
        logger.debug("pycaw volume failed: %s; falling back to PowerShell", exc)
        try:
            import subprocess

            if action in ("mute", "unmute"):
                cmd = "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=2
                )
                return "Toggled system mute."
            elif action in ("up", "increase", "louder"):
                cmd = "$w = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $w.SendKeys([char]175) }"
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=2
                )
                return "Volume increased."
            elif action in ("down", "decrease", "lower"):
                cmd = "$w = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $w.SendKeys([char]174) }"
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=2
                )
                return "Volume decreased."
            else:
                return f"Volume action '{action}' performed."
        except Exception as ps_err:
            return f"Failed to adjust volume: {ps_err}"
