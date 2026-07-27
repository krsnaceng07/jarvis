"""conftest.py — Pytest configuration and Windows path safety hooks."""

from __future__ import annotations

import sys
import _pytest.pathlib

# On Windows, pytest's default cleanup_dead_symlinks in _pytest/pathlib.py
# calls resolve().exists() on 'pytest-current', which can raise PermissionError
# when temporary directory junctions are locked by Windows OS handles.
_orig_cleanup = _pytest.pathlib.cleanup_dead_symlinks


def _safe_cleanup_dead_symlinks(root: _pytest.pathlib.Path) -> None:
    try:
        _orig_cleanup(root)
    except PermissionError:
        pass
    except Exception:
        pass


if sys.platform == "win32":
    _pytest.pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
