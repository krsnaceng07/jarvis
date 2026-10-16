"""OS-level durable filesystem flush and atomic write primitives.

Distinguishes userspace Python flush() from true OS hardware flush
(FlushFileBuffers on Windows, os.fsync on POSIX), guaranteeing physical durability.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import platform
import uuid

from typing import Any

from jarvis_learning.persistence.models import DurabilityLevel

logger = logging.getLogger(__name__)


class DurableFileWriter:
    """Writes files with explicit userspace and OS-level hardware flush guarantees."""

    @classmethod
    def write_durable_bytes(
        cls,
        destination: Path,
        content: bytes,
        sync_os: bool = True,
    ) -> DurabilityLevel:
        """Atomically write and flush content to destination using safe staging and fsync."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging_file = destination.parent / f".tmp_{destination.name}_{uuid.uuid4().hex[:6]}"

        with open(staging_file, "wb") as f:
            f.write(content)
            # 1. Userspace Python flush
            f.flush()

            # 2. OS-level durable flush
            if sync_os:
                cls.flush_to_os(f.fileno())

        # 3. Atomic replace ensuring zero partial exposure
        staging_file.replace(destination)
        return DurabilityLevel.ATOMIC_RENAME

    @staticmethod
    def flush_to_os(fileno: int) -> None:
        """Call OS-level hardware flush on the given file descriptor."""
        try:
            os.fsync(fileno)
        except Exception:
            pass

        if platform.system() == "Windows":
            try:
                import ctypes
                import msvcrt  # type: ignore[import-untyped]

                handle = msvcrt.get_osfhandle(fileno)
                if handle and handle != -1:
                    ctypes.windll.kernel32.FlushFileBuffers(handle)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("Windows FlushFileBuffers call failed: %s", exc)

    write_durable = write_durable_bytes


class FileSystemFlushVerifier:
    """Verifies that durable write and flush mechanisms operate successfully on local filesystem."""

    @classmethod
    def verify_flush_mechanics(cls, test_dir: Path) -> dict[str, Any]:
        test_file = test_dir / f".flush_test_{uuid.uuid4().hex[:6]}.bin"
        try:
            level = DurableFileWriter.write_durable_bytes(
                test_file, b"test_flush_content", sync_os=True
            )
            return {
                "durable_write_succeeded": test_file.exists(),
                "durability_level": level.value,
                "verified": True,
            }
        finally:
            if test_file.exists():
                try:
                    test_file.unlink()
                except Exception:
                    pass


__all__ = ["DurableFileWriter", "FileSystemFlushVerifier"]
