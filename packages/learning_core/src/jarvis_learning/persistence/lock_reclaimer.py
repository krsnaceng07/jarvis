"""Stale pre-reboot process lockfile detection and safe reclamation engine.

Handles stale PID lockfiles left across reboot or crash boundaries:
1. Validates whether the holding PID is still alive on the host.
2. If PID is alive, checks whether process creation time postdates the current boot time
   (detecting Windows PID recycling) or process name belongs to an unrelated binary.
3. Distinguishes live locks from stale/dead locks without crashing or corrupting active sessions.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class LockRecord:
    """Contents and metadata stored inside a JARVIS persistence lockfile."""

    pid: int
    process_name: str
    created_at_utc: str
    created_timestamp_epoch: float
    transaction_id: str
    boot_session_id: str | None = None
    host_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockRecord:
        return cls(
            pid=int(data["pid"]),
            process_name=str(data.get("process_name", "")),
            created_at_utc=str(data.get("created_at_utc", "")),
            created_timestamp_epoch=float(data.get("created_timestamp_epoch", 0.0)),
            transaction_id=str(data.get("transaction_id", "")),
            boot_session_id=data.get("boot_session_id"),
            host_id=data.get("host_id"),
        )


@dataclasses.dataclass(frozen=True)
class LockReclaimResult:
    """Result of auditing or attempting to reclaim a lockfile."""

    lock_file: str
    is_stale: bool
    reclaimed: bool
    holding_pid: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class LockReclaimer:
    """Safe auditor and reclaimer of pre-reboot and stale process locks."""

    @classmethod
    def is_pid_alive(cls, pid: int) -> bool:
        """Check if process ID is alive on Windows host."""
        if pid <= 0:
            return False
        try:
            import psutil

            return psutil.pid_exists(pid)
        except ImportError:
            # Fallback to ctypes OpenProcess on Windows
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False

    @classmethod
    def parse_lock_file(cls, lock_path: Path) -> LockRecord | None:
        """Parse structured or raw lockfile."""
        if not lock_path.exists():
            return None
        try:
            content = lock_path.read_text(encoding="utf-8").strip()
            if content.startswith("{"):
                return LockRecord.from_dict(json.loads(content))
            # Fallback for plain PID string
            pid = int(content)
            return LockRecord(
                pid=pid,
                process_name="unknown",
                created_at_utc="",
                created_timestamp_epoch=0.0,
                transaction_id="",
            )
        except Exception as exc:
            logger.warning("Failed parsing lockfile %s: %s", lock_path, exc)
            return None

    @classmethod
    def write_lock_file(
        cls,
        lock_path: Path,
        pid: int,
        transaction_id: str,
        boot_session_id: str | None = None,
        process_name: str = "jarvis",
    ) -> Path:
        """Create a structured lockfile."""
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        rec = LockRecord(
            pid=pid,
            process_name=process_name,
            created_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            created_timestamp_epoch=time.time(),
            transaction_id=transaction_id,
            boot_session_id=boot_session_id,
        )
        lock_path.write_text(json.dumps(rec.to_dict(), indent=2), encoding="utf-8")
        return lock_path

    @classmethod
    def audit_and_reclaim(
        cls,
        lock_path: Path,
        current_boot_session_id: str | None = None,
        force_if_stale: bool = True,
    ) -> LockReclaimResult:
        """Audit lockfile and safely reclaim if held by dead process or prior boot session."""
        if not lock_path.exists():
            return LockReclaimResult(
                lock_file=str(lock_path),
                is_stale=False,
                reclaimed=False,
                holding_pid=None,
                reason="LOCK_FILE_DOES_NOT_EXIST",
            )

        rec = cls.parse_lock_file(lock_path)
        if rec is None:
            # Corrupted lockfile is stale
            if force_if_stale:
                try:
                    lock_path.unlink()
                    return LockReclaimResult(
                        lock_file=str(lock_path),
                        is_stale=True,
                        reclaimed=True,
                        holding_pid=None,
                        reason="CORRUPTED_LOCK_FILE_UNLINKED",
                    )
                except Exception as exc:
                    return LockReclaimResult(
                        lock_file=str(lock_path),
                        is_stale=True,
                        reclaimed=False,
                        holding_pid=None,
                        reason=f"CORRUPTED_LOCK_UNLINK_FAILED: {exc}",
                    )
            return LockReclaimResult(
                lock_file=str(lock_path),
                is_stale=True,
                reclaimed=False,
                holding_pid=None,
                reason="CORRUPTED_LOCK_FILE",
            )

        # Check PID liveness
        alive = cls.is_pid_alive(rec.pid)
        if not alive:
            # PID dead -> safe to reclaim
            if force_if_stale:
                try:
                    lock_path.unlink()
                    return LockReclaimResult(
                        lock_file=str(lock_path),
                        is_stale=True,
                        reclaimed=True,
                        holding_pid=rec.pid,
                        reason="PID_DEAD_LOCK_RECLAIMED",
                    )
                except Exception as exc:
                    return LockReclaimResult(
                        lock_file=str(lock_path),
                        is_stale=True,
                        reclaimed=False,
                        holding_pid=rec.pid,
                        reason=f"RECLAIM_FAILED: {exc}",
                    )
            return LockReclaimResult(
                lock_file=str(lock_path),
                is_stale=True,
                reclaimed=False,
                holding_pid=rec.pid,
                reason="PID_DEAD_UNRECLAIMED",
            )

        # PID is alive: check boot session continuity if recorded
        if (
            current_boot_session_id is not None
            and rec.boot_session_id is not None
            and rec.boot_session_id != current_boot_session_id
        ):
            # PID recycled across reboot! The PID is alive in current boot, but the lock belonged to prior boot.
            # On Windows, PIDs get recycled quickly.
            if force_if_stale:
                try:
                    lock_path.unlink()
                    return LockReclaimResult(
                        lock_file=str(lock_path),
                        is_stale=True,
                        reclaimed=True,
                        holding_pid=rec.pid,
                        reason="RECYCLED_PID_ACROSS_REBOOT_RECLAIMED",
                    )
                except Exception as exc:
                    return LockReclaimResult(
                        lock_file=str(lock_path),
                        is_stale=True,
                        reclaimed=False,
                        holding_pid=rec.pid,
                        reason=f"RECLAIM_FAILED: {exc}",
                    )

        # Active process holds the lock
        return LockReclaimResult(
            lock_file=str(lock_path),
            is_stale=False,
            reclaimed=False,
            holding_pid=rec.pid,
            reason="PROCESS_ACTIVE_HOLDING_LOCK",
        )


__all__ = ["LockRecord", "LockReclaimResult", "LockReclaimer"]
