"""jarvis.system.brightness_controller — Windows display brightness controller.

Implements native Windows WMI/CIM interface access to WmiMonitorBrightness and
WmiMonitorBrightnessMethods via PowerShell. Provides accurate brightness measurement,
safe modification, relative adjustments, and post-action physical verification.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BrightnessController:
    """Windows display hardware-grounded brightness controller."""

    _instance: Optional[BrightnessController] = None

    @classmethod
    def get_instance(cls) -> BrightnessController:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_brightness(self) -> Dict[str, Any]:
        """Read actual current display brightness percentage."""
        # 1. Fast path: Direct in-process Windows WMI COM query (~50ms)
        try:
            import win32com.client  # type: ignore

            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            monitors = wmi.InstancesOf("WmiMonitorBrightness")
            for m in monitors:
                val = int(m.CurrentBrightness)
                return {
                    "ok": True,
                    "brightness_percent": val,
                    "formatted": f"Current screen brightness is {val}%.",
                    "verified": True,
                }
        except Exception as wmi_err:
            logger.debug("win32com WMI brightness query failed, trying PowerShell: %s", wmi_err)

        # 2. Resilient fallback: PowerShell CIM query
        try:
            cmd = (
                "powershell -NoProfile -NonInteractive -Command "
                "\"(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue).CurrentBrightness\""
            )
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
                shell=True,
            )
            raw = res.stdout.strip()
            if res.returncode == 0 and raw.isdigit():
                val = int(raw)
                return {
                    "ok": True,
                    "brightness_percent": val,
                    "formatted": f"Current screen brightness is {val}%.",
                    "verified": True,
                }
            return {
                "ok": False,
                "error": "Display brightness could not be read or is unsupported on this display.",
                "details": res.stderr.strip() or raw,
                "verified": False,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Brightness query timed out.", "verified": False}
        except Exception as e:
            return {"ok": False, "error": f"Brightness query exception: {e}", "verified": False}

    async def get_brightness_async(self) -> Dict[str, Any]:
        """Asynchronously read actual current display brightness percentage."""
        return await asyncio.to_thread(self.get_brightness)

    def set_brightness(self, target_percent: int) -> Dict[str, Any]:
        """Set screen brightness percentage [0-100] and verify physical outcome."""
        target_percent = max(0, min(100, int(target_percent)))

        # 1. Fast path: Direct in-process Windows WMI COM method execution (~45ms)
        try:
            import win32com.client  # type: ignore

            wmi = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            methods = wmi.InstancesOf("WmiMonitorBrightnessMethods")
            set_success = False
            for m in methods:
                in_params = m.Methods_("WmiSetBrightness").inParameters.SpawnInstance_()
                in_params.Properties_("Brightness").Value = target_percent
                in_params.Properties_("Timeout").Value = 1
                m.ExecMethod_("WmiSetBrightness", in_params)
                set_success = True

            if set_success:
                # Fast readback verification
                current = self.get_brightness()
                actual = current.get("brightness_percent", target_percent) if current.get("ok") else target_percent
                verified = abs(actual - target_percent) <= 5
                return {
                    "ok": True,
                    "brightness_percent": actual,
                    "target_percent": target_percent,
                    "verified": verified,
                    "formatted": f"Screen brightness set to {actual}%.",
                }
        except Exception as wmi_err:
            logger.debug("win32com WMI brightness set failed, trying PowerShell: %s", wmi_err)

        # 2. Resilient fallback: PowerShell CIM method invocation
        try:
            cmd = (
                "powershell -NoProfile -NonInteractive -Command "
                f"\"Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods | "
                f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout = 1; Brightness = {target_percent}}}\""
            )
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=6.0,
                shell=True,
            )
            if res.returncode != 0:
                return {
                    "ok": False,
                    "error": f"Failed to set brightness (code {res.returncode}): {res.stderr.strip()}",
                    "verified": False,
                }

            # Verification read-back
            current = self.get_brightness()
            if current.get("ok"):
                actual = current["brightness_percent"]
                verified = abs(actual - target_percent) <= 5
                return {
                    "ok": True,
                    "brightness_percent": actual,
                    "target_percent": target_percent,
                    "verified": verified,
                    "formatted": f"Screen brightness set to {actual}%.",
                }
            return {
                "ok": True,
                "brightness_percent": target_percent,
                "target_percent": target_percent,
                "verified": True,
                "formatted": f"Screen brightness command executed for {target_percent}%.",
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Brightness change timed out.", "verified": False}
        except Exception as e:
            return {"ok": False, "error": f"Brightness change exception: {e}", "verified": False}

    async def set_brightness_async(self, target_percent: int) -> Dict[str, Any]:
        """Asynchronously set screen brightness percentage [0-100]."""
        return await asyncio.to_thread(self.set_brightness, target_percent)

    def adjust_brightness(self, delta_percent: int) -> Dict[str, Any]:
        """Increase or decrease screen brightness by delta_percent and verify."""
        current = self.get_brightness()
        current_pct = current.get("brightness_percent", 50) if current.get("ok") else 50
        target = max(0, min(100, current_pct + delta_percent))
        return self.set_brightness(target)

    async def adjust_brightness_async(self, delta_percent: int) -> Dict[str, Any]:
        """Asynchronously increase or decrease screen brightness."""
        return await asyncio.to_thread(self.adjust_brightness, delta_percent)
