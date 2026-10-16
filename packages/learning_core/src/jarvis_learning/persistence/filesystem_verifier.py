"""Filesystem environment fingerprinting and volume attribute verifier.

Captures filesystem type (NTFS, ReFS), volume serial, disk space, and atomic rename capabilities.
"""

from __future__ import annotations

import ctypes
import dataclasses
import logging
from pathlib import Path
import platform
import shutil
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class FilesystemFingerprint:
    """Hardware and OS volume attributes for the persistence path."""

    drive_root: str
    filesystem_type: str
    volume_serial: str
    total_space_mb: int
    free_space_mb: int
    supports_atomic_rename: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class FilesystemVerifier:
    """Inspects underlying volume attributes and storage properties."""

    @classmethod
    def inspect(cls, target_path: Path) -> FilesystemFingerprint:
        """Capture filesystem attributes for target storage path."""
        resolved = target_path.resolve()
        drive_root = resolved.anchor or "C:\\"
        fs_type = "UNKNOWN"
        serial_str = "00000000"

        if platform.system() == "Windows":
            try:
                fs_name_buf = ctypes.create_unicode_buffer(261)
                serial = ctypes.c_ulong()
                ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
                    drive_root,
                    None,
                    0,
                    ctypes.byref(serial),
                    None,
                    None,
                    fs_name_buf,
                    260,
                )
                fs_type = fs_name_buf.value
                serial_str = f"{serial.value:08X}"
            except Exception as exc:
                logger.debug("Failed GetVolumeInformationW: %s", exc)

        total_mb = 0
        free_mb = 0
        try:
            usage = shutil.disk_usage(resolved)
            total_mb = int(usage.total / (1024 * 1024))
            free_mb = int(usage.free / (1024 * 1024))
        except Exception:
            pass

        atomic_rename = fs_type.upper() in ("NTFS", "REFS", "EXT4", "APFS") or fs_type == "UNKNOWN"

        return FilesystemFingerprint(
            drive_root=drive_root,
            filesystem_type=fs_type or "NTFS",
            volume_serial=serial_str,
            total_space_mb=total_mb,
            free_space_mb=free_mb,
            supports_atomic_rename=atomic_rename,
        )


__all__ = ["FilesystemFingerprint", "FilesystemVerifier"]
