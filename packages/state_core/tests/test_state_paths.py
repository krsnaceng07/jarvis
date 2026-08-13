"""Tests for ``jarvis_state_core.paths``.

Covers:
- default + override env paths
- per-agent path layout
- the canonical JARVIS state root + state dir + state DB
"""
from __future__ import annotations

import os

import pytest

from jarvis_state_core.paths import (
    resolve_agent_sqlite_dir,
    resolve_agent_sqlite_path,
    resolve_state_root_dir,
    resolve_state_sqlite_dir,
    resolve_state_sqlite_path,
)


def test_default_state_root_uses_home(monkeypatch, tmp_path):
    # On Windows ``os.path.expanduser`` uses ``USERPROFILE``;
    # on POSIX it uses ``HOME``. Set both for cross-platform
    # tests.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("JARVIS_STATE_DIR", raising=False)
    root = resolve_state_root_dir()
    assert root == os.path.join(str(tmp_path), ".jarvis", "state")


def test_explicit_state_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "custom-state"))
    root = resolve_state_root_dir()
    assert root == os.path.abspath(str(tmp_path / "custom-state"))


def test_empty_state_dir_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("JARVIS_STATE_DIR", "")
    root = resolve_state_root_dir()
    assert root == os.path.join(str(tmp_path), ".jarvis", "state")


def test_state_sqlite_dir_uses_root(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "alt"))
    sqlite_dir = resolve_state_sqlite_dir()
    assert sqlite_dir == os.path.abspath(str(tmp_path / "alt"))


def test_state_sqlite_path_default_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "alt"))
    sqlite_path = resolve_state_sqlite_path()
    assert sqlite_path.endswith("jarvis.sqlite")
    assert os.path.dirname(sqlite_path) == os.path.abspath(str(tmp_path / "alt"))


def test_agent_sqlite_dir_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "state"))
    agent_dir = resolve_agent_sqlite_dir("main")
    expected = os.path.join(
        os.path.abspath(str(tmp_path)), "agents", "main"
    )
    assert agent_dir == expected


def test_agent_sqlite_path_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "state"))
    agent_path = resolve_agent_sqlite_path("alpha")
    assert agent_path.endswith(os.path.join("alpha", "agent.sqlite"))


def test_agent_sqlite_path_rejects_empty():
    with pytest.raises(ValueError):
        resolve_agent_sqlite_path("   ")


def test_paths_use_env_dict_not_environ_when_provided(tmp_path):
    """Pass an explicit env dict to bypass os.environ."""
    env = {"JARVIS_STATE_DIR": str(tmp_path / "injected")}
    assert resolve_state_root_dir(env) == os.path.abspath(
        str(tmp_path / "injected")
    )
    assert resolve_state_sqlite_dir(env) == os.path.abspath(
        str(tmp_path / "injected")
    )
    assert resolve_state_sqlite_path(env) == os.path.abspath(
        os.path.join(str(tmp_path / "injected"), "jarvis.sqlite")
    )
    assert resolve_agent_sqlite_path("beta", env).endswith(
        os.path.join("beta", "agent.sqlite")
    )
