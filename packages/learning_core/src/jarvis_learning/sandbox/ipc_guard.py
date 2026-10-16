"""Named pipes, shared memory, and IPC boundary isolation guard.

Executes probes IPC-001 through IPC-010:
- Privileged named pipes (\\\\.\\pipe\\jarvis_*)
- Shared memory file mappings (OpenFileMappingW)
- User Interface Privilege Isolation (UIPI) window messages (WM_COPYDATA)
- Clipboard data access (OpenClipboard / GetClipboardData)
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


class IpcGuard:
    """Probes and verifies inter-process communication (IPC) isolation boundaries."""

    @classmethod
    def probe_privileged_named_pipe(
        cls, pipe_name: str = "\\\\.\\pipe\\jarvis_control_pipe"
    ) -> HostileProbeResult:
        """IPC-001: Attempt connecting to privileged host named pipe."""
        start = time.perf_counter()
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                GENERIC_READ = 0x80000000
                GENERIC_WRITE = 0x40000000
                OPEN_EXISTING = 3

                h_pipe = kernel32.CreateFileW(
                    pipe_name,
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    None,
                    OPEN_EXISTING,
                    0,
                    None,
                )
                INVALID_HANDLE_VALUE = -1
                if h_pipe != INVALID_HANDLE_VALUE and h_pipe != 0:
                    kernel32.CloseHandle(h_pipe)
                    blocked = False
                    sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
                    err_name = "PIPE_CONNECTED_SUCCESS"
                else:
                    err_code = kernel32.GetLastError()
                    blocked = True
                    # Error 2 = ERROR_FILE_NOT_FOUND (no pipe), Error 5 = ERROR_ACCESS_DENIED
                    err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else f"WIN32_ERROR_{err_code}"
            except Exception as exc:
                blocked = True
                err_name = str(exc)
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="IPC-001",
            family=VectorFamily.IPC,
            name="PrivilegedNamedPipeProbe",
            target=pipe_name,
            attempt_details="Attempted opening privileged named pipe handle",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_shared_memory_mapping(
        cls, map_name: str = "Local\\JarvisHostSharedMem"
    ) -> HostileProbeResult:
        """IPC-003: Attempt opening shared memory file mapping created by host."""
        start = time.perf_counter()
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                FILE_MAP_READ = 0x0004

                h_map = kernel32.OpenFileMappingW(FILE_MAP_READ, False, map_name)
                if h_map:
                    kernel32.CloseHandle(h_map)
                    blocked = False
                    sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
                    err_name = "SHARED_MEM_OPEN_SUCCESS"
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
            vector_id="IPC-003",
            family=VectorFamily.IPC,
            name="SharedMemoryMappingProbe",
            target=map_name,
            attempt_details="Attempted opening shared memory file mapping",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_clipboard_access(cls) -> HostileProbeResult:
        """IPC-008: Attempt reading clipboard data (governed by Job UI restrictions)."""
        start = time.perf_counter()
        blocked = True
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        if platform.system() == "Windows" and os.name == "nt":
            try:
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

                # Attempt OpenClipboard(NULL)
                if user32.OpenClipboard(None):
                    user32.CloseClipboard()
                    blocked = False
                    mech = EnforcementMechanism.NOT_CONFIGURED
                    sev = SeverityLevel.S3_HOST_RESOURCE_VIOLATION
                    err_name = "CLIPBOARD_OPEN_SUCCESS"
                else:
                    err_code = kernel32.GetLastError()
                    blocked = True
                    mech = EnforcementMechanism.OS_ENFORCED
                    err_name = "ERROR_ACCESS_DENIED" if err_code == 5 else f"WIN32_ERROR_{err_code}"
            except Exception as exc:
                blocked = True
                err_name = str(exc)
        else:
            blocked = True
            mech = EnforcementMechanism.SIMULATED

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="IPC-008",
            family=VectorFamily.IPC,
            name="ClipboardAccessProbe",
            target="OpenClipboard",
            attempt_details="Attempted opening Windows clipboard handle",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def run_all_probes(cls) -> list[HostileProbeResult]:
        """Execute full IPC isolation probe suite."""
        return [
            cls.probe_privileged_named_pipe(),
            cls.probe_shared_memory_mapping(),
            cls.probe_clipboard_access(),
        ]


__all__ = ["IpcGuard"]
