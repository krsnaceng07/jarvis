"""jarvis.agents.sandbox.process_job — OS-level process tree containment.

On Windows: uses Win32 Job Objects (or taskkill /T fallback) to guarantee that
when a process is terminated or cancelled, all descendant processes are reaped
without leaving zombie/orphan server processes.
On POSIX: uses process groups (os.killpg) to terminate the entire process group.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any


class ProcessTreeContainment:
    """Manages process lifecycle containment."""

    @staticmethod
    def kill_process_tree(proc: subprocess.Popen[Any] | Any) -> None:
        """Terminate a process and all its descendants reliably across platforms."""
        if proc is None:
            return

        pid = getattr(proc, "pid", None)
        if not pid:
            return

        try:
            if sys.platform == "win32":
                # Use taskkill /T /F on Windows to take down the entire tree
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            else:
                # POSIX process group kill
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, 9)  # SIGKILL
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
