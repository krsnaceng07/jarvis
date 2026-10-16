"""Single-instance run lock with stale process detection and Windows cleanup.

Enforces exclusive execution of GPU laboratory runs, preventing concurrent
test executions from contaminating physical hardware measurements.
"""

from __future__ import annotations

import atexit
import dataclasses
import datetime
import json
import logging
import os
import pathlib
import sys
from typing import Any

logger = logging.getLogger(__name__)


class LabRunConflictError(RuntimeError):
    """Raised when another GPU lab run is currently active on the host."""


@dataclasses.dataclass(frozen=True)
class RunLockPayload:
    """Contents of the active run lock file."""

    pid: int
    session_id: str
    host_name: str
    started_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "session_id": self.session_id,
            "host_name": self.host_name,
            "started_at_utc": self.started_at_utc,
        }


class SingleInstanceRunLock:
    """Manages exclusive lab execution and detects stale locks from crashed runs."""

    def __init__(self, lock_path: pathlib.Path | None = None, session_id: str = "default") -> None:
        if lock_path is None:
            home = pathlib.Path.home()
            self.lock_dir = home / ".jarvis" / "run"
            self.lock_file = self.lock_dir / "gpu_lab.lock"
        else:
            self.lock_file = lock_path
            self.lock_dir = self.lock_file.parent

        self.session_id = session_id
        self._acquired = False
        atexit.register(self.release)

    def acquire(self) -> None:
        """Acquire exclusive run lock or raise LabRunConflictError if an active run exists."""
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        if self.lock_file.exists():
            try:
                raw = self.lock_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                existing_pid = int(data.get("pid", 0))

                if self._is_process_alive(existing_pid):
                    if not self._acquired:
                        raise LabRunConflictError(
                            f"Active GPU lab run conflict: PID {existing_pid} is running since "
                            f"{data.get('started_at_utc')}"
                        )
                else:
                    logger.warning(
                        "Cleaning stale run lock from terminated process PID %s", existing_pid
                    )
                    self.lock_file.unlink(missing_ok=True)
            except (json.JSONDecodeError, ValueError, OSError):
                self.lock_file.unlink(missing_ok=True)

        payload = RunLockPayload(
            pid=os.getpid(),
            session_id=self.session_id,
            host_name=os.environ.get("COMPUTERNAME", "localhost"),
            started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        self.lock_file.write_text(json.dumps(payload.to_dict(), indent=2), encoding="utf-8")
        self._acquired = True

    def release(self) -> None:
        """Release exclusive run lock."""
        if self._acquired:
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink(missing_ok=True)
            except Exception:
                pass
            self._acquired = False

    def __enter__(self) -> SingleInstanceRunLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            import ctypes

            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
                PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid
            )
            if handle == 0:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))  # type: ignore[attr-defined]
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            STILL_ACTIVE = 259
            return exit_code.value == STILL_ACTIVE
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False


__all__ = ["LabRunConflictError", "RunLockPayload", "SingleInstanceRunLock"]
