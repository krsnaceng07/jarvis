"""Windows restricted token, low-integrity SID, and Job Object configuration models.

Enforces INV-P10-SBX-001: Required sandbox guarantees must be established
and verified before any restricted worker launch.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any


@dataclasses.dataclass(frozen=True)
class WindowsTokenConfig:
    """Configuration for Win32 Restricted Token generation."""

    strip_admin_sids: bool = True
    disable_max_privileges: bool = True
    integrity_level: str = "SECURITY_MANDATORY_LOW_RID"
    restricted_sids_count: int = 1
    zero_socket_handles: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class WindowsJobObjectConfig:
    """Configuration for Win32 Job Object process containment."""

    kill_on_job_close: bool = True
    max_active_processes: int = 1
    memory_limit_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB limit
    cpu_rate_limit_pct: int = 50

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class WorkerLaunchContext:
    """Complete security execution profile for a worker process."""

    command: list[str]
    scratch_dir: str
    token_config: WindowsTokenConfig
    job_config: WindowsJobObjectConfig

    def build_sanitized_environment(self) -> dict[str, str]:
        """Build an environment dictionary stripped of sensitive tokens and keys."""
        forbidden_substrings = ("KEY", "SECRET", "TOKEN", "AUTH", "PASSWD", "CREDENTIAL")
        sanitized: dict[str, str] = {}

        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(sub in k_upper for sub in forbidden_substrings):
                continue
            sanitized[k] = v

        # Add mandatory sandbox indicators
        sanitized["JARVIS_SANDBOX_RESTRICTED"] = "1"
        sanitized["JARVIS_SCRATCH_DIR"] = self.scratch_dir
        return sanitized
