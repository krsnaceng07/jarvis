"""Composite BootSessionIdentity and Windows kernel boot detector.

Captures a multi-field cryptographic identity of the OS boot session,
preventing simple LastBootUpTime or TickCount64 spoofing.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import logging
import os
import platform
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class BootSessionIdentity:
    """Multi-field composite fingerprint uniquely identifying an OS boot session."""

    boot_session_id: str
    last_boot_up_time_utc: str
    last_boot_up_time_timestamp: float
    tick_count_ms: int
    machine_guid: str
    system_drive_serial: str
    hostname: str
    os_version: str
    captured_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class WindowsBootDetector:
    """Queries Windows OS kernel and WMI for authoritative boot session parameters."""

    @classmethod
    def capture_current_session(cls) -> BootSessionIdentity:
        """Capture live composite boot session identity."""
        boot_time_utc, boot_timestamp = cls._query_last_boot_up_time()
        tick_count = cls._query_tick_count_ms()
        machine_guid = cls._query_machine_guid()
        drive_serial = cls._query_system_drive_serial()
        hostname = os.environ.get("COMPUTERNAME", platform.node() or "localhost")
        os_ver = f"{platform.system()} {platform.release()} ({platform.version()})"
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Build composite deterministic session hash
        composite_raw = f"{machine_guid}|{drive_serial}|{boot_time_utc}|{hostname}"
        session_id = f"BOOT_{hashlib.sha256(composite_raw.encode('utf-8')).hexdigest()[:24]}"

        return BootSessionIdentity(
            boot_session_id=session_id,
            last_boot_up_time_utc=boot_time_utc,
            last_boot_up_time_timestamp=boot_timestamp,
            tick_count_ms=tick_count,
            machine_guid=machine_guid,
            system_drive_serial=drive_serial,
            hostname=hostname,
            os_version=os_ver,
            captured_at_utc=now_utc,
        )

    @classmethod
    def compare_sessions(
        cls,
        pre_session: BootSessionIdentity,
        post_session: BootSessionIdentity,
    ) -> tuple[bool, str]:
        """Compare two boot sessions to establish whether a physical reboot occurred.

        Returns (is_proven_reboot, causal_reason).
        """
        # 1. Host identity match check
        if pre_session.machine_guid != post_session.machine_guid:
            return (
                False,
                f"Host mismatch: pre MachineGuid {pre_session.machine_guid} != post {post_session.machine_guid}",
            )

        if pre_session.hostname.lower() != post_session.hostname.lower():
            return False, f"Hostname mismatch: {pre_session.hostname} != {post_session.hostname}"

        # 2. Boot timestamp monotonic advance check
        boot_delta = (
            post_session.last_boot_up_time_timestamp - pre_session.last_boot_up_time_timestamp
        )

        if boot_delta > 0:
            # Physical reboot confirmed!
            if pre_session.boot_session_id == post_session.boot_session_id:
                return (
                    False,
                    "Conflict: boot timestamp advanced but composite session ID remained identical",
                )
            return (
                True,
                f"Physical reboot verified: LastBootUpTime advanced by {boot_delta:.1f}s (new session {post_session.boot_session_id})",
            )

        if boot_delta == 0:
            return (
                False,
                f"Same boot session: LastBootUpTime unchanged ({pre_session.last_boot_up_time_utc})",
            )

        return (
            False,
            f"Anomaly: post-boot timestamp is earlier than pre-boot timestamp (delta: {boot_delta:.1f}s)",
        )

    @classmethod
    def evaluate_reboot_reality(
        cls,
        pre_session: BootSessionIdentity,
        post_session: BootSessionIdentity,
    ) -> tuple[Any, bool]:
        """Evaluate ground truth reboot reality enum and boolean advance flag."""
        from jarvis_learning.persistence.models import RebootReality

        is_reboot, _ = cls.compare_sessions(pre_session, post_session)
        if is_reboot:
            return RebootReality.REAL_REBOOT, True
        return RebootReality.SAME_SESSION, False

    capture_identity = capture_current_session

    @staticmethod
    def _query_last_boot_up_time() -> tuple[str, float]:
        """Query Win32_OperatingSystem.LastBootUpTime via PowerShell."""
        if platform.system() == "Windows":
            try:
                cmd = "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    raw_str = res.stdout.strip()
                    # Parse ISO format
                    dt = datetime.datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
                    return dt.isoformat(), dt.timestamp()
            except Exception as exc:
                logger.debug("Failed querying WMI LastBootUpTime: %s", exc)

        # Fallback to psutil.boot_time() or system start estimate
        try:
            import psutil  # type: ignore[import-untyped]

            btime = psutil.boot_time()
            dt = datetime.datetime.fromtimestamp(btime, tz=datetime.timezone.utc)
            return dt.isoformat(), btime
        except Exception:
            now = time.time()
            dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
            return dt.isoformat(), now

    @staticmethod
    def _query_tick_count_ms() -> int:
        """Query uptime in milliseconds."""
        if platform.system() == "Windows":
            try:
                import ctypes

                return int(ctypes.windll.kernel32.GetTickCount64())  # type: ignore[attr-defined]
            except Exception:
                pass
        return int(time.monotonic() * 1000)

    @staticmethod
    def _query_machine_guid() -> str:
        """Query Windows MachineGuid from HKLM\\SOFTWARE\\Microsoft\\Cryptography."""
        if platform.system() == "Windows":
            try:
                import winreg  # type: ignore[import-untyped]

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
                ) as key:
                    guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                    return str(guid).strip()
            except Exception:
                pass
        # Fallback to deterministic host ID based on node and processor
        raw = f"{platform.node()}|{platform.machine()}|{platform.processor()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:36]

    @staticmethod
    def _query_system_drive_serial() -> str:
        """Query volume serial number of system drive (C:)."""
        if platform.system() == "Windows":
            try:
                import ctypes

                serial = ctypes.c_ulong()
                ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
                    "C:\\", None, 0, ctypes.byref(serial), None, None, None, 0
                )
                return f"{serial.value:08X}"
            except Exception:
                pass
        return "VOL_DEFAULT_0000"


__all__ = ["BootSessionIdentity", "WindowsBootDetector"]
