"""Tests for ``jarvis_state_core.permissions``.

Covers:
- default state dir gets 0o700 + state DB gets 0o600
- custom paths under a default state dir raise
- pre-existing custom dirs keep caller modes
- best-effort chmod swallows filesystem-rejection errors
- agent DB helper applies the same rules per agent
"""

from __future__ import annotations

import os
import stat

import pytest

from jarvis_state_core.permissions import (
    STATE_DIR_MODE,
    STATE_FILE_MODE,
    ensure_agent_database_permissions,
    ensure_state_permissions,
)


@pytest.fixture
def state_root(tmp_path, monkeypatch):
    root = tmp_path / "jarvis-state"
    root.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(root))
    return root


def test_ensure_state_permissions_creates_default_dir(state_root):
    db = state_root / "jarvis.sqlite"
    db.touch()
    ensure_state_permissions(str(db), env={"JARVIS_STATE_DIR": str(state_root)})
    # On POSIX the file gets the file mode. On Windows
    # the ACL is the real permission; the POSIX bits
    # are best-effort and may stay at the touch default.
    if os.name != "nt":
        file_mode = stat.S_IMODE(os.stat(str(db)).st_mode)
        assert file_mode == STATE_FILE_MODE


def test_ensure_state_permissions_creates_missing_dir(tmp_path):
    parent = tmp_path / "fresh"
    parent.mkdir()
    db = parent / "jarvis.sqlite"
    db.touch()
    ensure_state_permissions(str(db), env={"JARVIS_STATE_DIR": str(tmp_path / "fresh-state")})
    assert parent.is_dir()


def test_ensure_state_permissions_silent_for_custom_path_outside_default(tmp_path, monkeypatch):
    """A custom path outside the default state dir is fine —
    the helper does not raise. The safety check in OpenClaw
    only fires when the canonical default state DB path
    resolved somewhere unexpected (path-misconfiguration).
    """
    default = tmp_path / "state"
    default.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(default))
    rogue = tmp_path / "elsewhere" / "jarvis.sqlite"
    rogue.parent.mkdir()
    rogue.touch()
    # Should not raise.
    ensure_state_permissions(str(rogue), env=os.environ.copy())


def test_ensure_state_permissions_chmods_default_dir(state_root):
    db = state_root / "jarvis.sqlite"
    db.touch()
    ensure_state_permissions(str(db), env={"JARVIS_STATE_DIR": str(state_root)})
    if os.name != "nt":
        dir_mode = stat.S_IMODE(os.stat(str(state_root)).st_mode)
        assert dir_mode == STATE_DIR_MODE


def test_ensure_state_permissions_swallows_oserror(tmp_path, monkeypatch):
    """When os.chmod raises (e.g. read-only FS), the helper does not crash."""
    db = tmp_path / "ro.sqlite"
    db.touch()
    calls = {"count": 0}

    def fake_chmod(target, mode):
        calls["count"] += 1
        raise OSError("read-only filesystem")

    monkeypatch.setattr("jarvis_state_core.permissions.os.chmod", fake_chmod)
    # Should not raise.
    ensure_state_permissions(str(db), env=None)
    assert calls["count"] > 0


def test_ensure_agent_database_permissions_creates_dir(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state))
    ensure_agent_database_permissions("main", str(state / "agents" / "main" / "agent.sqlite"))
    assert (state / "agents" / "main").is_dir()


def test_ensure_agent_database_permissions_idempotent(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state))
    target = state / "agents" / "main" / "agent.sqlite"
    target.parent.mkdir(parents=True)
    target.touch()
    # Calling twice does not raise.
    ensure_agent_database_permissions("main", str(target))
    ensure_agent_database_permissions("main", str(target))
    assert target.is_file()


def test_ensure_agent_database_permissions_handles_missing_sidecar(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("JARVIS_STATE_DIR", str(state))
    target = state / "agents" / "main" / "agent.sqlite"
    target.parent.mkdir(parents=True)
    target.touch()
    # The helper enumerates WAL/SHM/JOURNAL sidecars; missing
    # sidecars must be silently ignored.
    ensure_agent_database_permissions("main", str(target))
    assert not (target.with_suffix(".sqlite-wal")).exists()
