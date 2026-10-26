"""tests.test_tool_inventory_parity — effective tool-surface invariants.

OpenClaw parity: ``tools-effective-inventory.ts`` guarantees that the tools a
model is offered are exactly the tools the host can run. These tests pin that
contract for JARVIS's single surface and for the live channel pipeline, which
previously declared 42 tools while holding 46+ executors.
"""

from __future__ import annotations

import pytest

from src.agents.system_prompt_tool_list import build_prompt_tool_lines
from src.agents.tool_loop_detection import (
    detect_tool_call_loop,
    record_tool_call,
    record_tool_call_outcome,
)
from src.agents.tools_effective_inventory import build_effective_tool_inventory

CHANNEL_LOOP_CONFIG = {
    "enabled": True,
    "historySize": 30,
    "warningThreshold": 2,
    "unknownToolThreshold": 2,
    "criticalThreshold": 3,
    "globalCircuitBreakerThreshold": 4,
}


def _host_tool(name: str, *, schema_key: str = "parameters", seen: list[str] | None = None):
    async def execute(_call_id: str, args: dict[str, object]) -> str:
        if seen is not None:
            seen.append(name)
        return f"{name}:{args}"

    return {
        "name": name,
        "description": f"{name} host tool",
        schema_key: {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        "execute": execute,
    }


def _control(seen: list[str]):
    async def execute(_args: dict[str, object], _call_id: str) -> str:
        seen.append("control")
        return "control ok"

    return execute


@pytest.mark.asyncio
async def test_declared_names_equal_executable_names() -> None:
    seen: list[str] = []
    surface = build_effective_tool_inventory(
        base_declarations=[{"name": "base_tool", "description": "base", "parameters": {}}],
        plugin_tools=[{"name": "plugin_tool", "description": "plugin", "parameters": {}}],
        plugin_dispatch={"plugin_tool": (type("P", (), {"call": lambda self, n, a: "ok"})(), "x")},
        host_tools={"host_tool": _host_tool("host_tool", seen=seen)},
        control_executors={"base_tool": _control(seen)},
    )

    declared = {decl["name"] for decl in surface.declarations()}
    assert declared == set(surface.names) == {"base_tool", "plugin_tool", "host_tool"}

    result = await surface.invoke("host_tool", {"path": "C:/tmp/x"})
    assert result.ok and "host_tool" in result.output

    unknown = await surface.invoke("missing_tool", {})
    assert not unknown.ok
    assert "not available" in unknown.output.lower() or "not available" in (unknown.error or "")


@pytest.mark.asyncio
async def test_undeclared_executor_is_not_offered() -> None:
    surface = build_effective_tool_inventory(
        base_declarations=[],
        host_tools={"orphan": _host_tool("orphan")},
    )
    # An executor with no declaration still gets a declaration from its own
    # host entry, so nothing runnable is silently hidden.
    assert "orphan" in surface.names
    assert {d["name"] for d in surface.declarations()} == {"orphan"}


@pytest.mark.asyncio
async def test_input_schema_host_tool_is_declared_with_parameters() -> None:
    surface = build_effective_tool_inventory(
        base_declarations=[],
        host_tools={"sessions_list": _host_tool("sessions_list", schema_key="inputSchema")},
    )
    decl = surface.declarations()[0]
    assert decl["name"] == "sessions_list"
    assert decl["parameters"]["properties"]["path"]["type"] == "string"


def test_policy_filters_declarations() -> None:
    surface = build_effective_tool_inventory(
        base_declarations=[],
        host_tools={"read": _host_tool("read"), "exec": _host_tool("exec")},
        deny=["exec"],
    )
    assert surface.names == ("read",)


def test_prompt_tool_lines_match_surface() -> None:
    surface = build_effective_tool_inventory(
        base_declarations=[],
        host_tools={"exec": _host_tool("exec")},
    )
    lines = build_prompt_tool_lines(surface)
    assert any(line.startswith("- exec") for line in lines)
    assert all(line.startswith("- ") for line in lines)


def test_loop_guard_warns_then_blocks() -> None:
    state: dict[str, object] = {}
    for _ in range(3):
        record_tool_call(state, "exec", {"command": "dir"}, config=CHANNEL_LOOP_CONFIG)
        record_tool_call_outcome(
            state,
            {
                "toolName": "exec",
                "toolParams": {"command": "dir"},
                "result": "same output",
                "config": CHANNEL_LOOP_CONFIG,
            },
        )

    verdict = detect_tool_call_loop(state, "exec", {"command": "dir"}, config=CHANNEL_LOOP_CONFIG)
    assert verdict.get("stuck") is True
    assert verdict.get("level") == "critical"


@pytest.mark.asyncio
async def test_executor_override_wins_over_plugin_dispatch() -> None:
    calls: list[str] = []

    def plugin_call(_name: str, _args: dict[str, object]) -> str:
        calls.append("plugin")
        return "plugin result"

    async def override(_args: dict[str, object], _call_id: str) -> str:
        calls.append("override")
        return "override result"

    surface = build_effective_tool_inventory(
        base_declarations=[{"name": "computer", "description": "desktop", "parameters": {}}],
        plugin_dispatch={
            "computer": (type("P", (), {"call": staticmethod(plugin_call)})(), "computer")
        },
        executor_overrides={"computer": override},
    )

    result = await surface.invoke("computer", {"action": "minimize"})
    assert result.ok and result.output == "override result"
    assert calls == ["override"]


def test_channel_surface_declares_every_host_executor() -> None:
    from src.channels.channel_agent_pipeline import ChannelAgentPipeline

    pipeline = ChannelAgentPipeline.get_instance()
    pipeline._ensure_tools_loaded()
    surface = pipeline._surface
    assert surface is not None

    declared = {decl["name"] for decl in surface.declarations()}
    assert declared == set(surface.names)
    # Every host executor is declared except local GUI control, which channel
    # policy withholds (declared-but-refused tools were the original defect).
    assert set(pipeline._coding_tools) - declared == {"computer"}

    for required in ("exec", "read", "write", "image_generate", "tts", "mkdir", "open_path"):
        assert required in declared, f"{required} must be declared on the channel surface"
