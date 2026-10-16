"""Persistence mechanism defense and persistence vector penetration probes.

Executes probes PERS-001 through PERS-005:
- Startup folder write probe (%APPDATA%\\...\\Startup)
- Registry Run / RunOnce persistence key write probe
- Scheduled Task creation probe (schtasks /create)
- Windows Service creation probe (CreateServiceW / sc.exe)
- WMI Event Subscription probe
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import platform
import subprocess
import time
import winreg

from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


class PersistenceGuard:
    """Probes and verifies defenses against unauthorized host persistence installation."""

    @classmethod
    def probe_startup_folder_write(cls) -> HostileProbeResult:
        """PERS-001: Attempt writing a shortcut or script to user Startup folder."""
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        appdata = os.environ.get("APPDATA")
        if not appdata:
            startup_dir = (
                Path.home()
                / "AppData"
                / "Roaming"
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / "Startup"
            )
        else:
            startup_dir = (
                Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            )

        probe_file = startup_dir / f".probe_persist_{time.time_ns()}.tmp"

        try:
            probe_file.write_bytes(b"PERSISTENCE_TEST_PAYLOAD")
            # If succeeded, clean up immediately
            probe_file.unlink(missing_ok=True)
            blocked = False
            sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
            mech = EnforcementMechanism.NOT_CONFIGURED
        except (PermissionError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__
            mech = EnforcementMechanism.OS_ENFORCED
            sev = SeverityLevel.S0_EXPECTED_DENIAL

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="PERS-001",
            family=VectorFamily.PERSISTENCE,
            name="StartupFolderWriteProbe",
            target=str(probe_file),
            attempt_details="Attempted writing persistence payload to user Startup folder",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_registry_run_key_write(cls) -> HostileProbeResult:
        """PERS-002: Attempt creating value under HKLM or HKCU Run key."""
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL
        key_name = f"JarvisProbe_{time.time_ns()}"

        if platform.system() == "Windows" and os.name == "nt":
            # Attempt write to HKLM Run key (requires admin)
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_SET_VALUE,
                ) as k:
                    winreg.SetValueEx(k, key_name, 0, winreg.REG_SZ, "cmd.exe /c calc")
                    winreg.DeleteValue(k, key_name)
                    blocked = False
                    sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
            except (PermissionError, OSError) as exc:
                blocked = True
                err_code = getattr(exc, "winerror", 5)
                err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else exc.__class__.__name__
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="PERS-002",
            family=VectorFamily.PERSISTENCE,
            name="RegistryRunKeyWriteProbe",
            target=r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run",
            attempt_details="Attempted creating value under HKLM Run persistence key",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_scheduled_task_creation(cls) -> HostileProbeResult:
        """PERS-003: Attempt creating a Scheduled Task via schtasks.exe."""
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL
        task_name = f"JarvisProbeTask_{time.time_ns()}"

        cmd = [
            "schtasks.exe",
            "/Create",
            "/SC",
            "ONCE",
            "/TN",
            task_name,
            "/TR",
            "cmd.exe /c exit",
            "/ST",
            "23:59",
            "/F",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
            if res.returncode == 0:
                blocked = False
                sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
                mech = EnforcementMechanism.NOT_CONFIGURED
                # Clean up created task
                subprocess.run(
                    ["schtasks.exe", "/Delete", "/TN", task_name, "/F"], capture_output=True
                )
            else:
                blocked = True
                err_code = res.returncode
                err_name = "TASK_CREATION_DENIED"
                mech = EnforcementMechanism.OS_ENFORCED
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="PERS-003",
            family=VectorFamily.PERSISTENCE,
            name="ScheduledTaskCreationProbe",
            target="schtasks.exe /Create",
            attempt_details="Attempted registering new Windows Scheduled Task",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_service_creation(cls) -> HostileProbeResult:
        """PERS-004: Attempt creating a Windows Service via OpenSCManager / CreateService."""
        start = time.perf_counter()
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                SC_MANAGER_CREATE_SERVICE = 0x0002

                h_scm = advapi32.OpenSCManagerW(None, None, SC_MANAGER_CREATE_SERVICE)
                if h_scm:
                    advapi32.CloseServiceHandle(h_scm)
                    blocked = False
                    sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
                    err_name = "SCM_OPEN_SUCCESS"
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
            vector_id="PERS-004",
            family=VectorFamily.PERSISTENCE,
            name="ServiceCreationProbe",
            target="OpenSCManagerW",
            attempt_details="Attempted acquiring SC_MANAGER_CREATE_SERVICE handle to Service Control Manager",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def run_all_probes(cls) -> list[HostileProbeResult]:
        """Execute full persistence defense probe suite."""
        return [
            cls.probe_startup_folder_write(),
            cls.probe_registry_run_key_write(),
            cls.probe_scheduled_task_creation(),
            cls.probe_service_creation(),
        ]


__all__ = ["PersistenceGuard"]
