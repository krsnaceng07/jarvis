"""OpenClaw parity tests for agent tool replay safety."""

from __future__ import annotations

from src.agents.tool_replay_safety import (
    collect_replay_safe_tool_names,
    is_agent_tool_replay_safe,
    is_agent_tool_restart_safe,
)


def test_allows_only_audited_unconditional_core_tools() -> None:
    assert is_agent_tool_replay_safe({"name": "search"}) is True
    assert is_agent_tool_replay_safe({"name": "update_plan"}) is True
    assert is_agent_tool_replay_safe({"name": "process"}) is False
    assert is_agent_tool_replay_safe({"name": "vendor_widget"}) is False


def test_requires_extension_owned_tools_to_opt_in_even_for_audited_name() -> None:
    plugin_tool = {"name": "search"}

    assert (
        is_agent_tool_replay_safe(
            plugin_tool,
            declared_replay_safe=lambda tool: False
            if tool is plugin_tool
            else None,
        )
        is False
    )


def test_accepts_opted_in_extension_tools_only_for_audited_names() -> None:
    assert (
        is_agent_tool_replay_safe(
            {"name": "x_search"},
            declared_replay_safe=lambda _tool: True,
        )
        is True
    )
    assert (
        is_agent_tool_replay_safe(
            {"name": "vendor_widget"},
            declared_replay_safe=lambda _tool: True,
        )
        is False
    )


def test_accepts_owner_declared_concrete_tools_for_restart_safe_turns() -> None:
    plugin_tool = {"name": "vendor_widget"}

    assert (
        is_agent_tool_restart_safe(
            plugin_tool,
            declared_replay_safe=lambda tool: True
            if tool is plugin_tool
            else None,
        )
        is True
    )
    assert (
        is_agent_tool_restart_safe(
            plugin_tool,
            declared_replay_safe=lambda _tool: False,
        )
        is False
    )


def test_rejects_memory_search_even_when_owner_declares_safe() -> None:
    assert (
        is_agent_tool_replay_safe(
            {"name": "memory_search"},
            declared_replay_safe=lambda _tool: True,
        )
        is False
    )


def test_rejects_duplicate_names_from_name_only_replay_metadata() -> None:
    core_tool = {"name": "search"}
    plugin_tool = {"name": "search"}

    assert (
        collect_replay_safe_tool_names(
            [core_tool, plugin_tool],
            declared_replay_safe=lambda tool: True
            if tool is plugin_tool
            else None,
        )
        == set()
    )


def test_overflow_fixture_defaults_to_real_replay_safety() -> None:
    from src.agents.embedded_agent_runner.run.run_overflow_compaction_fixture import (
        make_attempt_result,
    )

    attempt = make_attempt_result({"toolMetas": [{"toolName": "search"}]})

    assert attempt["toolMetas"] == [{"toolName": "search", "replaySafe": True}]
    assert attempt["replayMetadata"] == {
        "hadPotentialSideEffects": False,
        "replaySafe": True,
    }
