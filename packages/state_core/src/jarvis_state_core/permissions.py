"""State-database permission hardening.

Mirrors OpenClaw's ``src/state/openclaw-state-db-permissions.ts``.
The Python port focuses on the two operations the runtime
actually performs:

- ``ensure_state_permissions(pathname, env)`` — mkdir the
  parent dir + chmod 0o700 + chmod 0o600 on the SQLite
  file + WAL/SHM sidecars

The default JARVIS state directory at
``~/.jarvis/state`` is private by contract (mode 0o700).
Custom paths keep caller modes unless the directory is
newly created.

Permission hardening is best-effort on Windows (which
ignores POSIX ``chmod`` bits for ACL inheritance). The
helper swallows ``OSError`` from ``os.chmod`` so a
read-only filesystem / Windows / network share cannot
brick the gateway at open time. Azure Files / NFS /
Docker volume cases are exactly the failure modes
OpenClaw designed for (issue #91919).
"""

from __future__ import annotations

import os
from typing import Optional


STATE_DIR_MODE: int = 0o700
STATE_FILE_MODE: int = 0o600

# Sidecar files that SQLite writes next to the main DB.
_SQLITE_SIDECAR_SUFFIXES = ("", "-wal", "-shm", "-journal")


def _path_resolve(pathname: str) -> str:
    return os.path.abspath(pathname)


def _is_under_default_state_dir(pathname: str, default_state_dir: str) -> bool:
    """True when ``pathname`` lives directly inside the default state dir.

    Mirrors OpenClaw's ``isDefaultStateDatabase`` check.
    """
    try:
        return os.path.commonpath(
            [_path_resolve(pathname), _path_resolve(default_state_dir)]
        ) == _path_resolve(default_state_dir)
    except ValueError:
        # Different drives on Windows → not under the default.
        return False


def _safe_chmod(target: str, mode: int) -> bool:
    """Best-effort ``chmod`` that swallows filesystem-rejection errors.

    Returns True if applied; False if the OS refused (which
    is the expected outcome on Windows + many read-only
    network filesystems).
    """
    try:
        os.chmod(target, mode)
        return True
    except (OSError, AttributeError):
        return False


def ensure_state_permissions(pathname: str, env: Optional[dict[str, str]] = None) -> None:
    """Ensure the state DB file + parent dir are private by contract.

    Mirrors ``ensureOpenClawStatePermissions``. The dir
    gets mode 0o700 only when it's the default state dir
    or freshly created; existing custom dirs keep caller
    ownership. The DB file (and any WAL/SHM/journal
    sidecar) gets mode 0o600 if it already exists.
    """
    from .paths import resolve_state_sqlite_dir, resolve_state_sqlite_path

    env = env or os.environ
    resolved_path = _path_resolve(pathname)
    dir_path = os.path.dirname(resolved_path)
    default_dir = _path_resolve(resolve_state_sqlite_dir(env))
    is_default = _path_resolve(resolve_state_sqlite_path(env)) == resolved_path

    if is_default and not _is_under_default_state_dir(resolved_path, default_dir):
        raise ValueError(f"State database path resolved outside its state dir: {pathname}")

    dir_existed = os.path.isdir(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    if is_default or not dir_existed:
        _safe_chmod(dir_path, STATE_DIR_MODE)

    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        candidate = resolved_path + suffix
        if os.path.exists(candidate):
            _safe_chmod(candidate, STATE_FILE_MODE)


def ensure_agent_database_permissions(
    agent_id: str,
    pathname: str,
    env: Optional[dict[str, str]] = None,
) -> None:
    """Ensure the per-agent DB file + parent dir are private by contract.

    Mirrors ``ensureOpenClawAgentDatabasePermissions``.
    """
    from .paths import resolve_agent_sqlite_path

    env = env or os.environ
    resolved_path = _path_resolve(pathname)
    dir_path = os.path.dirname(resolved_path)
    default_path = _path_resolve(resolve_agent_sqlite_path(agent_id, env))
    is_default = default_path == resolved_path

    dir_existed = os.path.isdir(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    # Default agent state is private by contract; custom
    # pre-existing dirs keep caller ownership.
    if is_default or not dir_existed:
        _safe_chmod(dir_path, STATE_DIR_MODE)
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        candidate = resolved_path + suffix
        if os.path.exists(candidate):
            try:
                _safe_chmod(candidate, STATE_FILE_MODE)
            except (OSError, AttributeError):
                # ENOENT on transient sidecars: SQLite removes
                # them at checkpoint/close, so a concurrent
                # worker can race this sweep. A vanished
                # sidecar needs no tightening.
                pass


__all__ = [
    "STATE_DIR_MODE",
    "STATE_FILE_MODE",
    "ensure_agent_database_permissions",
    "ensure_state_permissions",
]
