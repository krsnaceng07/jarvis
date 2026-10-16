"""Raw device and volume namespace isolation guard.

Executes probes DEV-001 through DEV-003:
- Raw physical drive access (\\\\.\\PhysicalDrive0)
- Raw volume access (\\\\.\\C:)
- Device namespace kernel traversal (\\\\?\\GLOBALROOT\\Device\\...)
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import time

from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


class DeviceGuard:
    """Probes and verifies raw disk, volume, and device namespace boundaries."""

    @classmethod
    def probe_raw_physical_drive(cls, drive_idx: int = 0) -> HostileProbeResult:
        """DEV-001: Attempt opening handle to \\\\.\\PhysicalDriveN."""
        start = time.perf_counter()
        target = f"\\\\.\\PhysicalDrive{drive_idx}"
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                GENERIC_READ = 0x80000000
                FILE_SHARE_READ = 0x00000001
                FILE_SHARE_WRITE = 0x00000002
                OPEN_EXISTING = 3

                h_device = kernel32.CreateFileW(
                    target,
                    GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None,
                )
                INVALID_HANDLE_VALUE = -1
                if h_device != INVALID_HANDLE_VALUE and h_device != 0:
                    kernel32.CloseHandle(h_device)
                    blocked = False
                    sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
                    err_name = "RAW_DRIVE_OPEN_SUCCESS"
                else:
                    err_code = kernel32.GetLastError()
                    blocked = True
                    err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else f"WIN32_ERROR_{err_code}"
            except Exception as exc:
                blocked = True
                err_name = str(exc)
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="DEV-001",
            family=VectorFamily.DEVICE,
            name="RawPhysicalDriveProbe",
            target=target,
            attempt_details=f"Attempted opening direct read handle to {target}",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_raw_volume(cls, drive_letter: str = "C:") -> HostileProbeResult:
        """DEV-002: Attempt opening handle to \\\\.\\C: volume."""
        start = time.perf_counter()
        target = f"\\\\.\\{drive_letter}"
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                GENERIC_READ = 0x80000000
                FILE_SHARE_READ = 0x00000001
                FILE_SHARE_WRITE = 0x00000002
                OPEN_EXISTING = 3

                h_vol = kernel32.CreateFileW(
                    target,
                    GENERIC_READ,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None,
                )
                INVALID_HANDLE_VALUE = -1
                if h_vol != INVALID_HANDLE_VALUE and h_vol != 0:
                    kernel32.CloseHandle(h_vol)
                    blocked = False
                    sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
                    err_name = "RAW_VOLUME_OPEN_SUCCESS"
                else:
                    err_code = kernel32.GetLastError()
                    blocked = True
                    err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else f"WIN32_ERROR_{err_code}"
            except Exception as exc:
                blocked = True
                err_name = str(exc)
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="DEV-002",
            family=VectorFamily.DEVICE,
            name="RawVolumeAccessProbe",
            target=target,
            attempt_details=f"Attempted opening direct read handle to volume {target}",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_device_namespace(cls) -> HostileProbeResult:
        """DEV-003: Attempt accessing \\\\?\\GLOBALROOT\\Device\\HarddiskVolume1."""
        start = time.perf_counter()
        target = r"\\?\GLOBALROOT\Device\HarddiskVolume1"
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                GENERIC_READ = 0x80000000
                OPEN_EXISTING = 3

                h_dev = kernel32.CreateFileW(
                    target,
                    GENERIC_READ,
                    0,
                    None,
                    OPEN_EXISTING,
                    0,
                    None,
                )
                INVALID_HANDLE_VALUE = -1
                if h_dev != INVALID_HANDLE_VALUE and h_dev != 0:
                    kernel32.CloseHandle(h_dev)
                    blocked = False
                    sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
                    err_name = "GLOBALROOT_DEVICE_OPEN_SUCCESS"
                else:
                    err_code = kernel32.GetLastError()
                    blocked = True
                    err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else f"WIN32_ERROR_{err_code}"
            except Exception as exc:
                blocked = True
                err_name = str(exc)
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="DEV-003",
            family=VectorFamily.DEVICE,
            name="DeviceNamespaceProbe",
            target=target,
            attempt_details="Attempted opening handle to \\\\?\\GLOBALROOT\\Device namespace",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def run_all_probes(cls) -> list[HostileProbeResult]:
        """Execute full device namespace probe suite."""
        return [
            cls.probe_raw_physical_drive(0),
            cls.probe_raw_volume("C:"),
            cls.probe_device_namespace(),
        ]


__all__ = ["DeviceGuard"]
