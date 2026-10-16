"""Windows user privilege and driver query permission inspector.

Audits whether the harness is running with standard user vs administrative
privileges and probes access to WMI, DXGI, and NVML subsystems.
"""

from __future__ import annotations

import ctypes
import dataclasses
import logging
import platform
import subprocess

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class PermissionProfile:
    """Snapshot of security and driver query permissions on the host."""

    is_admin: bool
    wmi_access: str
    nvml_access: str
    dxgi_access: str
    driver_query_access: str
    permission_tier: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "is_admin": self.is_admin,
            "wmi_access": self.wmi_access,
            "nvml_access": self.nvml_access,
            "dxgi_access": self.dxgi_access,
            "driver_query_access": self.driver_query_access,
            "permission_tier": self.permission_tier,
        }


class PermissionInspector:
    """Probes Windows security context and telemetry subsystem access."""

    @staticmethod
    def inspect() -> PermissionProfile:
        """Probe elevation and access across WMI, NVML, and DXGI."""
        is_admin = False
        if platform.system() == "Windows":
            try:
                is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
            except Exception:
                is_admin = False

        wmi_status = PermissionInspector._probe_wmi()
        nvml_status = PermissionInspector._probe_nvml()
        dxgi_status = PermissionInspector._probe_dxgi()

        driver_query = "FULL" if (wmi_status == "AVAILABLE" and is_admin) else "PARTIAL"
        if wmi_status != "AVAILABLE" and nvml_status != "AVAILABLE":
            driver_query = "BLOCKED"

        tier = "ELEVATED_ADMIN" if is_admin else "STANDARD_USER"

        return PermissionProfile(
            is_admin=is_admin,
            wmi_access=wmi_status,
            nvml_access=nvml_status,
            dxgi_access=dxgi_status,
            driver_query_access=driver_query,
            permission_tier=tier,
        )

    @staticmethod
    def _probe_wmi() -> str:
        try:
            res = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return "AVAILABLE" if res.returncode == 0 and res.stdout.strip() else "RESTRICTED"
        except Exception:
            return "UNAVAILABLE"

    @staticmethod
    def _probe_nvml() -> str:
        try:
            res = subprocess.run(
                ["nvidia-smi", "-L"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return "AVAILABLE" if res.returncode == 0 else "UNAVAILABLE"
        except Exception:
            return "UNSUPPORTED"

    @staticmethod
    def _probe_dxgi() -> str:
        # DXGI is standard on modern Windows OS
        return "AVAILABLE" if platform.system() == "Windows" else "UNSUPPORTED"


__all__ = ["PermissionInspector", "PermissionProfile"]
