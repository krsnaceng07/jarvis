"""jarvis.shared.pid_alive — process-id liveness helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/pid-alive.ts``.

Public surface:

- :func:`is_pid_alive`
- :func:`is_pid_definitely_dead`
- :func:`get_process_start_time`
- :func:`get_file_lock_process_start_time`
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Optional


def _is_valid_pid(pid: object) -> bool:
    return isinstance(pid, int) and not isinstance(pid, bool) and pid > 0


def _is_zombie_process(pid: int) -> bool:
    if sys.platform != "linux":
        return False
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as f:
            data = f.read()
        import re
        match = re.search(r"^State:\s+(\S)", data, re.MULTILINE)
        return bool(match and match.group(1) == "Z")
    except (OSError, ValueError):
        return False


def is_pid_alive(pid: int) -> bool:
    """Return true only when a positive PID exists and is not a Linux zombie.

    Mirrors :func:`isPidAlive` (``shared/pid-alive.ts``).
    """
    if not _is_valid_pid(pid):
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ProcessLookupError):
        return False
    return not _is_zombie_process(int(pid))


def is_pid_definitely_dead(pid: int) -> bool:
    """Return true only when the PID is invalid, missing, or a Linux zombie.

    Mirrors :func:`isPidDefinitelyDead` (``shared/pid-alive.ts``).
    """
    if not _is_valid_pid(pid):
        return True
    try:
        os.kill(int(pid), 0)
    except (OSError, ProcessLookupError):
        return True
    return _is_zombie_process(int(pid))


def _get_darwin_process_start_time(pid: int) -> Optional[int]:
    try:
        env = dict(os.environ)
        env["LC_ALL"] = "C"
        env["TZ"] = "UTC"
        completed = subprocess.run(
            ["/bin/ps", "-o", "lstart=", "-p", str(int(pid))],
            env=env,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        text = (completed.stdout or "").strip()
        if not text:
            return None
        from datetime import datetime
        try:
            dt = datetime.strptime(f"{text} UTC", "%a %b %d %H:%M:%S %Y UTC")
        except ValueError:
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
        return int(dt.timestamp())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def get_process_start_time(pid: int) -> Optional[int]:
    """Read the Linux procfs start identity for a PID.

    Mirrors :func:`getProcessStartTime` (``shared/pid-alive.ts``).
    """
    if not _is_valid_pid(pid):
        return None
    if sys.platform != "linux":
        return None
    try:
        with open(f"/proc/{int(pid)}/stat", "r", encoding="utf-8") as f:
            data = f.read()
    except OSError:
        return None
    comm_end = data.rfind(")")
    if comm_end < 0:
        return None
    after = data[comm_end + 1 :].lstrip()
    fields = after.split()
    # field 22 (starttime) = index 19 after the comm split
    if len(fields) < 20:
        return None
    try:
        starttime = int(fields[19])
    except (ValueError, IndexError):
        return None
    return starttime if starttime >= 0 else None


def get_file_lock_process_start_time(pid: int) -> Optional[int]:
    """Read cross-platform process identity for filesystem lock ownership.

    Mirrors :func:`getFileLockProcessStartTime` (``shared/pid-alive.ts``).
    """
    if not _is_valid_pid(pid):
        return None
    if sys.platform == "darwin":
        return _get_darwin_process_start_time(int(pid))
    return get_process_start_time(int(pid))


__all__ = [
    "is_pid_alive",
    "is_pid_definitely_dead",
    "get_process_start_time",
    "get_file_lock_process_start_time",
]
