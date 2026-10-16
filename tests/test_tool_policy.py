"""Tests for src/agents/tool_policy.py.

Mirrors tests of OpenClaw's agent-tools.policy.test.ts and tool-catalog.ts.
"""

from __future__ import annotations


from src.agents.tool_policy import (
    expand_tool_groups,
    filter_tools_by_policy,
    is_tool_allowed_by_policy,
    normalize_tool_name,
    resolve_subagent_deny_list,
    resolve_tool_profile_policy,
)


def test_normalize_tool_name():
    assert normalize_tool_name("bash") == "exec"
    assert normalize_tool_name("apply-patch") == "apply_patch"
    assert normalize_tool_name("READ") == "read"
    assert normalize_tool_name("  exec  ") == "exec"


def test_expand_tool_groups():
    expanded = expand_tool_groups(["group:fs", "exec"])
    assert "read" in expanded
    assert "write" in expanded
    assert "edit" in expanded
    assert "apply_patch" in expanded
    assert "exec" in expanded


def test_resolve_tool_profile_policy():
    minimal = resolve_tool_profile_policy("minimal")
    assert "session_status" in minimal["allow"]
    assert "ask_user" in minimal["allow"]

    coding = resolve_tool_profile_policy("coding")
    assert "read" in coding["allow"]
    assert "exec" in coding["allow"]
    assert "web_search" in coding["allow"]

    messaging = resolve_tool_profile_policy("messaging")
    assert "message" in messaging["allow"]
    assert "read" not in messaging["allow"]

    full = resolve_tool_profile_policy("full")
    assert full["allow"] == ["*"]


def test_resolve_subagent_deny_list():
    leaf_deny = resolve_subagent_deny_list("leaf")
    assert "gateway" in leaf_deny
    assert "subagents" in leaf_deny

    orch_deny = resolve_subagent_deny_list("orchestrator")
    assert "gateway" in orch_deny
    assert "subagents" not in orch_deny


def test_is_tool_allowed_empty_policy():
    assert is_tool_allowed_by_policy("read", None) is True


def test_is_tool_allowed_deny_precedence():
    assert is_tool_allowed_by_policy("read", allow=["read", "write"], deny=["write"]) is True
    assert is_tool_allowed_by_policy("write", allow=["read", "write"], deny=["write"]) is False


def test_is_tool_allowed_wildcard():
    assert is_tool_allowed_by_policy("read", allow=["*"], deny=["exec"]) is True
    assert is_tool_allowed_by_policy("exec", allow=["*"], deny=["exec"]) is False


def test_is_tool_allowed_group():
    assert is_tool_allowed_by_policy("read", allow=["group:fs"], deny=["write"]) is True
    assert is_tool_allowed_by_policy("write", allow=["group:fs"], deny=["write"]) is False
    assert is_tool_allowed_by_policy("exec", allow=["group:fs"], deny=["write"]) is False


def test_is_tool_allowed_apply_patch_matches_write():
    assert is_tool_allowed_by_policy("apply_patch", allow=["write"]) is True


def test_filter_tools_by_policy():
    tools = [{"name": "read"}, {"name": "write"}, {"name": "browser"}]
    res = filter_tools_by_policy(tools, allow=["read", "write"])
    names = [t["name"] for t in res]
    assert names == ["read", "write"]
