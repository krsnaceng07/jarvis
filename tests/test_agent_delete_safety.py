"""Tests for src/agents/agent_delete_safety.py.

Covers overlap detection for same dir, parent/child containment, and
non-overlapping dirs.
"""

from __future__ import annotations

import pytest

from src.agents.agent_dir_registry import clear_agent_dir_registry
from src.agents.agent_delete_safety import find_overlapping_workspace_agent_ids


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_agent_dir_registry()


def _cfg(agents: list[dict]) -> dict:
    return {"agents": {"list": agents}}


# ---------------------------------------------------------------------------
# No overlaps
# ---------------------------------------------------------------------------


def test_no_overlap(tmp_path):
    ws_alice = str(tmp_path / "alice")
    ws_bob = str(tmp_path / "bob")
    cfg = _cfg([
        {"id": "main"},
        {"id": "alice", "workspace": ws_alice},
        {"id": "bob", "workspace": ws_bob},
    ])
    result = find_overlapping_workspace_agent_ids(cfg, "alice", ws_alice)
    assert "bob" not in result


def test_empty_agents(tmp_path):
    cfg = _cfg([])
    result = find_overlapping_workspace_agent_ids(cfg, "alice", str(tmp_path / "alice"))
    assert result == []


def test_single_agent_no_self_report(tmp_path):
    ws = str(tmp_path / "alice")
    cfg = _cfg([{"id": "alice", "workspace": ws}])
    result = find_overlapping_workspace_agent_ids(cfg, "alice", ws)
    assert result == []


# ---------------------------------------------------------------------------
# Same directory
# ---------------------------------------------------------------------------


def test_exact_same_workspace_detected(tmp_path):
    shared = str(tmp_path / "shared")
    cfg = _cfg([
        {"id": "alice", "workspace": shared},
        {"id": "bob", "workspace": shared},
    ])
    result = find_overlapping_workspace_agent_ids(cfg, "alice", shared)
    assert "bob" in result


# ---------------------------------------------------------------------------
# Parent / child containment
# ---------------------------------------------------------------------------


def test_child_inside_parent_detected(tmp_path):
    parent = str(tmp_path / "parent")
    child = str(tmp_path / "parent" / "child")
    cfg = _cfg([
        {"id": "alice", "workspace": parent},
        {"id": "bob", "workspace": child},
    ])
    result = find_overlapping_workspace_agent_ids(cfg, "alice", parent)
    assert "bob" in result


def test_parent_overlaps_child_from_child_perspective(tmp_path):
    parent = str(tmp_path / "parent")
    child = str(tmp_path / "parent" / "sub")
    cfg = _cfg([
        {"id": "alice", "workspace": parent},
        {"id": "bob", "workspace": child},
    ])
    result = find_overlapping_workspace_agent_ids(cfg, "bob", child)
    assert "alice" in result


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def test_result_is_sorted(tmp_path):
    shared = str(tmp_path / "s")
    cfg = _cfg([
        {"id": "zebra", "workspace": shared},
        {"id": "apple", "workspace": shared},
        {"id": "main", "workspace": shared},
    ])
    result = find_overlapping_workspace_agent_ids(cfg, "main", shared)
    assert result == sorted(result)
