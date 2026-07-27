"""PID liveness and start-time probes for cross-process health records.

OpenClaw parity: ``src/shared/pid-alive.ts``. ``get_process_start_time``
reads Linux ``/proc/<pid>/stat`` (field 22, ``starttime`` in clock ticks)
and returns ``None`` on any other platform or on any read/parse failure,
so callers fail closed exactly like the TS host.
"""
from __future__ import annotations

import os
import sys

__all__ = ["get_process_start_time", "is_pid_alive", "is_pid_definitely_dead"]


def is_pid_alive(pid: int) -> bool:
    """Best-effort liveness probe; ``True`` when unsure (fail open here)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Signal 0 rejected but the process exists.
        return True
    except OSError:
        return True


def is_pid_definitely_dead(pid: int) -> bool:
    """``True`` only when the platform positively reports the pid gone."""
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True
    except OSError:
        return False


def get_process_start_time(pid: int) -> int | None:
    """Return the process start time in clock ticks, or ``None``.

    Linux-only (``/proc/<pid>/stat``); any failure returns ``None`` so
    consumers treat the identity check as inconclusive and fail closed.
    """
    if not isinstance(pid, int) or pid <= 0:
        return None
    if not sys.platform.startswith("linux"):
        return None
    try:
        raw = pathlib_read(f"/proc/{pid}/stat")
    except OSError:
        return None
    if raw is None:
        return None
    # comm may contain spaces/parens; fields resume after the last ")".
    close = raw.rfind(")")
    if close < 0:
        return None
    rest = raw[close + 1 :].split()
    # rest[0] is field 3 (state); starttime is field 22 => rest index 19.
    if len(rest) <= 19:
        return None
    try:
        return int(rest[19], 10)
    except ValueError:
        return None


def pathlib_read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except FileNotFoundError:
        return None
