"""Temporary directory management for browser profiles."""

import tempfile
import shutil
import atexit
from pathlib import Path
from typing import Set

_tmp_dirs: Set[Path] = set()


def create_tmp_browser_dir(prefix: str = "openclaw-browser-") -> str:
    """Create a temporary directory for a browser profile and register it for cleanup."""
    tmp_path = Path(tempfile.mkdtemp(prefix=prefix))
    _tmp_dirs.add(tmp_path)
    return str(tmp_path)


def cleanup_tmp_dirs() -> None:
    """Remove all created temporary browser directories."""
    for tmp_dir in list(_tmp_dirs):
        try:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            _tmp_dirs.remove(tmp_dir)
        except Exception:
            pass


# Ensure cleanup on exit
atexit.register(cleanup_tmp_dirs)
