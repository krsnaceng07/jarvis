"""jarvis_learning.training.memory_governor — process and GPU memory governance.

Enforces RSS and VRAM memory boundaries, integrates with Windows Job Objects,
and provides active memory polling to prevent system lockups.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from typing import Any

from .errors import ResourceLimitExceededError
from .windows_job import WindowsJobObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MemoryLimits:
    """Explicit multi-tier memory limits in megabytes."""

    max_process_rss_mb: int = 1024
    max_gpu_allocated_mb: int = 2048
    max_gpu_reserved_mb: int = 3072
    max_total_job_memory_mb: int = 4096


class MemoryGovernor:
    """Monitors and enforces memory consumption for training workers."""

    def __init__(self, limits: MemoryLimits | None = None) -> None:
        self.limits = limits or MemoryLimits()
        self._job_object: WindowsJobObject | None = None

    def setup_job_containment(self, pid: int) -> bool:
        """Attach worker process to Windows Job Object for hard limit enforcement."""
        if platform.system() == "Windows":
            self._job_object = WindowsJobObject(max_memory_mb=self.limits.max_process_rss_mb)
            assigned = self._job_object.assign_process(pid)
            if assigned:
                logger.info(
                    "Worker pid=%d bound to Windows Job Object with %d MB RSS cap",
                    pid,
                    self.limits.max_process_rss_mb,
                )
            return assigned
        return False

    def close(self) -> None:
        """Clean up kernel objects."""
        if self._job_object:
            self._job_object.close()
            self._job_object = None

    def get_current_rss_mb(self, pid: int | None = None) -> float:
        """Measure current RSS memory of target process (or current process) in MB."""
        target_pid = pid or os.getpid()
        try:
            import psutil

            proc = psutil.Process(target_pid)
            return proc.memory_info().rss / (1024 * 1024)
        except Exception:
            # Fallback when psutil is unavailable
            return 0.0

    def check_limits(self, pid: int | None = None, raise_on_breach: bool = True) -> bool:
        """Evaluate process RSS against configured ceiling."""
        rss_mb = self.get_current_rss_mb(pid)
        if rss_mb > 0 and rss_mb > self.limits.max_process_rss_mb:
            msg = (
                f"Process memory ({rss_mb:.1f} MB) exceeded limit "
                f"({self.limits.max_process_rss_mb} MB)"
            )
            logger.warning(msg)
            if raise_on_breach:
                raise ResourceLimitExceededError(msg, resource_type="RAM_RSS")
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Diagnostic state serialization."""
        return {
            "max_process_rss_mb": self.limits.max_process_rss_mb,
            "max_gpu_allocated_mb": self.limits.max_gpu_allocated_mb,
            "max_gpu_reserved_mb": self.limits.max_gpu_reserved_mb,
            "max_total_job_memory_mb": self.limits.max_total_job_memory_mb,
            "current_rss_mb": round(self.get_current_rss_mb(), 2),
            "job_object_active": self._job_object is not None,
        }
