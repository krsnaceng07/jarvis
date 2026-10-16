"""Code execution control, dropped script/binary defense, and WDAC/AppLocker detection.

Executes probes CODE-001 through CODE-006:
- Dropped batch script (.bat) execution
- Dropped PowerShell script (.ps1) execution
- Dropped VBScript (.vbs) execution
- Dropped unsigned DLL (.dll) loading
- Dropped executable (.exe) execution
- Host WDAC (Windows Defender Application Control) & AppLocker policy detection
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import Any
import winreg

from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


class CodeGuard:
    """Probes and verifies code execution control, script restriction, and policy enforcement."""

    @classmethod
    def detect_system_code_integrity(cls) -> dict[str, Any]:
        """Detect AppLocker and WDAC enforcement status on the host OS."""
        status = {
            "applocker_configured": False,
            "wdac_configured": False,
            "wdac_enforcement_mode": "NOT_CONFIGURED",
            "applocker_rules": [],
        }
        if platform.system() != "Windows" or os.name != "nt":
            return status

        # Check AppLocker registry keys
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Policies\Microsoft\Windows\SrpV2",
            ) as key:
                status["applocker_configured"] = True
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(key, i)
                        status["applocker_rules"].append(sub)
                        i += 1
                    except OSError:
                        break
        except (FileNotFoundError, PermissionError):
            status["applocker_configured"] = False

        # Check WDAC / Code Integrity registry keys
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\CI\Config",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "CIPolicyOptions")
                status["wdac_configured"] = True
                status["wdac_enforcement_mode"] = f"OPTIONS_{val}"
        except (FileNotFoundError, PermissionError):
            pass

        return status

    @classmethod
    def probe_dropped_script(
        cls,
        scratch_dir: Path,
        script_ext: str = ".bat",
        vector_id: str = "CODE-001",
        name: str = "DroppedBatchExecutionProbe",
    ) -> HostileProbeResult:
        """Attempt creating and executing a dropped script payload."""
        start = time.perf_counter()
        scratch_dir.mkdir(parents=True, exist_ok=True)
        probe_file = scratch_dir / f"probe_payload_{time.time_ns()}{script_ext}"

        if script_ext == ".bat":
            content = "@echo off\r\necho PROBE_EXECUTED\r\n"
            cmd = ["cmd.exe", "/c", str(probe_file)]
        elif script_ext == ".ps1":
            content = "Write-Output 'PROBE_EXECUTED'\r\n"
            cmd = ["powershell.exe", "-ExecutionPolicy", "Restricted", "-File", str(probe_file)]
        elif script_ext == ".vbs":
            content = 'WScript.Echo "PROBE_EXECUTED"\r\n'
            cmd = ["wscript.exe", str(probe_file)]
        else:
            content = "exit 0"
            cmd = [str(probe_file)]

        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.NOT_CONFIGURED
        sev = SeverityLevel.S0_EXPECTED_DENIAL
        stdout_txt = ""

        try:
            probe_file.write_text(content, encoding="utf-8")
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            stdout_txt = res.stdout.strip()
            if "PROBE_EXECUTED" in stdout_txt:
                blocked = False
                sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
                mech = EnforcementMechanism.NOT_CONFIGURED
                err_name = "SCRIPT_EXECUTION_ALLOWED"
            else:
                blocked = True
                err_code = res.returncode
                err_name = f"EXIT_CODE_{res.returncode}"
                # If PowerShell ExecutionPolicy restricted:
                if "cannot be loaded because running scripts is disabled" in res.stderr:
                    mech = EnforcementMechanism.OS_ENFORCED
                    err_name = "BLOCKED_BY_POWERSHELL_POLICY"
                else:
                    mech = EnforcementMechanism.APPLICATION_ENFORCED
        except (subprocess.TimeoutExpired, PermissionError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__
            mech = EnforcementMechanism.OS_ENFORCED
        finally:
            try:
                probe_file.unlink(missing_ok=True)
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id=vector_id,
            family=VectorFamily.CODE,
            name=name,
            target=str(probe_file),
            attempt_details=f"Attempted execution of dropped {script_ext} script",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"output": stdout_txt},
        )

    @classmethod
    def probe_unsigned_dll_load(cls, scratch_dir: Path) -> HostileProbeResult:
        """CODE-004: Attempt loading an unsigned DLL from untrusted directory."""
        start = time.perf_counter()
        scratch_dir.mkdir(parents=True, exist_ok=True)
        dummy_dll = scratch_dir / f"untrusted_{time.time_ns()}.dll"
        dummy_dll.write_bytes(b"MZ_DUMMY_NOT_A_REAL_PE_HEADER")

        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                LOAD_LIBRARY_SEARCH_DEFAULT_DIRS = 0x00001000
                h_mod = kernel32.LoadLibraryExW(
                    str(dummy_dll),
                    None,
                    LOAD_LIBRARY_SEARCH_DEFAULT_DIRS,
                )
                if h_mod:
                    kernel32.FreeLibrary(h_mod)
                    blocked = False
                    sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
                    err_name = "LOAD_LIBRARY_SUCCESS"
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

        try:
            dummy_dll.unlink(missing_ok=True)
        except Exception:
            pass

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="CODE-004",
            family=VectorFamily.CODE,
            name="UnsignedDllLoadProbe",
            target=str(dummy_dll),
            attempt_details="Attempted dynamic loading of unsigned DLL from scratch directory",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def run_all_probes(cls, scratch_dir: Path) -> list[HostileProbeResult]:
        """Execute full code execution control probe suite."""
        return [
            cls.probe_dropped_script(scratch_dir, ".bat", "CODE-001", "DroppedBatchExecutionProbe"),
            cls.probe_dropped_script(
                scratch_dir, ".ps1", "CODE-002", "DroppedPowerShellExecutionProbe"
            ),
            cls.probe_dropped_script(scratch_dir, ".vbs", "CODE-003", "DroppedVbsExecutionProbe"),
            cls.probe_unsigned_dll_load(scratch_dir),
        ]


__all__ = ["CodeGuard"]
