"""jarvis_learning.training.disk_governor — disk space preflight and runtime growth governor.

Guarantees adequate disk space exists prior to training startup and monitors
storage consumption during checkpointing to prevent disk exhaustion.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import DiskSpaceExhaustedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiskGovernor:
    """Monitors workspace disk free space and workspace growth."""

    min_free_disk_mb: float = 500.0  # Minimum free space required on target volume
    max_workspace_growth_mb: float = 2048.0  # Maximum MB added during training

    def check_preflight(self, target_dir: Path | str) -> bool:
        """Verify that target volume has sufficient free space before starting."""
        p = Path(target_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(p)
        free_mb = usage.free / (1024 * 1024)

        if free_mb < self.min_free_disk_mb:
            msg = (
                f"Insufficient disk space on {p}: {free_mb:.1f} MB available, "
                f"minimum {self.min_free_disk_mb:.1f} MB required"
            )
            logger.error(msg)
            raise DiskSpaceExhaustedError(msg)
        return True

    def check_runtime_space(self, target_dir: Path | str) -> bool:
        """Verify free space during execution."""
        p = Path(target_dir).resolve()
        if not p.exists():
            return True
        usage = shutil.disk_usage(p)
        free_mb = usage.free / (1024 * 1024)

        if free_mb < self.min_free_disk_mb:
            msg = f"Runtime disk space exhausted on {p}: {free_mb:.1f} MB remaining"
            logger.error(msg)
            raise DiskSpaceExhaustedError(msg)
        return True

    @staticmethod
    def measure_directory_size_mb(directory: Path | str) -> float:
        """Measure total directory size in megabytes."""
        d = Path(directory)
        if not d.exists():
            return 0.0
        total_bytes = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        return round(total_bytes / (1024 * 1024), 2)
