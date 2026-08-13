"""Tests for Wave 15 — Tool Policy Pipeline (allow/deny, groups, loop detection)."""

from __future__ import annotations

import pytest

from src.agents.tool_policy import (
    apply_tool_policy_pipeline,
    expand_tool_groups,
    normalize_tool_list,
)
from src.agents.tool_allowlist_guard import ToolAllowlistGuard, ToolAllowlistDeniedError
from src.agents.tool_loop_detection import ToolLoopDetector, ToolLoopDetectedError


def test_expand_tool_groups():
    expanded = expand_tool_groups(["group:coding", "!bash"])
    assert "read_file" in expanded
    assert "write_to_file" in expanded
    assert "bash" not in expanded


def test_apply_tool_policy_pipeline():
    available = ["read_file", "write_to_file", "bash", "run_command", "search_web"]

    # Apply config allowlist
    res1 = apply_tool_policy_pipeline(available, config_allowlist=["group:web", "read_file"])
    assert set(res1) == {"search_web", "read_file"}

    # Apply denylist
    res2 = apply_tool_policy_pipeline(available, config_denylist=["bash", "run_command"])
    assert set(res2) == {"read_file", "write_to_file", "search_web"}


def test_tool_allowlist_guard():
    guard = ToolAllowlistGuard(["read_file", "view_file"])
    assert guard.is_allowed("read_file")
    assert not guard.is_allowed("bash")

    guard.check_allowed("read_file")
    with pytest.raises(ToolAllowlistDeniedError):
        guard.check_allowed("bash")


def test_tool_loop_detector():
    detector = ToolLoopDetector(window_size=5, threshold=3)

    detector.record_and_check("read_file", {"path": "a.txt"})
    detector.record_and_check("read_file", {"path": "a.txt"})
    is_loop = detector.record_and_check("read_file", {"path": "a.txt"})

    assert is_loop

    with pytest.raises(ToolLoopDetectedError):
        detector.check_or_raise("read_file", {"path": "a.txt"})
