"""Tests for src/agents/agent_dir_registry.py.

Covers register/lookup/clear contract, case-insensitive normalization on
Windows/macOS, and tilde expansion via env HOME.
"""

from __future__ import annotations

import sys

import pytest

from src.agents.agent_dir_registry import (
    clear_agent_dir_registry,
    register_resolved_agent_dir,
    resolve_registered_agent_id_for_dir,
)


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_agent_dir_registry()


# ---------------------------------------------------------------------------
# Basic register / lookup
# ---------------------------------------------------------------------------


def test_register_and_lookup(tmp_path):
    register_resolved_agent_dir("alice", str(tmp_path / "alice"))
    result = resolve_registered_agent_id_for_dir(str(tmp_path / "alice"))
    assert result == "alice"


def test_lookup_unregistered_returns_none(tmp_path):
    result = resolve_registered_agent_id_for_dir(str(tmp_path / "ghost"))
    assert result is None


def test_clear_removes_all(tmp_path):
    register_resolved_agent_dir("alice", str(tmp_path / "alice"))
    clear_agent_dir_registry()
    assert resolve_registered_agent_id_for_dir(str(tmp_path / "alice")) is None


def test_overwrite_registration(tmp_path):
    """Last registration for a dir wins."""
    register_resolved_agent_dir("alice", str(tmp_path / "shared"))
    register_resolved_agent_dir("bob", str(tmp_path / "shared"))
    result = resolve_registered_agent_id_for_dir(str(tmp_path / "shared"))
    assert result == "bob"


def test_multiple_agents_distinct_dirs(tmp_path):
    register_resolved_agent_dir("alice", str(tmp_path / "alice"))
    register_resolved_agent_dir("bob", str(tmp_path / "bob"))
    assert resolve_registered_agent_id_for_dir(str(tmp_path / "alice")) == "alice"
    assert resolve_registered_agent_id_for_dir(str(tmp_path / "bob")) == "bob"


# ---------------------------------------------------------------------------
# Case sensitivity (platform-aware)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform not in ("darwin", "win32"),
    reason="Case-insensitive normalization only on Windows/macOS",
)
def test_case_insensitive_lookup(tmp_path):
    register_resolved_agent_dir("alice", str(tmp_path / "Alice"))
    # Lookup with different case should resolve on case-insensitive FS.
    result = resolve_registered_agent_id_for_dir(str(tmp_path / "alice"))
    assert result == "alice"


# ---------------------------------------------------------------------------
# Tilde expansion via env
# ---------------------------------------------------------------------------


def test_tilde_expansion_via_env(tmp_path):
    env = {"HOME": str(tmp_path)}
    register_resolved_agent_dir("alice", "~/alice-dir", env=env)
    result = resolve_registered_agent_id_for_dir("~/alice-dir", env=env)
    assert result == "alice"


def test_tilde_expansion_mismatch_without_env(tmp_path):
    """Registering with env HOME, looking up with a different HOME — no match."""
    env_a = {"HOME": str(tmp_path / "home_a")}
    env_b = {"HOME": str(tmp_path / "home_b")}
    register_resolved_agent_dir("alice", "~/data", env=env_a)
    result = resolve_registered_agent_id_for_dir("~/data", env=env_b)
    assert result is None
