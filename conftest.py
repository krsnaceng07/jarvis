"""conftest.py — Pytest configuration, test isolation, and Windows path safety hooks."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import _pytest.pathlib

# Redirect the home/AppData roots before any project import. The suite must
# never read or write the operator's real ~/.jarvis, Chrome profile or cache
# dirs, and a single leaked test used to do exactly that. Every Path.home(),
# os.path.expanduser("~") and platformdirs lookup inside the suite resolves
# under this disposable root instead. Per-run directory, so two pytest runs in
# the same worktree cannot clear each other's state.
ISOLATION_ROOT = Path(tempfile.mkdtemp(prefix="jarvis-pytest-home-"))
_ISOLATED_HOME = ISOLATION_ROOT / "home"
_ISOLATED_APPDATA = ISOLATION_ROOT / "appdata"
_ISOLATED_LOCALAPPDATA = ISOLATION_ROOT / "localappdata"
_ISOLATED_STATE = _ISOLATED_HOME / ".jarvis" / "state"
for _path in (_ISOLATED_HOME, _ISOLATED_APPDATA, _ISOLATED_LOCALAPPDATA, _ISOLATED_STATE):
    _path.mkdir(parents=True, exist_ok=True)

# An explicit JARVIS_STATE_DIR (how the recorded baseline ran) still wins, but
# never when it points inside the real profile: that is the one value the suite
# must not be able to reach.
_REAL_HOME = Path(os.environ.get("USERPROFILE") or Path.home()).resolve()
_explicit_state = os.environ.get("JARVIS_STATE_DIR")
if _explicit_state:
    try:
        _inside_real_home = Path(_explicit_state).resolve().is_relative_to(_REAL_HOME)
    except OSError:
        _inside_real_home = True
    if _inside_real_home:
        _explicit_state = None
_STATE_DIR = Path(_explicit_state).resolve() if _explicit_state else _ISOLATED_STATE
_STATE_DIR.mkdir(parents=True, exist_ok=True)

_HOMEDRIVE, _HOMEPATH = os.path.splitdrive(str(_ISOLATED_HOME))
os.environ.update(
    {
        "HOME": str(_ISOLATED_HOME),
        "USERPROFILE": str(_ISOLATED_HOME),
        "HOMEDRIVE": _HOMEDRIVE,
        "HOMEPATH": _HOMEPATH,
        "APPDATA": str(_ISOLATED_APPDATA),
        "LOCALAPPDATA": str(_ISOLATED_LOCALAPPDATA),
        "XDG_CACHE_HOME": str(_ISOLATED_LOCALAPPDATA),
        "XDG_CONFIG_HOME": str(_ISOLATED_APPDATA),
        "XDG_DATA_HOME": str(_ISOLATED_LOCALAPPDATA),
        "JARVIS_STATE_DIR": str(_STATE_DIR),
    }
)

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


def pytest_report_header(config: object) -> str:
    """Show the isolated home so a leaking test path can be traced."""
    return f"jarvis test isolation home: {ISOLATION_ROOT}"


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    """Drop the isolated home; real-state leaks are caught by the canary."""
    shutil.rmtree(ISOLATION_ROOT, ignore_errors=True)
