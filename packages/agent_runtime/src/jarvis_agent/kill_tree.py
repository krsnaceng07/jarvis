"""jarvis_agent.kill_tree — process-tree termination.

OpenClaw parity: mirrors
``openclaw-main/packages/agent-core/src/harness/env/kill-tree.ts``.

Best-effort process-tree termination with graceful shutdown.

- Windows: use ``taskkill /T`` to include descendants. Sends a
  SIGTERM-equivalent first (without ``/F``), then force-kills if
  the process survives.
- Unix: send SIGTERM to the process group first, wait the grace
  period, then SIGKILL.

Group kill (``os.kill(-pid, ...)``) is only used when the PID is
verified as its own process-group leader, unless
``detached: True`` is explicitly passed. This prevents
accidentally signaling the gateway's process group when the
child shares its parent's group.

- ``detached: False``: skip group kill unconditionally.
- ``detached: True``: use group kill unconditionally (trust
  caller).
- ``detached`` omitted: use group kill only when the PID is the
  group leader.

Adaptations
-----------
- The OpenClaw source's ``setTimeout(...).unref()`` deferred
  SIGKILL is ported as a daemon :class:`threading.Timer` (same
  fire-and-forget semantics: it does not keep the process
  alive).
- ``process.kill(pid, signal)`` becomes :func:`os.kill`;
  Node's string signals map to :mod:`signal` constants.
- ``KillProcessTreeOptions`` (a TS type) becomes a plain
  keyword-argument surface (``grace_ms`` / ``detached`` /
  ``force``) plus the exported ``KillProcessTreeOptions = dict``
  alias for wire-shape parity.
"""

from __future__ import annotations

import os
import re
import signal as _signal
import subprocess
import sys
import threading
from typing import Optional

DEFAULT_GRACE_MS = 3000
MAX_GRACE_MS = 60_000

#: Mirrors ``KillProcessTreeOptions``
#: (``kill-tree.ts:8-12``).
#: ``{"graceMs"?, "detached"?, "force"?}``.
KillProcessTreeOptions = dict


def _is_windows() -> bool:
    """Mirrors ``process.platform === "win32"``."""
    return sys.platform == "win32"


def normalize_grace_ms(value: Optional[float] = None) -> int:
    """Mirrors ``normalizeGraceMs`` (``kill-tree.ts:83-88``)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return DEFAULT_GRACE_MS
    # JS Number.isFinite check.
    try:
        if value != value or value in (float("inf"), float("-inf")):
            return DEFAULT_GRACE_MS
    except TypeError:
        return DEFAULT_GRACE_MS
    import math

    return max(0, min(MAX_GRACE_MS, math.floor(value)))


def _is_process_alive(pid: int) -> bool:
    """Mirrors ``isProcessAlive`` (``kill-tree.ts:90-97``)."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _parse_process_group_id(value: object) -> Optional[int]:
    """Mirrors ``parseProcessGroupId``
    (``kill-tree.ts:99-105``)."""
    if not isinstance(value, str) or not re.fullmatch(r"\d+", value.strip()):
        return None
    pgid = int(value.strip())
    # JS Number.isSafeInteger + > 0.
    return pgid if 0 < pgid <= 2**53 - 1 else None


def _read_process_group_id_from_ps(pid: int) -> Optional[int]:
    """Mirrors ``readProcessGroupIdFromPs``
    (``kill-tree.ts:107-120``)."""
    try:
        res = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pgid="],
            capture_output=True,
            encoding="utf-8",
            timeout=0.5,
        )
        if res.returncode != 0:
            return None
        return _parse_process_group_id(res.stdout)
    except Exception:
        return None


