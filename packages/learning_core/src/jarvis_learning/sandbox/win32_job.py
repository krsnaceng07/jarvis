"""Real Win32 Job Object containment engine with process, memory, UI, and CPU limits.

Implements hard kernel-enforced process containment:
- CreateJobObjectW & SetInformationJobObject
- Extended Limits: KILL_ON_JOB_CLOSE, ACTIVE_PROCESS_LIMIT, PROCESS_MEMORY, JOB_MEMORY
- UI Restrictions: Read/Write Clipboard, Global Atoms, Desktops, Window Handles
- CPU Rate Control: Hard cap percentage enforcement
- Descendant accounting: Verifies child and grandchild process membership
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import platform
from typing import Any

logger = logging.getLogger(__name__)

# Constants from winnt.h
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000

# UI Restrictions from winuser.h
JOB_OBJECT_UILIMIT_HANDLES = 0x00000001
JOB_OBJECT_UILIMIT_READCLIPBOARD = 0x00000002
JOB_OBJECT_UILIMIT_WRITECLIPBOARD = 0x00000004
JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS = 0x00000008
JOB_OBJECT_UILIMIT_DISPLAYSETTINGS = 0x00000010
JOB_OBJECT_UILIMIT_GLOBALATOMS = 0x00000020
JOB_OBJECT_UILIMIT_DESKTOP = 0x00000040
JOB_OBJECT_UILIMIT_EXITWINDOWS = 0x00000080

# CPU Rate Control
JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x00000001
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x00000004

# Job Information Classes
JobObjectBasicAccountingInformation = 1
JobObjectBasicProcessIdList = 3
JobObjectBasicUIRestrictions = 4
JobObjectExtendedLimitInformation = 9
JobObjectCpuRateControlInformation = 15


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoCounters", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
    _fields_ = [
        ("UIRestrictionsClass", wintypes.DWORD),
    ]


class JOBOBJECT_CPU_RATE_CONTROL_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ControlFlags", wintypes.DWORD),
        ("CpuRate", wintypes.DWORD),
    ]


class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", wintypes.DWORD),
        ("NumberOfProcessIdsInList", wintypes.DWORD),
        ("ProcessIdList", ctypes.c_size_t * 1024),
    ]


class Win32JobObjectEngine:
    """Manages creation, hard limit assignment, and descendant process tracking for Job Objects."""

    def __init__(
        self,
        name: str | None = None,
        max_processes: int = 1,
        memory_limit_bytes: int = 2 * 1024 * 1024 * 1024,  # 2 GB
        cpu_rate_pct: int = 50,
        apply_ui_restrictions: bool = True,
        kill_on_close: bool = True,
    ) -> None:
        self.name = name
        self.max_processes = max_processes
        self.memory_limit_bytes = memory_limit_bytes
        self.cpu_rate_pct = cpu_rate_pct
        self.apply_ui_restrictions = apply_ui_restrictions
        self.kill_on_close = kill_on_close

        self._handle: int | None = None
        self._is_windows = platform.system() == "Windows" and os.name == "nt"

        if self._is_windows:
            self._create_and_configure_job()

    @property
    def handle(self) -> int | None:
        return self._handle

    @property
    def is_active(self) -> bool:
        return self._handle is not None

    def _create_and_configure_job(self) -> None:
        """Create and configure Job Object with extended limits, UI restrictions, and CPU caps."""
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        # 1. Create Job Object
        h_job = kernel32.CreateJobObjectW(None, self.name)
        if not h_job:
            logger.error("CreateJobObjectW failed (Win32 Error %d)", kernel32.GetLastError())
            return
        self._handle = h_job

        # 2. Configure Extended Limit Information
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        flags = JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION

        if self.kill_on_close:
            flags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        if self.max_processes > 0:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            limits.BasicLimitInformation.ActiveProcessLimit = self.max_processes

        if self.memory_limit_bytes > 0:
            flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY
            limits.ProcessMemoryLimit = self.memory_limit_bytes
            limits.JobMemoryLimit = self.memory_limit_bytes

        limits.BasicLimitInformation.LimitFlags = flags

        res = kernel32.SetInformationJobObject(
            self._handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not res:
            logger.warning(
                "SetInformationJobObject (ExtendedLimits) failed (Win32 Error %d)",
                kernel32.GetLastError(),
            )

        # 3. Configure UI Restrictions
        if self.apply_ui_restrictions:
            ui = JOBOBJECT_BASIC_UI_RESTRICTIONS()
            ui.UIRestrictionsClass = (
                JOB_OBJECT_UILIMIT_HANDLES
                | JOB_OBJECT_UILIMIT_READCLIPBOARD
                | JOB_OBJECT_UILIMIT_WRITECLIPBOARD
                | JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS
                | JOB_OBJECT_UILIMIT_DISPLAYSETTINGS
                | JOB_OBJECT_UILIMIT_GLOBALATOMS
                | JOB_OBJECT_UILIMIT_DESKTOP
                | JOB_OBJECT_UILIMIT_EXITWINDOWS
            )
            kernel32.SetInformationJobObject(
                self._handle,
                JobObjectBasicUIRestrictions,
                ctypes.byref(ui),
                ctypes.sizeof(ui),
            )

        # 4. Configure CPU Rate Control (if supported)
        if 0 < self.cpu_rate_pct < 100:
            cpu = JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()
            cpu.ControlFlags = (
                JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
            )
            # 100% CPU is represented as 10,000 basis points
            cpu.CpuRate = self.cpu_rate_pct * 100
            kernel32.SetInformationJobObject(
                self._handle,
                JobObjectCpuRateControlInformation,
                ctypes.byref(cpu),
                ctypes.sizeof(cpu),
            )

    def assign_process(self, process_id_or_handle: int, is_handle: bool = False) -> bool:
        """Assign target process to Job Object."""
        if not self._is_windows or not self._handle:
            return True

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        if is_handle:
            h_proc = process_id_or_handle
            should_close = False
        else:
            # Open process handle with PROCESS_SET_QUOTA | PROCESS_TERMINATE
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_TERMINATE = 0x0001
            h_proc = kernel32.OpenProcess(
                PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, process_id_or_handle
            )
            if not h_proc:
                logger.error(
                    "OpenProcess failed for PID %d (Win32 Error %d)",
                    process_id_or_handle,
                    kernel32.GetLastError(),
                )
                return False
            should_close = True

        try:
            ret = kernel32.AssignProcessToJobObject(self._handle, h_proc)
            if not ret:
                logger.error(
                    "AssignProcessToJobObject failed (Win32 Error %d)", kernel32.GetLastError()
                )
            return bool(ret)
        finally:
            if should_close:
                kernel32.CloseHandle(h_proc)

    def get_assigned_pids(self) -> list[int]:
        """Query list of all process IDs currently active in this Job Object."""
        if not self._is_windows or not self._handle:
            return []

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        proc_list = JOBOBJECT_BASIC_PROCESS_ID_LIST()
        cb = wintypes.DWORD(ctypes.sizeof(proc_list))

        res = kernel32.QueryInformationJobObject(
            self._handle,
            JobObjectBasicProcessIdList,
            ctypes.byref(proc_list),
            cb,
            None,
        )
        if not res:
            return []

        pids: list[int] = []
        for i in range(proc_list.NumberOfProcessIdsInList):
            pids.append(proc_list.ProcessIdList[i])
        return pids

    def terminate(self, exit_code: int = 1) -> bool:
        """Forcibly terminate all processes currently in the Job Object."""
        if not self._is_windows or not self._handle:
            return True

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        ret = kernel32.TerminateJobObject(self._handle, exit_code)
        return bool(ret)

    def close(self) -> None:
        """Close Job Object handle, triggering KILL_ON_JOB_CLOSE if configured."""
        if self._is_windows and self._handle:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> Win32JobObjectEngine:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


__all__ = ["Win32JobObjectEngine"]
