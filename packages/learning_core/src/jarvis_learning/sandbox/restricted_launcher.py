"""Fail-closed worker process launcher with environment sanitization and Job Object assignment."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess

from jarvis_learning.sandbox.win32_job import Win32JobObjectEngine

logger = logging.getLogger(__name__)

SAFE_ENV_ALLOWLIST = {
    "SYSTEMROOT",
    "WINDIR",
    "PATH",
    "PATHEXT",
    "TEMP",
    "TMP",
    "SYSTEMDRIVE",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES",
    "COMSPEC",
    "OS",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PYTHONHOME",
    "PYTHONPATH",
    "VIRTUAL_ENV",
}

FORBIDDEN_ENV_SUBSTRINGS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "AUTH",
    "CREDENTIAL",
    "API",
    "PRIVATE",
    "COOKIE",
)


class RestrictedProcessLauncher:
    """Launches isolated worker processes under Job Object containment with scrubbed environment."""

    @classmethod
    def sanitize_environment(cls, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Scrub sensitive credentials, tokens, and secrets from process environment."""
        source = dict(base_env if base_env is not None else os.environ)
        clean: dict[str, str] = {}

        for k, v in source.items():
            upper = k.upper()
            if upper in SAFE_ENV_ALLOWLIST:
                clean[k] = v
                continue
            # If variable contains any secret indicator, drop it
            if any(sub in upper for sub in FORBIDDEN_ENV_SUBSTRINGS):
                continue
            # Keep general unclassified variables
            clean[k] = v

        return clean

    @classmethod
    def launch_worker(
        cls,
        command: list[str],
        job: Win32JobObjectEngine | None = None,
        cwd: Path | None = None,
        timeout: float = 10.0,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Launch worker subprocess within Job Object and sanitized environment."""
        env = cls.sanitize_environment()
        if extra_env:
            env.update(extra_env)

        try:
            # close_fds=True ensures zero handle inheritance
            proc = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                close_fds=True,
            )
        except Exception as exc:
            raise RuntimeError(f"SandboxSetupError: failed to spawn worker process: {exc}") from exc

        # Assign to Job Object immediately
        if job is not None:
            assigned = job.assign_process(proc.pid)
            if not assigned:
                proc.kill()
                proc.wait()
                raise RuntimeError(
                    f"SandboxSetupError: failed assigning PID {proc.pid} to Job Object"
                )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise TimeoutError(f"Worker timed out after {timeout} seconds")

        return subprocess.CompletedProcess(
            args=command,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )


__all__ = ["RestrictedProcessLauncher", "SAFE_ENV_ALLOWLIST"]