def _read_process_group_id_from_proc(pid: int) -> Optional[int]:
    """Mirrors ``readProcessGroupIdFromProc``
    (``kill-tree.ts:122-138``)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            stat = f.read()
        comm_end = stat.rfind(")")
        if comm_end < 0:
            return None
        # After comm: state, ppid, pgrp. The command name may
        # contain spaces or ')'.
        fields = stat[comm_end + 1 :].strip().split()
        if len(fields) <= 2:
            return None
        return _parse_process_group_id(fields[2])
    except Exception:
        return None


def _is_process_group_leader(pid: int) -> bool:
    """Fail closed to direct-PID signaling when group ownership
    cannot be proved. Mirrors ``isProcessGroupLeader``
    (``kill-tree.ts:141-146``)."""
    # Linux exposes the fact in procfs; avoid a synchronous
    # child process on the common path.
    proc_pgid = _read_process_group_id_from_proc(pid) if sys.platform.startswith("linux") else None
    pgid = proc_pgid if proc_pgid is not None else _read_process_group_id_from_ps(pid)
    return pgid == pid


def _to_signal(signal_name: str) -> int:
    """Map ``"SIGTERM"`` / ``"SIGKILL"`` to the platform
    signal number."""
    if signal_name == "SIGKILL":
        return getattr(_signal, "SIGKILL", _signal.SIGTERM)
    return _signal.SIGTERM


def _signal_process_tree_unix(pid: int, signal_name: str, use_group_kill: bool) -> None:
    """Mirrors ``signalProcessTreeUnix``
    (``kill-tree.ts:148-167``)."""
    sig = _to_signal(signal_name)
    if use_group_kill:
        try:
            os.kill(-pid, sig)
            return
        except OSError:
            # Process group does not exist or we lack
            # permission; try direct pid.
            pass
    try:
        os.kill(pid, sig)
    except OSError:
        # Already gone.
        pass


def _run_taskkill(args: list) -> None:
    """Mirrors ``runTaskkill`` (``kill-tree.ts:169-180``)."""
    try:
        creationflags = 0
        if _is_windows():  # pragma: no cover - Windows only
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
        subprocess.Popen(
            ["taskkill", *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception:
        # Ignore taskkill spawn failures.
        pass


def _signal_process_tree_windows(pid: int, signal_name: str) -> None:
    """Mirrors ``signalProcessTreeWindows``
    (``kill-tree.ts:193-197``)."""
    args = ["/F", "/T", "/PID", str(pid)] if signal_name == "SIGKILL" else ["/T", "/PID", str(pid)]
    _run_taskkill(args)


def _defer(delay_ms: int, fn) -> None:
    """Port of ``setTimeout(fn, ms).unref()`` — a daemon timer
    that does not keep the interpreter alive."""
    timer = threading.Timer(delay_ms / 1000.0, fn)
    timer.daemon = True
    timer.start()


def _kill_process_tree_windows(pid: int, grace_ms: int) -> None:
    """Mirrors ``killProcessTreeWindows``
    (``kill-tree.ts:182-191``)."""
    _signal_process_tree_windows(pid, "SIGTERM")

    def _late_kill() -> None:
        if not _is_process_alive(pid):
            return
        _signal_process_tree_windows(pid, "SIGKILL")

    _defer(grace_ms, _late_kill)


def kill_process_tree(
    pid: int,
    opts: Optional[KillProcessTreeOptions] = None,
) -> None:
    """Best-effort process-tree termination with graceful
    shutdown. Mirrors ``killProcessTree``
    (``kill-tree.ts:29-62``)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return
    opts = opts or {}

    if _is_windows():  # pragma: no cover - Windows only
        if opts.get("force") is True:
            _signal_process_tree_windows(pid, "SIGKILL")
            return
        grace_ms = normalize_grace_ms(opts.get("graceMs"))
        _kill_process_tree_windows(pid, grace_ms)
        return

    use_group_kill = opts.get("detached") is True or (
        opts.get("detached") is not False and _is_process_group_leader(pid)
    )
    if opts.get("force") is True:
        _signal_process_tree_unix(pid, "SIGKILL", use_group_kill)
        return

    grace_ms = normalize_grace_ms(opts.get("graceMs"))
    _signal_process_tree_unix(pid, "SIGTERM", use_group_kill)

    def _late_kill() -> None:
        still_alive = (
            (_is_process_alive(-pid) or _is_process_alive(pid))
            if use_group_kill
            else _is_process_alive(pid)
        )
        if not still_alive:
            return
        _signal_process_tree_unix(pid, "SIGKILL", use_group_kill)

    _defer(grace_ms, _late_kill)


def signal_process_tree(
    pid: int,
    signal_name: str,
    opts: Optional[dict] = None,
) -> None:
    """Send a single signal to the process tree. Mirrors
    ``signalProcessTree`` (``kill-tree.ts:64-81``).

    ``signal_name`` is ``"SIGTERM"`` or ``"SIGKILL"``.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return
    opts = opts or {}

    if _is_windows():  # pragma: no cover - Windows only
        _signal_process_tree_windows(pid, signal_name)
        return

    use_group_kill = opts.get("detached") is True or (
        opts.get("detached") is not False and _is_process_group_leader(pid)
    )
    _signal_process_tree_unix(pid, signal_name, use_group_kill)


__all__ = [
    "DEFAULT_GRACE_MS",
    "KillProcessTreeOptions",
    "MAX_GRACE_MS",
    "kill_process_tree",
    "normalize_grace_ms",
    "signal_process_tree",
]
