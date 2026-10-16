"""Tests for Wave 15 — Tool Policy Pipeline (allow/deny, groups, loop detection)."""

from __future__ import annotations

import pytest

from src.agents.tool_policy import (
    filter_tools_by_policy,
    expand_tool_groups,
)
from src.agents.tool_allowlist_guard import ToolAllowlistGuard, ToolAllowlistDeniedError

def test_expand_tool_groups():
    expanded = expand_tool_groups(["group:fs", "!exec"])
    assert "read" in expanded
    assert "write" in expanded
    assert "exec" not in expanded


def test_apply_tool_policy_pipeline():
    available = ["read", "write", "exec", "run_command", "web_search"]

    # Apply config allowlist
    res1 = filter_tools_by_policy(available, allow=["group:web", "read"])
    assert set(res1) == {"web_search", "read"}

    # Apply denylist
    res2 = filter_tools_by_policy(available, deny=["exec", "run_command"])
    assert set(res2) == {"read", "write", "web_search"}


def test_tool_allowlist_guard():
    guard = ToolAllowlistGuard(["read_file", "view_file"])
    assert guard.is_allowed("read_file")
    assert not guard.is_allowed("bash")

    guard.check_allowed("read_file")
    with pytest.raises(ToolAllowlistDeniedError):
        guard.check_allowed("bash")



