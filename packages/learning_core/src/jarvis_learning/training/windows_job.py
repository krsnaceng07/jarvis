"""jarvis_learning.training.windows_job — Windows Job Object kernel-level resource containment.

On Windows, attaches child processes to a Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
and JOB_OBJECT_LIMIT_PROCESS_MEMORY to enforce hard memory and process tree termination.
Falls back safely on non-Windows platforms.
"""

from __future__ import annotations

import ctypes
import logging
import platform
from typing import Any

logger = logging.getLogger(__name__)

# Constants from winnt.h
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JobObjectExtendedLimitInformation = 9


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


class WindowsJobObject:
    """Manages a Windows Job Object for hard subprocess resource and lifecycle containment."""

    def __init__(self, max_memory_mb: int = 0) -> None:
        self.max_memory_mb = max_memory_mb
        self.is_windows = platform.system() == "Windows"
        self._handle: Any = None
        self._is_configured = False

        if self.is_windows:
            self._init_job_object()

    def _init_job_object(self) -> None:
        """Create and configure the Windows Job Object."""
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                logger.warning(
                    "Failed to create Windows Job Object: error=%d", kernel32.GetLastError()
                )
                return

            self._handle = handle

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            if self.max_memory_mb > 0:
                flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY
                limit_bytes = self.max_memory_mb * 1024 * 1024
                info.ProcessMemoryLimit = limit_bytes
                info.JobMemoryLimit = limit_bytes

            info.BasicLimitInformation.LimitFlags = flags

            success = kernel32.SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not success:
                logger.warning("Failed to configure Job Object: error=%d", kernel32.GetLastError())
            else:
                self._is_configured = True
                logger.debug(
                    "Windows Job Object configured: kill_on_close=True, max_memory_mb=%d",
                    self.max_memory_mb,
                )
        except Exception as exc:
            logger.warning("Error initializing Windows Job Object: %s", exc)

    def assign_process(self, pid_or_handle: int) -> bool:
        """Assign a process to this Job Object by PID or Process Handle."""
        if not self.is_windows or not self._handle:
            return False

        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # PROCESS_SET_QUOTA (0x0100) | PROCESS_TERMINATE (0x0001)
            process_handle = kernel32.OpenProcess(0x0101, False, pid_or_handle)
            if not process_handle:
                logger.warning("Could not open process %d for Job assignment", pid_or_handle)
                return False

            try:
                success = kernel32.AssignProcessToJobObject(self._handle, process_handle)
                if not success:
                    logger.warning("AssignProcessToJobObject failed for pid=%d", pid_or_handle)
                    return False
                logger.info("Assigned pid=%d to Windows Job Object", pid_or_handle)
                return True
            finally:
                kernel32.CloseHandle(process_handle)
        except Exception as exc:
            logger.warning("Exception assigning process to Job Object: %s", exc)
            return False

    def terminate(self, exit_code: int = 1) -> bool:
        """Forcefully terminate all processes in the Job Object."""
        if not self.is_windows or not self._handle:
            return False

        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            success = kernel32.TerminateJobObject(self._handle, exit_code)
            return bool(success)
        except Exception as exc:
            logger.warning("Exception terminating Job Object: %s", exc)
            return False

    def is_supported(self) -> bool:
        """Return True if running on Windows and the Job Object was successfully created."""
        return self.is_windows and self._is_configured

    def contains_process(self, pid: int) -> bool:
        """Check if process is assigned to this Job Object using IsProcessInJob."""
        if not self.is_windows or not self._handle:
            return False
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            result = ctypes.c_bool()
            proc_h = kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
            if not proc_h:
                return False
            try:
                success = kernel32.IsProcessInJob(proc_h, self._handle, ctypes.byref(result))
                return bool(success and result.value)
            finally:
                kernel32.CloseHandle(proc_h)
        except Exception:
            return False

    def close(self) -> None:
        """Close the Job Object handle."""
        if self.is_windows and self._handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self._handle)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._handle = None

    def __enter__(self) -> WindowsJobObject:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
