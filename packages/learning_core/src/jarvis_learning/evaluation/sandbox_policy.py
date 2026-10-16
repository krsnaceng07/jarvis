"""jarvis_learning.evaluation.sandbox_policy — Process, Credential & Network Isolation.

Enforces:
1. INV-P9-SAFE-001: Sanitized worker environment with zero API keys, cookies, or secrets.
2. INV-P9-SAFE-003: Application-level network denial (blocks external raw sockets/HTTP).
3. Resource Governance: Windows Job Object quotas (1024MB RAM, max_child_processes=0, task execution timeouts).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

FORBIDDEN_ENV_KEYWORDS = (
    "API_KEY",
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "BEARER",
    "PRIVATE_KEY",
    "SSH_KEY",
)

SAFE_ENV_ALLOWLIST = frozenset(
    {
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "TEMP",
        "TMP",
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUNBUFFERED",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "USERNAME",
        "COMPUTERNAME",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
    }
)


class SecurityPolicyViolationError(RuntimeError):
    """Raised when process isolation or credential hygiene is breached."""


class NetworkAccessBlockedError(RuntimeError):
    """Raised when an unauthorized outbound network request is attempted."""


@dataclass(frozen=True, slots=True)
class WorkerResourceQuota:
    """Resource constraints for background shadow execution."""

    max_memory_mb: int = 1024
    max_child_processes: int = 0
    cpu_rate_control_pct: float = 25.0
    max_execution_time_per_shadow_task: float = 15.0


def create_sanitized_environment(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Create a stripped, safe environment dictionary for child workers."""
    source = dict(base_env if base_env is not None else os.environ)
    sanitized: dict[str, str] = {}

    for key, value in source.items():
        norm_key = key.upper()
        # Check against allowlist and ensure no forbidden substrings
        if norm_key in SAFE_ENV_ALLOWLIST or norm_key.startswith("JARVIS_TEST_"):
            if not any(kw in norm_key for kw in FORBIDDEN_ENV_KEYWORDS):
                sanitized[key] = value

    return sanitized


def verify_sanitized_environment(env: Mapping[str, str]) -> tuple[bool, str]:
    """Validate that an environment dictionary contains zero sensitive keys (INV-P9-SAFE-001).

    Never includes secret values in failure messages.
    """
    detected_violations: list[str] = []

    for key in env:
        norm_key = key.upper()
        for kw in FORBIDDEN_ENV_KEYWORDS:
            if kw in norm_key:
                detected_violations.append(f"Forbidden key pattern: {norm_key}")
                break

    if detected_violations:
        return (
            False,
            f"Sanitization failed: {len(detected_violations)} sensitive key patterns detected",
        )
    return True, "Environment verified safe"


def assert_worker_environment_safe(env: Mapping[str, str] | None = None) -> None:
    """Startup assertion for worker subprocesses. Fails fast if secrets are detected."""
    check_env = env if env is not None else os.environ
    safe, msg = verify_sanitized_environment(check_env)
    if not safe:
        raise SecurityPolicyViolationError(
            f"SECURITY_POLICY_VIOLATION: Worker refuses to initialize. {msg}"
        )


def check_outbound_network_allowed(target_host: str, target_port: int) -> bool:
    """Validate whether network destination is allowed in shadow worker (INV-P9-SAFE-003).

    Only localhost / loopback endpoints are permitted for IPC.
    """
    clean_host = target_host.strip().lower()
    allowed_hosts = {"127.0.0.1", "localhost", "::1"}

    if clean_host in allowed_hosts:
        return True

    logger_msg = f"Outbound network request to {clean_host}:{target_port} is BLOCKED"
    raise NetworkAccessBlockedError(f"NETWORK_POLICY_BLOCKED: {logger_msg}")
